import importlib
import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest


DEFAULT_GUARDRAIL_ENV_KEYS = [
    "GUARDRAILS_ENABLED",
    "GUARDRAILS_AUDIT_LOW_RISK",
    "GUARDRAILS_MAX_PROMPT_CHARS",
    "GUARDRAILS_MAX_FILE_WRITE_BYTES",
    "GUARDRAILS_MAX_MODIFY_REPLACEMENT_BYTES",
    "GUARDRAILS_MAX_LIST_FILES_DEPTH",
]

MARKER_FILE_ALLOWLIST = {
    "unit": {"test_guardrails_prompt.py", "test_workflow_resilience.py"},
    "integration": {
        "test_guardrails_tools.py",
        "test_guardrails_output.py",
        "test_internal_auth_and_concurrency.py",
        "test_tools.py",
        "test_workflow_resilience.py",
    },
    "harness": {
        "test_guardrails_tools.py",
        "test_guardrails_output.py",
        "test_internal_auth_and_concurrency.py",
        "test_tools.py",
        "test_workflow_imports_unittest.py",
        "test_workflow_resilience.py",
    },
}


def pytest_ignore_collect(collection_path, config):
    markexpr = (config.option.markexpr or "").strip()
    if not markexpr or collection_path.suffix != ".py":
        return False

    requested_markers = {
        marker_name
        for marker_name in MARKER_FILE_ALLOWLIST
        if marker_name in markexpr.split()
    }
    if not requested_markers:
        return False

    allowed_files = set().union(
        *(MARKER_FILE_ALLOWLIST[marker_name] for marker_name in requested_markers)
    )
    return Path(collection_path).name not in allowed_files


@pytest.fixture
def reload_guardrail_modules():
    def _reload_guardrail_modules():
        for module_name in [
            "guardrails",
            "guardrails.audit",
            "guardrails.engine",
            "guardrails.models",
            "guardrails.policy",
            "guardrails.prompt_guard",
        ]:
            sys.modules.pop(module_name, None)

    return _reload_guardrail_modules


@pytest.fixture
def reload_config_module_fixture():
    def _reload_config_module(monkeypatch):
        for key in DEFAULT_GUARDRAIL_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        sys.modules.pop("config", None)
        return importlib.import_module("config")

    return _reload_config_module


@pytest.fixture
def tool_context():
    from tools import set_tool_context

    @contextmanager
    def _tool_context(app_id="test-app", user_role="user"):
        with tempfile.TemporaryDirectory() as tmpdir:
            set_tool_context(tmpdir, app_id, user_role)
            yield tmpdir

    return _tool_context


@pytest.fixture
def fake_conversation_memory():
    class _FakeConversationMemory:
        def get_context(self, thread_id):
            return {"summary": "", "recent_messages": []}

        def add_message(self, thread_id, role, content):
            return None

    return _FakeConversationMemory()


@pytest.fixture
def collect_json_events():
    async def _collect(async_iterable):
        events = []
        async for event in async_iterable:
            events.append(json.loads(event))
        return events

    return _collect
