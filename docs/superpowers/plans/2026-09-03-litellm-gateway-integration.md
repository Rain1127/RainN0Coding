# LiteLLM Gateway Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route every Python Agent LLM call through a locally runnable LiteLLM Proxy with PostgreSQL-backed keys/budgets, Redis coordination, deterministic DeepSeek-to-GLM fallback, and Prometheus observability.

**Architecture:** Keep Spring Boot as the business gateway and FastAPI as the workflow boundary. Replace Python's provider-aware retry loop with a thin mapping from `reasoning`, `structured`, and `lightweight` to LiteLLM model aliases; LiteLLM owns provider credentials, retries, cooldowns, fallbacks, key authorization, and spend records.

**Tech Stack:** Python 3.12, LangChain `ChatOpenAI`, LiteLLM Proxy 1.98.0, PostgreSQL, Redis, Prometheus, Grafana, pytest, PowerShell.

**Approved design:** `docs/superpowers/specs/2026-09-03-litellm-gateway-design.md`

---

## File map

### Create

- `infrastructure/litellm/config.yaml` — production-shaped LiteLLM model, fallback, Redis, database, and metrics configuration.
- `infrastructure/litellm/config.contract.yaml` — deterministic configuration for fake-provider fallback tests.
- `infrastructure/litellm/.env.example` — LiteLLM-only environment contract without secrets.
- `infrastructure/litellm/requirements.txt` — isolated LiteLLM CLI dependency pin.
- `infrastructure/litellm/start-local.ps1` — starts LiteLLM from its own virtual environment.
- `infrastructure/litellm/health-check.ps1` — verifies liveness, models, metrics, and database-backed key access.
- `infrastructure/litellm/provision-agent-key.ps1` — creates a constrained FastAPI service key without persisting it to Git.
- `infrastructure/litellm/tests/fake_openai_provider.py` — local OpenAI-compatible success/failure provider.
- `infrastructure/litellm/tests/test_config_contract.py` — static configuration and secret-boundary tests.
- `infrastructure/litellm/tests/test_fallback_contract.py` — live fallback contract test against fake providers.
- `python-agent/request_context.py` — request-local metadata shared with the gateway adapter.
- `python-agent/tests/test_request_context.py` — context isolation and reset tests.
- `python-agent/tests/test_litellm_gateway_config.py` — FastAPI-side gateway configuration tests.
- `grafana/dashboards/litellm-gateway.json` — LiteLLM traffic, latency, token, spend, and fallback panels.

### Modify

- `python-agent/config.py` — replace provider-facing runtime settings with LiteLLM endpoint, key, and aliases.
- `python-agent/.env.example` — expose only the LiteLLM service key to FastAPI.
- `python-agent/core/model_registry.py` — replace provider candidates with immutable business-group aliases.
- `python-agent/core/model_router.py` — make one zero-retry request to LiteLLM and translate the result.
- `python-agent/llm_factory.py` — point compatibility clients and tool-enabled clients at the gateway.
- `python-agent/memory/conversation_memory.py` — route summarization through `code-lightweight`.
- `python-agent/workflow/autogen_discussion.py` — route AutoGen through `code-reasoning`.
- `python-agent/rag/ragas_evaluator.py` — route the offline judge through the gateway.
- `python-agent/server/generate_code_orchestrator.py` — bind request metadata for the SSE generator lifetime.
- `python-agent/server/main.py` — report gateway health and aliases instead of provider credentials/models.
- `python-agent/monitoring.py` — remove the obsolete local circuit-breaker gauge.
- `python-agent/tests/test_model_router_resilience.py` — replace candidate-loop tests with one-hop gateway tests.
- `python-agent/tests/test_tool_enabled_llm_router.py` — verify tool calls still use the gateway adapter.
- `python-agent/tests/test_generate_code_orchestrator.py` — verify request context propagation and cleanup.
- `prometheus.yml` — scrape LiteLLM with a token file.
- `grafana/dashboards/ai-workflow-overview.json` — remove the obsolete Python circuit-breaker panel and link to gateway metrics.
- `.gitignore` — ignore local gateway environments, secret token files, and test process artifacts.
- `STARTUP_CHECKLIST.md` — document native local startup and verification order.

### Delete

- `python-agent/core/circuit_breaker.py` — provider cooldown moves to LiteLLM.

## Task 1: Add the LiteLLM configuration contract

**Files:**
- Create: `infrastructure/litellm/config.yaml`
- Create: `infrastructure/litellm/.env.example`
- Create: `infrastructure/litellm/requirements.txt`
- Create: `infrastructure/litellm/tests/test_config_contract.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write the failing configuration tests**

```python
# infrastructure/litellm/tests/test_config_contract.py
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "infrastructure" / "litellm" / "config.yaml"
ENV_EXAMPLE = ROOT / "infrastructure" / "litellm" / ".env.example"


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
```

- [ ] **Step 2: Run the test and verify the missing files fail**

Run:

```powershell
& '.\python-agent\.venv\Scripts\python.exe' -m pytest infrastructure/litellm/tests/test_config_contract.py -v
```

Expected: FAIL with `FileNotFoundError` for `config.yaml` or `.env.example`.

- [ ] **Step 3: Add the isolated dependency and environment contracts**

```text
# infrastructure/litellm/requirements.txt
litellm[proxy]==1.98.0
```

```dotenv
# infrastructure/litellm/.env.example
LITELLM_MASTER_KEY=sk-replace-with-random-master-key
DATABASE_URL=postgresql://litellm:replace-me@127.0.0.1:5432/litellm_gateway

