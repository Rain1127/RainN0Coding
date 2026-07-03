"""
SSE stream wrapper for the LangGraph workflow.
"""
import json
import sys
import time
from typing import AsyncGenerator

from guardrails.audit import audit_from_decision
from guardrails.engine import evaluate_output_event
from guardrails.models import OutputEvent
from memory.conversation_memory import conversation_memory
from monitoring import record_files_generated, record_phase_duration, record_retries
from tracing import start_span
from workflow.code_gen_workflow import run_workflow_async

print("[SSE_STREAM_v2] Module loaded with _event-based metrics recording", file=sys.stderr, flush=True)


async def stream_workflow(
    user_request: str,
    user_id: str = "",
    app_id: str = "",
    code_gen_type: str = "vue_project",
    user_role: str = "user",
    trace_id: str = "",
    request_id: str = "",
) -> AsyncGenerator[str, None]:
    """Yield SSE events from the async workflow."""

    with start_span(
        "workflow.stream",
        {
            "app.user_id": user_id,
            "app.app_id": app_id,
            "app.code_gen_type": code_gen_type,
            "app.user_role": user_role,
            "app.trace_id": trace_id,
            "app.request_id": request_id,
        },
    ):
        phase_timers: dict[str, float] = {}
        seen_phases: set[str] = set()
        prev_retry_count = 0
        code_gen_type_value = code_gen_type

        def _event(event_type: str, **kwargs) -> str:
            now = time.time()
            payload = {"type": event_type, "timestamp": now, "trace_id": trace_id, "request_id": request_id}
            payload.update(kwargs)

            phase_name = kwargs.get("phase", "")
            if event_type == "phase_start" and phase_name:
                phase_timers[phase_name] = now
            elif event_type == "phase_complete" and phase_name:
                started_at = phase_timers.pop(phase_name, None)
                if started_at is not None:
                    record_phase_duration(phase_name, code_gen_type_value, now - started_at)
            elif event_type == "trace_summary":
                trace_data = kwargs.get("trace", {})
                record_retries(code_gen_type_value, trace_data.get("retry_count", 0))
                record_files_generated(code_gen_type_value, trace_data.get("file_count", 0))

            return json.dumps(payload, ensure_ascii=False)

        thread_id = f"{user_id}_{app_id}"
        memory_ctx = conversation_memory.get_context(thread_id)
        summary = memory_ctx.get("summary", "")
        recent = memory_ctx.get("recent_messages", [])

        enriched_request = user_request
        if summary or recent:
            parts = []
            if summary:
                parts.append(f"[瀵硅瘽鎽樿] {summary}")
            if recent:
                parts.append("[鏈€杩戝璇漖")
                for message in recent[-6:]:
                    role_label = "鐢ㄦ埛" if message["role"] == "user" else "AI"
                    parts.append(f"{role_label}: {message['content'][:300]}")
            parts.append(f"[褰撳墠璇锋眰] {user_request}")
            enriched_request = "\n".join(parts)

        yield _event("workflow_start", message=f"寮€濮嬪鐞嗛渶姹? {user_request[:50]}")
        if summary:
            yield _event("memory_loaded", summary=summary[:200], recent_count=len(recent))

        phase_start_times: dict[str, float] = {}

        try:
            phase_start_times["intent"] = time.time()
            yield _event("phase_start", phase="intent", message="姝ｅ湪鐞嗚В浣犵殑闇€姹?..")
            seen_phases.add("intent_done")

            async for state in run_workflow_async(
                enriched_request,
                user_id,
                app_id,
                code_gen_type,
                user_role,
                trace_id,
            ):
                phase = state.get("phase", "")
                error = state.get("error")
                retry_count = state.get("retry_count", 0)

                if error:
                    yield _event("error", message=str(error))
                    yield _event("done", status="error")
                    return

                if phase == "mode_detected" and "mode_detected" not in seen_phases:
                    seen_phases.add("mode_detected")
                    mode = state.get("mode", "new")
                    mode_messages = {
                        "new": "姝ｅ湪鍚姩鍏ㄦ柊浠ｇ爜鐢熸垚...",
                        "modify": "妫€娴嬪埌宸叉湁浠ｇ爜锛屾鍦ㄥ熀浜庣幇鏈変唬鐮佽繘琛屽閲忎慨鏀?...",
                        "rebuild": "姝ｅ湪閲嶆柊鏋勫缓椤圭洰...",
                    }
                    yield _event("mode_detected", mode=mode, message=mode_messages.get(mode, ""))

                if phase == "intent_done" and "intent_done" not in seen_phases:
                    seen_phases.add("intent_done")
                    intent = state.get("intent") or {}
                    clarification = state.get("clarification")
                    mode = state.get("mode", "new")
                    yield _event(
                        "phase_complete",
                        phase="intent",
                        output={
                            "primary_intent": intent.get("primary_intent", ""),
                            "confidence": intent.get("confidence", 0),
                            "should_clarify": intent.get("should_clarify", False),
                            "note": clarification.get("note") if clarification else None,
                        },
                    )
                    if mode == "modify":
                        phase_start_times["code"] = time.time()
                        yield _event(
                            "phase_start",
                            phase="code",
                            message="绋嬪簭鍛樻鍦ㄥ熀浜庣幇鏈変唬鐮佽繘琛屽閲忎慨鏀?...",
                        )
                        seen_phases.add("code_done")
                    else:
                        phase_start_times["pm"] = time.time()
                        yield _event(
                            "phase_start",
                            phase="pm",
                            message="浜у搧缁忕悊姝ｅ湪鍒嗘瀽闇€姹?...",
                        )
                        seen_phases.add("prd_done")

                if phase == "clarify" and "clarify" not in seen_phases:
                    seen_phases.add("clarify")
                    clarification = state.get("clarification") or {}
                    yield _event(
                        "clarify",
                        questions=clarification.get("questions", []),
                        missing_slots=clarification.get("missing_slots", []),
                    )
                    yield _event("done", status="clarify_needed")
                    return

                if phase == "prd_done" and "prd_done" not in seen_phases:
                    seen_phases.add("prd_done")
                    prd = state.get("prd") or {}
                    yield _event(
                        "phase_complete",
                        phase="pm",
                        output={
                            "page_name": prd.get("page_name", ""),
                            "page_type": prd.get("page_type", ""),
                            "feature_count": len(prd.get("features", [])),
                        },
                    )
                    phase_start_times["arch"] = time.time()
                    yield _event("phase_start", phase="arch", message="鏋舵瀯甯堟鍦ㄨ璁′唬鐮佺粨鏋?...")

                if phase == "arch_done" and "arch_done" not in seen_phases:
                    seen_phases.add("arch_done")
                    arch = state.get("architecture") or {}
                    yield _event(
                        "phase_complete",
                        phase="arch",
                        output={
                            "component_count": len(arch.get("component_tree", [])),
                            "file_count": len(arch.get("file_list", [])),
                        },
                    )
                    phase_start_times["code"] = time.time()
                    yield _event("phase_start", phase="code", message="绋嬪簭鍛樻鍦ㄧ紪鍐欎唬鐮?...")

                if phase == "code_done":
                    is_retry = retry_count > prev_retry_count
                    if is_retry:
                        prev_retry_count = retry_count
                        phase_start_times["code_retry"] = time.time()
                        yield _event(
                            "phase_start",
                            phase="code_retry",
                            retry=retry_count,
                            message=f"姝ｅ湪淇瀹℃煡鍙戠幇鐨勯棶棰橈紙绗�{retry_count} 娆￠噸璇曪級...",
                        )

                    code_files = state.get("code_files", [])
                    for file_info in code_files:
                        decision = evaluate_output_event(
                            OutputEvent(
                                event_type="code_file",
                                path=file_info.get("path", ""),
                                content=file_info.get("content", ""),
                                request_id=request_id,
                                trace_id=trace_id,
                            )
                        )
                        audit_from_decision(
                            decision,
                            request_id=request_id,
                            trace_id=trace_id,
                            user_id=user_id,
                            app_id=app_id,
                            path=file_info.get("path", ""),
                        )
                        if decision.action == "block":
                            yield _event(
                                "error",
                                status="guardrail_blocked",
                                rule_id=decision.rule_id,
                                message=decision.message,
                            )
                            yield _event("done", status="guardrail_blocked")
                            return
                        yield _event(
                            "code_file",
                            path=file_info.get("path", ""),
                            content=file_info.get("content", ""),
                        )

                    yield _event(
                        "phase_complete",
                        phase="code_retry" if is_retry else "code",
                        output={
                            "file_count": len(code_files),
                            "total_lines": sum(len(f.get("content", "").split("\n")) for f in code_files),
                        },
                    )

                    if not is_retry:
                        phase_start_times["review"] = time.time()
                        yield _event("phase_start", phase="review", message="浠ｇ爜瀹℃煡涓?...")

                if phase == "review_done":
                    review = state.get("review") or {}
                    passed = review.get("passed", False)
                    issues = review.get("issues", [])

                    yield _event(
                        "phase_complete",
                        phase="review",
                        output={
                            "score": review.get("score"),
                            "passed": passed,
                            "issue_count": len(issues),
                            "retry_count": retry_count,
                        },
                    )

                    for issue in issues[:10]:
                        yield _event(
                            "review_issue",
                            file=issue.get("file", ""),
                            severity=issue.get("severity", "info"),
                            description=issue.get("description", ""),
                        )

                    if not passed and retry_count < state.get("max_retries", 3):
                        phase_start_times["code"] = time.time()
                        phase_start_times["code_retry"] = time.time()
                    else:
                        phase_start_times["build"] = time.time()

                if phase == "build_done":
                    build = state.get("build_result") or {}
                    yield _event("phase_complete", phase="build", output={"success": build.get("success")})

                if phase == "completed" or phase == "error":
                    final = state.get("final_result") or {}
                    review = state.get("review") or {}
                    final_status = final.get("status") or "success"

                    code_files = state.get("code_files", [])
                    yield _event(
                        "trace_summary",
                        trace={
                            "thread_id": thread_id,
                            "phases": sorted(seen_phases),
                            "file_count": len(code_files),
                            "retry_count": retry_count,
                            "review_score": review.get("score"),
                            "intent": (state.get("intent") or {}).get("primary_intent", ""),
                        },
                    )

                    try:
                        conversation_memory.add_message(thread_id, "user", user_request)
                        if code_files:
                            file_list = ", ".join(f.get("path", "") for f in code_files[:5])
                            resp = f"[{len(code_files)}涓枃浠�] {file_list}"
                        else:
                            resp = final.get("phase", "completed")
                        conversation_memory.add_message(thread_id, "assistant", resp)
                    except Exception as ex:
                        print(f"[Memory] save failed: {ex}")

                    if final.get("degraded"):
                        for reason in final.get("degraded_reasons", []):
                            yield _event(
                                "warning",
                                status="degraded",
                                phase=final.get("failed_phase") or state.get("phase"),
                                reason=reason,
                                message=final.get("recovery_hint") or "Workflow completed with a degraded path.",
                            )

                    yield _event(
                        "done",
                        status=final_status,
                        failed_phase=final.get("failed_phase"),
                        degraded=final.get("degraded", False),
                        degraded_reasons=final.get("degraded_reasons", []),
                        partial_code_available=final.get("partial_code_available", False),
                        recovery_hint=final.get("recovery_hint"),
                        result=final,
                    )
                    return

        except Exception as exc:
            try:
                conversation_memory.add_message(thread_id, "user", user_request)
                conversation_memory.add_message(thread_id, "assistant", f"[閿欒] {str(exc)[:200]}")
            except Exception:
                pass
            yield _event("error", message=str(exc))
            yield _event("done", status="error")
