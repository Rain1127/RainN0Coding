"""Three-layer conversation memory and incremental compression."""

import json
import re

from memory.conversation_memory import ConversationMemory
from memory.fact_store import migrate_legacy_facts
from workflow import sse_stream


def _memory(monkeypatch, *, window_size=2, summary_trigger=3):
    memory = ConversationMemory(window_size=window_size, summary_trigger=summary_trigger)
    monkeypatch.setattr(memory, "_get_redis", lambda: None)
    return memory


def _response(summary, ops=None):
    return json.dumps({"summary_delta": summary, "fact_ops": ops or []},
                      ensure_ascii=False)


def test_compaction_only_reads_newly_evicted_messages(monkeypatch):
    memory = _memory(monkeypatch)
    prompts = []
    responses = iter([
        _response("确定用 Vue"),
        _response("新增导出需求"),
    ])

    def fake_llm(prompt):
        prompts.append(prompt)
        return next(responses)

    monkeypatch.setattr(memory, "_call_llm", fake_llm)
    for content in ("旧消息甲", "旧消息乙", "窗口消息丙", "窗口消息丁"):
        memory.add_message("u_a", "user", content)

    first = memory.get_context("u_a")
    assert first["summary"] == "确定用 Vue"
    assert [m["content"] for m in first["recent_messages"]] == ["窗口消息丙", "窗口消息丁"]
    assert first["facts"]["decisions"] == []

    memory.add_message("u_a", "user", "新消息戊")
    memory.add_message("u_a", "user", "新消息己")

    second = memory.get_context("u_a")
    assert second["summary"] == "确定用 Vue\n新增导出需求"
    assert second["facts"]["pending_tasks"] == []
    assert [m["content"] for m in second["recent_messages"]] == ["新消息戊", "新消息己"]
    assert len(prompts) == 2
    assert "旧消息甲" in prompts[0] and "旧消息乙" in prompts[0]
    assert "旧消息甲" not in prompts[1] and "旧消息乙" not in prompts[1]
    assert "确定用 Vue" not in prompts[1]
    assert "窗口消息丙" in prompts[1] and "窗口消息丁" in prompts[1]


def test_invalid_compaction_keeps_raw_messages_for_retry(monkeypatch):
    memory = _memory(monkeypatch)
    monkeypatch.setattr(memory, "_call_llm", lambda _prompt: "not json")
    for content in ("a", "b", "c", "d"):
        memory.add_message("u_a", "user", content)

    assert [m["content"] for m in memory._load_messages("memory:u_a")] == ["a", "b", "c", "d"]
    assert memory.get_context("u_a")["summary"] == ""
    assert memory.get_context("u_a")["facts"] == {
        "goal": "", "constraints": [], "decisions": [], "pending_tasks": []
    }

    monkeypatch.setattr(memory, "_call_llm", lambda _prompt: _response("a 和 b"))
    memory.add_message("u_a", "user", "e")
    assert [m["content"] for m in memory._load_messages("memory:u_a")] == ["d", "e"]


def test_existing_summary_migrates_without_being_recompressed(monkeypatch):
    memory = _memory(monkeypatch)
    memory._save_summary("memory:u_a", "旧版摘要")
    prompts = []

    def fake_llm(prompt):
        prompts.append(prompt)
        return _response("新摘要")

    monkeypatch.setattr(memory, "_call_llm", fake_llm)
    for content in ("a", "b", "c", "d"):
        memory.add_message("u_a", "user", content)

    assert memory.get_context("u_a")["summary"] == "旧版摘要\n新摘要"
    assert "旧版摘要" not in prompts[0]


def test_compaction_sees_facts_at_end_of_stored_message(monkeypatch):
    memory = _memory(monkeypatch)
    prompts = []

    def fake_llm(prompt):
        prompts.append(prompt)
        source_id = re.search(r"\[source:([^\]]+)\] \[user\] .*必须部署到内网", prompt).group(1)
        return _response("确认了部署约束", [{
            "op": "upsert", "key": "部署约束", "category": "constraint",
            "value": "必须部署到内网", "source_id": source_id,
            "evidence": "必须部署到内网",
        }])

    monkeypatch.setattr(memory, "_call_llm", fake_llm)
    memory.add_message("u_a", "user", "普通描述" * 200 + "必须部署到内网")
    for content in ("b", "c", "d"):
        memory.add_message("u_a", "user", content)

    assert "必须部署到内网" in prompts[0]
    assert memory.get_context("u_a")["facts"]["constraints"] == ["部署约束: 必须部署到内网"]


def test_sse_prompt_puts_summary_before_canonical_facts(monkeypatch):
    monkeypatch.setattr(
        sse_stream.conversation_memory,
        "get_context",
        lambda _thread_id, query=None: {
            "facts": {"goal": "制作后台", "constraints": ["只能用 Vue"],
                      "decisions": ["选用 Ant Design Vue"], "pending_tasks": ["完成导出"]},
            "summary": "此前已完成登录页",
            "recent_messages": [],
        },
    )
    captured = {}

    async def fake_run_workflow_async(prompt, *_args, **_kwargs):
        captured["prompt"] = prompt
        yield {"phase": "mode_detected", "mode": "new", "retry_count": 0}

    monkeypatch.setattr(sse_stream, "run_workflow_async", fake_run_workflow_async)

    import asyncio
    async def collect():
        return [event async for event in sse_stream.stream_workflow("继续做", "u", "a")]

    asyncio.run(collect())
    prompt = captured["prompt"]
    assert prompt.index("[对话摘要]") < prompt.index("[关键事实]") < prompt.index("[当前请求]")
    assert '[关键事实] {"goal":"制作后台","constraints":["只能用 Vue"],"decisions":["选用 Ant Design Vue"],"pending_tasks":["完成导出"]}' in prompt
    assert "制作后台" in prompt
    assert "只能用 Vue" in prompt
    assert "完成导出" in prompt