DEEPSEEK_API_KEY=
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
DEEPSEEK_REASONING_MODEL=deepseek/deepseek-v4-pro
DEEPSEEK_CHAT_MODEL=deepseek/deepseek-chat

ZHIPUAI_API_KEY=
ZHIPUAI_API_BASE=https://open.bigmodel.cn/api/paas/v4
ZHIPUAI_MODEL=zhipuai/glm-4.7-flash

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=
LITELLM_PORT=4000
```

- [ ] **Step 4: Add the LiteLLM model and reliability configuration**

```yaml
# infrastructure/litellm/config.yaml
model_list:
  - model_name: code-reasoning
    litellm_params:
      model: os.environ/DEEPSEEK_REASONING_MODEL
      api_key: os.environ/DEEPSEEK_API_KEY
      api_base: os.environ/DEEPSEEK_API_BASE
      timeout: 120
  - model_name: code-reasoning-chat
    litellm_params:
      model: os.environ/DEEPSEEK_CHAT_MODEL
      api_key: os.environ/DEEPSEEK_API_KEY
      api_base: os.environ/DEEPSEEK_API_BASE
      timeout: 60
  - model_name: code-reasoning-glm
    litellm_params:
      model: os.environ/ZHIPUAI_MODEL
      api_key: os.environ/ZHIPUAI_API_KEY
      api_base: os.environ/ZHIPUAI_API_BASE
      timeout: 60
  - model_name: code-structured
    litellm_params:
      model: os.environ/DEEPSEEK_CHAT_MODEL
      api_key: os.environ/DEEPSEEK_API_KEY
      api_base: os.environ/DEEPSEEK_API_BASE
      timeout: 120
  - model_name: code-structured-glm
    litellm_params:
      model: os.environ/ZHIPUAI_MODEL
      api_key: os.environ/ZHIPUAI_API_KEY
      api_base: os.environ/ZHIPUAI_API_BASE
      timeout: 60
  - model_name: code-lightweight
    litellm_params:
      model: os.environ/DEEPSEEK_CHAT_MODEL
      api_key: os.environ/DEEPSEEK_API_KEY
      api_base: os.environ/DEEPSEEK_API_BASE
      timeout: 60
  - model_name: code-lightweight-glm
    litellm_params:
      model: os.environ/ZHIPUAI_MODEL
      api_key: os.environ/ZHIPUAI_API_KEY
      api_base: os.environ/ZHIPUAI_API_BASE
      timeout: 60

router_settings:
  num_retries: 1
  request_timeout: 120
  allowed_fails: 3
  cooldown_time: 30
  fallbacks:
    - code-reasoning: [code-reasoning-chat, code-reasoning-glm]
    - code-structured: [code-structured-glm]
    - code-lightweight: [code-lightweight-glm]

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/DATABASE_URL
  user_api_key_cache_ttl: 300

litellm_settings:
  callbacks: [prometheus]
  cache: true
  enable_redis_auth_cache: true
  cache_params:
    type: redis
    host: os.environ/REDIS_HOST
    port: os.environ/REDIS_PORT
    password: os.environ/REDIS_PASSWORD
    namespace: litellm
    supported_call_types: []
  prometheus_metrics_config:
    - group: proxy_requests
      metrics: [litellm_proxy_total_requests_metric, litellm_proxy_failed_requests_metric]
      include_labels: [status_code, requested_model, model_group]
    - group: deployment_responses
      metrics: [litellm_deployment_success_responses, litellm_deployment_failure_responses]
      include_labels: [requested_model, api_provider]
    - group: fallbacks
      metrics: [litellm_deployment_successful_fallbacks, litellm_deployment_failed_fallbacks]
      include_labels: [requested_model, fallback_model, exception_status]
    - group: deployment_state
      metrics: [litellm_deployment_state]
      include_labels: [litellm_model_name, api_provider]
    - group: usage
      metrics: [litellm_input_tokens_metric, litellm_output_tokens_metric, litellm_total_tokens_metric, litellm_spend_metric]
      include_labels: [requested_model, model, api_provider, api_key_alias]
    - group: latency
      metrics: [litellm_request_total_latency_metric, litellm_llm_api_latency_metric]
      include_labels: [requested_model, model, api_provider, api_key_alias]
