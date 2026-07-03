"""
Model router with fallback and circuit breaker support.
"""
import time

from langchain_openai import ChatOpenAI

from config import config
from core.model_registry import MODEL_GROUPS, ModelCandidate, get_group
from monitoring import record_llm_call, update_circuit_breaker
from tracing import start_span

EMPTY_CANDIDATE_RETRY_COUNT = 3
EMPTY_CANDIDATE_RETRY_DELAY_SECONDS = 1.0


class ModelRouter:
    """Route model calls across candidates with fallback."""

    def route(
        self,
        group_name: str,
        messages: list,
        parser=None,
        allow_degraded: bool = True,
        langsmith_extra: dict = None,
    ):
        group = get_group(group_name)
        candidates = self._get_active_candidates_with_retry(group, group_name)

        if not candidates:
            if not allow_degraded:
                raise RuntimeError(f"{group_name}: no available candidates")

            candidates = self._build_probe_candidates(group)
            if not candidates:
                print(f"[Router] {group_name}: all candidates are open")
                return None

            probe_names = ", ".join(c.name for c in candidates)
            print(
                f"[Router] {group_name}: no active candidates after "
                f"{EMPTY_CANDIDATE_RETRY_COUNT} retries, probing {probe_names}"
            )

        with start_span(
            "llm.route",
            {
                "llm.group": group_name,
                "llm.candidate_count": len(candidates),
            },
        ):
            last_error = None
            for i, candidate in enumerate(candidates):
                cb = candidate.circuit_breaker
                cb_name = candidate.name

                attempt_extra = dict(langsmith_extra) if langsmith_extra else {}
                attempt_extra.setdefault("metadata", {})
                attempt_extra["metadata"].update(
                    {
                        "attempt": i + 1,
                        "fallback": i > 0,
                        "model_candidate": cb_name,
                    }
                )
                tags = list(attempt_extra.get("tags", []))
                if i > 0:
                    tags.append(f"fallback_attempt_{i+1}")
                attempt_extra["tags"] = tags

                print(f"[Router] {group_name}: trying [{i+1}/{len(candidates)}] {cb_name} ({candidate.model})")

                try:
                    with start_span(
                        "llm.attempt",
                        {
                            "llm.group": group_name,
                            "llm.model_candidate": cb_name,
                            "llm.model": candidate.model,
                            "llm.attempt": i + 1,
                            "llm.fallback": i > 0,
                        },
                    ):
                        result = self._call_llm(candidate, messages, parser, langsmith_extra=attempt_extra)
                    if result is not None:
                        if cb:
                            cb.record_success()
                        print(f"[Router] {group_name}: {cb_name} success")
                        record_llm_call(candidate.model, status="success")
                        return result
                except Exception as exc:
                    last_error = exc
                    if cb:
                        cb.record_failure()
                    print(f"[Router] {group_name}: {cb_name} failed -> {type(exc).__name__}: {str(exc)[:120]}")
                    record_llm_call(candidate.model, status="error")

            print(f"[Router] {group_name}: all {len(candidates)} candidates failed, last_error={last_error}")

            if allow_degraded:
                return None
            raise RuntimeError(f"{group_name}: all model calls failed") from last_error

    def _get_active_candidates_with_retry(self, group, group_name: str) -> list:
        """Wait briefly for circuit breakers to recover before giving up."""
        for attempt in range(1, EMPTY_CANDIDATE_RETRY_COUNT + 1):
            candidates = group.get_active()
            if candidates:
                if attempt > 1:
                    print(
                        f"[Router] {group_name}: candidates recovered on retry "
                        f"{attempt}/{EMPTY_CANDIDATE_RETRY_COUNT}"
                    )
                return candidates

            if attempt < EMPTY_CANDIDATE_RETRY_COUNT:
                print(
                    f"[Router] {group_name}: no active candidates, retrying "
                    f"{attempt}/{EMPTY_CANDIDATE_RETRY_COUNT}"
                )
                time.sleep(EMPTY_CANDIDATE_RETRY_DELAY_SECONDS)

        return []

    def _build_probe_candidates(self, group) -> list:
        """Prefer GLM candidates when probing after breaker recovery is pending."""
        candidates = list(group.candidates)
        glm_candidates = [candidate for candidate in candidates if self._is_glm_candidate(candidate)]
        if not glm_candidates:
            return candidates
        return glm_candidates + [candidate for candidate in candidates if candidate not in glm_candidates]

    @staticmethod
    def _is_glm_candidate(candidate: ModelCandidate) -> bool:
        candidate_text = f"{candidate.name} {candidate.model}".lower()
        return "glm" in candidate_text

    def _call_llm(self, candidate: ModelCandidate, messages: list, parser=None, langsmith_extra: dict = None) -> object:
        """Call the actual LLM provider."""
        with start_span(
            "llm.call",
            {
                "llm.model": candidate.model,
                "llm.model_candidate": candidate.name,
            },
        ):
            llm = ChatOpenAI(
                model=candidate.model,
                api_key=candidate.api_key,
                base_url=candidate.base_url,
                timeout=candidate.timeout,
                max_retries=0,
                temperature=0.0,
            )

            if parser:
                return parser(messages, _client=llm, _config=langsmith_extra)

            response = llm.invoke(messages, config=langsmith_extra)
            content = response.content or ""
            if not content:
                raise ValueError(f"{candidate.name}: empty LLM response")
            return content

    def get_status(self) -> dict:
        status = {}
        for group_name, group in MODEL_GROUPS.items():
            for candidate in group.candidates:
                cb = candidate.circuit_breaker
                status[candidate.name] = {
                    "state": cb.state if cb else "none",
                    "failures": cb.failure_count if cb else 0,
                }
        return status


model_router = ModelRouter()
