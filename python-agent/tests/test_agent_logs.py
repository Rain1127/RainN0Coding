import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.architect_agent import architect_agent
from agents.builder_agent import builder_agent
from agents.coder_agent import coder_agent
from agents.image_collector_agent import image_collector_agent
from agents.intent_agent import IntentRecognitionResult, intent_agent
from agents.pm_agent import pm_agent
from agents.reviewer_agent import Issue, ReviewResult, reviewer_agent
from agents.supervisor_agent import supervisor_decision


def test_pm_agent_logs_clear_failure_when_user_request_missing(monkeypatch):
    logs = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: logs.append(" ".join(str(arg) for arg in args)))

    result = pm_agent({"phase": "init"})

    assert result["phase"] == "error"
    assert result["error"] == "user_request 为空"
    assert logs == [
        "[PM Agent] START 正在生成 PRD，code_gen_type=vue_project request=-",
        "[PM Agent] FAIL 缺少 user_request，无法生成 PRD",
    ]


def test_architect_agent_logs_clear_failure_when_prd_missing(monkeypatch):
    logs = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: logs.append(" ".join(str(arg) for arg in args)))

    result = architect_agent({"phase": "prd_done"})

    assert result["phase"] == "error"
    assert result["error"] == "PRD 为空，Architect Agent 无法设计架构"
    assert logs == [
        "[Architect Agent] START 正在设计项目结构，page_name=- feature_count=0",
        "[Architect Agent] FAIL 缺少 PRD，无法设计项目结构",
    ]


def test_reviewer_agent_logs_clear_review_summary(monkeypatch):
    logs = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: logs.append(" ".join(str(arg) for arg in args)))

    def fake_create_json_parser(*args, **kwargs):
        def fake_parser(messages, user_id=None):
            return ReviewResult(
                passed=False,
                score=70,
                issues=[
                    Issue(
                        file="src/App.vue",
                        severity="warn",
                        category="logic",
                        description="missing empty state",
                        suggestion="add fallback content",
                    )
                ],
                summary="need one fix",
            )

        return fake_parser

    monkeypatch.setattr("agents.reviewer_agent.create_json_parser", fake_create_json_parser)

    result = reviewer_agent(
        {
            "phase": "code_done",
            "user_id": "u1",
            "code_gen_type": "vue_project",
            "retry_count": 0,
            "max_retries": 3,
            "prd": {"features": [{"priority": "high", "name": "文章列表", "description": "展示文章"}]},
            "architecture": {"file_list": [{"path": "src/App.vue"}]},
            "code_files": [{"path": "src/App.vue", "content": "<template><div>blog</div></template>"}],
        }
    )

    assert result["phase"] == "review_done"
    assert result["retry_count"] == 1
    assert logs == [
        "[Reviewer Agent] START 正在审查代码，generated_files=1 expected_files=1 retry_count=0",
        "[Reviewer Agent] OK 审查完成，score=70 passed=no issues=1 retry_count=1/3",
    ]


def test_coder_agent_logs_clear_failure_when_architecture_missing(monkeypatch):
    logs = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: logs.append(" ".join(str(arg) for arg in args)))

    result = coder_agent(
        {
            "phase": "arch_done",
            "code_gen_type": "vue_project",
            "app_id": "app1",
            "mode": "new",
            "retry_count": 0,
        }
    )

    assert result["phase"] == "error"
    assert result["error"] == "Architecture 为空，Coder Agent 无法生成代码"
    assert logs == [
        "[Coder Agent] START 正在生成代码，mode=new retry_count=0 target_files=0",
        "[Coder Agent] FAIL 缺少 architecture，无法生成代码",
    ]


def test_coder_agent_logs_clear_success_summary(monkeypatch, tmp_path):
    logs = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: logs.append(" ".join(str(arg) for arg in args)))
    monkeypatch.setattr("agents.coder_agent.get_all_tools", lambda: [])
    monkeypatch.setattr("agents.coder_agent.set_tool_context", lambda *args, **kwargs: None)
    monkeypatch.setattr("agents.coder_agent.build_rag_context", lambda *args, **kwargs: "")

    class FakeResponse:
        def __init__(self):
            self.content = '{"files":[{"path":"src/App.vue","content":"<template>ok</template>"}]}'
            self.tool_calls = []
            self.additional_kwargs = {}

    class FakeLLM:
        def invoke(self, messages, config=None):
            return FakeResponse()

    monkeypatch.setattr("agents.coder_agent.create_tool_enabled_llm", lambda *args, **kwargs: FakeLLM())

    result = coder_agent(
        {
            "phase": "arch_done",
            "code_gen_type": "vue_project",
            "app_id": "app2",
            "mode": "new",
            "retry_count": 1,
            "project_dir": str(tmp_path),
            "architecture": {
                "file_list": [{"path": "src/App.vue"}],
                "component_tree": [],
                "data_flow": [],
                "tech_stack": {},
            },
        }
    )

    assert result["phase"] == "code_done"
    assert len(result["code_files"]) == 1
    assert logs == [
        "[Coder Agent] START 正在生成代码，mode=new retry_count=1 target_files=1",
        "[Coder Agent] OK LLM 直接返回文件结果，files=1",
        "[Coder Agent] OK 代码已生成，files=1 total_lines=1 project_dir=" + str(tmp_path),
    ]


