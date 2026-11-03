"""
Prometheus 指标模块 —— FastAPI 自动埋点 + 业务自定义指标

用法：
    from monitoring import setup_monitoring
    setup_monitoring(app)  # 自动挂载 /metrics 端点 + HTTP 埋点

自定义指标：
    from monitoring import (record_phase_duration, record_llm_call,
                            record_request, record_retries, record_files_generated,
                            record_rag_cache_hit, track_phase_duration)
"""
import time
import contextvars
from contextlib import contextmanager
from prometheus_client import Counter, Histogram, Gauge
from prometheus_fastapi_instrumentator import Instrumentator


# ============ 指标定义 ============

# --- 请求级指标 ---
ai_code_gen_requests_total = Counter(
    "ai_code_gen_requests_total",
    "代码生成请求总数",
    ["user_id", "app_id", "code_gen_type", "status"],  # status: success / error
)

ai_code_gen_active_requests = Gauge(
    "ai_code_gen_active_requests",
    "当前正在执行的代码生成请求数",
)

# --- 阶段耗时 ---
ai_code_gen_phase_duration_seconds = Histogram(
    "ai_code_gen_phase_duration_seconds",
    "每个 Agent 阶段的耗时（秒）",
    ["phase", "code_gen_type"],
    buckets=[0.5, 1, 2.5, 5, 10, 30, 60, 120],
)

# --- LLM 调用 ---
ai_code_gen_llm_calls_total = Counter(
    "ai_code_gen_llm_calls_total",
    "LLM API 调用总次数",
    ["model_name", "phase", "status"],  # status: success / error
)

# --- 重试 ---
ai_code_gen_retries = Histogram(
    "ai_code_gen_retries",
    "Review → Coder 重试次数分布",
    ["code_gen_type"],
    buckets=[0, 1, 2, 3, 4, 5],
)

# --- 产出文件 ---
ai_code_gen_files_generated = Histogram(
    "ai_code_gen_files_generated",
    "每次生成产出的文件数",
    ["code_gen_type"],
    buckets=[1, 2, 5, 10, 20, 50, 100],
)

# --- RAG 缓存 ---
ai_rag_cache_hit_total = Counter(
    "ai_rag_cache_hit_total",
    "RAG 缓存命中/未命中次数",
    ["phase", "channel", "status"],  # status: hit / miss / bypass
)

ai_prompt_cache_tokens_total = Counter(
    "ai_prompt_cache_tokens_total",
    "Provider-reported prompt cache and input tokens",
    ["phase", "request_model", "actual_model", "kind"],
)

ai_memory_compaction_total = Counter(
    "ai_memory_compaction_total", "Redis session compaction attempts", ["status"],
)

ai_memory_compaction_duration_seconds = Histogram(
    "ai_memory_compaction_duration_seconds", "Redis session compaction duration",
    ["status"], buckets=[0.01, 0.1, 0.5, 1, 2.5, 5, 10, 30, 60],
)

_KNOWN_PHASES = {"intent", "pm", "arch", "code", "coder", "review", "builder",
                 "memory_summary", "unknown"}
_KNOWN_RAG_CHANNELS = {"grep_fa", "grep_cl", "grep_ep", "grep_cs", "semantic",
                       "intent_directed", "global_vector", "unknown"}
_KNOWN_ACTUAL_MODELS = {"deepseek", "glm", "claude", "openai", "unknown"}


def _bounded(value: str, allowed: set[str]) -> str:
    return value if value in allowed else "unknown"

# ============ Agent 阶段追踪（contextvars，跨越异步上下文） ============

_current_phase: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_phase", default="unknown"
)


def set_current_phase(phase: str) -> None:
    """设置当前 Agent 阶段，供 model_router 读取。"""
    _current_phase.set(phase)


def get_current_phase() -> str:
    return _current_phase.get("unknown")


@contextmanager
def phase_scope(phase: str):
    token = _current_phase.set(phase)
    try:
        yield
    finally:
        _current_phase.reset(token)


