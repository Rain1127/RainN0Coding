import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agents.intent_agent as intent_agent


def test_custom_intent_tree_uses_java_backend_base_url(monkeypatch):
    seen = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"data": {"customized": True, "treeJson": '{"name":"custom"}'}}

    def fake_get(url, timeout):
        seen["url"] = url
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr(intent_agent.config, "JAVA_BASE_URL", "http://java-backend:8123", raising=False)
    monkeypatch.setattr(intent_agent.httpx, "get", fake_get)
    monkeypatch.setattr(intent_agent, "_cache_loaded", False)
    monkeypatch.setattr(intent_agent, "_cached_custom_tree", None)

    result = intent_agent._get_custom_tree()

    assert result == '{"name":"custom"}'
    assert seen == {
        "url": "http://java-backend:8123/api/intent-config/tree",
        "timeout": 5,
    }
