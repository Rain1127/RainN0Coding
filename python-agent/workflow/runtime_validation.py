"""Requirement-driven browser acceptance for static HTML and built Vue output."""
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit
import json
import time


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def translate_path(self, path):
        resolved=Path(super().translate_path(path)).resolve()
        root=Path(self.directory).resolve()
        return str(resolved if resolved.is_relative_to(root) else root / "__blocked_resource__")


def acceptance_contract(request: str) -> dict:
    """Versioned task rules, independent of generated implementation/selectors."""
    from agents.mode_detector import current_request
    request = current_request(request)
    if "登录" in request or "login" in request.lower():
        return {"version": "login-v1", "steps": [
            {"action": "fill", "selector": "input:not([type=password]):not([type=submit]):not([type=hidden])", "value": "demo@example.com"},
            {"action": "fill", "selector": "input[type=password]", "value": ""},
            {"action": "invalid", "selector": "input[type=password]"},
            {"action": "fill", "selector": "input[type=password]", "value": "Demo123456!"},
            {"action": "click_change", "selector": "button[type=submit], input[type=submit]"},
        ]}
    if "待办" in request or "todo" in request.lower():
        return {"version": "todo-v1", "steps": [
            {"action": "fill", "selector": "input[type=text], input:not([type])", "value": "Acceptance task"},
            {"action": "press", "selector": "input[type=text], input:not([type])", "value": "Enter"},
            {"action": "text", "value": "Acceptance task"},
            {"action": "check", "selector": "input[type=checkbox]"},
            {"action": "click", "selector": "button[aria-label*=删除], button[title*=删除]"},
            {"action": "absent_text", "value": "Acceptance task"},
        ]}
    return {"version": "smoke-v1", "steps": []}


def validate_page(root: Path, contract: dict, *, report_dir: Path, timeout_ms: int = 5000) -> dict:
    started = time.monotonic()
    result = {"status": "unverified", "failure_kind": "environment", "log": "", "steps": [],
              "contract": contract["version"], "interaction_status": "not_required" if not contract["steps"] else "unverified"}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        result["log"] = "Playwright is not installed"
        return result
    report_dir.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(root)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.set_default_timeout(timeout_ms)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("requestfailed", lambda request: errors.append(f"resource failed: {request.url}"))
                page.on("response", lambda response: errors.append(f"HTTP {response.status}: {response.url}") if response.status >= 400 else None)
                base = f"http://127.0.0.1:{server.server_port}"
                # Only the artifact origin and common public stylesheet/CDN hosts are accepted.
                allowed = {"fonts.googleapis.com", "fonts.gstatic.com", "cdn.tailwindcss.com", "cdn.jsdelivr.net"}
                def route_request(route):
                    url = urlsplit(route.request.url)
                    if route.request.url.startswith(base + "/") or (url.scheme == "https" and url.hostname in allowed):
                        route.continue_()
                    else:
                        route.abort()
                page.route("**/*", route_request)
                result.update(status="failed", failure_kind="code")
                response = page.goto(base + "/index.html", wait_until="networkidle", timeout=timeout_ms)
                if response is None or response.status >= 400:
                    raise AssertionError("Entry did not load")
                visible = page.locator("body").inner_text().strip()
                if not visible and page.locator("body img, body canvas, body svg").count() == 0:
                    raise AssertionError("Blank page")
                result["steps"].append({"action": "load", "expected": "nonblank entry without resource/script failures", "actual": "loaded"})
                for step in contract["steps"]:
                    observation = {**step, "expected": step["action"], "actual": "failed"}
                    result["steps"].append(observation)
                    locator = page.locator(step["selector"]).first if "selector" in step else None
                    action = step["action"]
                    if action == "fill":
                        locator.fill(step["value"])
                    elif action == "invalid":
                        assert locator.evaluate("e => !e.checkValidity()"), "required field accepted empty input"
                    elif action == "press":
                        locator.press(step["value"])
                    elif action == "text":
                        page.get_by_text(step["value"], exact=True).first.wait_for(state="visible")
                    elif action == "absent_text":
                        page.get_by_text(step["value"], exact=True).first.wait_for(state="hidden")
                    elif action == "check":
                        locator.check()
                        assert locator.is_checked()
                    elif action == "click":
                        locator.click()
                    elif action == "click_change":
                        before = (page.url, page.locator("body").inner_text())
                        dialog_messages = []
                        def on_dialog(dialog):
                            dialog_messages.append(dialog.message)
                            dialog.dismiss()
                        page.on("dialog", on_dialog)
                        locator.click()
                        page.wait_for_function("([url, text]) => location.href !== url || document.body.innerText !== text",
                                               arg=list(before), timeout=timeout_ms) if not dialog_messages else None
                    else:
                        raise ValueError(f"unknown acceptance action: {action}")
                    observation["actual"] = "passed"
                if errors:
                    raise AssertionError("; ".join(errors))
                result.update(status="succeeded", failure_kind=None, log="Browser acceptance passed",
                              interaction_status="passed" if contract["steps"] else "not_required")
            except Exception as exc:
                result["log"] = str(exc)
                if result["status"] == "failed":
                    page.screenshot(path=str(report_dir / "failure.png"), full_page=True)
                    result["screenshot"] = str(report_dir / "failure.png")
            finally:
                browser.close()
    except Exception as exc:
        result.update(status="unverified", failure_kind="environment", log=str(exc))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 2)
    (report_dir / "runtime.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def runtime_validation(state: dict) -> dict:
    from workflow.repair import after_validation
    kind = state.get("code_gen_type")
    if kind not in ("html", "multi_file", "vue_project"):
        state["runtime_result"] = {"status": "not_required", "log": "No browser profile for this language"}
    else:
        project = Path(state["project_dir"])
        root = project / "dist" if kind == "vue_project" else project
        if not (root / "index.html").is_file() and (root / "src/index.html").is_file():
            root = root / "src"
        state["runtime_result"] = validate_page(root, acceptance_contract(state.get("user_request", "")),
            report_dir=project.parent / (state.get("artifact_run_id", project.name) + ".acceptance"))
    state["phase"] = "runtime_done"
    state["validation_route"] = after_validation(state, "runtime")
    return state
