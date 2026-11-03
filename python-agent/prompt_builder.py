"""Stable message layout shared by structured and tool-using agents."""

from langchain_core.messages import HumanMessage, SystemMessage


PROMPT_VERSION = "2026-09-27-v1"


def stable_system(system: str, field_spec: str = "") -> SystemMessage:
    version = f"Prompt version: {PROMPT_VERSION}"
    parts = [system.strip()] if system.strip().startswith(version) else [version, system.strip()]
    if field_spec:
        parts.append(f"## Output format\n{field_spec.strip()}")
    return SystemMessage(content="\n\n".join(parts))


def compose_messages(*, agent: str, system: str, context: str = "",
                     rag: str = "", retry: str = "", request: str = "",
                     field_spec: str = "") -> list:
    """Keep fixed instructions first and the current request last."""
    context_parts = []
    marker = "\n[当前请求] "
    if marker in request and any(label in request for label in (
            "[对话摘要]", "[关键事实]", "[最近对话]")):
        memory_context, request = request.rsplit(marker, 1)
        context_parts.append(memory_context)
    if context:
        context_parts.append(context)
    context = "\n\n".join(context_parts)
    sections = []
    for title, value in (("Project and conversation context", context),
                         ("Retrieved references", rag),
                         ("Retry information", retry)):
        if value:
            sections.append(f"## {title}\n{value.strip()}")
    sections.append(f"## Current request\n{request.strip()}")
    return [stable_system(f"Agent: {agent}\n\n{system}", field_spec),
            HumanMessage(content="\n\n".join(sections))]
