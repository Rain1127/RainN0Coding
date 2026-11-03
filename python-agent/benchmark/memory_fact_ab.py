"""Paired synthetic key-fact accuracy test for the two cloud memory releases."""

from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path


CASES = (
    {
        "id": "stable_facts",
        "events": {0: "项目名称最终确定为青岚看板。", 2: "前端技术栈固定为 Vue 3。",
                   4: "界面主色调固定为青绿色。", 6: "数据来源固定为本地 CSV 文件。"},
        "questions": (
            {"id": "name", "prompt": "项目名称是什么？", "expected": "青岚看板", "aliases": ("青岚看板",)},
            {"id": "frontend", "prompt": "前端技术栈是什么？", "expected": "Vue 3", "aliases": ("Vue 3", "Vue3")},
            {"id": "color", "prompt": "界面主色调是什么？", "expected": "青绿色", "aliases": ("青绿色",)},
            {"id": "source", "prompt": "数据来源是什么？", "expected": "本地 CSV", "aliases": ("本地 CSV", "本地CSV")},
        ),
    },
    {
        "id": "explicit_corrections",
        "events": {0: "初版导出格式为 CSV。", 2: "初版主题为浅色。",
                   4: "初版登录方式为邮箱验证码。", 6: "初版部署平台为腾讯云。",
                   12: "更正最终需求：导出改用 XLSX，不再用 CSV；主题改为深色，不再用浅色。",
                   14: "更正最终需求：登录改为密码登录，不再用邮箱验证码；部署改为阿里云，不再用腾讯云。"},
        "questions": (
            {"id": "export", "prompt": "最终导出格式是什么？", "expected": "XLSX", "aliases": ("XLSX", "Excel"), "reject": ("CSV",)},
            {"id": "theme", "prompt": "最终主题是什么？", "expected": "深色", "aliases": ("深色", "暗色"), "reject": ("浅色",)},
            {"id": "login", "prompt": "最终登录方式是什么？", "expected": "密码登录", "aliases": ("密码登录", "账号密码"), "reject": ("邮箱验证码",)},
            {"id": "cloud", "prompt": "最终部署平台是什么？", "expected": "阿里云", "aliases": ("阿里云",), "reject": ("腾讯云",)},
        ),
    },
    {
        "id": "task_status",
        "events": {0: "项目名称确定为校园报名系统。", 2: "待办事项之一是实现报名表单。",
                   4: "另一项待办是加入短信通知。", 6: "项目明确不接入支付功能。",
                   12: "状态更新：报名表单已经完成，不再是待办。",
                   14: "状态更新：短信通知仍未完成，是下一阶段待办。"},
        "questions": (
            {"id": "name", "prompt": "项目名称是什么？", "expected": "校园报名系统", "aliases": ("校园报名系统",)},
            {"id": "pending", "prompt": "下一阶段未完成的待办是什么？只回答事项名称。", "expected": "短信通知", "aliases": ("短信通知",), "reject": ("报名表单",)},
            {"id": "completed", "prompt": "哪项功能已经完成？只回答事项名称。", "expected": "报名表单", "aliases": ("报名表单",)},
            {"id": "payment", "prompt": "项目是否接入支付功能？", "expected": "否", "aliases": ("否", "不接入支付", "不增加支付", "无需支付", "不需要支付")},
        ),
    },
    {
        "id": "requirements_and_decisions",
        "events": {0: "目标用户明确为校内管理员。", 2: "数据库明确使用 MySQL。",
                   4: "初版图表库选用 ECharts。", 6: "交付界面必须使用中文。",
                   12: "新增硬性要求：必须支持导出 PDF。",
                   14: "图表库的最终决定改为 AntV G2，不再使用 ECharts。"},
        "questions": (
            {"id": "audience", "prompt": "目标用户是谁？", "expected": "校内管理员", "aliases": ("校内管理员",)},
            {"id": "database", "prompt": "数据库使用什么？", "expected": "MySQL", "aliases": ("MySQL",)},
            {"id": "chart", "prompt": "最终图表库是什么？", "expected": "AntV G2", "aliases": ("AntV G2", "G2"), "reject": ("ECharts",)},
            {"id": "pdf", "prompt": "新增的导出格式要求是什么？", "expected": "PDF", "aliases": ("PDF",)},
        ),
    },
    {
        "id": "long_revision_chain",
        "message_count": 72,
        "events": {
            0: "项目名称确定为星桥巡检台。",
            2: "星桥巡检台的目标用户是工厂巡检员。",
            4: "初版不支持离线操作。",
            6: "初版导出格式为 CSV。",
            8: "初版数据库采用 PostgreSQL。",
            10: "初版登录方式为短信验证码。",
            12: "初版部署在腾讯云。",
            16: "初版移动端选用 Flutter。",
            24: "技术方案更正：前端最终改为 Vue 3 PWA，不再使用 Flutter。",
            32: "离线策略更正：断网可暂存巡检记录，联网后由用户手动同步，不再禁止离线。",
            40: "数据库最终改用 MySQL，不再使用 PostgreSQL。",
            46: "导出最终改为 XLSX，不再使用 CSV。",
            52: "登录最终改为企业微信单点登录，不再使用短信验证码。",
            58: "部署平台最终改为阿里云，不再使用腾讯云。",
        },
        "interludes": (
            "检查巡检列表的空态提示。", "给巡检记录添加设备编号筛选。",
            "完善巡检详情的时间展示。", "给异常记录添加处理备注。",
            "让列表页支持按更新时间排序。", "检查表单必填项提示。",
            "优化移动端按钮的点击区域。", "在详情页展示设备所在车间。",
            "给异常图片添加预览入口。", "整理巡检员提交时的确认文案。",
            "给设备列表添加分页。", "在记录页展示最近操作人。",
            "完善巡检失败时的错误提示。", "增加巡检记录的状态筛选。",
            "调整详情页字段顺序。", "检查批量操作的二次确认。",
        ),
        "questions": (
            {"id": "name", "prompt": "项目名称是什么？", "expected": "星桥巡检台", "aliases": ("星桥巡检台",)},
            {"id": "audience", "prompt": "目标用户是谁？", "expected": "工厂巡检员", "aliases": ("工厂巡检员",)},
            {"id": "frontend", "prompt": "最终前端方案是什么？", "expected": "Vue 3 PWA", "aliases": ("Vue 3 PWA", "Vue3 PWA"), "reject": ("Flutter",)},
            {"id": "offline", "prompt": "联网后离线记录如何同步？", "expected": "手动同步", "aliases": ("手动同步",), "reject": ("自动同步",)},
            {"id": "database", "prompt": "最终数据库是什么？", "expected": "MySQL", "aliases": ("MySQL",), "reject": ("PostgreSQL",)},
            {"id": "export", "prompt": "最终导出格式是什么？", "expected": "XLSX", "aliases": ("XLSX", "Excel"), "reject": ("CSV",)},
            {"id": "login", "prompt": "最终登录方式是什么？", "expected": "企业微信单点登录", "aliases": ("企业微信单点登录", "企业微信SSO"), "reject": ("短信验证码",)},
            {"id": "cloud", "prompt": "最终部署平台是什么？", "expected": "阿里云", "aliases": ("阿里云",), "reject": ("腾讯云",)},
        ),
    },
    {
        "id": "long_task_transitions",
        "message_count": 84,
        "events": {
            0: "项目名称确定为云杉课程管理台。",
            2: "目标用户固定为校务管理员。",
            4: "批量导入学员列入待办。",
            6: "课表冲突提醒列入待办。",
            8: "成绩导出列入待办。",
            10: "单点登录列入待办。",
            20: "状态更新：批量导入学员已经完成，不再是待办。",
            32: "状态更新：课表冲突提醒已经取消，不再开发，也不再是待办。",
            44: "状态更新：成绩导出已经完成，不再是待办。",
            56: "状态更新：单点登录因校方接口未开放，仍未完成。",
            62: "新增补课申请为待办。",
            68: "状态更新：补课申请已经完成，不再是待办；单点登录仍是唯一未完成的事项。",
        },
        "interludes": (
            "检查课程列表的筛选交互。", "完善教师详情页的排版。",
            "给班级列表增加分页。", "梳理课程开始时间的展示格式。",
            "调整教室选择器的搜索提示。", "检查空课表的引导文案。",
            "给学员详情页增加备注区域。", "完善提交表单时的错误提示。",
            "调整课程卡片的字段顺序。", "给排课记录增加操作日志入口。",
            "检查移动端课程表的可读性。", "整理课程筛选条件的重置操作。",
            "给教师列表增加姓名搜索。", "检查批量操作的确认弹窗。",
            "统一表格中的日期格式。", "完善课程详情的返回入口。",
        ),
        "questions": (
            {"id": "name", "prompt": "项目名称是什么？", "expected": "云杉课程管理台", "aliases": ("云杉课程管理台",)},
            {"id": "audience", "prompt": "目标用户是谁？", "expected": "校务管理员", "aliases": ("校务管理员",)},
            {"id": "import_status", "prompt": "批量导入学员目前是什么状态？", "expected": "已完成", "aliases": ("已完成", "已经完成"), "reject": ("未完成", "待办", "取消")},
            {"id": "conflict_status", "prompt": "课表冲突提醒目前是什么状态？", "expected": "已取消", "aliases": ("已取消", "取消", "不再开发"), "reject": ("已完成", "未完成")},
            {"id": "export_status", "prompt": "成绩导出目前是什么状态？", "expected": "已完成", "aliases": ("已完成", "已经完成"), "reject": ("未完成", "待办", "取消")},
            {"id": "sso_status", "prompt": "单点登录目前是什么状态？", "expected": "未完成", "aliases": ("未完成", "仍是待办", "仍未完成"), "reject": ("已完成", "取消")},
            {"id": "makeup_status", "prompt": "补课申请目前是什么状态？", "expected": "已完成", "aliases": ("已完成", "已经完成"), "reject": ("未完成", "待办", "取消")},
            {"id": "pending", "prompt": "目前唯一未完成且未取消的事项是什么？只回答事项名称。", "expected": "单点登录", "aliases": ("单点登录",), "reject": ("补课申请", "成绩导出", "课表冲突提醒", "批量导入学员")},
        ),
    },
    {
        "id": "two_projects_entity_binding",
        "message_count": 96,
        "events": {
            0: "云帆工单台的目标用户是维修工程师。",
            2: "北辰仓储台的目标用户是库管员。",
            4: "云帆工单台初版数据库用 MySQL。",
            6: "北辰仓储台数据库固定为 PostgreSQL。",
            8: "云帆工单台导出格式固定为 PDF。",
            10: "北辰仓储台初版导出格式用 XLSX。",
            12: "云帆工单台部署平台固定为腾讯云。",
            14: "北辰仓储台初版部署平台用阿里云。",
            46: "云帆工单台数据库最终改为 SQLite，不再使用 MySQL；北辰仓储台仍用 PostgreSQL。",
            62: "北辰仓储台导出最终改为 CSV，不再使用 XLSX；云帆工单台仍导出 PDF。",
            78: "北辰仓储台部署最终改为华为云，不再使用阿里云；云帆工单台仍部署腾讯云。",
        },
        "interludes": (
            "云帆工单台：检查工单列表的状态筛选。",
            "北辰仓储台：完善入库单详情布局。",
            "云帆工单台：给维修记录添加设备编号搜索。",
            "北辰仓储台：给库存列表增加分页。",
            "云帆工单台：优化工单关闭时的确认文案。",
            "北辰仓储台：检查出库单的空态提示。",
            "云帆工单台：调整维修备注字段顺序。",
            "北辰仓储台：完善库位选择器的搜索。",
            "云帆工单台：给工单详情增加附件预览。",
            "北辰仓储台：给盘点记录增加时间筛选。",
            "云帆工单台：检查移动端按钮尺寸。",
            "北辰仓储台：整理批量入库的错误提示。",
            "云帆工单台：展示工单最近处理人。",
            "北辰仓储台：展示库存最近更新人。",
            "云帆工单台：统一工单日期格式。",
            "北辰仓储台：检查批量出库确认弹窗。",
        ),
        "questions": (
            {"id": "a_audience", "prompt": "云帆工单台的目标用户是谁？", "expected": "维修工程师", "aliases": ("维修工程师",), "reject": ("库管员",)},
            {"id": "b_audience", "prompt": "北辰仓储台的目标用户是谁？", "expected": "库管员", "aliases": ("库管员",), "reject": ("维修工程师",)},
            {"id": "a_database", "prompt": "云帆工单台最终使用什么数据库？", "expected": "SQLite", "aliases": ("SQLite",), "reject": ("MySQL", "PostgreSQL")},
            {"id": "b_database", "prompt": "北辰仓储台最终使用什么数据库？", "expected": "PostgreSQL", "aliases": ("PostgreSQL",), "reject": ("MySQL", "SQLite")},
            {"id": "a_export", "prompt": "云帆工单台最终导出什么格式？", "expected": "PDF", "aliases": ("PDF",), "reject": ("CSV", "XLSX")},
            {"id": "b_export", "prompt": "北辰仓储台最终导出什么格式？", "expected": "CSV", "aliases": ("CSV",), "reject": ("PDF", "XLSX")},
            {"id": "a_cloud", "prompt": "云帆工单台最终部署在哪个平台？", "expected": "腾讯云", "aliases": ("腾讯云",), "reject": ("华为云", "阿里云")},
            {"id": "b_cloud", "prompt": "北辰仓储台最终部署在哪个平台？", "expected": "华为云", "aliases": ("华为云",), "reject": ("腾讯云", "阿里云")},
        ),
    },
)


