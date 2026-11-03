"""Long-running conversation behavior through the public memory API."""

import json
import re

from memory.conversation_memory import ConversationMemory


def _memory(monkeypatch):
    memory = ConversationMemory(window_size=2, summary_trigger=3)
    monkeypatch.setattr(memory, "_get_redis", lambda: None)
    prompts = []

    def fake_llm(prompt):
        prompts.append(prompt)
        operations = []
        for source_id, content in re.findall(r"\[source:([^\]]+)\] \[user\] ([^\n]+)", prompt):
            match = re.search(r"(字段\d+)最终确定为(值\d+)", content)
            if match:
                operations.append({"op": "upsert", "key": match.group(1),
                                   "category": "decision", "value": match.group(2),
                                   "source_id": source_id, "evidence": content})
        return json.dumps({"summary_delta": "本批新增需求。", "fact_ops": operations},
                          ensure_ascii=False)

    monkeypatch.setattr(memory, "_call_llm", fake_llm)
    return memory, prompts


def test_fourteen_facts_survive_many_compactions_and_summary_rotation(monkeypatch):
    memory, prompts = _memory(monkeypatch)
    for number in range(1, 15):
        memory.add_message("thread", "user", f"字段{number}最终确定为值{number}。")
    for number in range(15, 42):
        memory.add_message("thread", "user", f"第{number}轮继续调整空态。")

    context = memory.get_context("thread")

    assert len(context["facts"]["decisions"]) == 14
    assert "字段1: 值1" in context["facts"]["decisions"]
    assert "字段14: 值14" in context["facts"]["decisions"]
    assert len(context["summary"]) <= 2400
    assert len(prompts) > 10
    assert all("已有摘要" not in prompt for prompt in prompts)


def test_old_source_is_available_after_it_leaves_hot_summary(monkeypatch):
    memory, _ = _memory(monkeypatch)
    memory.add_message("thread", "user", "字段1最终确定为值1。")
    for number in range(2, 75):
        memory.add_message("thread", "user", f"第{number}轮继续调整空态。")

    matches = memory.search_history("thread", "字段1")

    assert matches
    assert any("字段1最终确定为值1" in source["content"]
               for hit in matches for source in hit["sources"])


def test_query_selects_relevant_fact_and_reports_prompt_omissions(monkeypatch):
    memory, _ = _memory(monkeypatch)
    for number in range(1, 31):
        memory.add_message("thread", "user", f"字段{number}最终确定为值{number}。")
    for number in range(31, 35):
        memory.add_message("thread", "user", f"第{number}轮继续调整空态。")

    context = memory.get_context("thread", query="字段1最终是什么？", max_fact_chars=100)

    assert "字段1: 值1" in context["facts"]["decisions"]
    assert context["omitted_fact_count"] > 0
    assert len(memory.get_context("thread")["facts"]["decisions"]) == 30


def test_archived_source_redacts_a_credential(monkeypatch):
    memory, _ = _memory(monkeypatch)
    memory.add_message("thread", "user", "检查配置 api_key=sk-1234567890abcdef")
    for number in range(2, 6):
        memory.add_message("thread", "user", f"第{number}轮继续调整空态。")

    archived = memory.search_history("thread", "检查配置")

    assert archived
    assert "sk-1234567890abcdef" not in str(archived)


def test_archived_source_redacts_natural_language_password(monkeypatch):
    memory, _ = _memory(monkeypatch)
    memory.add_message("thread", "user", "字段1最终确定为值1。我的密码是 123456")
    for number in range(2, 6):
        memory.add_message("thread", "user", f"第{number}轮继续调整空态。")

    archived = memory.search_history("thread", "字段1")

    assert archived
    assert "123456" not in str(archived)
    assert "字段1最终确定为值1" in str(archived)


def test_history_query_finds_chinese_source_when_fact_key_is_english(monkeypatch):
    memory = ConversationMemory(window_size=2, summary_trigger=3)
    monkeypatch.setattr(memory, "_get_redis", lambda: None)

    def fake_llm(prompt):
        source_id, content = re.findall(
            r"\[source:([^\]]+)\] \[user\] (前端方案最终确定为Vue 3。)", prompt
        )[0] if "前端方案最终确定为Vue 3。" in prompt else (None, None)
        operations = ([{"op": "upsert", "key": "frontend", "category": "decision",
                       "value": "Vue 3", "source_id": source_id, "evidence": content}]
                      if source_id else [])
        return json.dumps({"summary_delta": "本批需求摘要。", "fact_ops": operations},
                          ensure_ascii=False)

    monkeypatch.setattr(memory, "_call_llm", fake_llm)
    memory.add_message("thread", "user", "前端方案最终确定为Vue 3。")
    for number in range(2, 20):
        memory.add_message("thread", "user", f"第{number}轮继续调整空态。")

    context = memory.get_context("thread", query="追溯前端方案的原始证据")

    assert context["history_hits"]
    assert "前端方案最终确定为Vue 3" in str(context["history_hits"])


