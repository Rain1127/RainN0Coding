"""Paired cloud A/B probe of fact retention and updated-fact answers.

One synthetic 200-turn dialogue is replayed once per release. Gold values and
checkpoints are fixed in this file before either arm runs.
"""

from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path


CHECKPOINTS = (50, 100, 200)

# Each version is (user turn, canonical value, exact user message).
FACTS = (
    {"id": "project", "question": "项目的正式名称是什么？",
     "versions": ((1, "远汐设备运维台", "项目的正式名称确定为远汐设备运维台。"),)},
    {"id": "audience", "question": "这个项目的目标用户是谁？",
     "versions": ((2, "区域维护主管", "目标用户确定为区域维护主管。"),)},
    {"id": "frontend", "question": "最终前端方案是什么？",
     "versions": ((3, "Angular", "前端初版采用 Angular。"),
                  (31, "Vue 3 PWA", "前端最终改为 Vue 3 PWA，不再使用 Angular。"))},
    {"id": "database", "question": "最终数据库是什么？",
     "versions": ((4, "PostgreSQL", "数据库初版采用 PostgreSQL。"),
                  (33, "MySQL", "数据库最终改用 MySQL，不再使用 PostgreSQL。"))},
    {"id": "cloud", "question": "最终部署在哪个云平台？",
     "versions": ((5, "腾讯云", "初版部署平台确定为腾讯云。"),
                  (35, "阿里云", "最终部署平台改为阿里云，不再使用腾讯云。"))},
    {"id": "export", "question": "最终导出格式是什么？",
     "versions": ((6, "CSV", "初版导出格式确定为 CSV。"),
                  (37, "XLSX", "最终导出格式改为 XLSX，不再使用 CSV。"))},
    {"id": "auth", "question": "最终登录方式是什么？",
     "versions": ((7, "短信验证码", "初版登录采用短信验证码。"),
                  (81, "企业微信单点登录", "最终登录改为企业微信单点登录，不再使用短信验证码。")),
     "aliases": {"企业微信单点登录": ("企业微信单点登录", "企业微信SSO")}},
    {"id": "theme", "question": "最终界面主题是什么？",
     "versions": ((8, "浅色", "初版界面主题采用浅色。"),
                  (83, "深色", "最终界面主题改为深色，不再使用浅色。"))},
    {"id": "chart", "question": "最终图表库是什么？",
     "versions": ((9, "ECharts", "初版图表库采用 ECharts。"),
                  (85, "AntV G2", "最终图表库改为 AntV G2，不再使用 ECharts。")),
     "aliases": {"AntV G2": ("AntV G2", "G2")}},
    {"id": "notification", "question": "最终告警通知渠道是什么？",
     "versions": ((10, "邮件", "初版告警通知渠道采用邮件。"),
                  (87, "企业微信消息", "最终告警通知渠道改为企业微信消息，不再使用邮件。"))},
    {"id": "retention", "question": "最终操作日志保留多久？",
     "versions": ((11, "30天", "初版操作日志保留 30 天。"),
                  (171, "90天", "最终操作日志保留 90 天，不再是 30 天。"))},
    {"id": "sync", "question": "最终离线记录如何同步？",
     "versions": ((12, "自动同步", "初版离线记录联网后自动同步。"),
                  (173, "手动同步", "最终离线记录联网后由用户手动同步，不再自动同步。"))},
    {"id": "language", "question": "最终界面支持哪些语言？",
     "versions": ((13, "仅中文", "初版界面仅支持中文。"),
                  (175, "中英双语", "最终界面支持中英双语，不再仅支持中文。")),
     "aliases": {"中英双语": ("中英双语", "中文和英文", "中英文双语")}},
    {"id": "approval", "question": "最终工单关闭需要几人审批？",
     "versions": ((14, "双人审批", "初版工单关闭需要双人审批。"),
                  (177, "单人审批", "最终工单关闭改为单人审批，不再要求双人审批。"))},
)

