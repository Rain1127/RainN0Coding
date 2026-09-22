from __future__ import annotations
import math
import statistics

def describe(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    n = len(ordered)
    return {"observations": n, "sum": float(sum(ordered)), "mean": float(statistics.mean(ordered)), "min": float(ordered[0]), "max": float(ordered[-1]), "p50": float(ordered[(n - 1) // 2]), "p95": float(ordered[math.ceil(n * 0.95) - 1]), "stdev": float(statistics.pstdev(ordered)) if n > 1 else 0.0}
