# Agent Golden Trajectory Evaluation

This package scores Agent outputs against frozen, versioned constraints without using an LLM as a judge. A Golden case defines an input state and assertions over the resulting state or routing decision; it does not prescribe the Agent's prose or source code verbatim.

## Run deterministic Supervisor cases

From `python-agent`:

```powershell
$env:PYTHONPATH='.'
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m agent_eval.runner --dataset agent_eval/golden/dev --agent supervisor --output agent-eval-supervisor-report.json
```

The Supervisor is executed against the production `supervisor_decision` function. Its report contains total pass rate, assertion pass rate, categories, and one traceable result per case. `metric_ledger` records every assertion with its named metric, checks, passes, failures, and rate; it also groups the same figures by Agent and category.

## Evaluate LLM-backed Agents offline

Persist a recorded output keyed by Golden case ID after a controlled generation run, then evaluate it locally:

```json
{
  "intent-fallback-vue": {
    "output": {
      "phase": "intent_done",
      "error": null,
      "intent": {"primary_intent": "code generation", "slots": {"code_gen_type": "vue_project"}},
      "clarification": {"questions": []}
    },
    "metrics": {"latency_ms": 820.0, "input_tokens": 340, "output_tokens": 102, "retry_count": 0}
  },
  "reviewer-detects-xss": {
    "output": {
      "passed": false,
      "score": 40,
      "issues": [{"description": "XSS caused by v-html"}]
    },
    "metrics": {"latency_ms": 760.0, "input_tokens": 510, "output_tokens": 88, "retry_count": 1}
  }
}
```

```powershell
& 'D:\yu-ai-code-mother\python-agent\.venv\Scripts\python.exe' -m agent_eval.runner --dataset agent_eval/golden/dev --records saved-agent-outputs.json --output agent-eval-report.json
```

`equals` checks exact scalar fields, `required_paths` checks output protocol completeness, `required_text` accepts any one matching phrase, and `forbidden_text` rejects unsafe output. Each expectation can be named with `metric_tags`, while `output_metrics` extracts numerical output fields such as `review_score`. The saved-record `metrics` object retains operational indicators such as latency, token use, retries, retrieval counts, and build duration; the report calculates count, sum, mean, min, max, P50, and P95 for each. Add new frozen cases under `golden/test` only after validation; use `golden/dev` for iterative prompt and workflow changes.