def select_cases(case_set: str) -> tuple[dict, ...]:
    if case_set == "baseline":
        return CASES[:4]
    if case_set == "extended":
        return CASES[4:]
    if case_set == "all":
        return CASES
    raise ValueError(f"unknown case set: {case_set}")


def build_history(case: dict) -> list[dict[str, str]]:
    history = []
    for index in range(case.get("message_count", 28)):
        role = "user" if index % 2 == 0 else "assistant"
        content = case["events"].get(index)
        if content is None:
            turn = index // 2 + 1
            if role == "user" and case.get("interludes"):
                content = f"第 {turn} 轮：{case['interludes'][(turn - 1) % len(case['interludes'])]}"
            else:
                content = (f"第 {turn} 轮：继续按已确认需求完善页面，本轮不增加或变更事实。"
                           if role == "user" else f"第 {turn} 轮：收到，继续按既定需求处理。")
        history.append({"role": role, "content": content})
    return history


def _normalize(value: str) -> str:
    return "".join(char.casefold() for char in value if char.isalnum())


def score_answer(answer: str, question: dict) -> bool:
    normalized = _normalize(answer)
    return bool(normalized) and any(
        _normalize(alias) in normalized for alias in question["aliases"]
    ) and not any(
        _normalize(stale) in normalized for stale in question.get("reject", ())
    )