INTERLUDES = (
    "检查设备列表的空态提示。", "给设备详情增加序列号展示。",
    "调整工单列表的状态筛选。", "完善异常记录的备注输入。",
    "给巡检列表增加分页。", "检查提交按钮的加载状态。",
    "整理维修记录中的日期格式。", "优化移动端详情页的字段布局。",
    "给设备列表增加所在车间筛选。", "检查附件预览的关闭操作。",
    "在工单详情展示最近处理人。", "完善表单校验失败的提示。",
    "给设备搜索添加清空按钮。", "检查确认弹窗的描述文案。",
    "调整异常卡片的字段顺序。", "为维修记录增加设备编号搜索。",
    "检查图片缩略图的占位状态。", "完善工单列表的排序入口。",
    "给巡检详情增加返回列表的按钮。", "整理设备状态标签的颜色。",
    "完善空工单列表的引导说明。", "给操作记录增加时间筛选。",
    "检查窄屏下的表格滚动。", "整理设备详情的分组标题。",
    "给维修记录添加附件预览。", "检查批量操作的二次确认。",
    "优化工单搜索框的提示文案。", "给巡检列表添加执行人筛选。",
    "完善表单保存失败后的重试提示。", "检查设备详情的长文本换行。",
    "给列表页增加返回顶部入口。", "统一设备编号的显示样式。",
)


def build_event_map() -> dict[int, str]:
    events: dict[int, str] = {}
    for fact in FACTS:
        for turn, _value, message in fact["versions"]:
            if turn in events:
                raise ValueError(f"duplicate fact event at turn {turn}")
            events[turn] = message
    return events


def build_dialogue() -> list[dict[str, str]]:
    events = build_event_map()
    messages = []
    for turn in range(1, CHECKPOINTS[-1] + 1):
        user_text = events.get(turn, f"第 {turn} 轮：{INTERLUDES[(turn - 1) % len(INTERLUDES)]}")
        messages.append({"role": "user", "content": user_text})
        messages.append({"role": "assistant", "content": "收到，继续按已确认的需求完善。"})
    return messages


def active_version(fact: dict, turn: int) -> tuple[int, str, str]:
    return max((version for version in fact["versions"] if version[0] <= turn),
               key=lambda version: version[0])


def _normalize(value: str) -> str:
    return "".join(char.casefold() for char in value if char.isalnum())


def _aliases(fact: dict, value: str) -> tuple[str, ...]:
    return fact.get("aliases", {}).get(value, (value,))


def fact_retained(memory_text: str, fact: dict, turn: int) -> bool:
    expected = active_version(fact, turn)[1]
    normalized = _normalize(memory_text)
    return any(_normalize(alias) in normalized for alias in _aliases(fact, expected))


def score_answer(answer: str, fact: dict, turn: int) -> bool:
    current = active_version(fact, turn)[1]
    normalized = _normalize(answer)
    if not normalized or not any(_normalize(alias) in normalized for alias in _aliases(fact, current)):
        return False
    return not any(_normalize(old_value) in normalized
                   for version_turn, old_value, _ in fact["versions"] if version_turn < active_version(fact, turn)[0])


def _memory_text(context: dict) -> str:
    parts = []
    facts = context.get("facts") or {}
    if facts and any(facts.values()):
        parts.append(f"[关键事实] {json.dumps(facts, ensure_ascii=False)}")
    if summary := context.get("summary"):
        parts.append(f"[对话摘要] {summary}")
    recent = context.get("recent_messages") or []
    if recent:
        parts.append("[最近对话]")
        for message in recent[-6:]:
            role = "用户" if message["role"] == "user" else "AI"
            parts.append(f"{role}: {message['content'][:300]}")
    return "\n".join(parts)


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("answer is not a JSON object")
    return value