# ============ 便捷记录函数 ============

def record_request(user_id: str, app_id: str, code_gen_type: str, status: str) -> None:
    """记录一次代码生成请求的结果。"""
    ai_code_gen_requests_total.labels(
        user_id=user_id, app_id=app_id, code_gen_type=code_gen_type, status=status
    ).inc()


def record_phase_duration(phase: str, code_gen_type: str, duration_seconds: float) -> None:
    """记录某个 Agent 阶段的耗时。"""
    ai_code_gen_phase_duration_seconds.labels(
        phase=phase, code_gen_type=code_gen_type
    ).observe(duration_seconds)


@contextmanager
def track_phase_duration(phase: str, code_gen_type: str = "vue_project"):
    """上下文管理器：自动记录阶段耗时。

    Usage:
        with track_phase_duration("coder", "vue_project"):
            ...
    """
    set_current_phase(phase)
    start = time.time()
    try:
        yield
    finally:
        duration = time.time() - start
        record_phase_duration(phase, code_gen_type, duration)


def record_llm_call(model_name: str, phase: str = "", status: str = "success") -> None:
    """记录一次 LLM API 调用。phase 为空时从 contextvars 读取。"""
    phase = phase or get_current_phase()
    ai_code_gen_llm_calls_total.labels(
        model_name=model_name, phase=phase, status=status
    ).inc()


def record_retries(code_gen_type: str, retry_count: int) -> None:
    """记录一次代码生成的重试次数。"""
    ai_code_gen_retries.labels(code_gen_type=code_gen_type).observe(retry_count)


def record_files_generated(code_gen_type: str, file_count: int) -> None:
    """记录一次代码生成产出的文件数。"""
    ai_code_gen_files_generated.labels(code_gen_type=code_gen_type).observe(file_count)


def record_rag_cache_hit(status: str, *, phase: str = "unknown",
                         channel: str = "unknown") -> None:
    """Record a bounded RAG cache read outcome."""
    ai_rag_cache_hit_total.labels(
        phase=_bounded(phase, _KNOWN_PHASES),
        channel=_bounded(channel, _KNOWN_RAG_CHANNELS),
        status=_bounded(status, {"hit", "miss", "bypass"}),
    ).inc()


def record_prompt_cache_tokens(usage: dict, *, phase: str = "") -> None:
    """Expose distinct provider token categories and input denominator."""
    from config import config
    request_model = _bounded(str(usage.get("request_model") or usage.get("model") or ""),
                             set(config.LLM_MODEL_ALIASES.values()))
    actual_model = _bounded(str(usage.get("actual_model") or "unknown"),
                            _KNOWN_ACTUAL_MODELS)
    labels = {"phase": _bounded(phase or get_current_phase(), _KNOWN_PHASES),
              "request_model": request_model, "actual_model": actual_model}
    for kind, field in (("input", "input_tokens"), ("hit", "cache_hit_tokens"),
                        ("miss", "cache_miss_tokens"),
                        ("creation", "cache_creation_tokens")):
        value = usage.get(field, 0)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            ai_prompt_cache_tokens_total.labels(kind=kind, **labels).inc(value)


def record_memory_compaction(success: bool, duration_seconds: float) -> None:
    status = "success" if success else "failure"
    ai_memory_compaction_total.labels(status=status).inc()
    ai_memory_compaction_duration_seconds.labels(status=status).observe(duration_seconds)


# ============ FastAPI 集成 ============

def setup_monitoring(app) -> None:
    """为 FastAPI 应用挂载 Prometheus 指标端点 + HTTP 自动埋点。

    挂载后访问 GET /metrics 即可获得 Prometheus 文本格式的指标。
    HTTP 级别的指标（请求数、延迟、状态码）由 instrumentator 自动提供。
    """
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
    )
    instrumentator.instrument(app).expose(
        app, endpoint="/metrics", include_in_schema=False
    )
