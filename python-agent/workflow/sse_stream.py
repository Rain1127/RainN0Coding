"""
SSE 流式包装 —— 真正节点级流式输出

使用 LangGraph astream() 实现：每个 Agent 节点完成时立即推送 SSE 事件。
前端可看到 PM → Architect → Coder → Reviewer → Builder 的实时进度。

事件格式：
  {"type":"phase_start","phase":"pm","message":"产品经理正在分析需求..."}
  {"type":"phase_complete","phase":"pm","output":{...}}
  {"type":"code_file","path":"...","content":"..."}
  {"type":"review_issue","file":"...","severity":"warn","description":"..."}
  {"type":"done","status":"success","result":{...}}

重试可见性：
  审查不通过时发送 code_retry 阶段事件，携带 retry_count。
"""
import json
import time
from typing import AsyncGenerator
from workflow.code_gen_workflow import run_workflow_async
from memory.conversation_memory import conversation_memory
from monitoring import record_phase_duration, record_retries, record_files_generated
import sys
print("[SSE_STREAM_v2] Module loaded with _event-based metrics recording", file=sys.stderr, flush=True)


async def stream_workflow(user_request: str, user_id: str = "",
                           app_id: str = "",
                           code_gen_type: str = "vue_project",
                           user_role: str = "user",
                           trace_id: str = "") -> AsyncGenerator[str, None]:
    """异步生成器 —— 消费 astream() 快照，逐节点 yield SSE 事件。"""

    # 阶段耗时与重试计数（在 _event 闭包中跟踪，确保指标一定能被记录）
    _phase_timers: dict[str, float] = {}
    _code_gen_type = code_gen_type

    def _event(event_type: str, **kwargs) -> str:
        nonlocal _phase_timers
        now = time.time()
        payload = {"type": event_type, "timestamp": now, "trace_id": trace_id}
        payload.update(kwargs)

        # ---- Prometheus 指标自动记录 ----
        phase_name = kwargs.get("phase", "")
        if event_type == "phase_start" and phase_name:
            _phase_timers[phase_name] = now
        elif event_type == "phase_complete" and phase_name:
            start = _phase_timers.pop(phase_name, None)
            if start is not None:
                record_phase_duration(phase_name, _code_gen_type, now - start)
        elif event_type == "trace_summary":
            trace_data = kwargs.get("trace", {})
            retry_c = trace_data.get("retry_count", 0)
            file_c = trace_data.get("file_count", 0)
            record_retries(_code_gen_type, retry_c)
            record_files_generated(_code_gen_type, file_c)

        return json.dumps(payload, ensure_ascii=False)

    # ===== 加载会话记忆 =====
    thread_id = f"{user_id}_{app_id}"
    memory_ctx = conversation_memory.get_context(thread_id)
    summary = memory_ctx.get("summary", "")
    recent = memory_ctx.get("recent_messages", [])

    # 将历史上下文注入用户请求
    enriched_request = user_request
    if summary or recent:
        parts = []
        if summary:
            parts.append(f"[对话摘要] {summary}")
        if recent:
            parts.append("[最近对话]")
            for m in recent[-6:]:  # 最多取最近 6 条
                role_label = "用户" if m["role"] == "user" else "AI"
                parts.append(f"{role_label}: {m['content'][:300]}")
        parts.append(f"[当前请求] {user_request}")
        enriched_request = "\n".join(parts)

    yield _event("workflow_start", message=f"开始处理需求: {user_request[:50]}")
    if summary:
        yield _event("memory_loaded", summary=summary[:200],
                     recent_count=len(recent))

    # 跟踪已处理阶段，避免重试回路中重复发送 phase_start

    seen_phases: set[str] = set()
    prev_retry_count = 0
    assistant_response_parts: list[str] = []
    # 阶段耗时追踪
    phase_start_times: dict[str, float] = {}

    try:
        # ===== 发送初始 phase_start =====
        phase_start_times["intent"] = time.time()
        yield _event("phase_start", phase="intent", message="正在理解你的需求...")
        seen_phases.add("intent_done")

        async for state in run_workflow_async(enriched_request, user_id, app_id, code_gen_type, user_role, trace_id):
            phase = state.get("phase", "")
            error = state.get("error")

            if error:
                yield _event("error", message=str(error))
                yield _event("done", status="error")
                return

            retry_count = state.get("retry_count", 0)

            # ---- Mode 检测完成 ----
            if phase == "mode_detected" and "mode_detected" not in seen_phases:
                seen_phases.add("mode_detected")
                mode = state.get("mode", "new")
                mode_messages = {
                    "new": "正在启动全新代码生成...",
                    "modify": "检测到已有代码，正在基于现有代码进行增量修改...",
                    "rebuild": "正在重新构建项目...",
                }
                yield _event("mode_detected", mode=mode,
                             message=mode_messages.get(mode, ""))

            # ---- Intent 完成 ----
            if phase == "intent_done" and "intent_done" not in seen_phases:
                seen_phases.add("intent_done")
                intent = state.get("intent") or {}
                clarification = state.get("clarification")
                mode = state.get("mode", "new")
                yield _event("phase_complete", phase="intent", output={
                    "primary_intent": intent.get("primary_intent", ""),
                    "confidence": intent.get("confidence", 0),
                    "should_clarify": intent.get("should_clarify", False),
                    "note": clarification.get("note") if clarification else None,
                })
                pass  # metrics recorded by _event() closure
                # 根据 mode 决定下一个阶段
                if mode == "modify":
                    phase_start_times["code"] = time.time()
                    yield _event("phase_start", phase="code",
                                 message="程序员正在基于现有代码进行增量修改...")
                    seen_phases.add("code_done")
                else:
                    phase_start_times["pm"] = time.time()
                    yield _event("phase_start", phase="pm",
                                 message="产品经理正在分析需求...")
                    seen_phases.add("prd_done")

            # ---- Clarify（低置信度）----
            if phase == "clarify" and "clarify" not in seen_phases:
                seen_phases.add("clarify")
                clarification = state.get("clarification") or {}
                yield _event("clarify", questions=clarification.get("questions", []),
                             missing_slots=clarification.get("missing_slots", []))
                yield _event("done", status="clarify_needed")
                return

            # ---- PM 完成 ----
            if phase == "prd_done" and "prd_done" not in seen_phases:
                seen_phases.add("prd_done")
                prd = state.get("prd") or {}
                yield _event("phase_complete", phase="pm", output={
                    "page_name": prd.get("page_name", ""),
                    "page_type": prd.get("page_type", ""),
                    "feature_count": len(prd.get("features", [])),
                })
                phase_start_times["arch"] = time.time()
                yield _event("phase_start", phase="arch",
                             message="架构师正在设计代码结构...")

            # ---- Architect 完成 ----
            if phase == "arch_done" and "arch_done" not in seen_phases:
                seen_phases.add("arch_done")
                arch = state.get("architecture") or {}
                yield _event("phase_complete", phase="arch", output={
                    "component_count": len(arch.get("component_tree", [])),
                    "file_count": len(arch.get("file_list", [])),
                })
                phase_start_times["code"] = time.time()
                yield _event("phase_start", phase="code",
                             message="程序员正在编写代码...")

            # ---- Coder 完成（含重试）----
            if phase == "code_done":
                # 判断是否为重试
                is_retry = retry_count > prev_retry_count
                if is_retry:
                    prev_retry_count = retry_count
                    phase_start_times["code_retry"] = time.time()
                    yield _event("phase_start", phase="code_retry",
                                 retry=retry_count,
                                 message=f"正在修复审查发现的问题（第 {retry_count} 次重试）...")

                # 逐文件发送代码
                code_files = state.get("code_files", [])
                for f in code_files:
                    yield _event("code_file",
                                 path=f.get("path", ""),
                                 content=f.get("content", ""))

                yield _event("phase_complete", phase="code_retry" if is_retry else "code",
                             output={
                                 "file_count": len(code_files),
                                 "total_lines": sum(
                                     len(f.get("content", "").split("\n"))
                                     for f in code_files
                                 ),
                             })
                pass  # metrics recorded by _event() closure

                if not is_retry:
                    phase_start_times["review"] = time.time()
                    yield _event("phase_start", phase="review",
                                 message="代码审查中...")

            # ---- Reviewer 完成 ----
            if phase == "review_done":
                review = state.get("review") or {}
                passed = review.get("passed", False)
                issues = review.get("issues", [])

                yield _event("phase_complete", phase="review", output={
                    "score": review.get("score"),
                    "passed": passed,
                    "issue_count": len(issues),
                    "retry_count": retry_count,
                })

                for iss in issues[:10]:
                    yield _event("review_issue",
                                 file=iss.get("file", ""),
                                 severity=iss.get("severity", "info"),
                                 description=iss.get("description", ""))

                if not passed and retry_count < state.get("max_retries", 3):
                    # 即将进入重试 → 标记 Coder 开始
                    phase_start_times["code"] = time.time()
                    phase_start_times["code_retry"] = time.time()
                else:
                    # 审查通过 → Builder 开始
                    phase_start_times["build"] = time.time()

            # ---- Builder 完成 ----
            if phase == "build_done":
                build = state.get("build_result") or {}
                yield _event("phase_complete", phase="build", output={
                    "success": build.get("success"),
                })

            # ---- 完成 ----
            if phase == "completed" or phase == "error":
                final = state.get("final_result") or {}
                review = state.get("review") or {}
                status = "success"
                if phase == "error":
                    status = "error"
                elif not review.get("passed"):
                    status = "retry_limit"

                # ===== 发送 trace 摘要 =====
                code_files = state.get("code_files", [])
                yield _event("trace_summary", trace={
                    "thread_id": thread_id,
                    "phases": sorted(seen_phases),
                    "file_count": len(code_files),
                    "retry_count": retry_count,
                    "review_score": review.get("score"),
                    "intent": (state.get("intent") or {}).get("primary_intent", ""),
                })

                # ===== 保存会话记忆 =====
                try:
                    conversation_memory.add_message(thread_id, "user", user_request)
                    code_files = state.get("code_files", [])
                    if code_files:
                        file_list = ", ".join(f.get("path", "") for f in code_files[:5])
                        resp = f"[{len(code_files)}个文件] {file_list}"
                    else:
                        resp = final.get("phase", "completed")
                    conversation_memory.add_message(thread_id, "assistant", resp)
                except Exception as ex:
                    print(f"[Memory] 保存失败: {ex}")

                yield _event("done", status=status, result=final)

    except Exception as e:
        # 保存失败时的记忆
        try:
            conversation_memory.add_message(thread_id, "user", user_request)
            conversation_memory.add_message(thread_id, "assistant", f"[错误] {str(e)[:200]}")
        except Exception:
            pass
        yield _event("error", message=str(e))
        yield _event("done", status="error")