```

Start LiteLLM once with this configuration and no provider request, then fetch `/metrics`. Configuration validation is complete only when LiteLLM starts cleanly and every configured metric family is present.

- [ ] **Step 5: Ignore local gateway state**

Append:

```gitignore
infrastructure/litellm/.venv/
infrastructure/litellm/.env
infrastructure/litellm/.gateway.pid
infrastructure/litellm/.contract-*.pid
secrets/
```

- [ ] **Step 6: Run the configuration tests**

Run:

```powershell
& '.\python-agent\.venv\Scripts\python.exe' -m pytest infrastructure/litellm/tests/test_config_contract.py -v
```

Expected: `3 passed`.

- [ ] **Step 7: Commit**

```powershell
git add .gitignore infrastructure/litellm/config.yaml infrastructure/litellm/.env.example infrastructure/litellm/requirements.txt infrastructure/litellm/tests/test_config_contract.py
git commit -m "feat: add LiteLLM gateway configuration"
```

## Task 2: Add request-local gateway metadata

**Files:**
- Create: `python-agent/request_context.py`
- Create: `python-agent/tests/test_request_context.py`
- Modify: `python-agent/server/generate_code_orchestrator.py`
- Modify: `python-agent/tests/test_generate_code_orchestrator.py`

- [ ] **Step 1: Write failing context isolation tests**

```python
# python-agent/tests/test_request_context.py
from request_context import bind_request_context, get_request_metadata


def test_request_context_is_bound_and_reset():
    assert get_request_metadata() == {}
    with bind_request_context(request_id="req-1", trace_id="tr-1", user_id="u-1", app_id="a-1"):
        assert get_request_metadata() == {
            "request_id": "req-1",
            "trace_id": "tr-1",
            "user_id": "u-1",
            "app_id": "a-1",
        }
    assert get_request_metadata() == {}


def test_request_context_omits_empty_values():
    with bind_request_context(request_id="", trace_id="tr-2", user_id="", app_id=""):
        assert get_request_metadata() == {"trace_id": "tr-2"}
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run from `python-agent`:

```powershell
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests/test_request_context.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'request_context'`.

- [ ] **Step 3: Implement a reset-safe ContextVar boundary**

```python
# python-agent/request_context.py
from contextlib import contextmanager
from contextvars import ContextVar


_request_metadata: ContextVar[dict[str, str]] = ContextVar("request_metadata", default={})


def get_request_metadata() -> dict[str, str]:
    return dict(_request_metadata.get())


@contextmanager
def bind_request_context(*, request_id: str, trace_id: str, user_id: str, app_id: str):
    metadata = {
        key: value
        for key, value in {
            "request_id": request_id,
            "trace_id": trace_id,
            "user_id": user_id,
            "app_id": app_id,
        }.items()
        if value
    }
    token = _request_metadata.set(metadata)
    try:
        yield
    finally:
        _request_metadata.reset(token)
```

- [ ] **Step 4: Bind context for the complete SSE generator lifetime**

In `event_generator()` wrap the current `async for event in stream_workflow(...)` block:

```python
from request_context import bind_request_context


async def event_generator():
    status = "success"
    try:
        with bind_request_context(
            request_id=request.request_id,
            trace_id=resolved_trace_id,
            user_id=request.user_id,
            app_id=request.app_id,
        ):
            async for event in stream_workflow(
                user_request=request.prompt,
                user_id=request.user_id,
                app_id=request.app_id,
                code_gen_type=request.code_gen_type,
                user_role=request.user_role,
                trace_id=resolved_trace_id,
                request_id=request.request_id,
            ):
                event_status = _status_from_sse_event(event)
                if event_status and status == "success":
                    status = event_status
                yield {"data": event}
    except Exception:
        status = "error"
        raise
    finally:
        active_requests_metric.dec()
        record_request(request.user_id, request.app_id, request.code_gen_type, status)
        semaphore.release()
```

- [ ] **Step 5: Extend the orchestrator test with context capture**

Add a fake `stream_workflow` that asserts `get_request_metadata()` inside iteration and assert `{}` after consuming the generator.

```python
async def fake_stream_workflow(**kwargs):
    assert get_request_metadata()["request_id"] == "req-context"
    assert get_request_metadata()["trace_id"] == "trace-context"
    yield json.dumps({"type": "done", "status": "success"})
```

- [ ] **Step 6: Run focused tests**

```powershell
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests/test_request_context.py tests/test_generate_code_orchestrator.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```powershell
git add python-agent/request_context.py python-agent/server/generate_code_orchestrator.py python-agent/tests/test_request_context.py python-agent/tests/test_generate_code_orchestrator.py
git commit -m "feat: propagate request metadata to model calls"
```

## Task 3: Replace provider settings with gateway aliases

**Files:**
- Create: `python-agent/tests/test_litellm_gateway_config.py`
- Modify: `python-agent/config.py`
- Modify: `python-agent/.env.example`
- Modify: `python-agent/core/model_registry.py`

- [ ] **Step 1: Write failing gateway configuration tests**

```python
# python-agent/tests/test_litellm_gateway_config.py
import importlib