def _memory_prompt(context: dict, questions: tuple[dict, ...]) -> str:
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
    question_text = "\n".join(f"{question['id']}: {question['prompt']}" for question in questions)
    parts.append(f"[当前请求] 根据以上记忆回答下列问题，每个答案尽量只写最短的值。\n{question_text}")
    return "\n".join(parts)


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def run(variant: str, run_id: str, case_set: str = "all") -> dict:
    import openai

    from config import config
    from memory.conversation_memory import ConversationMemory
    from request_context import bind_request_context, build_litellm_metadata

    memory = ConversationMemory(window_size=config.MEMORY_WINDOW_SIZE,
                                summary_trigger=config.MEMORY_SUMMARY_TRIGGER)
    redis_client = memory._get_redis()
    if redis_client is None or not redis_client.ping():
        raise RuntimeError("Redis memory backend unavailable; A/B result would be invalid")
    client = openai.OpenAI(api_key=config.LITELLM_API_KEY, base_url=config.LITELLM_BASE_URL)
    case_results = []

    for case in select_cases(case_set):
        thread_id = f"abfact-{run_id}-{variant}-{case['id']}"
        try:
            with bind_request_context(request_id=thread_id, trace_id="",
                                      user_id="ab-memory-eval", app_id=case["id"]):
                for message in build_history(case):
                    memory.add_message(thread_id, message["role"], message["content"])
                context = memory.get_context(thread_id)
                if not context["summary"] or len(context["recent_messages"]) != 10:
                    raise RuntimeError(f"memory compression incomplete: {case['id']}")
                prompt = _memory_prompt(context, case["questions"])
                response = client.chat.completions.create(
                    model=config.LLM_LIGHTWEIGHT_MODEL,
                    messages=[
                        {"role": "system", "content": "仅根据给定记忆回答。未知时回答‘未知’。只输出由问题 ID 到简短答案的 JSON 对象，不要解释。"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                    max_tokens=600,
                    extra_body={"metadata": build_litellm_metadata({"evaluation": "memory_fact_ab", "variant": variant})},
                )
                raw = response.choices[0].message.content or ""
                answers = _parse_json(raw)
                details = []
                for question in case["questions"]:
                    answer = str(answers.get(question["id"], ""))
                    details.append({"id": question["id"], "expected": question["expected"],
                                    "answer": answer, "correct": score_answer(answer, question)})
                case_results.append({"case_id": case["id"], "facts": details})
        finally:
            memory.clear(thread_id)

    total = sum(len(case["facts"]) for case in case_results)
    correct = sum(fact["correct"] for case in case_results for fact in case["facts"])
    return {"variant": variant, "run_id": run_id, "case_set": case_set,
            "memory_module": inspect.getfile(ConversationMemory),
            "model": config.LLM_LIGHTWEIGHT_MODEL,
            "metric": "key_fact_accuracy", "correct": correct, "total": total,
            "accuracy": correct / total, "cases": case_results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=("A", "B"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--case-set", choices=("baseline", "extended", "all"), default="all")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.variant, args.run_id, args.case_set)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"FACT_ACCURACY={result['correct']}/{result['total']}")


if __name__ == "__main__":
    main()
