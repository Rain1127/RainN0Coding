"""Validate fact changes and merge them without rewriting untouched facts."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from benchmark.redaction import redact


CATEGORIES = {"goal": "goal", "constraint": "constraints",
              "decision": "decisions", "pending_task": "pending_tasks"}
DELETE_WORDS = ("取消", "删除", "撤销", "不再", "停止", "废弃", "移除")


def empty_fact_state() -> dict:
    return {"records": {}, "retired": {}}


def migrate_legacy_facts(facts: dict) -> dict:
    """Keep v2 values visible; later extraction can reference their assigned keys."""
    state = empty_fact_state()
    if not isinstance(facts, dict):
        return state
    goal = facts.get("goal")
    if isinstance(goal, str) and goal.strip():
        state["records"]["legacy.goal"] = {
            "key": "legacy.goal", "category": "goal", "value": goal.strip(),
            "source_id": "legacy", "source_timestamp": 0.0, "history": [],
            "label": "",
        }
    for old_category, category in (("constraints", "constraint"),
                                    ("decisions", "decision"),
                                    ("pending_tasks", "pending_task")):
        for value in facts.get(old_category, []):
            if not isinstance(value, str) or not value.strip():
                continue
            value = value.strip()
            key = f"legacy.{old_category}.{sha256(value.encode('utf-8')).hexdigest()[:12]}"
            state["records"][key] = {
                "key": key, "category": category, "value": value,
                "source_id": "legacy", "source_timestamp": 0.0,
                "history": [], "label": "",
            }
    return state


def active_facts(state: dict) -> dict:
    """Render only current values in the legacy context shape."""
    result = {"goal": "", "constraints": [], "decisions": [], "pending_tasks": []}
    for record in state.get("records", {}).values():
        category = record["category"]
        value = record["value"]
        label = record.get("label", record["key"])
        rendered = f"{label}: {value}" if label else value
        if category == "goal":
            result["goal"] = f"{result['goal']}；{rendered}" if result["goal"] else rendered
        else:
            result[CATEGORIES[category]].append(rendered)
    return result


def select_active_facts(state: dict, query: str, max_chars: int = 6000) -> tuple[dict, int]:
    """Bound prompt text while retaining all active records in storage."""
    records = state.get("records", {})
    rendered = active_facts(state)
    if len(str(rendered)) <= max_chars:
        return rendered, 0
    needle = query.casefold()
    def mentioned(item: tuple[str, dict]) -> bool:
        key, record = item
        return any(label and label.casefold() in needle
                   for label in (key, record.get("label", "")))
    ranked = sorted(records.items(), key=lambda item: (
        mentioned(item),
        item[1]["category"] == "goal",
        float(item[1].get("source_timestamp", 0)),
    ), reverse=True)
    chosen = {}
    used = 0
    for key, record in ranked:
        size = len(key) + len(record["value"]) + 5
        if chosen and used + size > max_chars:
            continue
        chosen[key] = record
        used += size
    return active_facts({"records": chosen}), len(records) - len(chosen)


def apply_fact_ops(state: dict, operations: list[dict],
                   source_messages: list[dict]) -> dict:
    """Apply verified changes atomically in memory; callers persist once."""
    if not isinstance(operations, list):
        raise ValueError("fact_ops must be an array")
    sources = {message.get("id"): message for message in source_messages
               if message.get("role") == "user"}
    source_order = {message.get("id"): index
                    for index, message in enumerate(source_messages)}
    verified = []
    for operation in operations:
        if not isinstance(operation, dict):
            raise ValueError("fact operation must be an object")
        kind = operation.get("op")
        key = operation.get("key")
        category = operation.get("category")
        source = sources.get(operation.get("source_id"))
        evidence = operation.get("evidence")
        if kind not in {"upsert", "delete"} or not isinstance(key, str) or not key.strip():
            raise ValueError("invalid fact operation")
        if category not in CATEGORIES or not isinstance(evidence, str) or not evidence:
            raise ValueError("invalid fact category or evidence")
        if source is None or evidence not in source.get("content", ""):
            raise ValueError("fact evidence is absent from the source batch")
        value = operation.get("value", "")
        if kind == "upsert" and (not isinstance(value, str) or not value.strip()
                                  or value.casefold() not in evidence.casefold()):
            raise ValueError("fact value is absent from the evidence")
        if kind == "delete" and not any(word in evidence for word in DELETE_WORDS):
            raise ValueError("fact deletion lacks explicit user cancellation")
        previous = state.get("records", {}).get(key.strip())
        if kind == "delete" and previous and not any(
            label and label.casefold() in evidence.casefold()
            for label in (key, previous.get("label", ""), previous["value"])
        ):
            raise ValueError("fact deletion does not name the current fact")
        if kind == "upsert" and redact(value) != value:
            continue
        verified.append((kind, key.strip(), category, value.strip() if isinstance(value, str)
                         else "", source, redact(evidence)))

    merged = deepcopy(state)
    merged.setdefault("records", {})
    merged.setdefault("retired", {})
    for kind, key, category, value, source, evidence in sorted(
        verified, key=lambda item: source_order[item[4]["id"]]
    ):
        proposed_key = key
        if kind == "upsert" and key not in merged["records"]:
            old_matches = [old_key for old_key, record in merged["records"].items()
                           if record["category"] == category and
                           f"不再采用{record['value']}".casefold() in evidence.casefold()]
            if len(old_matches) == 1:
                key = old_matches[0]
        previous = merged["records"].get(key)
        source_timestamp = float(source.get("timestamp", 0))
        if previous and source_timestamp < float(previous.get("source_timestamp", 0)):
            continue
        if kind == "delete":
            if previous:
                retired = deepcopy(previous)
                retired["retired_source_id"] = source["id"]
                merged["retired"][key] = retired
                del merged["records"][key]
            continue
        history = deepcopy(previous.get("history", [])) if previous else []
        if previous and previous["value"] != value:
            history.append({"value": previous["value"],
                            "source_id": previous["source_id"],
                            "source_timestamp": previous["source_timestamp"]})
        merged["records"][key] = {
            "key": key, "category": category, "value": value,
            "source_id": source["id"], "source_timestamp": source_timestamp,
            "history": history, "label": operation_label(key, previous, proposed_key),
            "evidence": evidence,
        }
    return merged


def operation_label(key: str, previous: dict | None, proposed_key: str) -> str:
    if proposed_key != key:
        return proposed_key
    if previous and previous.get("label"):
        return previous["label"]
    return "" if key.startswith("legacy.") else key