def test_gateway_defaults(monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("LITELLM_API_KEY", "sk-agent-test")
    import config as config_module
    importlib.reload(config_module)
    assert config_module.config.LITELLM_BASE_URL == "http://127.0.0.1:4000/v1"
    assert config_module.config.LITELLM_API_KEY == "sk-agent-test"
    assert config_module.config.LLM_MODEL_ALIASES == {
        "reasoning": "code-reasoning",
        "structured": "code-structured",
        "lightweight": "code-lightweight",
    }


def test_unknown_group_falls_back_to_lightweight():
    from core.model_registry import get_model_alias
    assert get_model_alias("unknown") == "code-lightweight"
```

- [ ] **Step 2: Run tests and verify missing gateway settings fail**

```powershell
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests/test_litellm_gateway_config.py -v
```

Expected: FAIL because `LITELLM_BASE_URL` and `LLM_MODEL_ALIASES` do not exist.

- [ ] **Step 3: Add FastAPI-side gateway settings**

Replace the provider-facing block in `Config` with:

```python
LITELLM_BASE_URL: str = os.getenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1").rstrip("/")
LITELLM_API_KEY: str = os.getenv("LITELLM_API_KEY", "")
LITELLM_HEALTH_URL: str = os.getenv(
    "LITELLM_HEALTH_URL", "http://127.0.0.1:4000/health/liveliness"
)
LLM_REASONING_MODEL: str = os.getenv("LLM_REASONING_MODEL", "code-reasoning")
LLM_STRUCTURED_MODEL: str = os.getenv("LLM_STRUCTURED_MODEL", "code-structured")
LLM_LIGHTWEIGHT_MODEL: str = os.getenv("LLM_LIGHTWEIGHT_MODEL", "code-lightweight")
LLM_MODEL_ALIASES: dict[str, str] = {
    "reasoning": LLM_REASONING_MODEL,
    "structured": LLM_STRUCTURED_MODEL,
    "lightweight": LLM_LIGHTWEIGHT_MODEL,
}
```

Retain generic LLM temperature/token/timeout settings. Remove runtime DeepSeek/GLM keys, base URLs, candidate timeout, and circuit-breaker settings from the FastAPI config.

- [ ] **Step 4: Replace the model registry with aliases only**

```python
# python-agent/core/model_registry.py
from config import config


def get_model_alias(group_name: str) -> str:
    return config.LLM_MODEL_ALIASES.get(
        group_name,
        config.LLM_MODEL_ALIASES["lightweight"],
    )
```

- [ ] **Step 5: Update the FastAPI environment example**

Replace provider keys with:

```dotenv
LITELLM_BASE_URL=http://127.0.0.1:4000/v1
LITELLM_HEALTH_URL=http://127.0.0.1:4000/health/liveliness
LITELLM_API_KEY=sk-agent-virtual-key
LLM_REASONING_MODEL=code-reasoning
LLM_STRUCTURED_MODEL=code-structured
LLM_LIGHTWEIGHT_MODEL=code-lightweight
LLM_TIMEOUT=120
```

- [ ] **Step 6: Run focused configuration tests**

```powershell
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests/test_litellm_gateway_config.py tests/test_vector_store_config.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```powershell
git add python-agent/config.py python-agent/.env.example python-agent/core/model_registry.py python-agent/tests/test_litellm_gateway_config.py
git commit -m "refactor: configure Python agent for LiteLLM"
```

## Task 4: Collapse ModelRouter to one gateway hop

**Files:**
- Modify: `python-agent/core/model_router.py`
- Modify: `python-agent/tests/test_model_router_resilience.py`
- Delete: `python-agent/core/circuit_breaker.py`

- [ ] **Step 1: Replace old resilience tests with failing one-hop tests**

Test these behaviors explicitly:

```python
def test_route_calls_gateway_once_with_alias_and_zero_sdk_retries(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def invoke(self, messages, config=None):
            return type("Response", (), {"content": "ok"})()

    monkeypatch.setattr(model_router_module, "ChatOpenAI", FakeClient)
    result = ModelRouter().route("structured", ["prompt"], allow_degraded=False)
    assert result == "ok"
    assert len(calls) == 1
    assert calls[0]["model"] == "code-structured"
    assert calls[0]["max_retries"] == 0
    assert calls[0]["base_url"].endswith(":4000/v1")


def test_route_puts_request_context_in_litellm_metadata(monkeypatch):
    captured = {}
    # FakeClient stores kwargs in captured and returns content="ok".
    with bind_request_context(request_id="req-1", trace_id="tr-1", user_id="u-1", app_id="a-1"):
        ModelRouter().route("reasoning", ["prompt"], allow_degraded=False)
    assert captured["extra_body"]["metadata"]["request_id"] == "req-1"


def test_route_returns_none_only_when_degraded_mode_is_allowed(monkeypatch):
    # FakeClient.invoke raises TimeoutError.
    assert ModelRouter().route("lightweight", ["prompt"], allow_degraded=True) is None
```

- [ ] **Step 2: Run tests and verify the old candidate router fails the new contract**

```powershell
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests/test_model_router_resilience.py -v
```

Expected: FAIL because the current router constructs provider candidates and retries locally.

- [ ] **Step 3: Implement the thin gateway router**

```python
# python-agent/core/model_router.py
from langchain_openai import ChatOpenAI

from config import config
from core.model_registry import get_model_alias
from monitoring import record_llm_call
from request_context import get_request_metadata
from tracing import start_span


class ModelRouter:
    """Map a business model group to one LiteLLM request."""

    def route(self, group_name, messages, parser=None, allow_degraded=True, langsmith_extra=None):
        model_alias = get_model_alias(group_name)
        runnable_config = dict(langsmith_extra or {})
        gateway_metadata = get_request_metadata()
        gateway_metadata.update(runnable_config.get("metadata", {}))

        with start_span("llm.gateway", {"llm.group": group_name, "llm.model": model_alias}):
            try:
                client = ChatOpenAI(
                    model=model_alias,
                    api_key=config.LITELLM_API_KEY,
                    base_url=config.LITELLM_BASE_URL,
                    timeout=config.LLM_TIMEOUT,
                    max_retries=0,
                    temperature=0.0,
                    extra_body={"metadata": gateway_metadata},
                )
                if parser:
                    result = parser(messages, _client=client, _config=runnable_config)
                else:
                    response = client.invoke(messages, config=runnable_config)
                    result = response.content or ""
                    if not result:
                        raise ValueError(f"{model_alias}: empty gateway response")
                record_llm_call(model_alias, status="success")
                return result
            except Exception as exc:
                record_llm_call(model_alias, status="error")
                if allow_degraded:
                    return None
                raise RuntimeError(f"{group_name}: LiteLLM gateway call failed") from exc


model_router = ModelRouter()
```

- [ ] **Step 4: Delete the local circuit breaker**

Delete `python-agent/core/circuit_breaker.py`. Confirm no Python import remains:

```powershell
rg -n 'CircuitBreaker|core\.circuit_breaker|ModelCandidate|MODEL_GROUPS' python-agent
```

Expected: no production-code matches.

- [ ] **Step 5: Run router and tool adapter tests**

```powershell
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests/test_model_router_resilience.py tests/test_tool_enabled_llm_router.py -v
```

Expected: all tests PASS and each invocation creates one gateway client.

- [ ] **Step 6: Commit**

```powershell
git add python-agent/core/model_router.py python-agent/core/circuit_breaker.py python-agent/tests/test_model_router_resilience.py
git commit -m "refactor: delegate model resilience to LiteLLM"
```

## Task 5: Route every remaining Python LLM caller through LiteLLM

**Files:**
- Modify: `python-agent/llm_factory.py`
- Modify: `python-agent/memory/conversation_memory.py`
- Modify: `python-agent/workflow/autogen_discussion.py`
- Modify: `python-agent/rag/ragas_evaluator.py`
- Modify: `python-agent/tests/test_tool_enabled_llm_router.py`
- Create: `python-agent/tests/test_no_direct_provider_access.py`

- [ ] **Step 1: Add a failing direct-provider boundary test**

```python
# python-agent/tests/test_no_direct_provider_access.py
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_FILES = [path for path in ROOT.rglob("*.py") if "tests" not in path.parts]


def test_python_agent_has_no_provider_credentials_or_urls():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in PRODUCTION_FILES)
    for forbidden in (
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "ZHIPU_API_KEY",
        "ZHIPU_BASE_URL",
        "api.deepseek.com",
        "open.bigmodel.cn",
    ):
        assert forbidden not in combined
```

- [ ] **Step 2: Run the boundary test and verify it fails**

```powershell
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests/test_no_direct_provider_access.py -v
```

Expected: FAIL and list the current direct callers.

- [ ] **Step 3: Point compatibility clients at gateway aliases**

In `llm_factory.py`, make `create_llm()` and `create_reasoning_llm()` use:

```python
return ChatOpenAI(
    model=config.LLM_REASONING_MODEL,
    api_key=config.LITELLM_API_KEY,
    base_url=config.LITELLM_BASE_URL,
    temperature=temperature if temperature is not None else config.LLM_TEMPERATURE,
    max_tokens=config.LLM_MAX_TOKENS,
    max_retries=0,
)
```

Update docstrings so they describe business groups and gateway routing rather than DeepSeek fallback.

- [ ] **Step 4: Move memory summarization to the lightweight alias**

In `ConversationMemory._call_llm` keep the OpenAI-compatible client but use:

```python
client = openai.OpenAI(
    api_key=config.LITELLM_API_KEY,
    base_url=config.LITELLM_BASE_URL,
)
response = client.chat.completions.create(
    model=config.LLM_LIGHTWEIGHT_MODEL,
    messages=[
        {"role": "system", "content": "你是一个对话摘要助手。输出简洁的中文摘要。"},
        {"role": "user", "content": prompt},
    ],
    temperature=0.1,
    max_tokens=300,
    extra_body={"metadata": get_request_metadata()},
)
```

- [ ] **Step 5: Move AutoGen and RAGAS to gateway aliases**

Use `config.LLM_REASONING_MODEL`, `config.LITELLM_API_KEY`, and `config.LITELLM_BASE_URL` in `_create_model_client()` and `create_ragas_judge_llm()`. Keep `max_retries=0` where the client supports it. Set the RAGAS model default to `config.LLM_REASONING_MODEL`.

- [ ] **Step 6: Run boundary and caller tests**

```powershell
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests/test_no_direct_provider_access.py tests/test_tool_enabled_llm_router.py -v
```

Expected: all tests PASS. Live JSON-output validation is deferred to Task 10, after the local gateway is running.

- [ ] **Step 7: Commit**

```powershell
git add python-agent/llm_factory.py python-agent/memory/conversation_memory.py python-agent/workflow/autogen_discussion.py python-agent/rag/ragas_evaluator.py python-agent/tests/test_tool_enabled_llm_router.py python-agent/tests/test_no_direct_provider_access.py
git commit -m "refactor: route all Python LLM clients through gateway"
```

## Task 6: Expose gateway health and remove obsolete breaker metrics

**Files:**
- Modify: `python-agent/server/main.py`
- Modify: `python-agent/monitoring.py`
- Modify: `python-agent/tests/test_internal_auth_and_concurrency.py`

- [ ] **Step 1: Write failing health assertions**

Extend the health test to monkeypatch `httpx.AsyncClient` and assert:

```python
assert payload["llm_gateway"]["configured"] is True
assert payload["llm_gateway"]["reachable"] is True
assert payload["llm_gateway"]["models"] == [
    "code-reasoning", "code-structured", "code-lightweight"
]
assert "model" not in payload
assert "chat_model" not in payload
```

- [ ] **Step 2: Run the health test and verify it fails**

```powershell
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests/test_internal_auth_and_concurrency.py -k health -v
```

Expected: FAIL because health currently reports provider model fields.

- [ ] **Step 3: Add bounded LiteLLM liveness probing**

In `health()` use `httpx.AsyncClient(timeout=2.0)` to call `config.LITELLM_HEALTH_URL`; catch `httpx.HTTPError` and report `reachable: false` without making the FastAPI health endpoint itself fail. Return only configured aliases, never keys or database URLs.

```python
"llm_gateway": {
    "configured": bool(_config().LITELLM_API_KEY),
    "reachable": gateway_ok,
    "models": list(_config().LLM_MODEL_ALIASES.values()),
}
```

- [ ] **Step 4: Remove Python circuit-breaker instrumentation**

Delete `ai_circuit_breaker_state`, `update_circuit_breaker`, and their documentation references from `monitoring.py`. LiteLLM metrics become the source of truth.

- [ ] **Step 5: Run server and monitoring tests**

```powershell
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests/test_internal_auth_and_concurrency.py tests/test_tracing.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add python-agent/server/main.py python-agent/monitoring.py python-agent/tests/test_internal_auth_and_concurrency.py
git commit -m "feat: report LiteLLM gateway health"
```

## Task 7: Add native Windows startup and key provisioning

**Files:**
- Create: `infrastructure/litellm/start-local.ps1`
- Create: `infrastructure/litellm/health-check.ps1`
- Create: `infrastructure/litellm/provision-agent-key.ps1`
- Modify: `STARTUP_CHECKLIST.md`

- [ ] **Step 1: Add the local startup script**

The script must resolve paths from `$PSScriptRoot`, never from the caller's current directory:

```powershell
$ErrorActionPreference = 'Stop'
$gatewayRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $gatewayRoot '.venv\Scripts\python.exe'
$envFile = Join-Path $gatewayRoot '.env'
$configFile = Join-Path $gatewayRoot 'config.yaml'

if (-not (Test-Path -LiteralPath $envFile)) { throw "Missing $envFile; copy .env.example and set secrets." }
if (-not (Test-Path -LiteralPath $venvPython)) {
    py -3.12 -m venv (Join-Path $gatewayRoot '.venv')
    & $venvPython -m pip install -r (Join-Path $gatewayRoot 'requirements.txt')
}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2], 'Process') }
}
& $venvPython -m litellm --config $configFile --port $env:LITELLM_PORT
```

- [ ] **Step 2: Add a key provisioning script that never writes the key**

Read `LITELLM_MASTER_KEY` from the process environment, POST to `/key/generate`, request only the three public models, and print the returned key once:

```powershell
$body = @{
  key_alias = 'python-agent'
  models = @('code-reasoning', 'code-structured', 'code-lightweight')
  rpm_limit = 20
  tpm_limit = 200000
  max_budget = 10
  budget_duration = '30d'
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$gatewayBase/key/generate" -Headers @{ Authorization = "Bearer $env:LITELLM_MASTER_KEY" } -ContentType 'application/json' -Body $body
```

These are local validation limits, not production capacity values. The operator copies the returned `key` into `python-agent/.env` as `LITELLM_API_KEY`.

- [ ] **Step 3: Add a health-check script**

Check, in order, `/health/liveliness`, `/v1/models` with the agent key, `/metrics` with the master key, and a zero-cost fake-provider request when `-ContractMode` is passed. Print `[PASS]` per boundary and exit nonzero on the first failure.

- [ ] **Step 4: Update the startup checklist**

Document this native sequence:

```text
MySQL -> PostgreSQL -> Redis -> LiteLLM -> vector store -> Python -> Java -> Vue -> Prometheus/Grafana
```

Include PostgreSQL database creation:

```text
psql -U postgres
CREATE ROLE litellm LOGIN;
\password litellm
CREATE DATABASE litellm_gateway OWNER litellm;
\q
```

Do not place an actual password in the document or command history example.

- [ ] **Step 5: Parse-check the PowerShell scripts**

```powershell
Get-ChildItem infrastructure/litellm/*.ps1 | ForEach-Object {
  $tokens=$null; $errors=$null
  [System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$tokens,[ref]$errors) | Out-Null
  if ($errors.Count) { throw ($errors | Out-String) }
}
```

Expected: exit code 0 and no parser errors.

- [ ] **Step 6: Commit**

```powershell
git add infrastructure/litellm/start-local.ps1 infrastructure/litellm/health-check.ps1 infrastructure/litellm/provision-agent-key.ps1 STARTUP_CHECKLIST.md
git commit -m "docs: add native LiteLLM startup workflow"
```

## Task 8: Add LiteLLM Prometheus and Grafana views

**Files:**
- Modify: `prometheus.yml`
- Create: `grafana/dashboards/litellm-gateway.json`
- Modify: `grafana/dashboards/ai-workflow-overview.json`

- [ ] **Step 1: Add a failing dashboard contract test**

Add to `test_config_contract.py`:

```python
import json


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
    assert "ai_circuit_breaker_state" not in text
```

- [ ] **Step 2: Run the test and verify the dashboard is missing**

```powershell
& '.\python-agent\.venv\Scripts\python.exe' -m pytest infrastructure/litellm/tests/test_config_contract.py -v
```

Expected: FAIL with missing `litellm-gateway.json`.

- [ ] **Step 3: Add the authenticated Prometheus scrape job**

```yaml
- job_name: 'LiteLLM'
  metrics_path: '/metrics'
  authorization:
    type: Bearer
    credentials_file: 'secrets/litellm_metrics_token'
  static_configs:
    - targets: ['localhost:4000']
  scrape_interval: 10s
  scrape_timeout: 10s
```

The local token file is ignored by Git and contains the master key or a metrics-only key without the `Bearer ` prefix.

- [ ] **Step 4: Add gateway dashboard panels**

Create valid Grafana provisioning JSON with these exact PromQL expressions:

```promql
sum(rate(litellm_proxy_total_requests_metric[5m])) by (requested_model)
sum(rate(litellm_proxy_failed_requests_metric[5m])) / clamp_min(sum(rate(litellm_proxy_total_requests_metric[5m])), 1)
histogram_quantile(0.95, sum by (requested_model, le) (rate(litellm_request_total_latency_metric_bucket[5m])))
sum(rate(litellm_total_tokens_metric[5m])) by (requested_model, api_provider)
sum(increase(litellm_spend_metric[24h])) by (requested_model, api_provider)
sum(increase(litellm_deployment_successful_fallbacks[1h])) by (requested_model, fallback_model)
max(litellm_deployment_state) by (litellm_model_name, api_provider)
```

Remove the `ai_circuit_breaker_state` panel from the existing workflow dashboard. Keep Reviewer retry panels because they measure quality retries.

- [ ] **Step 5: Run dashboard and YAML checks**

```powershell
& '.\python-agent\.venv\Scripts\python.exe' -m pytest infrastructure/litellm/tests/test_config_contract.py -v
& '.\python-agent\.venv\Scripts\python.exe' -c "import json; json.load(open('grafana/dashboards/litellm-gateway.json', encoding='utf-8')); json.load(open('grafana/dashboards/ai-workflow-overview.json', encoding='utf-8'))"
```

Expected: tests PASS and JSON parser exits 0.

- [ ] **Step 6: Commit**

```powershell
git add prometheus.yml grafana/dashboards/litellm-gateway.json grafana/dashboards/ai-workflow-overview.json infrastructure/litellm/tests/test_config_contract.py
git commit -m "feat: monitor LiteLLM gateway"
```

## Task 9: Prove fallback without spending real model tokens

**Files:**
- Create: `infrastructure/litellm/config.contract.yaml`
- Create: `infrastructure/litellm/tests/fake_openai_provider.py`
- Create: `infrastructure/litellm/tests/test_fallback_contract.py`

- [ ] **Step 1: Implement two fake OpenAI-compatible behaviors**

```python
# infrastructure/litellm/tests/fake_openai_provider.py
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
MODE = os.getenv("FAKE_PROVIDER_MODE", "success")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    if MODE == "fail":
        return JSONResponse({"error": {"message": "forced upstream failure"}}, status_code=500)
    return {
        "id": "chatcmpl-contract",
        "object": "chat.completion",
        "created": 1,
        "model": body.get("model", "fake"),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "fallback-ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
```

- [ ] **Step 2: Configure an actual HTTP 500 primary and successful fallback**

`config.contract.yaml` uses `openai/fake-primary` at `http://127.0.0.1:4101/v1` and `openai/fake-fallback` at `http://127.0.0.1:4102/v1`, with `num_retries: 1` and `fallbacks: [{code-reasoning: [code-reasoning-glm]}]`. It does not use LiteLLM `mock_testing_*` request flags.

- [ ] **Step 3: Write the live contract test**

```python
def test_primary_500_falls_back_once():
    response = httpx.post(
        "http://127.0.0.1:4001/v1/chat/completions",
        headers={"Authorization": "Bearer sk-contract"},
        json={"model": "code-reasoning", "messages": [{"role": "user", "content": "ping"}]},
        timeout=10,
    )
    response.raise_for_status()
    assert response.json()["choices"][0]["message"]["content"] == "fallback-ok"
```

Add a second test where both providers fail and assert a non-2xx gateway response. Capture fake-provider request counts and assert the primary receives exactly two calls and the fallback exactly one.

- [ ] **Step 4: Start the three local processes and run the contract**

Add a module-scoped fixture that owns exactly the processes it creates:

```python
@pytest.fixture(scope="module", autouse=True)
def contract_stack():
    processes: list[subprocess.Popen[str]] = []
    specs = [
        ({"FAKE_PROVIDER_MODE": "fail"}, [PYTHON, "-m", "uvicorn", "infrastructure.litellm.tests.fake_openai_provider:app", "--port", "4101"]),
        ({"FAKE_PROVIDER_MODE": "success"}, [PYTHON, "-m", "uvicorn", "infrastructure.litellm.tests.fake_openai_provider:app", "--port", "4102"]),
        ({"LITELLM_MASTER_KEY": "sk-contract"}, [LITELLM, "--config", "infrastructure/litellm/config.contract.yaml", "--port", "4001"]),
    ]
    try:
        for overrides, command in specs:
            processes.append(subprocess.Popen(command, env=os.environ | overrides))
        wait_until_ready([4101, 4102, 4001], timeout_seconds=30)
        yield
    finally:
        for process in reversed(processes):
            process.terminate()
        for process in reversed(processes):
            process.wait(timeout=10)
```

Resolve `PYTHON` and `LITELLM` from the active test environment, and implement `wait_until_ready` as bounded HTTP polling. The fixture must not use broad process-name termination.

```powershell
& '.\python-agent\.venv\Scripts\python.exe' -m pytest infrastructure/litellm/tests/test_fallback_contract.py -v
```

Expected: fallback test PASS, terminal-failure test PASS, and no real provider key is present.

- [ ] **Step 5: Commit**

```powershell
git add infrastructure/litellm/config.contract.yaml infrastructure/litellm/tests/fake_openai_provider.py infrastructure/litellm/tests/test_fallback_contract.py
git commit -m "test: verify LiteLLM fallback contract"
```

## Task 10: Run local integration and full regression

**Files:**
- Modify: `scripts/api_smoke_test.py`
- Modify: `STARTUP_CHECKLIST.md`

- [ ] **Step 1: Extend live smoke checks with gateway health**

Add `--litellm-base` defaulting to `http://127.0.0.1:4000`. Before Python health, assert LiteLLM liveness and authorized model listing. Do not print response headers or keys.

- [ ] **Step 2: Run deterministic Python tests**

```powershell
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests/test_request_context.py tests/test_litellm_gateway_config.py tests/test_model_router_resilience.py tests/test_tool_enabled_llm_router.py tests/test_no_direct_provider_access.py tests/test_generate_code_orchestrator.py tests/test_internal_auth_and_concurrency.py tests/test_tracing.py -v
```

Expected: all selected tests PASS with process exit code 0.

- [ ] **Step 3: Run the complete Python suite**

```powershell
$env:PYTHONPATH='.'
& '.\.venv\Scripts\python.exe' -m pytest tests/ -v
```

Expected: pytest exit code 0. Report native-library access violations separately if they occur; do not equate assertion success with healthy process termination.

- [ ] **Step 4: Run Java tests and frontend checks**

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
$env:Path="$env:JAVA_HOME/bin;$env:Path"
mvn test
Push-Location RainN0Coding-frontend
npm run test
npm run build
Pop-Location
```

Expected: Maven, Vitest, type-check, and Vite all exit 0. Before the Vite build, protect any untracked output under `src/main/resources/static` because production build uses `emptyOutDir`.

- [ ] **Step 5: Run native local integration**

With PostgreSQL, Redis, LiteLLM, Python, Java, and the frontend running:

```powershell
& '.\infrastructure\litellm\health-check.ps1'
& '.\python-agent\.venv\Scripts\python.exe' scripts/api_smoke_test.py
```

Expected: LiteLLM checks print `[PASS]`; API smoke ends with `ALL LIVE API SMOKE TESTS PASSED`; PostgreSQL spend logs contain the request; Prometheus target `LiteLLM` is UP.

- [ ] **Step 6: Verify secret and direct-egress boundaries**

```powershell
rg -n 'DEEPSEEK_API_KEY|ZHIPUAI_API_KEY|api\.deepseek\.com|open\.bigmodel\.cn' python-agent
git grep -n -E 'sk-[A-Za-z0-9_-]{16,}|DATABASE_URL=.*:[^@]+@'
```

Expected: first command has no Python Agent runtime matches; second command has no real credential matches. Every match in an example environment file must be an empty assignment or a documented non-secret sentinel.

- [ ] **Step 7: Update verification evidence in `STARTUP_CHECKLIST.md` and commit**

Record commands and expected markers, not machine-specific passwords or live keys.

```powershell
git add scripts/api_smoke_test.py STARTUP_CHECKLIST.md
git commit -m "test: verify LiteLLM gateway end to end"
```

## Completion gate

Before starting the cloud deployment plan, verify all of the following with fresh command output:

- The fallback contract uses only local fake providers.
- All production Python LLM clients use `LITELLM_BASE_URL` and a Virtual Key.
- The Python process has no DeepSeek or Zhipu provider credential.
- PostgreSQL contains spend/key records and Redis keys are namespaced.
- Prometheus scrapes LiteLLM and Grafana loads both dashboards.
- Full Python, Java, and frontend checks exit 0.
- A real end-to-end generation completes through the gateway and preserves SSE behavior.
