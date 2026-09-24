from __future__ import annotations
import math
import statistics


def retrieval_metrics(
    retrieved_document_ids: list[str], relevant_document_ids: list[str], *, k: int
) -> dict[str, float]:
    """Calculate deterministic binary-relevance retrieval metrics at ``k``.

    Precision keeps the requested cutoff as its denominator, while repeated
    retrieved identifiers only receive credit once.  This mirrors standard IR
    evaluation and keeps recall bounded by one.
    """
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k must be at least 1")
    if any(not isinstance(document_id, str) or not document_id.strip() for document_id in retrieved_document_ids):
        raise ValueError("retrieved document ids must be nonblank strings")
    if not relevant_document_ids or any(
        not isinstance(document_id, str) or not document_id.strip()
        for document_id in relevant_document_ids
    ):
        raise ValueError("relevant document labels must be nonempty, nonblank strings")

    relevant = set(relevant_document_ids)
    seen: set[str] = set()
    credited: list[bool] = []
    for document_id in retrieved_document_ids[:k]:
        is_new_relevant = document_id in relevant and document_id not in seen
        credited.append(is_new_relevant)
        seen.add(document_id)

    hits = sum(credited)
    precision = hits / k
    recall = min(hits / len(relevant), 1.0)
    first_relevant_rank = next((index + 1 for index, hit in enumerate(credited) if hit), None)
    mrr = 0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank
    dcg = sum(1.0 / math.log2(index + 2) for index, hit in enumerate(credited) if hit)
    ideal_hits = min(len(relevant), k)
    ideal_dcg = sum(1.0 / math.log2(index + 2) for index in range(ideal_hits))
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0
    return {
        "precision_at_k": float(precision),
        "recall_at_k": float(recall),
        "mrr": float(mrr),
        "ndcg_at_k": float(ndcg),
    }

def describe(values: list[float]) -> dict[str, float | int]:
    if not values:
        raise ValueError("describe requires at least one value")
    ordered = sorted(values)
    n = len(ordered)
    return {"observations": n, "sum": float(sum(ordered)), "mean": float(statistics.mean(ordered)), "min": float(ordered[0]), "max": float(ordered[-1]), "p50": float(ordered[(n - 1) // 2]), "p95": float(ordered[math.ceil(n * 0.95) - 1]), "stdev": float(statistics.pstdev(ordered)) if n > 1 else 0.0}
