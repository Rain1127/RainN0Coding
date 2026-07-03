# Production Hardening Harness

This harness verifies the first production baseline without calling real LLM providers.

## Java Compile

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn compile -DskipTests
```

Expected result: the Spring Boot application compiles with Java 21 release target.

## Java Focused Tests

Run the production-baseline focused suite:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn test '-Dtest=ProductionBaselinePropertiesTest,IdempotencyServiceTest,AiGenerationPermitServiceTest,PythonAiClientTest,AppControllerProductionBaselineTest,AppControllerTest,AppServiceImplProductionBaselineTest,AiCodeGeneratorFacadeTest'
```

Expected result: all listed tests pass.

Current focused baseline evidence: 54 Java tests pass in this suite.

For a narrow Python client regression check:

```powershell
$env:JAVA_HOME='D:/Program Files/Java/jdk-23'
mvn test '-Dtest=PythonAiClientTest'
```

Expected result: `PythonAiClient` sends request metadata, internal-token headers, and uses configured timeout plumbing.

## Python Focused Tests

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_internal_auth_and_concurrency.py tests/test_workflow_imports_unittest.py -v
```

Expected result: internal-token auth, CORS preflight, local overload rejection, request id propagation, and semantic SSE failure metrics pass.

Current focused baseline evidence: 13 Python tests pass in this suite.

## Python Guardrail Focused Tests

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_guardrails_prompt.py tests/test_guardrails_tools.py tests/test_guardrails_output.py tests/test_internal_auth_and_concurrency.py tests/test_workflow_imports_unittest.py tests/test_tools.py -v
```

Expected result: prompt blocks, tool guards, output guards, FastAPI entry guardrails, SSE output interception, and tool regressions all pass without real model calls.

## Python Deterministic Harness Markers

- `unit`: deterministic pure-python checks such as guardrail rules and config behavior
- `integration`: runtime boundary checks inside `python-agent`, including FastAPI `TestClient`, SSE output wiring, and tool integration
- `harness`: focused production-hardening verification suites used for release-confidence checks

The marker commands are backed by a collection guard in `python-agent/tests/conftest.py`, so `pytest -m ...` only collects the deterministic harness suites instead of unrelated legacy tests that can stall or fail during collection.

### Unit Command

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m unit -v
```

Expected result: 17 guardrail/config unit tests pass.

### Integration Command

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m integration -v
```

Expected result: 27 runtime-boundary tests pass.

### Canonical Harness Command

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m harness -v
```

Expected result: 61 focused production-hardening tests pass without requiring Redis, Milvus, or real LLM providers.

## Python Agent Availability Harness

- `degraded_success`: workflow completed with fallback or soft-fail paths
- `partial_success`: editable code was returned, but a late stage such as reviewer or builder failed
- `failed`: no safe editable code artifact could be returned

### Focused Resilience File

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest tests/test_workflow_resilience.py -v
```

Expected result: 23 deterministic workflow resilience tests pass, covering fallback, timeout budgets, degraded warnings, coder partial-success, and failed-without-code outcomes.

### Canonical Harness Command

```powershell
cd python-agent
$env:PYTHONPATH='.'
.venv/Scripts/python.exe -m pytest -m harness -v
```

Expected result: deterministic mocked workflow resilience checks are included in the 61-test harness suite and pass without real LLM providers.

## Local Service Auth Smoke Check

Start Python with an internal token:

```powershell
cd python-agent
$env:INTERNAL_API_TOKEN='dev-secret'
$env:PYTHONPATH='.'
.venv/Scripts/python.exe server/main.py
```

Unauthenticated generation should fail:

```powershell
curl -i -X POST http://localhost:8000/api/generate-code -H "Content-Type: application/json" -d "{\"prompt\":\"hello\"}"
```

Authenticated generation should enter the normal SSE path:

```powershell
curl -i -X POST http://localhost:8000/api/generate-code -H "Content-Type: application/json" -H "X-Internal-Token: dev-secret" -H "X-Request-Id: smoke-1" -d "{\"prompt\":\"hello\",\"requestId\":\"smoke-1\"}"
```

Production deployments should set `INTERNAL_API_TOKEN` on Python and `PYTHON_AI_INTERNAL_TOKEN` on Java to the same non-empty value. If Python starts with `APP_ENV=production` and no token, protected `/api/*` endpoints fail closed with a 503 misconfiguration response.
