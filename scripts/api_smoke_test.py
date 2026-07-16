"""Live API contract smoke test for the Vue -> Java -> Python stack.

Run while MySQL, Redis, the Python agent, and the Spring Boot gateway are up:

    python scripts/api_smoke_test.py

Use --skip-generation for a fast CRUD-only pass.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from typing import Any

import httpx


def require_base_response(response: httpx.Response, step: str) -> Any:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("code") != 0:
        raise AssertionError(f"{step}: expected BaseResponse code=0, got {payload!r}")
    print(f"[PASS] {step}")
    return payload.get("data")


def request_base(
    client: httpx.Client,
    method: str,
    path: str,
    step: str,
    **kwargs: Any,
) -> Any:
    return require_base_response(client.request(method, path, **kwargs), step)


def require_raw(response: httpx.Response, step: str) -> Any:
    response.raise_for_status()
    payload = response.json()
    print(f"[PASS] {step}")
    return payload


def parse_java_sse_payload(line: str) -> dict[str, Any] | None:
    if not line.startswith("data:"):
        return None
    try:
        outer = json.loads(line[5:].strip())
        inner = outer.get("d") if isinstance(outer, dict) else None
        if not isinstance(inner, str):
            return None
        inner = inner.strip()
        if inner.startswith("data:"):
            inner = inner[5:].strip()
        payload = json.loads(inner)
        return payload if isinstance(payload, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--java-base", default="http://127.0.0.1:8123/api")
    parser.add_argument("--python-base", default="http://127.0.0.1:8000")
    parser.add_argument("--skip-generation", action="store_true")
    args = parser.parse_args()

    timeout = httpx.Timeout(60.0, connect=10.0)
    public = httpx.Client(base_url=args.java_base, timeout=timeout)
    user = httpx.Client(base_url=args.java_base, timeout=timeout)
    admin = httpx.Client(base_url=args.java_base, timeout=timeout)
    python_api = httpx.Client(base_url=args.python_base, timeout=timeout)

    suffix = f"{int(time.time())}{uuid.uuid4().hex[:5]}"
    user_account = f"smoke_{suffix}"
    user_password = "SmokePass123!"
    user_id: int | None = None
    user_app_id: int | None = None
    generated_app_id: int | None = None
    version_id: int | None = None

    try:
        python_health = python_api.get("/api/health")
        python_health.raise_for_status()
        assert python_health.json().get("status") == "ok"
        print("[PASS] Python health")

        routed = python_api.post(
            "/api/route-codegen-type",
            json={"prompt": "创建一个 Vue 登录页面"},
            timeout=120.0,
        )
        routed.raise_for_status()
        assert routed.json().get("codeGenType") == "vue_project"
        print("[PASS] Python code generation type routing")

        assert request_base(public, "GET", "/health/", "Java health") == "Healthy"

        admin_account = os.getenv("SMOKE_ADMIN_ACCOUNT", "admin")
        admin_password = os.getenv("SMOKE_ADMIN_PASSWORD", "admin123")
        admin_user = request_base(
            admin,
            "POST",
            "/user/login",
            "Admin login",
            json={"userAccount": admin_account, "userPassword": admin_password},
        )
        assert admin_user["userRole"] == "admin"

        user_id = int(
            request_base(
                public,
                "POST",
                "/user/register",
                "User registration",
                json={
                    "userAccount": user_account,
                    "userPassword": user_password,
                    "checkPassword": user_password,
                },
            )
        )
        logged_in = request_base(
            user,
            "POST",
            "/user/login",
            "User login",
            json={"userAccount": user_account, "userPassword": user_password},
        )
        assert int(logged_in["id"]) == user_id
        assert int(request_base(user, "GET", "/user/get/login", "Current user")["id"]) == user_id

        user_app_id = int(
            request_base(
                user,
                "POST",
                "/app/add",
                "Create user app",
                json={"initPrompt": "创建一个简洁的 Vue 待办清单页面"},
                headers={"Idempotency-Key": f"smoke-add-{uuid.uuid4()}"},
                timeout=120.0,
            )
        )
        app = request_base(public, "GET", "/app/get/vo", "Get app detail", params={"id": user_app_id})
        assert int(app["id"]) == user_app_id
        assert app["codeGenType"] == "vue_project"

        assert request_base(
            user,
            "POST",
            "/app/update",
            "Update own app",
            json={"id": user_app_id, "appName": "Smoke Todo"},
        ) is True
        my_apps = request_base(
            user,
            "POST",
            "/app/my/list/page/vo",
            "List own apps",
            json={"pageNum": 1, "pageSize": 20, "codeGenType": "vue_project"},
        )
        assert any(int(item["id"]) == user_app_id for item in my_apps["records"])
        request_base(
            user,
            "GET",
            f"/chatHistory/app/{user_app_id}",
            "List app chat history",
            params={"pageSize": 20},
        )
        request_base(
            public,
            "POST",
            "/app/good/list/page/vo",
            "List featured apps",
            json={"pageNum": 1, "pageSize": 20},
        )

        users = request_base(
            admin,
            "POST",
            "/user/list/page/vo",
            "Admin list users",
            json={"pageNum": 1, "pageSize": 50, "userAccount": user_account},
        )
        assert any(int(item["id"]) == user_id for item in users["records"])
        assert int(
            request_base(admin, "GET", "/user/get/vo", "Admin get user", params={"id": user_id})["id"]
        ) == user_id
        assert request_base(
            admin,
            "POST",
            "/user/update",
            "Admin update user",
            json={"id": user_id, "userName": "Smoke User", "userRole": "user"},
        ) is True

        apps = request_base(
            admin,
            "POST",
            "/app/admin/list/page/vo",
            "Admin list apps",
            json={"pageNum": 1, "pageSize": 50, "id": user_app_id},
        )
        assert any(int(item["id"]) == user_app_id for item in apps["records"])
        assert int(
            request_base(
                admin, "GET", "/app/admin/get/vo", "Admin get app", params={"id": user_app_id}
            )["id"]
        ) == user_app_id
        assert request_base(
            admin,
            "POST",
            "/app/admin/update",
            "Admin update app",
            json={"id": user_app_id, "appName": "Smoke Todo Admin", "priority": 0},
        ) is True

        tree = request_base(admin, "GET", "/intent-config/tree", "Get intent tree")
        assert "customized" in tree and "treeJson" in tree
        custom_tree = '[{"key":"smoke","title":"Smoke"}]'
        assert request_base(
            admin,
            "POST",
            "/intent-config/save",
            "Save intent tree",
            json={"treeJson": custom_tree},
        ) is True
        assert request_base(admin, "GET", "/intent-config/tree", "Read saved intent tree")["treeJson"] == custom_tree
        assert request_base(
            admin, "POST", "/intent-config/reset", "Reset intent tree", json={}
        ) is True
        reset_tree = request_base(admin, "GET", "/intent-config/tree", "Read reset intent tree")
        assert reset_tree == {"customized": False, "treeJson": ""}

        request_base(
            admin,
            "POST",
            "/chatHistory/admin/list/page/vo",
            "Admin list chat history",
            json={"pageNum": 1, "pageSize": 50},
        )

        version_number = int(time.time())
        assert require_raw(
            admin.post(
                "/appVersion/save",
                json={
                    "appId": user_app_id,
                    "versionNumber": version_number,
                    "codeContent": "smoke",
                    "description": "smoke version",
                },
            ),
            "Save app version",
        ) is True
        versions = require_raw(admin.get("/appVersion/list"), "List app versions")
        version = next(
            item
            for item in versions
            if int(item["appId"]) == user_app_id and item["versionNumber"] == version_number
        )
        version_id = int(version["id"])
        assert int(require_raw(admin.get(f"/appVersion/getInfo/{version_id}"), "Get app version")["id"]) == version_id
        assert require_raw(
            admin.put(
                "/appVersion/update",
                json={"id": version_id, "appId": user_app_id, "versionNumber": version_number,
                      "codeContent": "smoke-2", "description": "updated"},
            ),
            "Update app version",
        ) is True
        require_raw(
            admin.get("/appVersion/page", params={"pageNumber": 1, "pageSize": 20}),
            "Page app versions",
        )

        assert request_base(
            user, "POST", "/app/delete", "Delete own app", json={"id": user_app_id}
        ) is True
        user_app_id = None

        generated_app_id = int(
            request_base(
                user,
                "POST",
                "/app/add",
                "Create generation app",
                json={"initPrompt": "创建一个单页 HTML 欢迎页面"},
                headers={"Idempotency-Key": f"smoke-add-{uuid.uuid4()}"},
                timeout=120.0,
            )
        )

        if not args.skip_generation:
            event_data = 0
            done_event = False
            successful_workflow = False
            semantic_failures: list[dict[str, Any]] = []
            with user.stream(
                "GET",
                "/app/chat/gen/code",
                params={"appId": generated_app_id, "message": "生成完整可运行页面"},
                headers={"Idempotency-Key": f"smoke-generate-{uuid.uuid4()}"},
                timeout=httpx.Timeout(1800.0, connect=10.0),
            ) as stream:
                stream.raise_for_status()
                for line in stream.iter_lines():
                    if line.startswith("data:"):
                        event_data += 1
                        payload = parse_java_sse_payload(line)
                        if payload:
                            event_type = payload.get("type")
                            status = payload.get("status")
                            if event_type == "error" or (
                                event_type == "done"
                                and status not in {None, "success", "partial_success", "degraded_success"}
                            ):
                                semantic_failures.append(payload)
                            if event_type == "done" and status in {
                                "success", "partial_success", "degraded_success"
                            }:
                                successful_workflow = True
                    if line == "event:done" or line == "event: done":
                        done_event = True
            assert event_data > 0 and done_event
            assert not semantic_failures, f"generation failed: {semantic_failures!r}"
            assert successful_workflow, "generation stream ended without a successful workflow status"
            print("[PASS] Java -> Python SSE generation")

            history = request_base(
                user,
                "GET",
                f"/chatHistory/app/{generated_app_id}",
                "Read generated chat history",
                params={"pageSize": 20},
            )
            assert len(history["records"]) >= 2

            download = user.get(f"/app/download/{generated_app_id}", timeout=120.0)
            download.raise_for_status()
            assert download.headers.get("content-type", "").startswith("application/zip")
            assert len(download.content) > 0
            print("[PASS] Download generated app")

            deploy_url = request_base(
                user,
                "POST",
                "/app/deploy",
                "Deploy generated app",
                json={"appId": generated_app_id},
                headers={"Idempotency-Key": f"smoke-deploy-{uuid.uuid4()}"},
                timeout=120.0,
            )
            deployed = public.get(deploy_url, timeout=30.0)
            deployed.raise_for_status()
            assert "text/html" in deployed.headers.get("content-type", "")
            print("[PASS] Read deployed app")

        if version_id is not None:
            assert require_raw(admin.delete(f"/appVersion/remove/{version_id}"), "Delete app version") is True
            version_id = None
        assert request_base(
            admin,
            "POST",
            "/app/admin/delete",
            "Admin delete app",
            json={"id": generated_app_id},
        ) is True
        generated_app_id = None
        assert request_base(user, "POST", "/user/logout", "User logout", json={}) is True
        assert request_base(
            admin, "POST", "/user/delete", "Admin delete user", json={"id": user_id}
        ) is True
        user_id = None

        print("ALL LIVE API SMOKE TESTS PASSED")
    finally:
        try:
            request_base(admin, "POST", "/intent-config/reset", "Cleanup intent tree", json={})
        except Exception:
            pass
        if version_id is not None:
            try:
                admin.delete(f"/appVersion/remove/{version_id}")
            except Exception:
                pass
        for app_id in (user_app_id, generated_app_id):
            if app_id is not None:
                try:
                    admin.post("/app/admin/delete", json={"id": app_id})
                except Exception:
                    pass
        if user_id is not None:
            try:
                admin.post("/user/delete", json={"id": user_id})
            except Exception:
                pass
        public.close()
        user.close()
        admin.close()
        python_api.close()


if __name__ == "__main__":
    main()
