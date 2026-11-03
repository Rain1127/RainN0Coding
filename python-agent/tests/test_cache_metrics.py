import monitoring


def _sample_value(metric, suffix, labels):
    for sample in metric.collect()[0].samples:
        if sample.name.endswith(suffix) and all(sample.labels.get(k) == v for k, v in labels.items()):
            return sample.value
    return 0


def test_prompt_cache_tokens_keep_hit_miss_and_creation_distinct():
    recorder = getattr(monitoring, "record_prompt_cache_tokens", None)
    assert callable(recorder)
    before = _sample_value(monitoring.ai_prompt_cache_tokens_total, "_total", {
        "phase": "coder", "request_model": "code-reasoning",
        "actual_model": "glm", "kind": "hit",
    })
    recorder({"model": "code-reasoning", "actual_model": "glm", "input_tokens": 100,
              "cache_hit_tokens": 20, "cache_miss_tokens": 30,
              "cache_creation_tokens": 0}, phase="coder")
    after = _sample_value(monitoring.ai_prompt_cache_tokens_total, "_total", {
        "phase": "coder", "request_model": "code-reasoning",
        "actual_model": "glm", "kind": "hit",
    })
    assert after - before == 20


def test_rag_metric_has_phase_channel_and_bypass():
    before = _sample_value(monitoring.ai_rag_cache_hit_total, "_total", {
        "phase": "code", "channel": "semantic", "status": "bypass",
    })
    monitoring.record_rag_cache_hit("bypass", phase="code", channel="semantic")
    after = _sample_value(monitoring.ai_rag_cache_hit_total, "_total", {
        "phase": "code", "channel": "semantic", "status": "bypass",
    })
    assert after - before == 1


def test_memory_summary_phase_scope_restores_prior_agent():
    scope = getattr(monitoring, "phase_scope", None)
    assert callable(scope)
    original = monitoring.get_current_phase()
    with scope("memory_summary"):
        assert monitoring.get_current_phase() == "memory_summary"
    assert monitoring.get_current_phase() == original
