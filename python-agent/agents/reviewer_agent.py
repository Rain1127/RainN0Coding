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
from llm_factory import create_json_parser
from state.code_gen_state import CodeGenState
from config import config, get_lang_config


# ============ Pydantic 输出模型 ============

class Issue(BaseModel):
    file: str = Field(description="问题所在文件路径")
    severity: str = Field(description="严重度: critical / warn / info")
    category: str = Field(description="问题分类: syntax / logic / security / style / performance / accessibility")
    description: str = Field(description="问题描述")
    suggestion: str = Field(description="修复建议")


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
    """构建代码摘要——不发完整代码以节省 Token"""
    if not code_files:
        return "(无代码文件)"

    lines = []
    for f in code_files:
        path = f.get("path", "unknown")
        content = f.get("content", "")
        line_count = len(content.split("\n"))

        # 提取关键结构信息
        has_template = "<template>" in content
        has_script = "<script" in content
        has_style = "<style" in content
        imports = [l.strip() for l in content.split("\n") if l.strip().startswith("import")]

        block_info = []
        if has_template: block_info.append("template")
        if has_script: block_info.append("script")
        if has_style: block_info.append("style")
        blocks = "+".join(block_info) if block_info else "empty"

        lines.append(f"### {path} ({line_count} 行, 含: {blocks})")
        if imports:
            lines.append("导入: " + " | ".join(imports[:5]))
            if len(imports) > 5:
                lines.append(f"  ... 共 {len(imports)} 个 import")

        # 只传关键结构，不传完整代码
        lines.append(content[:2500])
        if len(content) > 2500:
            lines.append(f"  ... (截断，共 {len(content)} 字符)")
        lines.append("---")

    return "\n".join(lines)


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
    if not code_files:
        state["error"] = "code_files 为空，Reviewer Agent 无法审查"
        state["phase"] = "error"
        return state

    prd = state.get("prd") or {}
    architecture = state.get("architecture") or {}

    code_summary = _build_code_summary(code_files)

    user_prompt = f"""请审查以下代码，对照架构方案检查完整性和正确性：

## 架构方案（参考）
- 需要生成的文件: {len(architecture.get('file_list', []))} 个
- 实际生成的文件: {len(code_files)} 个

## PRD 功能清单（对照检查）
{_format_prd_features(prd.get('features', []))}

## 代码文件
{code_summary}

请逐一审查每个文件，输出 ReviewResult。"""

    code_gen_type = state.get("code_gen_type", "vue_project")

    messages = [
        SystemMessage(content=_build_review_prompt(code_gen_type)),
        HumanMessage(content=user_prompt),
    ]

    try:
        result: ReviewResult = parser(messages, user_id=state.get("user_id"))
    except Exception as e:
        state["error"] = f"Reviewer Agent LLM 调用失败: {e}"
        state["phase"] = "error"
        return state

    if result is None:
        state["error"] = "Reviewer Agent 失败：所有模型候选不可用（全部已熔断或调用失败）"
        state["phase"] = "error"
        return state

    # 写入 State
    state["review"] = result.model_dump()

    # === 关键：递增 retry_count（修复 §7.6 和 §8.6 记录的无限循环 bug）===
    if result.passed:
        state["retry_count"] = state.get("retry_count", 0)  # 保持不变
    else:
        state["retry_count"] = state.get("retry_count", 0) + 1

    state["phase"] = "review_done"

    status = "PASS" if result.passed else f"FAIL ({len(result.issues)} issues)"
    print(f"[Reviewer Agent] 评分 {result.score}/100, {status}, "
          f"retry_count={state['retry_count']}/{state.get('max_retries', config.MAX_RETRIES)}")

    return state
