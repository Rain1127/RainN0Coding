"""
会话记忆 —— 结构化关键事实 + 递进摘要 + 滑动窗口

存储: Redis Hash (key: "memory:{thread_id}")，不可用时降级为内存字典

结构:
  messages: 尚未压缩的原始消息，压缩成功后只留窗口 [{role, content, timestamp}]
  summary:  新移出窗口的消息所产生的增量摘要
  facts:    目标、约束、决定、待办的结构化快照

机制:
  1. 每条新消息追加到 messages 末尾
  2. 消息总数超过 summary_trigger 时，仅压缩本次移出窗口的消息
  3. 摘要增量追加保存，旧摘要不再次交给 LLM 压缩
  4. get_context() 返回三层上下文供 Agent 使用

用途:
  多轮对话场景 —— "继续"、"按第二种方案"、"把这个改成XX" 等短输入
"""
import json
import re
import time
from contextlib import nullcontext
from uuid import uuid4
import redis
from typing import Optional
from config import config
from langchain_core.messages import HumanMessage
from prompt_builder import stable_system
from benchmark.redaction import redact
from memory.fact_store import (active_facts, apply_fact_ops, empty_fact_state,
                               migrate_legacy_facts, select_active_facts)


FACT_LIST_FIELDS = ("constraints", "decisions", "pending_tasks")
MAX_SUMMARY_CHARS = 2400
MEMORY_FORMAT_VERSION = "3"
HISTORY_QUERY_WORDS = ("历史", "之前", "原始", "证据", "追溯")


def _history_terms(text: str) -> set[str]:
    """Use CJK bigrams and word tokens so longer Chinese queries find short labels."""
    terms = set()
    for segment in re.findall(r"[\u4e00-\u9fffA-Za-z0-9_.-]+",
                              text.casefold()):
        if any("\u4e00" <= char <= "\u9fff" for char in segment):
            terms.update(segment[index:index + 2]
                         for index in range(len(segment) - 1))
        else:
            terms.add(segment)
    return terms


def _history_index_key(key: str) -> str:
    return f"{key}:history:index"


SUMMARY_SCHEMA = {
    "type": "object",
    "required": ["summary_delta", "fact_ops"],
    "properties": {
        "summary_delta": {"type": "string"},
        "fact_ops": {"type": "array", "items": {
            "type": "object",
            "required": ["op", "key", "category", "value", "source_id", "evidence"],
            "properties": {
                "op": {"type": "string", "enum": ["upsert", "delete"]},
                "key": {"type": "string"},
                "category": {"type": "string", "enum": [
                    "goal", "constraint", "decision", "pending_task"]},
                "value": {"type": "string"},
                "source_id": {"type": "string"},
                "evidence": {"type": "string"},
            },
        }},
    },
}

SUMMARY_SYSTEM = """你是对话摘要助手。只处理本批尚未压缩的原始消息，并输出 JSON 对象：
summary_delta：仅概括本批新信息，中文 200 字以内，不重述已有事实。
fact_ops：只提取本批用户消息明确确认或更正的关键事实操作；没有关键事实时返回空数组。
每个操作包含 op（upsert 或 delete）、key（稳定的事实字段名，尽量沿用已有 key）、category（goal、constraint、decision、pending_task）、value（upsert 时从原文复制的新值）、source_id 和 evidence（原用户消息中的连续原文片段，必须包含 value）。
更正时用已有 key 覆盖；未提及的旧事实不要输出。不要把界面微调等普通待办当作项目关键决策。
只有用户明确取消时才用 delete；不得根据助手回复推断事实。
不要保存密码、令牌等凭证，不要推测未确认事实。
只输出 JSON，不要代码块。\nJSON Schema:\n""" + json.dumps(SUMMARY_SCHEMA, ensure_ascii=False)


def _empty_facts() -> dict:
    return {"goal": "", **{field: [] for field in FACT_LIST_FIELDS}}


