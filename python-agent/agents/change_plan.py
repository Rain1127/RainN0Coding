"""Constrain edits before tools run and report source differences before publication."""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from pydantic import BaseModel, Field
from llm_factory import create_json_parser
from prompt_builder import compose_messages
from agents.mode_detector import current_request


class ChangePlan(BaseModel):
    files: list[str] = Field(min_length=1, max_length=30)
    reason: str
    regression_checks: list[str] = Field(min_length=1)


def simple_target(state: dict) -> str | None:
    text = current_request(state.get("user_request", ""))
    if state.get("mode") != "modify" or not re.search(r"颜色|文案|字体|间距|字号", text):
        return None
    if re.search(r"新增|添加|接口|模块|路由|登录|权限|数据库|重构", text):
        return None
    paths = [file["path"] for file in state.get("existing_code_files", [])]
    explicit = [path for path in paths if path in text]
    if len(explicit) == 1:
        return explicit[0]
    if "导航" in text:
        targets = [p for p in paths if re.search(r"(?:nav|header)", p, re.I)]
        if len(targets) == 1:
            return targets[0]
    return None


def change_plan(state: dict) -> dict:
    target = simple_target(state)
    if target:
        plan = ChangePlan(files=[target], reason="明确的单文件文案或样式修改",
                          regression_checks=["其他源文件保持不变", "原有交互通过浏览器验收"])
        state["task_complexity"] = "local"
    else:
        parser = create_json_parser(ChangePlan, 'Output JSON: {"files":["relative/path"],"reason":"why","regression_checks":["existing behavior"]}',
                                    group="structured", agent_name="change_plan")
        plan = parser(compose_messages(agent="change_plan", system="在编辑前制定最小修改计划。只列出完成需求必需的文件及需要保留的行为。",
            context="现有文件: " + json.dumps([f["path"] for f in state.get("existing_code_files", [])]),
            request=state.get("user_request", "")), user_id=state.get("user_id"))
        if plan is None:
            raise RuntimeError("修改计划未生成，未执行编辑")
        risky = re.search(r"接口|模块|路由|登录|权限|数据库|重构", current_request(state.get("user_request", "")))
        state["task_complexity"] = "cross_module" if len(plan.files) > 2 or risky else "single_page"
    from tools.path_guard import resolve_project_path
    for path in plan.files:
        resolve_project_path(state["project_dir"], path)
    state["change_plan"] = plan.model_dump()
    state["phase"] = "change_planned"
    return state


def diff_changes(state: dict) -> dict:
    before = {f["path"]: f.get("content", "") for f in state.get("existing_code_files", [])}
    after = {f["path"]: f.get("content", "") for f in state.get("code_files", [])}
    paths = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
    planned = set((state.get("change_plan") or {}).get("files", []))
    changes = []
    for path in paths:
        changes.append({"path": path, "planned": path in planned,
            "diff": "".join(difflib.unified_diff(before.get(path, "").splitlines(keepends=True),
                                                 after.get(path, "").splitlines(keepends=True),
                                                 fromfile="before/" + path, tofile="after/" + path))})
    unexpected = [p for p in paths if p not in planned] if state.get("mode") == "modify" else []
    state["change_result"] = {"files": changes, "unexpected": unexpected}
    if unexpected:
        state["phase"] = "error"
        state["error"] = "修改超出计划，候选版本已保留: " + ", ".join(unexpected)
    return state
