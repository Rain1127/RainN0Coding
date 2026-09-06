import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CLOUD_DIR = ROOT / "deploy" / "cloud"


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def test_all_external_images_are_immutable_digest_pins():
    versions = _read_env(CLOUD_DIR / "versions.env")
    required = {
        "MYSQL_IMAGE",
        "POSTGRES_IMAGE",
        "REDIS_IMAGE",
        "QDRANT_IMAGE",
        "LITELLM_IMAGE",
        "PROMETHEUS_IMAGE",
        "GRAFANA_IMAGE",
        "OTEL_IMAGE",
        "TEMPO_IMAGE",
        "CURL_IMAGE",
    }

    assert required <= versions.keys()
    for key in required:
        assert re.search(r"@sha256:[0-9a-f]{64}$", versions[key]), key


def test_runtime_example_contains_no_secret_values():
    runtime = _read_env(CLOUD_DIR / "runtime.env.example")
    secret_names = {
        key
        for key in runtime
        if key.endswith(("_KEY", "_TOKEN", "_PASSWORD"))
    }

    assert secret_names
    assert all(runtime[key] == "" for key in secret_names)


def test_prerequisite_script_creates_only_named_resources():
    script = (CLOUD_DIR / "create-network-and-volumes.sh").read_text(
        encoding="utf-8"
    )

    assert "docker network inspect rain-network" in script
    for volume in {
        "rain-mysql",
        "rain-postgres",
        "rain-redis",
        "rain-qdrant",
        "rain-code-output",
        "rain-prometheus",
        "rain-grafana",
        "rain-tempo",
    }:
        assert volume in script
    assert "docker system prune" not in script


def test_data_script_has_private_ports_and_health_gates():
    script = (CLOUD_DIR / "start-data-services.sh").read_text(
        encoding="utf-8"
    )

    for name in ("mysql", "postgres", "redis", "qdrant"):
        assert f"replace_container {name}" in script
        assert f"wait_healthy {name}" in script
    assert "--publish" not in script
    assert "--network rain-network" in script
    assert '${MYSQL_PASSWORD:?' in script
    assert '${POSTGRES_PASSWORD:?' in script
    assert '${REDIS_PASSWORD:?' in script
    assert "--env REDIS_PASSWORD" in script


def test_application_script_starts_private_dependencies_in_order():
    script = (CLOUD_DIR / "start-app-services.sh").read_text(
        encoding="utf-8"
    )

    positions = [
        script.index("replace_container litellm"),
        script.index("replace_container python-agent"),
        script.index("replace_container java-api"),
        script.index("replace_container frontend"),
    ]
    assert positions == sorted(positions)
    assert script.count("--publish") == 1
    assert '--publish "${PUBLIC_HTTP_PORT}:80"' in script
    assert "--env INTERNAL_API_TOKEN=\"$PYTHON_AI_INTERNAL_TOKEN\"" in script
    assert "--env PYTHON_AI_INTERNAL_TOKEN" in script
    assert "--volume rain-code-output:/data/code-output" in script
    assert "--volume rain-code-output:/app/tmp" in script


def test_observability_configs_use_private_container_dns():
    prometheus = (CLOUD_DIR / "prometheus.yml").read_text(encoding="utf-8")
    collector = (CLOUD_DIR / "otel-collector-config.yml").read_text(
        encoding="utf-8"
    )
    tempo = (CLOUD_DIR / "tempo.yml").read_text(encoding="utf-8")

    for target in (
        "java-api:8123",
        "python-agent:8000",
        "litellm:4000",
    ):
        assert target in prometheus
    assert "/etc/prometheus/secrets/litellm_metrics_token" in prometheus
    assert "endpoint: tempo:4317" in collector
    assert "insecure: true" in collector
    assert "endpoint: 0.0.0.0:4317" in collector
    assert "endpoint: 0.0.0.0:4318" in collector
    assert "backend: local" in tempo
    assert "/var/tempo" in tempo


def test_observability_script_only_publishes_loopback_grafana():
    script = (CLOUD_DIR / "start-observability.sh").read_text(
        encoding="utf-8"
    )
    datasource = (ROOT / "grafana" / "datasources" / "prometheus.yml").read_text(
        encoding="utf-8"
    )

    assert script.count("--publish") == 1
    assert "--publish 127.0.0.1:3001:3000" in script
    assert (
        "${metrics_token_file}:/etc/prometheus/secrets/"
        "litellm_metrics_token:ro"
    ) in script
    assert "GF_SECURITY_ADMIN_PASSWORD" in script
    assert "${PROMETHEUS_URL}" in datasource
