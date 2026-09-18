import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SMALL_SERVER_DIR = ROOT / "deploy" / "small-server"
LITELLM_DIR = Path(__file__).resolve().parent


def _read(path: Path) -> str:
    assert path.is_file(), f"missing deployment file: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _parse_example_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        assert separator, f"invalid env line: {raw_line}"
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _load_script(name: str) -> object:
    path = LITELLM_DIR / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compose_keeps_gateway_private_and_state_persistent() -> None:
    compose = _read(LITELLM_DIR / "compose.yml")

    assert "rainn0coding-cloud_default" in compose
    assert "127.0.0.1:4000:4000" in compose
    assert "rainn0coding_litellm_postgres_data" in compose
    assert "mem_limit: 256m" in compose
    assert "mem_limit: 768m" in compose
    assert "5432:5432" not in compose
    assert "POSTGRES_IMAGE" in compose
    assert "LITELLM_IMAGE" in compose
    assert "LITELLM_RUNTIME_ENV" in compose


def test_rollback_is_non_destructive() -> None:
    rollback = _read(LITELLM_DIR / "rollback.sh").lower()

    assert "docker volume rm" not in rollback
    assert "docker system prune" not in rollback
    assert "down -v" not in rollback
    assert "rm -rf" not in rollback


def test_example_environment_contains_no_secret_values() -> None:
    env = _parse_example_env(_read(LITELLM_DIR / "runtime.env.example"))

    secret_values = {
        key: value
        for key, value in env.items()
        if key.endswith(("_KEY", "_PASSWORD"))
    }
    assert secret_values
    assert all(value == "" for value in secret_values.values())


def test_runtime_preparation_never_prints_secrets_and_uses_strong_generation() -> None:
    source = _read(LITELLM_DIR / "prepare-runtime.py")

    assert "secrets.token_urlsafe" in source
    assert "0o600" in source
    assert "DEEPSEEK_API_KEY" in source
    assert "ZHIPU_API_KEY" in source
    assert "ZHIPUAI_API_KEY" in source
    assert "print(env" not in source
    assert "print(value" not in source


def test_prometheus_scrapes_litellm_with_credentials_file() -> None:
    prometheus = _read(SMALL_SERVER_DIR / "monitoring" / "prometheus.yml")
    monitoring_compose = _read(SMALL_SERVER_DIR / "monitoring" / "compose.yml")

    assert "job_name: litellm" in prometheus
    assert "127.0.0.1:4000" in prometheus
    assert "credentials_file:" in prometheus
    assert "litellm-metrics-token" in monitoring_compose
    assert "LITELLM_MASTER_KEY" not in prometheus


def test_operational_scripts_cover_preflight_and_verification() -> None:
    start = _read(LITELLM_DIR / "start.sh")
    verify = _read(LITELLM_DIR / "verify.py")
    provision = _read(LITELLM_DIR / "provision-agent-key.py")

    assert "rainn0coding-cloud_default" in start
    assert "docker compose" in start
    assert "/health/liveliness" in verify
    assert "/v1/models" in verify
    assert "/metrics" in verify
    assert "127.0.0.1:4000" in verify
    assert "/key/generate" in provision
    for alias in ("code-reasoning", "code-structured", "code-lightweight"):
        assert alias in provision
    assert "python.env.litellm-candidate" in provision
    assert "litellm-metrics-token" in provision
    assert 'allowed_routes=["/metrics"]' in provision
    assert "secrets.token_hex" in provision
    assert 'purpose="python-agent"' in provision
    assert 'purpose="prometheus"' in provision
    assert "print(key" not in provision
    assert "expect_json=False" in provision
    assert "os.chown" in provision
    assert "stat.S_IMODE" in provision
    assert "arguments.python_env.stat()" in provision
    assert "arguments.candidate_env.chmod" in provision
    assert "0o640" in provision
    assert "code-reasoning-glm" in provision
    assert "urllib.error.HTTPError" in provision


def test_python_operational_scripts_are_importable() -> None:
    for script in ("prepare-runtime.py", "verify.py", "provision-agent-key.py"):
        _load_script(script)
