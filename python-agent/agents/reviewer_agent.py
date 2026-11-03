"""
Reviewer Agent —— 代码审查员

输入：Coder Agent 产出的 code_files + PRD 功能清单（对照检查完整性）
输出：ReviewResult {passed, score, issues[]}
行为：调用 LLM 1 次，手动 JSON 解析 + Pydantic validate
      通过 → 设置 phase="review_done"（supervisor 会路由到 builder）
      未通过 → 递增 retry_count → supervisor 决定重试或人工介入
"""
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from agents.agent_logging import log_agent_fail, log_agent_ok, log_agent_start
from llm_factory import create_json_parser
from prompt_builder import compose_messages
from state.code_gen_state import CodeGenState
from config import config, get_lang_config
from agents.review_context import review_units, dependency_manifest, static_issues
from request_context import capture_llm_usage
import json
import os
import time


# ============ Pydantic 输出模型 ============

class Issue(BaseModel):
    file: str = Field(description="问题所在文件路径")
    severity: str = Field(description="严重度: critical / warn / info")
    category: str = Field(description="问题分类: syntax / logic / security / style / performance / accessibility")
    description: str = Field(description="问题描述")
    suggestion: str = Field(description="修复建议")
    line: int | None = Field(default=None, description="原文件行号")


class ReviewResult(BaseModel):
    passed: bool = Field(description="是否通过审查。score >= 80 → true")
    score: int = Field(description="评分 0-100")
    issues: list[Issue] = Field(default_factory=list, description="发现的问题列表")
    summary: str | None = Field(default=None, description="审查总结")


# ============ Prompt ============

def _build_review_prompt(code_gen_type: str | None) -> str:
    lc = get_lang_config(code_gen_type)
    is_frontend = lc.get("is_frontend", False)
    lang_specific = ""
    if is_frontend:
        lang_specific = """### 前端专项
- import 路径是否正确
- 组件引用是否正确
- 图片是否有 alt 属性
- 表单元素是否有 label
- 大列表是否有 :key (Vue) / key (React)"""
    else:
        lang_specific = f"""### {lc['label']} 专项
- 包导入/引用路径是否正确
- 错误处理是否完善
- 类型/接口定义是否完整
- 是否符合 {lc['label']} 标准项目结构"""

    return f"""你是资深{lc['review_role']}。审查{lc['label']}项目代码（{lc['framework']} + {lc['lang']}）。

## 审查维度

### 语法与类型 (30%)
- 类型/类型注解是否正确
- 模块导入路径是否存在
- 函数签名/接口定义是否完整

### 逻辑完整 (30%)
- 是否实现了架构方案中的所有功能
- 边界情况处理（空值、错误、加载状态）
- 数据流是否与架构设计一致

### 安全 (15%)
- 用户输入是否有防护（SQL注入/XSS/命令注入）
- 敏感数据是否硬编码（API key、token、密码）

### 代码质量 (15%)
{lang_specific}

### 性能 (10%)
- 是否有明显的性能问题（N+1查询、未释放资源）

## 评分标准
- >=90: 优秀，通过
- 80-89: 良好，通过
- 60-79: 需要修复，列出具体问题 -> passed=false
- <60: 严重问题，必须重写 -> passed=false

## 输出规则
1. score >= 80 -> passed=true, issues 可为空（仅列 warn/info 级别改进建议）
2. score < 80 -> passed=false, issues 必须列出所有 blocker 问题
3. 每个 issue 必须给出具体修复建议
"""

REVIEW_FIELD_SPEC = """Output ONLY a valid JSON object with these EXACT field names:
{
  "passed": true or false,
  "score": 0-100,
  "issues": [
    {
      "file": "string (file path)",
      "severity": "critical|warn|info",
      "category": "syntax|logic|security|style|performance|accessibility",
      "description": "string (what is wrong)",
      "suggestion": "string (how to fix)"
    }
  ],
  "summary": "string or null (brief overall assessment)"
}
Output ONLY the JSON, no markdown, no explanation."""


# ============ 辅助函数 ============

def _build_code_summary(code_files: list) -> str:
    """Compatibility formatter: every review unit is retained, with original locations."""
    return "\n".join(f"### {u['file']}:{u['start']}-{u['end']}\n{u['content']}" for u in review_units(code_files))


def _format_prd_features(features: list) -> str:
    """从 PRD 提取功能清单供 Reviewer 对照"""
    if not features:
        return "(无)"

    return "\n".join(
        f"- [{f.get('priority', '?')}] {f.get('name', '?')}: {f.get('description', '')}"
        for f in features
    )


# ============ Agent 主函数 ============