def test_generated_summary_does_not_persist_a_credential(monkeypatch):
    memory = ConversationMemory(window_size=2, summary_trigger=3)
    monkeypatch.setattr(memory, "_get_redis", lambda: None)
    monkeypatch.setattr(memory, "_call_llm", lambda _prompt: json.dumps({
        "summary_delta": "凭证 api_key=sk-1234567890abcdef", "fact_ops": [],
    }, ensure_ascii=False))
    for number in range(4):
        memory.add_message("thread", "user", f"第{number}轮继续。")

    assert "sk-1234567890abcdef" not in memory.get_context("thread")["summary"]


def test_invalid_model_fact_does_not_block_compaction_or_valid_fact(monkeypatch):
    memory = ConversationMemory(window_size=2, summary_trigger=3)
    monkeypatch.setattr(memory, "_get_redis", lambda: None)

    def fake_llm(prompt):
        sources = re.findall(r"\[source:([^\]]+)\] \[user\] ([^\n]+)", prompt)
        operations = []
        for source_id, content in sources:
            if "数据库最终确定为MySQL" in content:
                operations.extend([
                    {"op": "upsert", "key": "数据库", "category": "decision",
                     "value": "MySQL", "source_id": source_id, "evidence": content},
                    {"op": "upsert", "key": "图表库", "category": "decision",
                     "value": "ECharts", "source_id": source_id, "evidence": content},
                ])
        return json.dumps({"summary_delta": "新增数据库决定。", "fact_ops": operations},
                          ensure_ascii=False)

    monkeypatch.setattr(memory, "_call_llm", fake_llm)
    memory.add_message("thread", "user", "数据库最终确定为MySQL。")
    for number in range(2, 5):
        memory.add_message("thread", "user", f"第{number}轮继续。")

    context = memory.get_context("thread")
    assert context["total"] == 2
    assert "数据库: MySQL" in context["facts"]["decisions"]
    assert "ECharts" not in str(context["facts"])


def test_redis_history_index_supports_lookup_and_clear(monkeypatch):
    class Redis:
        def __init__(self):
            self.hashes = {}
            self.sorted_sets = {}
            self.expirations = []

        def pipeline(self, transaction=True):
            assert transaction
            return self

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self):
            return []

        def hset(self, key, mapping):
            self.hashes.setdefault(key, {}).update(
                {field: value.encode() if isinstance(value, str) else value
                 for field, value in mapping.items()})

        def hget(self, key, field):
            return self.hashes.get(key, {}).get(field)

        def hmget(self, key, fields):
            return [self.hget(key, field) for field in fields]

        def zadd(self, key, mapping):
            self.sorted_sets.setdefault(key, set()).update(
                item.encode() for item in mapping)

        def zrangebylex(self, key, lower, upper):
            start, stop = lower[1:].encode(), upper[1:].encode()
            return [item for item in sorted(self.sorted_sets.get(key, set()))
                    if start <= item <= stop]

        def expire(self, key, _seconds):
            self.expirations.append(key)
            return True

        def delete(self, *keys):
            for raw_key in keys:
                key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
                self.hashes.pop(key, None)
                self.sorted_sets.pop(key, None)

    memory, _ = _memory(monkeypatch)
    redis = Redis()
    monkeypatch.setattr(memory, "_get_redis", lambda: redis)
    memory._redis_ok = True
    memory._redis = redis

    memory.add_message("thread", "user", "字段1最终确定为值1。")
    for number in range(2, 20):
        memory.add_message("thread", "user", f"第{number}轮继续调整空态。")

    stored = redis.hashes["memory:thread"]
    assert "history" not in stored
    assert len([field for field in stored if field.startswith("history_chunk:")]) > 1
    assert memory.search_history("thread", "字段1的历史证据")
    assert "memory:thread:history:index" in redis.sorted_sets

    redis.hashes["memory:thread"]["history"] = json.dumps([{
        "id": "legacy", "text": "字段99确定为旧值。",
        "sources": [{"role": "user", "content": "字段99确定为旧值。"}],
    }], ensure_ascii=False).encode()
    assert memory.search_history("thread", "字段99的历史证据")[0]["id"] == "legacy"

    redis.expirations.clear()
    memory.add_message("thread", "user", "继续")
    assert "memory:thread:history:index" in redis.expirations

    memory.clear("thread")
    assert not redis.hashes and not redis.sorted_sets


def test_readable_redis_archive_is_recovered_when_compaction_write_fails(monkeypatch):
    memory = ConversationMemory(window_size=2, summary_trigger=3)
    old_chunk = {"id": "old", "text": "字段1历史决定。",
                 "sources": [{"role": "user", "content": "字段1最终确定为值1。"}],
                 "created_at_ns": 1}

    class Redis:
        def pipeline(self, **_kwargs):
            raise RuntimeError("write unavailable")

        def hscan_iter(self, _key, match):
            assert match == "history_chunk:*"
            yield b"history_chunk:old", json.dumps(old_chunk, ensure_ascii=False).encode()

        def hget(self, *_args):
            return None

    redis = Redis()
    memory._redis_ok = True
    monkeypatch.setattr(memory, "_get_redis",
                        lambda: redis if memory._redis_ok else None)
    new_chunk = {"id": "new", "text": "字段2新决定。", "sources": [],
                 "created_at_ns": 2}

    memory._save_compacted("memory:thread", "摘要", {"records": {}, "retired": {}},
                           [], new_chunk)

    assert memory._redis_ok is False
    assert {hit["id"] for hit in memory.search_history("thread", "字段1历史证据")} == {
        "old", "new"}
