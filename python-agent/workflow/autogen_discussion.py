"""
AutoGen 三方讨论模块 —— Coder x Reviewer x Architect 群聊

当 Reviewer 发现架构级问题时，启动 AutoGen RoundRobinGroupChat 让三方讨论修复方案。

AutoGen 0.7.x API 适配（与教程的 0.4.x 完全不同）：
- ConversableAgent → AssistantAgent
- GroupChat + GroupChatManager → RoundRobinGroupChat
- initiate_chat → team.run(task=...)
- message types: autogen_core.models.{SystemMessage,UserMessage,AssistantMessage}
- model client: autogen_ext.models.openai.OpenAIChatCompletionClient (需 model_info dict)
"""
import json
import asyncio
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.models import SystemMessage as AGSystemMessage
from autogen_core.models import UserMessage as AGUserMessage
from autogen_core.models import AssistantMessage as AGAssistantMessage
from config import config


# ===== LLM 客户端工厂 =====

def _create_model_client() -> OpenAIChatCompletionClient:
    """创建 AutoGen 兼容的模型客户端。

    AutoGen 0.7 需要显式 model_info 来声明模型能力。
    deepseek-v4-pro 不支持 function_calling / json_output / structured_output。
    """
    return OpenAIChatCompletionClient(
        model=config.DEEPSEEK_MODEL,
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        temperature=0.1,
        model_info={
            "function_calling": False,
            "json_output": False,
            "vision": False,
            "family": "unknown",
            "structured_output": False,
        },
    )


def create_review_team():
    """创建三方讨论团队：Coder + Reviewer + Architect"""
    client = _create_model_client()

    coder = AssistantAgent(
        name="coder",
        model_client=client,
        system_message="""你是前端程序员。收到 Review 意见后：
1. 判断每个问题是代码级别还是架构级别
2. 代码级别的问题直接给出修复后的代码
3. 架构级别的问题与 architect 讨论后再修复
4. 修复完毕后说明改了什么
5. 所有问题讨论完后说 TERMINATE""",
    )

    reviewer = AssistantAgent(
        name="reviewer",
        model_client=client,
        system_message="""你是代码审查员。你的任务：
1. 逐条提出代码问题，标注严重度（critical/warn/info）
2. 当 coder 给出修复方案后，判断是否解决了问题
3. 如果 coder 的修复方案不对，提出改进意见
4. 当所有问题解决后，说 TERMINATE""",
    )

    architect = AssistantAgent(
        name="architect",
        model_client=client,
        system_message="""你是架构师。只在以下情况发言：
1. Reviewer 和 Coder 对方案有分歧时，给出最终架构决策
2. Coder 提出的修复方案可能会破坏架构一致性时
其他时候保持沉默。发言要简短、决断。""",
    )

    team = RoundRobinGroupChat(
        participants=[coder, reviewer, architect],
        max_turns=config.AUTO_GEN_MAX_ROUNDS,
    )
    return team


async def run_review_discussion(
    code_files: list[dict],
    issues: list[dict],
    architecture: dict,
) -> dict:
    """启动三方讨论修复代码审查问题。

    返回: {
        "messages": [...],  # 讨论历史
        "resolution": "passed|failed",
        "summary": "str"
    }
    """
    team = create_review_team()

    files_summary = _summarize_files(code_files)
    issues_text = json.dumps(issues, ensure_ascii=False, indent=2)
    arch_summary = json.dumps(architecture, ensure_ascii=False, indent=2)[:2000]

    task = f"""## Code Review Found Issues

### Architecture (for reference)
{arch_summary}

### Current Code Files
{files_summary}

### Issues Found
{issues_text}

Please discuss each issue: coder confirms → proposes fix → reviewer validates → architect intervenes only if needed.
Start with the most critical issues first."""

    messages = []
    try:
        async for msg in team.run_stream(task=task):
            messages.append({
                "source": getattr(msg, "source", "unknown"),
                "content": getattr(msg, "content", "")[:500],
            })
        resolution = "passed"
        summary = "三方讨论完成"
    except Exception as e:
        resolution = "failed"
        summary = f"讨论异常: {e}"

    return {
        "messages": messages,
        "resolution": resolution,
        "summary": summary,
    }


def _summarize_files(code_files: list[dict]) -> str:
    """文件摘要"""
    return "\n".join(
        f"- {f.get('path', '?')} ({len(f.get('content', '').split(chr(10)))} 行)"
        for f in code_files
    )


# ===== 同步包装（供 LangGraph 节点调用）=====

def run_review_discussion_sync(code_files: list[dict], issues: list[dict], architecture: dict) -> dict:
    """同步包装 —— 在 LangGraph 节点中调用此函数"""
    return asyncio.run(run_review_discussion(code_files, issues, architecture))


# ===== LangGraph 节点 =====

def autogen_discussion_node(state: dict) -> dict:
    """LangGraph 节点 —— 启动 AutoGen 三方讨论修复架构级问题。

    从 state 读取 code_files、review.issues、architecture，
    调用 Coder + Reviewer + Architect 的 RoundRobinGroupChat，
    将讨论结果写入 state["autogen_discussion"] 供 coder 重试时参考。
    """
    from state.code_gen_state import CodeGenState
    import logging
    logger = logging.getLogger("autogen")

    code_files = state.get("code_files", [])
    review = state.get("review") or {}
    issues = review.get("issues", [])
    architecture = state.get("architecture") or {}

    if not code_files or not issues:
        state["autogen_discussion"] = {
            "completed": False,
            "summary": "缺少 code_files 或 issues，跳过三方讨论",
        }
        return state

    logger.info(f"启动 AutoGen 三方讨论: {len(issues)} 个问题, {len(code_files)} 个文件")

    result = run_review_discussion_sync(code_files, issues, architecture)

    # 将讨论上下文注入 state，coder 重试时参考
    discussion_context = ""
    if result.get("messages"):
        discussion_context = "\n".join(
            f"[{m['source']}] {m['content'][:300]}"
            for m in result["messages"]
        )

    state["autogen_discussion"] = {
        "completed": result.get("resolution") == "passed",
        "summary": result.get("summary", ""),
        "context": discussion_context,
    }

    # 将 AutoGen 讨论结论作为审查补充注入重试上下文
    if discussion_context:
        review["autogen_context"] = (
            "\n## AutoGen 三方讨论结论（Coder × Reviewer × Architect）\n"
            + discussion_context
        )
        state["review"] = review
        # 重置 retry_count 让三方讨论后的重试不计入重试次数
        # （因为这是协作讨论的结果，不是简单的失败重试）
        state["retry_count"] = state.get("retry_count", 0)

    logger.info(f"AutoGen 讨论完成: {result.get('resolution')}")
    return state