def canonical_facts_json(facts: dict) -> str:
    """Serialize the fixed memory fields in one stable order."""
    ordered = {"goal": facts.get("goal", "")}
    ordered.update({field: facts.get(field, []) for field in FACT_LIST_FIELDS})
    return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))


class ConversationMemory:
    """结构化事实、增量摘要和原始消息窗口的会话记忆管理器。"""

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
            "id": uuid4().hex[:12],
            "role": role,
            "content": content[:2000],
            "timestamp": time.time(),
        })
        self._save_messages(key, messages)

        if len(messages) > self.summary_trigger:
            self._summarize(key, messages)

    def get_context(self, thread_id: str, query: str | None = None,
                    max_fact_chars: int = 6000) -> dict:
        """
        返回 {facts, summary, recent_messages, total}。

        summary: 旧消息摘要（空字符串 = 无历史）
        recent_messages: 滑动窗口内的最近消息列表
        """
        key = f"memory:{thread_id}"
        messages = self._load_messages(key)
        summary = self._load_summary(key)
        fact_state = self._load_fact_state(key)
        facts, omitted = (select_active_facts(fact_state, query, max_fact_chars)
                          if query is not None else (active_facts(fact_state), 0))
        history_hits = []
        if query and any(marker in query for marker in HISTORY_QUERY_WORDS):
            history_hits = self.search_history(thread_id, query, limit=2)

        recent = messages[-self.window_size:] if messages else []
        return {
            "facts": facts,
            "summary": summary,
            "recent_messages": recent,
            "omitted_fact_count": omitted,
            "history_hits": history_hits,
            "total": len(messages),
        }

    def clear(self, thread_id: str):
        """清除会话记忆。"""
        key = f"memory:{thread_id}"
        if self._redis_ok:
            try:
                self._redis.delete(key, _history_index_key(key))
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
                password=config.REDIS_PASSWORD or None,
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
                r.hset(key, mapping={"format_version": MEMORY_FORMAT_VERSION,
                                     "messages": data})
                r.expire(key, config.MEMORY_REDIS_TTL_SECONDS)
                r.expire(_history_index_key(key), config.MEMORY_REDIS_TTL_SECONDS)
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
                r.hset(key, mapping={"format_version": MEMORY_FORMAT_VERSION,
                                     "summary": summary})
                r.expire(key, config.MEMORY_REDIS_TTL_SECONDS)
                return
            except Exception:
                pass
        fb = self._fallback.setdefault(key, {})
        fb["summary"] = summary

    def _load_facts(self, key: str) -> dict:
        return active_facts(self._load_fact_state(key))

    def _load_fact_state(self, key: str) -> dict:
        r = self._get_redis()
        if r:
            try:
                current = r.hget(key, "facts_v3")
                if current:
                    value = json.loads(current)
                    if isinstance(value, dict) and isinstance(value.get("records"), dict):
                        return value
                raw = r.hget(key, "facts")
                if raw:
                    return migrate_legacy_facts(self._validate_facts(json.loads(raw)))
            except (ValueError, TypeError):
                return empty_fact_state()
            except Exception:
                pass
        fb = self._fallback.get(key, {})
        if "facts_v3" in fb:
            return fb["facts_v3"]
        return migrate_legacy_facts(fb.get("facts", _empty_facts()))

    def _load_history(self, key: str) -> list[dict]:
        r = self._get_redis()
        if r:
            try:
                raw = r.hget(key, "history")
                if raw:
                    value = json.loads(raw)
                    if isinstance(value, list):
                        return value
            except Exception:
                pass
        return self._fallback.get(key, {}).get("history", [])

    def search_history(self, thread_id: str, query: str, limit: int = 5) -> list[dict]:
        """Find preserved summary batches and their original source messages."""
        needle = query.strip().casefold()
        for word in HISTORY_QUERY_WORDS:
            needle = needle.replace(word, "")
        terms = _history_terms(needle)
        if not terms or limit <= 0:
            return []
        key = f"memory:{thread_id}"
        r = self._get_redis()
        indexed = []
        if r:
            try:
                chunk_ids = set()
                index_key = _history_index_key(key)
                for term in terms:
                    lower = f"[{term}\0"
                    upper = f"[{term}\0\xff"
                    for raw_member in r.zrangebylex(index_key, lower, upper):
                        member = raw_member.decode() if isinstance(raw_member, bytes) else raw_member
                        chunk_ids.add(member.rsplit("\0", 1)[-1])
                if chunk_ids:
                    chunks = r.hmget(key, [f"history_chunk:{item}" for item in chunk_ids])
                    indexed = [json.loads(raw) for raw in chunks if raw]
            except Exception:
                pass
        history = indexed + self._load_history(key)  # include pre-index v3 archive
        matches = []
        for chunk in {item["id"]: item for item in history}.values():
            source_text = "\n".join(item["content"] for item in chunk["sources"])
            score = len(terms & _history_terms(chunk["text"] + "\n" + source_text))
            if score:
                matches.append((score, chunk.get("created_at_ns", 0), chunk))
        matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [chunk for _, _, chunk in matches[:limit]]

    def _save_compacted(self, key: str, summary: str, fact_state: dict,
                        messages: list[dict], chunk: dict):
        """Commit all three memory layers and the evidence archive atomically."""
        facts = active_facts(fact_state)
        terms = _history_terms(chunk["text"] + "\n" + "\n".join(
            source["content"] for source in chunk["sources"]))
        r = self._get_redis()
        recovered = []
        if r:
            try:
                with r.pipeline(transaction=True) as pipe:
                    pipe.hset(key, mapping={
                        "format_version": MEMORY_FORMAT_VERSION,
                        "summary": summary,
                        "facts": canonical_facts_json(facts),
                        "facts_v3": json.dumps(fact_state, ensure_ascii=False),
                        f"history_chunk:{chunk['id']}": json.dumps(chunk, ensure_ascii=False),
                        "messages": json.dumps(messages, ensure_ascii=False),
                    })
                    index_key = _history_index_key(key)
                    if terms:
                        pipe.zadd(index_key, {
                            f"{term}\0{chunk['id']}": 0 for term in terms
                        })
                        pipe.expire(index_key, config.MEMORY_REDIS_TTL_SECONDS)
                    pipe.expire(key, config.MEMORY_REDIS_TTL_SECONDS)
                    pipe.execute()
                return
            except Exception:
                # Redis may still be readable after a failed write. Preserve its
                # existing archive before this instance switches to memory mode.
                try:
                    for _field, raw in r.hscan_iter(key, match="history_chunk:*"):
                        recovered.append(json.loads(raw))
                    legacy = r.hget(key, "history")
                    if legacy:
                        recovered.extend(json.loads(legacy))
                except Exception:
                    pass
                self._redis_ok = False
        fb = self._fallback.setdefault(key, {})
        fb.update({"format_version": MEMORY_FORMAT_VERSION,
                   "summary": summary, "facts": facts,
                   "facts_v3": fact_state, "messages": messages})
        history = fb.setdefault("history", [])
        known = {item["id"] for item in history}
        history.extend(item for item in recovered if item["id"] not in known)
        history.append(chunk)

    @staticmethod
    def _validate_facts(value: object) -> dict:
        if not isinstance(value, dict) or not isinstance(value.get("goal"), str):
            raise ValueError("invalid memory facts")
        facts = {"goal": value["goal"].strip()[:200]}
        for field in FACT_LIST_FIELDS:
            items = value.get(field)
            if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
                raise ValueError(f"invalid memory facts: {field}")
            facts[field] = list(dict.fromkeys(item.strip()[:200] for item in items if item.strip()))
        return facts

    @staticmethod
    def _append_summary(existing: str, delta: str) -> str:
        chunks = [chunk for chunk in (existing, delta.strip()) if chunk]
        combined = "\n".join(chunks)
        if len(combined) <= MAX_SUMMARY_CHARS:
            return combined
        lines = combined.splitlines()
        while len("\n".join(lines)) > MAX_SUMMARY_CHARS and len(lines) > 1:
            lines.pop(0)
        return "\n".join(lines)[-MAX_SUMMARY_CHARS:]

    # ========== 摘要生成 ==========

    def _summarize(self, key: str, messages: list[dict]):
        """仅压缩尚未压缩的旧消息，并更新结构化事实。"""
        old = messages[: -self.window_size]
        if not old:
            return

        for message in messages:
            message.setdefault("id", uuid4().hex)
        old_text = "\n".join(
            f"[source:{m['id']}] [{m['role']}] {m['content']}" for m in old
        )

        existing_facts = self._load_fact_state(key)
        fact_index = {field: {"category": record["category"],
                              "value": record["value"],
                              "label": record.get("label", "")}
                      for field, record in existing_facts["records"].items()}
        prompt = f"""已有关键事实（只用于复用字段 key，不要整表重写，也不要写入摘要）：
{json.dumps(fact_index, ensure_ascii=False)}

本批尚未压缩的原始消息：
{old_text}"""

        started = time.perf_counter()
        success = False
        try:
            raw = self._call_llm(prompt)
            if not raw:
                return
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json.loads(raw)
            if not isinstance(result, dict) or not isinstance(result.get("summary_delta"), str):
                raise ValueError("invalid summary delta")
            delta = result["summary_delta"].strip()
            if not delta:
                raise ValueError("empty summary delta")
            delta = redact(delta)
            operations = result.get("fact_ops")
            try:
                fact_state = apply_fact_ops(existing_facts, operations, old)
            except ValueError:
                # A model can emit one ungrounded operation alongside valid ones.
                # Keep the verified changes and still advance the raw-message window.
                fact_state = existing_facts
                source_order = {message["id"]: index for index, message in enumerate(old)}
                ordered = sorted(operations if isinstance(operations, list) else [],
                                 key=lambda item: source_order.get(
                                     item.get("source_id"), len(old))
                                 if isinstance(item, dict) else len(old))
                for operation in ordered:
                    try:
                        fact_state = apply_fact_ops(fact_state, [operation], old)
                    except ValueError:
                        continue
            summary = self._append_summary(self._load_summary(key), delta[:200])
            archived_sources = redact([message for message in old
                                       if message["role"] == "user"])
            chunk = {"id": uuid4().hex, "text": redact(delta[:200]),
                     "source_ids": [message["id"] for message in archived_sources],
                     "sources": archived_sources,
                     "created_at_ns": time.time_ns()}
            self._save_compacted(key, summary, fact_state,
                                 messages[-self.window_size:], chunk)
            success = True
        except Exception as e:
            print(f"[Memory] 摘要生成失败: {e}")
        finally:
            try:
                from monitoring import record_memory_compaction
                record_memory_compaction(success, time.perf_counter() - started)
            except Exception:
                pass

    def _call_llm(self, prompt: str) -> Optional[str]:
        """调用 LLM 生成摘要。"""
        try:
            from llm_factory import create_llm_router
            import monitoring
            invoke = create_llm_router(group="lightweight", agent_name="memory_summary")
            scope = getattr(monitoring, "phase_scope", lambda _phase: nullcontext())
            with scope("memory_summary"):
                return invoke([stable_system(SUMMARY_SYSTEM), HumanMessage(content=prompt)])
        except Exception as e:
            print(f"[Memory] LLM 调用失败: {e}")
            return None


# ========== 全局单例 ==========

conversation_memory = ConversationMemory(
    window_size=config.MEMORY_WINDOW_SIZE,
    summary_trigger=config.MEMORY_SUMMARY_TRIGGER,
)
