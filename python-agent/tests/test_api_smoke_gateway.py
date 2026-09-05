import os
from pathlib import Path
import sys

import httpx


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, os.fspath(ROOT))

from scripts.api_smoke_test import validate_litellm_gateway


def test_validate_litellm_gateway_checks_liveness_and_authorized_aliases():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/health/liveliness":
            return httpx.Response(200, json={"status": "healthy"})
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "code-reasoning"},
                        {"id": "code-structured"},
                        {"id": "code-lightweight"},
                    ]
                },
            )
        return httpx.Response(404)

    client = httpx.Client(
        base_url="http://gateway.test",
        transport=httpx.MockTransport(handler),
    )

    validate_litellm_gateway(client, "sk-agent-test")

    assert [request.url.path for request in requests] == [
        "/health/liveliness",
        "/v1/models",
    ]
    assert requests[1].headers["authorization"] == "Bearer sk-agent-test"