def run(variant: str, run_id: str) -> dict:
    import openai

    from config import config
    from memory.conversation_memory import ConversationMemory
    from request_context import bind_request_context, build_litellm_metadata

    memory = ConversationMemory(window_size=config.MEMORY_WINDOW_SIZE,
                                summary_trigger=config.MEMORY_SUMMARY_TRIGGER)
    redis_client = memory._get_redis()
    if redis_client is None or not redis_client.ping():
        raise RuntimeError("Redis memory backend unavailable")
    client = openai.OpenAI(api_key=config.LITELLM_API_KEY, base_url=config.LITELLM_BASE_URL)
    thread_id = f"ablong-{run_id}-{variant}"
    redis_key = f"memory:{thread_id}"
    if redis_client.exists(redis_key):
        raise RuntimeError(f"test key already exists: {redis_key}")

    checkpoints = []
    dialogue = build_dialogue()
    try:
        with bind_request_context(request_id=thread_id, trace_id="",
                                  user_id="ab-memory-eval", app_id="long-horizon"):
            for turn in range(1, CHECKPOINTS[-1] + 1):
                for message in dialogue[(turn - 1) * 2:turn * 2]:
                    memory.add_message(thread_id, message["role"], message["content"])
                if turn not in CHECKPOINTS:
                    continue

                context = memory.get_context(thread_id)
                if not context.get("summary") or len(context.get("recent_messages") or []) != 10:
                    raise RuntimeError(f"memory compression incomplete at turn {turn}")
                memory_text = _memory_text(context)
                question_text = "\n".join(f"{fact['id']}: {fact['question']}" for fact in FACTS)
                response = client.chat.completions.create(
                    model=config.LLM_LIGHTWEIGHT_MODEL,
                    messages=[
                        {"role": "system", "content": "仅根据给定记忆回答。未知时回答‘未知’。只输出由问题 ID 到最短答案的 JSON 对象，不要解释。"},
                        {"role": "user", "content": f"{memory_text}\n[当前请求]\n{question_text}"},
                    ],
                    temperature=0,
                    max_tokens=1000,
                    extra_body={"metadata": build_litellm_metadata({"evaluation": "memory_long_horizon_ab", "variant": variant})},
                )
                raw_answer = response.choices[0].message.content or ""
                answers = _parse_json(raw_answer)
                fact_results = []
                for fact in FACTS:
                    version = active_version(fact, turn)
                    answer = str(answers.get(fact["id"], ""))
                    fact_results.append({
                        "id": fact["id"], "expected": version[1], "answer": answer,
                        "was_updated": len(fact["versions"]) > 1 and version[0] > fact["versions"][0][0],
                        "retained": fact_retained(memory_text, fact, turn),
                        "answer_correct": score_answer(answer, fact, turn),
                    })
                retained = sum(item["retained"] for item in fact_results)
                updated = [item for item in fact_results if item["was_updated"]]
                updated_correct = sum(item["answer_correct"] for item in updated)
                checkpoints.append({
                    "turn": turn,
                    "retention": {"correct": retained, "total": len(FACTS), "rate": retained / len(FACTS)},
                    "update_accuracy": {"correct": updated_correct, "total": len(updated),
                                        "rate": updated_correct / len(updated)},
                    "facts": fact_results,
                    "memory_snapshot": {"facts": context.get("facts"), "summary": context["summary"],
                                        "recent_six": context["recent_messages"][-6:]},
                    "raw_answer": raw_answer,
                })
    finally:
        memory.clear(thread_id)
        if redis_client.exists(redis_key):
            raise RuntimeError(f"test key not cleaned: {redis_key}")

    return {"variant": variant, "run_id": run_id,
            "memory_module": inspect.getfile(ConversationMemory),
            "model": config.LLM_LIGHTWEIGHT_MODEL,
            "dialogue_turns": CHECKPOINTS[-1], "fact_count": len(FACTS),
            "checkpoints": checkpoints}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=("A", "B"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.variant, args.run_id)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for point in result["checkpoints"]:
        print(f"TURN={point['turn']} RETAINED={point['retention']['correct']}/{point['retention']['total']} "
              f"UPDATED={point['update_accuracy']['correct']}/{point['update_accuracy']['total']}")


if __name__ == "__main__":
    main()