def reviewer_agent(state: CodeGenState) -> CodeGenState:
    """Reviewer Agent 主逻辑 —— 审查代码 + 递增 retry_count"""
    parser = create_json_parser(ReviewResult, REVIEW_FIELD_SPEC, group="structured", agent_name="reviewer_agent")

    code_files = state.get("code_files", [])
    expected_files = len((state.get("architecture") or {}).get("file_list", []))
    log_agent_start(
        "Reviewer Agent",
        f"正在审查代码，generated_files={len(code_files)} expected_files={expected_files} "
        f"retry_count={state.get('retry_count', 0)}",
    )

    if not code_files:
        state["error"] = "code_files 为空，Reviewer Agent 无法审查"
        state["phase"] = "error"
        log_agent_fail("Reviewer Agent", "缺少 code_files，无法审查代码")
        return state

    prd = state.get("prd") or {}
    architecture = state.get("architecture") or {}

    units = review_units(code_files)
    manifest = dependency_manifest(code_files)
    static = static_issues(code_files)
    coverage = {"reviewed": [], "uncovered": [], "calls": 0, "tokens": None,
                "static_checks": ["python_ast", "local_import_paths"], "elapsed_ms": 0}
    started = time.monotonic()

    user_prompt = f"""请审查以下代码，对照架构方案检查完整性和正确性：

## 架构方案（参考）
- 需要生成的文件: {len(architecture.get('file_list', []))} 个
- 实际生成的文件: {len(code_files)} 个

## PRD 功能清单（对照检查）
{_format_prd_features(prd.get('features', []))}

## 全项目文件与导入依赖
{manifest}

"""

    code_gen_type = state.get("code_gen_type", "vue_project")

    results = []
    try:
        with capture_llm_usage() as usage:
            for unit in units:
                location = {k: unit[k] for k in ("file", "start", "end")}
                if coverage["calls"] >= getattr(config, "REVIEW_MAX_CALLS", 24) or len(manifest) > 16000:
                    coverage["uncovered"].append(location)
                    continue
                messages = compose_messages(
                    agent="reviewer_agent", system=_build_review_prompt(code_gen_type),
                    context=user_prompt + f"\n## 本次审查 {unit['file']} 行 {unit['start']}–{unit['end']}\n{unit['content']}",
                    request="审查本片段并结合依赖表检查跨文件问题。行号使用原文件行号，禁止把未见的片段视为已审查。",
                )
                coverage["calls"] += 1
                result = parser(messages, user_id=state.get("user_id"))
                if result is None:
                    coverage["uncovered"].append(location)
                else:
                    results.append(result)
                    coverage["reviewed"].append(location)
            total = [entry.get("total_tokens") for entry in usage]
            if total and all(isinstance(n, (int, float)) for n in total):
                coverage["tokens"] = sum(total)
    except Exception as e:
        covered = len(coverage["reviewed"]) + len(coverage["uncovered"])
        coverage["uncovered"].extend({k: u[k] for k in ("file", "start", "end")} for u in units[covered:])
        state["review_coverage"] = coverage
        state["error"] = f"Reviewer Agent LLM 调用失败: {e}"
        state["phase"] = "error"
        log_agent_fail("Reviewer Agent", f"审查代码失败，原因={e}")
        return state

    coverage["elapsed_ms"] = round((time.monotonic() - started) * 1000, 2)
    state["review_coverage"] = coverage
    if state.get("project_dir"):
        with open(os.path.join(state["project_dir"], "review-coverage.json"), "w", encoding="utf-8") as fh:
            json.dump(coverage, fh, ensure_ascii=False, indent=2)
    if not results:
        state["error"] = "Reviewer Agent 失败：所有模型候选不可用（全部已熔断或调用失败）"
        state["phase"] = "error"
        log_agent_fail("Reviewer Agent", "审查代码失败，可用模型候选为空")
        return state

    # 写入 State
    issues = [issue.model_dump() for item in results for issue in item.issues] + static
    passed = all(item.passed for item in results) and not coverage["uncovered"] and not any(i["severity"] == "critical" for i in issues)
    result = ReviewResult(passed=passed, score=min(item.score for item in results),
                          issues=[Issue(**issue) for issue in issues],
                          summary=f"reviewed={len(coverage['reviewed'])}, uncovered={len(coverage['uncovered'])}")
    state["review"] = result.model_dump()

    # === 关键：递增 retry_count（修复 §7.6 和 §8.6 记录的无限循环 bug）===
    if result.passed:
        state["retry_count"] = state.get("retry_count", 0)  # 保持不变
    else:
        state["retry_count"] = state.get("retry_count", 0) + 1

    state["phase"] = "review_done"

    log_agent_ok(
        "Reviewer Agent",
        f"审查完成，score={result.score} passed={'yes' if result.passed else 'no'} "
        f"issues={len(result.issues)} retry_count={state['retry_count']}/{state.get('max_retries', config.MAX_RETRIES)}",
    )

    return state
