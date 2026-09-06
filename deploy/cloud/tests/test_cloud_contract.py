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
