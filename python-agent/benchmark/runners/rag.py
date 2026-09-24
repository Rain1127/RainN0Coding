from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from benchmark.contracts import LoadedCase, RawRunRecord, normalize_metric_value
from benchmark.evaluators.metrics import retrieval_metrics

from .base import RunContext


RetrieveCallable = Callable[[dict[str, Any]], list[dict[str, Any]]]
_DOCUMENT_ID_FIELDS = ("api_name", "component_name", "pattern_name", "error_signature", "file_path")


def retrieve_with_engine(input_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Run the real engine only when a live/nightly case explicitly needs it.

    Imports live RAG dependencies lazily so PR replay cases never initialize
    embedding, vector-store, or LLM clients.
    """
    from rag.retrieval_common import RetrievalContext
    from rag.retrieval_engine import retrieval_engine

    context = RetrievalContext(
        phase=str(input_data.get("phase", "code")),
        user_request=str(input_data.get("user_request", "")),
        file_info=input_data.get("file_info"),
        architecture=input_data.get("architecture"),
        retry_count=input_data.get("retry_count", 0),
        code_gen_type=str(input_data.get("code_gen_type", "vue_project")),
        app_id=str(input_data.get("app_id", "")),
    )
    return [
        {
            "content": result.content,
            "source_collection": result.source_collection,
            "source_channel": result.source_channel,
            "score": result.score,
            "metadata": dict(result.metadata),
        }
        for result in retrieval_engine.retrieve_results(context)
    ]


class RagRunner:
    def __init__(self, retrieve: RetrieveCallable | None = None):
        self._injected_retriever = retrieve is not None
        self._retrieve = retrieve or retrieve_with_engine

    def run(self, case: LoadedCase, context: RunContext) -> list[RawRunRecord]:
        context.assert_mode_allowed(case.case.execution.mode)
        case_id = case.case.id
        if case.case.execution.mode != "rag":
            raise ValueError(f"{case_id}: rag runner requires rag mode")
        if case.case.target != "rag":
            raise ValueError(f"{case_id}: rag runner requires rag target")

        input_data = dict(case.case.input)
        if input_data.get("ragas") and context.offline:
            raise ValueError(f"{case_id}: RAGAS is not allowed in an offline suite")
        relevant_document_ids = case.case.expectations.relevant_document_ids
        if not relevant_document_ids:
            raise ValueError(f"{case_id}: relevant document labels are required")
        if context.offline and case.record_path is None and not self._injected_retriever:
            raise ValueError(f"{case_id}: offline RAG requires a replay record or an injected retriever")

        records: list[RawRunRecord] = []
        for attempt_index in range(case.case.execution.repeats):
            started_at = datetime.now(timezone.utc).isoformat()
            started = perf_counter()
            results = self._replay_results(case) if case.record_path is not None else self._retrieve(input_data)
            document_ids, contexts = self._document_ids_and_contexts(case_id, results)
            k = input_data.get("k") or len(document_ids) or 1
            observed_metrics = retrieval_metrics(document_ids, relevant_document_ids, k)
            if input_data.get("ragas"):
                observed_metrics.update(self._ragas_metrics(case_id, context.run_id, input_data, contexts))
            observed_metrics["retrieval_latency_ms"] = (perf_counter() - started) * 1000
            output = {"retrieved_document_ids": list(document_ids), "retrieved_count": len(document_ids)}
            records.append(
                RawRunRecord(
                    case_id=case_id,
                    attempt_index=attempt_index,
                    output=output,
                    observed_metrics=observed_metrics,
                    started_at=started_at,
                    duration_ms=(perf_counter() - started) * 1000,
                )
            )
        return records

    @staticmethod
    def _replay_results(case: LoadedCase) -> list[dict[str, Any]]:
        case_id = case.case.id
        try:
            raw: Any = json.loads(case.record_path.read_text(encoding="utf-8"))  # type: ignore[union-attr]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{case_id}: invalid RAG replay record") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"{case_id}: invalid RAG replay record")
        results = raw.get(case_id)
        if not isinstance(results, list):
            raise ValueError(f"{case_id}: replay record is missing results")
        return results

    @staticmethod
    def _document_ids_and_contexts(case_id: str, results: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
        if not isinstance(results, list):
            raise ValueError(f"{case_id}: retrieval results must be a list")
        document_ids: list[str] = []
        contexts: list[str] = []
        for result in results:
            if not isinstance(result, Mapping):
                raise ValueError(f"{case_id}: retrieval result must be an object")
            metadata = result.get("metadata", {})
            source_collection = result.get("source_collection")
            content = result.get("content")
            if not isinstance(metadata, Mapping) or not isinstance(source_collection, str) or not source_collection.strip():
                raise ValueError(f"{case_id}: retrieval result is missing source_collection or metadata")
            if not isinstance(content, str):
                raise ValueError(f"{case_id}: retrieval result content must be text")
            document_id = metadata.get("document_id")
            if not isinstance(document_id, str) or not document_id.strip():
                document_id = next(
                    (
                        f"{source_collection}:{metadata[field]}"
                        for field in _DOCUMENT_ID_FIELDS
                        if isinstance(metadata.get(field), str) and metadata[field].strip()
                    ),
                    None,
                )
            if not document_id:
                raise ValueError(f"{case_id}: retrieval result has no stable document id")
            document_ids.append(document_id)
            contexts.append(content)
        return document_ids, contexts

    @staticmethod
    def _ragas_metrics(case_id: str, run_id: str, input_data: dict[str, Any], contexts: list[str]) -> dict[str, float]:
        ragas_input = input_data.get("ragas")
        if ragas_input is True:
            ragas_input = {}
        if not isinstance(ragas_input, Mapping):
            raise ValueError(f"{case_id}: ragas must be an object or true")
        question = ragas_input.get("question", input_data.get("user_request", ""))
        answer = ragas_input.get("answer", input_data.get("answer", ""))
        ground_truth = ragas_input.get("ground_truth", input_data.get("ground_truth", ""))
        if not all(isinstance(value, str) and value.strip() for value in (question, answer, ground_truth)) or not contexts:
            raise ValueError(f"{case_id}: ragas requires nonblank question, answer, contexts, and ground_truth")

        from rag.ragas_evaluator import evaluate_offline
        from request_context import bind_request_context

        evaluation_id = f"benchmark-{run_id}-{case_id}-ragas"
        request_context = {
            "request_id": evaluation_id,
            "trace_id": evaluation_id,
            "user_id": "benchmark",
            "app_id": "benchmark-rag",
        }
        with bind_request_context(**request_context):
            rows = evaluate_offline([
                {"question": question, "answer": answer, "contexts": contexts, "ground_truth": ground_truth}
            ])
        if not isinstance(rows, list) or not rows:
            raise RuntimeError(f"{case_id}: RAGAS returned no rows")
        metrics: dict[str, float] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            for name, value in row.items():
                if not isinstance(name, str) or not name.strip():
                    continue
                try:
                    normalized = normalize_metric_value(value)
                except ValueError:
                    continue
                if normalized is not None:
                    metrics[name] = normalized
        return metrics
