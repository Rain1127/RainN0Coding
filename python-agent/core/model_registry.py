"""
模型候选注册表 —— 定义每个 model group 的候选列表及熔断器

3 个 group:
  - reasoning:   Coder Agent
  - structured:  PM / Architect / Reviewer
  - lightweight: Intent / Summarizer
"""
from dataclasses import dataclass, field
from core.circuit_breaker import CircuitBreaker
from config import config


@dataclass
class ModelCandidate:
    """单个模型候选"""
    name: str           # 显示名称，如 "deepseek-v4-pro"
    model: str          # model name 参数
    api_key: str
    base_url: str
    timeout: int = 120
    circuit_breaker: CircuitBreaker | None = None


@dataclass
class ModelGroup:
    """一组候选模型（按优先级排列）"""
    name: str
    candidates: list[ModelCandidate] = field(default_factory=list)

    def get_active(self) -> list[ModelCandidate]:
        """返回当前未被熔断的候选（按优先级）。"""
        active = []
        for c in self.candidates:
            cb = c.circuit_breaker
            if cb is None or cb.allow_request():
                active.append(c)
        return active


def _make_cb(name: str) -> CircuitBreaker:
    return CircuitBreaker(name, failure_threshold=config.CB_FAILURE_THRESHOLD,
                          cooldown_seconds=config.CB_COOLDOWN_SECONDS)


# ===== 模型候选注册表 =====

MODEL_GROUPS: dict[str, ModelGroup] = {
    "reasoning": ModelGroup(
        name="reasoning",
        candidates=[
            ModelCandidate(name="deepseek-v4-pro", model=config.DEEPSEEK_MODEL,
                           api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL,
                           timeout=config.LLM_TIMEOUT, circuit_breaker=_make_cb("deepseek-v4-pro")),
            ModelCandidate(name="deepseek-chat", model=config.CHAT_MODEL,
                           api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL,
                           timeout=config.LLM_FALLBACK_TIMEOUT, circuit_breaker=_make_cb("deepseek-chat-r")),
            ModelCandidate(name="GLM-4.7-Flash", model=config.ZHIPU_FLASH_MODEL,
                           api_key=config.ZHIPU_API_KEY, base_url=config.ZHIPU_BASE_URL,
                           timeout=config.LLM_FALLBACK_TIMEOUT, circuit_breaker=_make_cb("glm-4.7-flash-r")),
        ]
    ),
    "structured": ModelGroup(
        name="structured",
        candidates=[
            ModelCandidate(name="deepseek-chat", model=config.CHAT_MODEL,
                           api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL,
                           timeout=config.LLM_TIMEOUT, circuit_breaker=_make_cb("deepseek-chat-s")),
            ModelCandidate(name="GLM-4.7-Flash", model=config.ZHIPU_FLASH_MODEL,
                           api_key=config.ZHIPU_API_KEY, base_url=config.ZHIPU_BASE_URL,
                           timeout=config.LLM_FALLBACK_TIMEOUT, circuit_breaker=_make_cb("glm-4.7-flash-s")),
        ]
    ),
    "lightweight": ModelGroup(
        name="lightweight",
        candidates=[
            ModelCandidate(name="deepseek-chat", model=config.CHAT_MODEL,
                           api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL,
                           timeout=config.LLM_TIMEOUT, circuit_breaker=_make_cb("deepseek-chat-l")),
            ModelCandidate(name="GLM-4.7-Flash", model=config.ZHIPU_FLASH_MODEL,
                           api_key=config.ZHIPU_API_KEY, base_url=config.ZHIPU_BASE_URL,
                           timeout=config.LLM_FALLBACK_TIMEOUT, circuit_breaker=_make_cb("glm-4.7-flash-l")),
        ]
    ),
}


def get_group(name: str) -> ModelGroup:
    return MODEL_GROUPS.get(name, MODEL_GROUPS["lightweight"])
