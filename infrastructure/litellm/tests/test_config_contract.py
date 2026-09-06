import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "infrastructure" / "litellm" / "config.yaml"
ENV_EXAMPLE = ROOT / "infrastructure" / "litellm" / ".env.example"
REQUIREMENTS = ROOT / "infrastructure" / "litellm" / "requirements.txt"
HEALTH_CHECK = ROOT / "infrastructure" / "litellm" / "health-check.ps1"
PROMETHEUS = ROOT / "prometheus.yml"


def test_gateway_config_exposes_only_stable_business_models():
    text = CONFIG.read_text(encoding="utf-8")
    for model in ("code-reasoning", "code-structured", "code-lightweight"):
        assert f"model_name: {model}" in text
    assert "num_retries: 1" in text
    assert "code-reasoning: [code-reasoning-chat, code-reasoning-glm]" in text
    assert "callbacks: [prometheus]" in text


def test_gateway_config_references_environment_instead_of_secrets():
    text = CONFIG.read_text(encoding="utf-8")
    assert "os.environ/LITELLM_MASTER_KEY" in text
    assert "os.environ/DATABASE_URL" in text
    assert "os.environ/DEEPSEEK_API_KEY" in text
    assert "os.environ/ZHIPUAI_API_KEY" in text
    assert "sk-your" not in text


def test_gateway_env_contract_keeps_provider_keys_out_of_python_agent():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "DATABASE_URL=" in text
    assert "LITELLM_MASTER_KEY=" in text
    assert "DEEPSEEK_API_KEY=" in text
    assert "ZHIPUAI_API_KEY=" in text
    assert "ZHIPUAI_MODEL=zai/" in text


def test_gateway_dependencies_support_database_and_legacy_local_redis():
    text = REQUIREMENTS.read_text(encoding="utf-8")
    assert "prisma==0.11.0" in text
    assert "redis==5.2.1" in text


def test_local_start_rejects_missing_and_example_secrets():
    text = (
        ROOT / "infrastructure" / "litellm" / "start-local.ps1"
    ).read_text(encoding="utf-8")
    for required_name in (
        "LITELLM_MASTER_KEY",
        "DATABASE_URL",
        "DEEPSEEK_API_KEY",
        "ZHIPUAI_API_KEY",
    ):
        assert required_name in text
    assert "sk-replace-with-random-master-key" in text
    assert "replace-me" in text
    assert "Get-FileHash" in text
    assert "prisma generate" in text
    assert "npm_config_cache" in text
    assert "litellm_proxy_extras\\schema.prisma" in text
    assert "PRISMA_HOME_DIR" in text
    assert "PRISMA_HEALTH_WATCHDOG_ENABLED = 'false'" in text


def test_litellm_dashboard_uses_current_metrics():
    path = ROOT / "grafana" / "dashboards" / "litellm-gateway.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    text = json.dumps(payload)
    for metric in (
        "litellm_proxy_total_requests_metric",
        "litellm_request_total_latency_metric_bucket",
        "litellm_total_tokens_metric",
        "litellm_spend_metric",
        "litellm_deployment_successful_fallbacks",
    ):
        assert metric in text
    for counter_sample in (
        "litellm_proxy_total_requests_metric_total",
        "litellm_proxy_failed_requests_metric_total",
        "litellm_total_tokens_metric_total",
        "litellm_spend_metric_total",
        "litellm_deployment_successful_fallbacks_total",
    ):
        assert counter_sample in text
    assert "ai_circuit_breaker_state" not in text


def test_metrics_scrapers_avoid_the_auth_stripping_redirect():
    assert 'Uri = "$gatewayBase/metrics/"' in HEALTH_CHECK.read_text(encoding="utf-8")
    prometheus = PROMETHEUS.read_text(encoding="utf-8")
    assert "job_name: 'LiteLLM'" in prometheus
    assert "metrics_path: '/metrics/'" in prometheus
