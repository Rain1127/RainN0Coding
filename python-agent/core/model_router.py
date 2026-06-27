"""
模型路由器 —— 多候选路由 + Sentinel 熔断降级

用法:
    from core.model_router import model_router
    result = model_router.route("structured", messages, parser=None)

路由逻辑:
  1. 从 ModelRegistry 获取 group 候选列表
  2. 过滤已熔断的候选
  3. 按优先级依次尝试，成功即返回
  4. 全部失败 → 降级策略
"""
from langchain_openai import ChatOpenAI
from core.model_registry import get_group, ModelCandidate, MODEL_GROUPS
from config import config
from monitoring import record_llm_call, update_circuit_breaker


class ModelRouter:
    """多候选路由器"""

    def route(self, group_name: str, messages: list,
              parser=None, allow_degraded: bool = True,
              langsmith_extra: dict = None):
        """
        路由 LLM 调用到可用的候选模型。

        Args:
            group_name:   "reasoning" | "structured" | "lightweight"
            messages:     LangChain 消息列表
            parser:       可选，JSON parser（结构化输出时使用）
            allow_degraded: 全部失败时是否允许降级返回 None
            langsmith_extra: LangSmith trace metadata (metadata, tags, run_name)

        Returns:
            parser 的返回值（结构化输出），或 LLM 的 str 响应
        """
        group = get_group(group_name)
        candidates = group.get_active()

        if not candidates:
            print(f"[Router] {group_name}: 所有候选已熔断")
            if allow_degraded:
                return None
            raise RuntimeError(f"{group_name}: 所有模型候选不可用")

        last_error = None
        for i, candidate in enumerate(candidates):
            cb = candidate.circuit_breaker
            cb_name = candidate.name

            # ===== 丰富 LangSmith trace：标记 attempt / fallback / model =====
            attempt_extra = dict(langsmith_extra) if langsmith_extra else {}
            attempt_extra.setdefault("metadata", {})
            attempt_extra["metadata"].update({
                "attempt": i + 1,
                "fallback": i > 0,
                "model_candidate": cb_name,
            })
            tags = list(attempt_extra.get("tags", []))
            if i > 0:
                tags.append(f"fallback_attempt_{i+1}")
            attempt_extra["tags"] = tags

            print(f"[Router] {group_name}: 尝试 [{i+1}/{len(candidates)}] {cb_name} ({candidate.model})")

            try:
                result = self._call_llm(candidate, messages, parser,
                                        langsmith_extra=attempt_extra)
                if result is not None:
                    if cb:
                        cb.record_success()
                    print(f"[Router] {group_name}: {cb_name} 成功")
                    record_llm_call(candidate.model, status="success")
                    return result
            except Exception as e:
                last_error = e
                if cb:
                    cb.record_failure()
                print(f"[Router] {group_name}: {cb_name} 失败 -> {type(e).__name__}: {str(e)[:120]}")
                record_llm_call(candidate.model, status="error")

        # 全部失败 → 降级
        print(f"[Router] {group_name}: 全部 {len(candidates)} 个候选失败，last_error={last_error}")

        if allow_degraded:
            return None
        raise RuntimeError(f"{group_name}: 所有模型调用失败") from last_error

    def _call_llm(self, candidate: ModelCandidate, messages: list,
                  parser=None, langsmith_extra: dict = None) -> object:
        """实际调用 LLM API。

        Args:
            langsmith_extra: LangSmith RunnableConfig (metadata, tags, run_name)
                             会自动被 LangSmith callback 捕获到 trace。
        """
        # Qwen/阿里云 DashScope 在 Windows Python 环境存在 TLS 兼容
        # 问题(UNEXPECTED_EOF_WHILE_READING), curl 不受影响。
        if "dashscope" in candidate.base_url:
            return self._call_via_curl(candidate, messages, parser)

        llm = ChatOpenAI(
            model=candidate.model,
            api_key=candidate.api_key,
            base_url=candidate.base_url,
            timeout=candidate.timeout,
            max_retries=0,              # 关掉 LangChain 自带重试，让熔断器控制失败计数
            temperature=0.0,
        )

        if parser:
            # 结构化输出路径：用 create_json_parser 的模式
            return parser(messages, _client=llm, _config=langsmith_extra)

        # 纯文本路径 —— langsmith_extra 作为 LangChain RunnableConfig 传入
        response = llm.invoke(messages, config=langsmith_extra)
        content = response.content or ""
        if not content:
            raise ValueError(f"{candidate.name}: LLM 返回空内容")
        return content

    def _call_via_curl(self, candidate: ModelCandidate, messages: list,
                        parser=None) -> object:
        """通过 curl 子进程调用 Qwen API（绕过 Python SSL 兼容问题）。"""
        import subprocess, json

        role_map = {"system": "system", "human": "user", "ai": "assistant"}
        msgs = [{"role": role_map.get(getattr(m, 'type', ''), 'user'), "content": m.content}
                for m in messages]

        # 如果有 parser，追加 field_spec 到最后一条消息
        body = {
            "model": candidate.model,
            "messages": msgs,
            "temperature": config.LLM_TEMPERATURE_STRUCTURED if parser else config.LLM_TEMPERATURE,
            "max_tokens": config.LLM_MAX_TOKENS,
        }

        cmd = [
            "curl", "-s", "-w", "\n%{http_code}",
            f"{candidate.base_url}/chat/completions",
            "-H", f"Authorization: Bearer {candidate.api_key}",
            "-H", "Content-Type: application/json",
            "-d", json.dumps(body, ensure_ascii=False),
            "--max-time", str(candidate.timeout),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace",
                                    timeout=candidate.timeout + 5)
            output = (result.stdout or "").strip()
            if not output:
                raise RuntimeError(f"curl 无输出, stderr: {result.stderr[:200]}")
            lines = output.rsplit("\n", 1)
            if len(lines) == 2:
                resp_json, http_code = lines[0], lines[1]
            else:
                raise RuntimeError(f"curl 输出格式异常: {output[:200]}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("curl 超时")

        if http_code != "200":
            raise RuntimeError(f"Qwen 返回 HTTP {http_code}: {resp_json[:200]}")

        try:
            data = json.loads(resp_json)
            content = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            raise RuntimeError(f"Qwen 响应解析失败: {e}") from e

        if parser and content:
            # 解析 JSON 内容为 Pydantic 模型
            import re
            clean = content.strip()
            if clean.startswith("```"):
                parts = clean.split("```")
                if len(parts) >= 2:
                    inner = parts[1]
                    if inner.startswith("json"):
                        inner = inner[4:]
                    clean = inner.strip()
            obj = json.loads(clean)
            return parser.__self__ if hasattr(parser, '__self__') else obj

        if not content:
            raise ValueError(f"{candidate.name}: curl 路径返回空内容")
        return content

    def get_status(self) -> dict:
        """返回所有模型的熔断状态（用于监控）。"""
        status = {}
        for group_name, group in MODEL_GROUPS.items():
            for c in group.candidates:
                cb = c.circuit_breaker
                status[c.name] = {
                    "state": cb.state if cb else "none",
                    "failures": cb.failure_count if cb else 0,
                }
        return status


# 全局单例
model_router = ModelRouter()
