"""Simple shared logging helpers for agent progress output."""


def _clip(text: str | None, limit: int = 80) -> str:
    if not text:
        return ""
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def log_agent_start(agent_name: str, message: str) -> None:
    print(f"[{agent_name}] START {message}")


def log_agent_ok(agent_name: str, message: str) -> None:
    print(f"[{agent_name}] OK {message}")


def log_agent_fail(agent_name: str, message: str) -> None:
    print(f"[{agent_name}] FAIL {message}")


def summarize_request(user_request: str | None, limit: int = 60) -> str:
    clipped = _clip(user_request, limit)
    return clipped or "-"
