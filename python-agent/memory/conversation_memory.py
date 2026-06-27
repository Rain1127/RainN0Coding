"""
会话记忆 —— 滑动窗口 + 自动摘要压缩

存储: Redis Hash (key: "memory:{thread_id}")，不可用时降级为内存字典

结构:
  messages: JSON 数组，全部消息 [{role, content, timestamp}]
  summary:  旧消息的摘要文本（滑动窗口外的消息被 LLM 压缩至此）

机制:
  1. 每条新消息追加到 messages 末尾
  2. 消息总数超过 summary_trigger 时，将窗口外的旧消息汇总给 LLM 生成摘要
  3. get_context() 返回 {summary, recent_messages} 供 Agent 使用

用途:
  多轮对话场景 —— "继续"、"按第二种方案"、"把这个改成XX" 等短输入
"""
import json
import time
import redis
from typing import Optional
from config import config


class ConversationMemory:
    """滑动窗口 + 摘要压缩的会话记忆管理器。"""

    def __init__(
        self,
        window_size: int = 10,
        summary_trigger: int = 15,
    ):
        self.window_size = window_size
        self.summary_trigger = summary_trigger
        self._redis: Optional[redis.Redis] = None
        self._redis_ok: bool | None = None
        self._fallback: dict[str, dict] = {}  # 内存降级存储

    # ========== 公开 API ==========

    def add_message(self, thread_id: str, role: str, content: str):
        """追加一条消息。role: 'user' | 'assistant'"""
        if not content:
            return

        key = f"memory:{thread_id}"
        messages = self._load_messages(key)
        messages.append({
            "role": role,
            "content": content[:2000],
            "timestamp": time.time(),
        })
        self._save_messages(key, messages)

        if len(messages) > self.summary_trigger:
            self._summarize(key, messages)

    def get_context(self, thread_id: str) -> dict:
        """
        返回 {summary, recent_messages, total}。

        summary: 旧消息摘要（空字符串 = 无历史）
        recent_messages: 滑动窗口内的最近消息列表
        """
        key = f"memory:{thread_id}"
        messages = self._load_messages(key)
        summary = self._load_summary(key)

        recent = messages[-self.window_size:] if messages else []
        return {
            "summary": summary,
            "recent_messages": recent,
            "total": len(messages),
        }

    def clear(self, thread_id: str):
        """清除会话记忆。"""
        key = f"memory:{thread_id}"
        if self._redis_ok:
            try:
                self._redis.delete(key)
            except Exception:
                pass
        self._fallback.pop(key, None)

    # ========== 存储后端 ==========

    def _get_redis(self) -> Optional[redis.Redis]:
        if self._redis_ok is False:
            return None
        if self._redis_ok is True:
            return self._redis
        # 首次尝试连接
        try:
            self._redis = redis.Redis(
                host=config.REDIS_HOST,
                port=config.REDIS_PORT,
                db=1,
                socket_connect_timeout=2,
            )
            self._redis.ping()
            self._redis_ok = True
            print("[Memory] 使用 Redis 存储")
        except Exception:
            self._redis_ok = False
            print("[Memory] Redis 不可用，使用内存降级存储（重启丢失）")
        return self._redis if self._redis_ok else None

    def _load_messages(self, key: str) -> list[dict]:
        r = self._get_redis()
        if r:
            try:
                raw = r.hget(key, "messages")
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
        # 内存降级
        fb = self._fallback.get(key, {})
        return fb.get("messages", [])

    def _save_messages(self, key: str, messages: list[dict]):
        r = self._get_redis()
        data = json.dumps(messages, ensure_ascii=False)
        if r:
            try:
                r.hset(key, "messages", data)
                r.expire(key, config.MEMORY_REDIS_TTL_SECONDS)
                return
            except Exception:
                pass
        # 内存降级
        fb = self._fallback.setdefault(key, {})
        fb["messages"] = messages

    def _load_summary(self, key: str) -> str:
        r = self._get_redis()
        if r:
            try:
                raw = r.hget(key, "summary")
                if raw:
                    return raw.decode("utf-8", errors="replace")
            except Exception:
                pass
        fb = self._fallback.get(key, {})
        return fb.get("summary", "")

    def _save_summary(self, key: str, summary: str):
        r = self._get_redis()
        if r:
            try:
                r.hset(key, "summary", summary)
                r.expire(key, config.MEMORY_REDIS_TTL_SECONDS)
                return
            except Exception:
                pass
        fb = self._fallback.setdefault(key, {})
        fb["summary"] = summary

    # ========== 摘要生成 ==========

    def _summarize(self, key: str, messages: list[dict]):
        """调用 LLM 将窗口外的旧消息压缩为摘要。"""
        old = messages[: -self.window_size]
        if not old:
            return

        old_text = "\n".join(
            f"[{m['role']}] {m['content'][:500]}"
            for m in old
        )

        existing_summary = self._load_summary(key)

        prompt = f"""你是一个对话摘要助手。将以下对话历史压缩为一段简洁的摘要（中文，200字以内），只保留关键信息：任务目标、已完成的步骤、重要决策、待处理事项。

已有摘要（如有）：
{existing_summary or '(无)'}

最近新增的旧消息：
{old_text}

请输出新的完整摘要："""

        try:
            new_summary = self._call_llm(prompt)
            if new_summary:
                self._save_summary(key, new_summary)
                # 移除已摘要的旧消息，只保留窗口内的
                recent = messages[-self.window_size:]
                self._save_messages(key, recent)
        except Exception as e:
            print(f"[Memory] 摘要生成失败: {e}")

    def _call_llm(self, prompt: str) -> Optional[str]:
        """调用 LLM 生成摘要。"""
        try:
            import openai
            client = openai.OpenAI(
                api_key=config.DEEPSEEK_API_KEY,
                base_url=config.DEEPSEEK_BASE_URL,
            )
            response = client.chat.completions.create(
                model=config.CHAT_MODEL,
                messages=[
                    {"role": "system", "content": "你是一个对话摘要助手。输出简洁的中文摘要。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=300,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[Memory] LLM 调用失败: {e}")
            return None


# ========== 全局单例 ==========

conversation_memory = ConversationMemory(
    window_size=config.MEMORY_WINDOW_SIZE,
    summary_trigger=config.MEMORY_SUMMARY_TRIGGER,
)