def test_builder_agent_logs_clear_failure_when_code_files_missing(monkeypatch):
    logs = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: logs.append(" ".join(str(arg) for arg in args)))

    result = builder_agent({"phase": "code_done", "code_gen_type": "vue_project", "project_dir": "D:/tmp/missing"})

    assert result["phase"] == "error"
    assert result["error"] == "code_files 为空，Builder 无文件可构建"
    assert logs == [
        "[Builder Agent] START 正在构建项目，code_gen_type=vue_project file_count=0 project_dir=D:/tmp/missing",
        "[Builder Agent] FAIL 缺少 code_files，无法执行构建",
    ]


def test_builder_agent_logs_clear_success_summary(monkeypatch, tmp_path):
    logs = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: logs.append(" ".join(str(arg) for arg in args)))
    monkeypatch.setattr(
        "agents.builder_agent.get_lang_config",
        lambda code_gen_type: {"is_frontend": False, "needs_npm_build": False, "needs_syntax_check": False},
    )
    monkeypatch.setattr(
        "agents.builder_agent._check_review_quality_gate",
        lambda state, threshold: {"passed": True, "score": 92, "has_critical": False, "reason": "ok"},
    )
    monkeypatch.setattr(
        "agents.builder_agent._run_syntax_check",
        lambda project_dir, code_files, lc: {"passed": True, "log": "[no syntax check needed]", "tool_available": True},
    )

    result = builder_agent(
        {
            "phase": "code_done",
            "code_gen_type": "python",
            "project_dir": str(tmp_path),
            "code_files": [{"path": "main.py", "content": "print('ok')\n"}],
            "review": {"score": 92, "passed": True, "issues": []},
            "app_id": "",
        }
    )

    assert result["phase"] == "build_done"
    assert result["build_result"]["success"] is True
    assert result["quality_gate_result"]["passed"] is True
    assert logs == [
        "[Builder Agent] START 正在构建项目，code_gen_type=python file_count=1 project_dir=" + str(tmp_path),
        "[Builder Agent] OK 构建阶段完成，build_success=yes log_mode=no_npm_build",
        "[Builder Agent] OK 质量门禁通过，review_score=92 syntax_passed=yes reason=ok",
        "[Builder Agent] OK 跳过索引，reason=app_id missing",
        "[Builder Agent] OK 构建结束，build_success=yes quality_gate=passed files=1 project_dir=" + str(tmp_path),
    ]


def test_intent_agent_logs_clear_failure_when_user_request_missing(monkeypatch):
    logs = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: logs.append(" ".join(str(arg) for arg in args)))

    result = intent_agent({"phase": "init"})

    assert result["phase"] == "error"
    assert result["error"] == "用户输入为空，无法识别意图"
    assert logs == [
        "[Intent Agent] START 正在识别用户意图，request=-",
        "[Intent Agent] FAIL 缺少 user_request，无法识别意图",
    ]


def test_intent_agent_logs_clear_fallback_summary(monkeypatch):
    logs = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: logs.append(" ".join(str(arg) for arg in args)))

    monkeypatch.setattr("agents.intent_agent.recognize_intent", lambda user_request, user_id=None: None)
    monkeypatch.setattr("agents.intent_agent.route_code_gen_type", lambda user_request, user_id=None: "vue_project")

    result = intent_agent({"phase": "init", "user_request": "做一个博客首页", "user_id": "u1"})

    assert result["phase"] == "intent_done"
    assert result["intent"]["slots"]["code_gen_type"] == "vue_project"
    assert logs == [
        "[Intent Agent] START 正在识别用户意图，request=做一个博客首页",
        "[Intent Agent] OK 意图识别完成，intent=代码生成 / 前端代码生成 / 生成 Vue 项目 confidence=55% clarify=no source=fallback",
    ]


def test_image_collector_logs_clear_summary(monkeypatch):
    logs = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: logs.append(" ".join(str(arg) for arg in args)))

    result = image_collector_agent(
        {
            "phase": "arch_done",
            "prd": {
                "page_type": "blog",
                "features": [{"name": "用户评论"}, {"name": "文章列表"}],
            },
        }
    )

    assert len(result["images"]) >= 1
    assert logs == [
        "[Image Collector] START 正在收集素材，page_type=blog feature_count=2",
        "[Image Collector] OK 素材收集完成，image_count=5 categories=avatar,banner,icon,illustration,logo",
    ]


def test_supervisor_logs_clear_review_route_to_coder(monkeypatch):
    logs = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: logs.append(" ".join(str(arg) for arg in args)))

    route = supervisor_decision(
        {
            "phase": "review_done",
            "retry_count": 1,
            "max_retries": 3,
            "review": {
                "passed": False,
                "score": 72,
                "issues": [
                    {
                        "file": "src/App.vue",
                        "severity": "warn",
                        "category": "logic",
                        "description": "empty state missing",
                        "suggestion": "add fallback content",
                    }
                ],
            },
        }
    )

    assert route == "coder_agent"
    assert logs == [
        "[Supervisor Agent] START 正在判断下一步路由，phase=review_done",
        "[Supervisor Agent] OK review 未通过，进入 coder_agent，retry_count=1/3",
    ]


def test_supervisor_logs_clear_review_route_to_human(monkeypatch):
    logs = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: logs.append(" ".join(str(arg) for arg in args)))

    route = supervisor_decision(
        {
            "phase": "review_done",
            "retry_count": 3,
            "max_retries": 3,
            "review": {
                "passed": False,
                "score": 60,
                "issues": [{"file": "src/App.vue", "severity": "warn", "category": "logic", "description": "x", "suggestion": "y"}],
            },
        }
    )

    assert route == "human_intervention"
    assert logs == [
        "[Supervisor Agent] START 正在判断下一步路由，phase=review_done",
        "[Supervisor Agent] FAIL review 未通过且重试已达上限，进入 human_intervention，retry_count=3/3",
    ]