def test_sse_uses_query_to_select_facts_and_show_requested_evidence(monkeypatch):
    captured = {}

    def fake_context(_thread_id, query=None):
        captured["query"] = query
        return {
            "facts": {"goal": "", "constraints": [],
                      "decisions": ["前端方案: Vue 3"], "pending_tasks": []},
            "summary": "近期摘要", "recent_messages": [],
            "omitted_fact_count": 5,
            "history_hits": [{"id": "chunk1", "text": "用户更正前端方案",
                              "sources": [{"role": "user", "content": "更正前端方案：采用Vue 3。"}]}],
        }

    async def fake_run_workflow_async(prompt, *_args, **_kwargs):
        captured["prompt"] = prompt
        yield {"phase": "mode_detected", "mode": "new", "retry_count": 0}

    monkeypatch.setattr(sse_stream.conversation_memory, "get_context", fake_context)
    monkeypatch.setattr(sse_stream, "run_workflow_async", fake_run_workflow_async)

    import asyncio
    async def collect():
        return [event async for event in sse_stream.stream_workflow(
            "追溯前端方案的原始证据", "u", "a")]

    asyncio.run(collect())
    assert captured["query"] == "追溯前端方案的原始证据"
    assert "[关键事实]" in captured["prompt"]
    assert "[历史证据]" in captured["prompt"]
    assert "更正前端方案：采用Vue 3" in captured["prompt"]
    assert "5 项有效事实未注入" in captured["prompt"]


def test_compacted_redis_hash_has_version_and_canonical_facts(monkeypatch):
    memory = ConversationMemory()
    captured = {}

    class Pipeline:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def hset(self, key, mapping):
            captured.update(mapping)
        def expire(self, *_args):
            pass
        def zadd(self, *_args):
            pass
        def execute(self):
            pass

    class Redis:
        def pipeline(self, transaction):
            assert transaction is True
            return Pipeline()

    monkeypatch.setattr(memory, "_get_redis", lambda: Redis())
    fact_state = migrate_legacy_facts({
        "pending_tasks": [], "decisions": ["Vue"], "constraints": [], "goal": "demo",
    })
    memory._save_compacted("memory:x", "summary", fact_state, [], {
        "id": "chunk1", "text": "summary", "sources": [], "source_ids": [],
    })
    assert captured["format_version"] == "3"
    assert captured["facts"] == '{"goal":"demo","constraints":[],"decisions":["Vue"],"pending_tasks":[]}'
    assert "facts_v3" in captured and "history" not in captured
    assert "history_chunk:chunk1" in captured


def test_new_message_hash_is_versioned_before_compaction(monkeypatch):
    memory = ConversationMemory(summary_trigger=100)
    captured = {}

    class Redis:
        def hget(self, *_args):
            return None
        def hset(self, key, *args, **kwargs):
            captured.update(kwargs.get("mapping", {}))
        def expire(self, *_args):
            pass

    monkeypatch.setattr(memory, "_get_redis", lambda: Redis())
    memory.add_message("u", "user", "hello")
    assert captured["format_version"] == "3"


def test_legacy_redis_hash_without_version_remains_readable(monkeypatch):
    memory = ConversationMemory(window_size=2)
    fields = {
        "messages": b'[{"role":"user","content":"old","timestamp":1}]',
        "summary": "legacy summary".encode("utf-8"),
        "facts": b'{"goal":"old goal","constraints":[],"decisions":[],"pending_tasks":[]}',
    }

    class Redis:
        def hget(self, key, field):
            return fields.get(field)

    monkeypatch.setattr(memory, "_get_redis", lambda: Redis())
    context = memory.get_context("u")
    assert context["summary"] == "legacy summary"
    assert context["facts"]["goal"] == "old goal"
    assert context["recent_messages"][0]["content"] == "old"


def test_compaction_records_success_and_failure_duration(monkeypatch):
    import monitoring
    memory = _memory(monkeypatch)
    recorded = []
    monkeypatch.setattr(monitoring, "record_memory_compaction",
                        lambda success, duration: recorded.append((success, duration)))
    monkeypatch.setattr(memory, "_call_llm", lambda _prompt: "not json")
    for content in ("a", "b", "c", "d"):
        memory.add_message("u", "user", content)
    monkeypatch.setattr(memory, "_call_llm", lambda _prompt: _response("delta"))
    memory.add_message("u", "user", "e")
    assert [success for success, _ in recorded] == [False, True]
    assert all(duration >= 0 for _, duration in recorded)


def test_llm_call_works_when_optional_phase_scope_is_absent(monkeypatch):
    import llm_factory
    import monitoring
    memory = _memory(monkeypatch)
    monkeypatch.delattr(monitoring, "phase_scope", raising=False)
    monkeypatch.setattr(llm_factory, "create_llm_router",
                        lambda **_kwargs: lambda _messages: '{"summary_delta":"ok","fact_ops":[]}')

    assert memory._call_llm("本批消息") == '{"summary_delta":"ok","fact_ops":[]}'
