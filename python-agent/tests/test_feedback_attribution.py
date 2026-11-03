from pathlib import Path
import pytest

from rag.feedback_tracker import FeedbackTracker, attribution_scope


@pytest.fixture
def tracker(tmp_path, monkeypatch):
    import rag.feedback_tracker as module
    monkeypatch.setattr(module.config, "CODE_STORE_DIR", str(tmp_path))
    store=FeedbackTracker()
    store.init_tables()
    source=tmp_path / "source" / "helper.py"
    source.parent.mkdir()
    source.write_text("# verified reusable implementation\n" + "print('reuse evidence')\n" * 5)
    yield store, source.read_text()
    store.close()


def test_run_scoped_evidence_is_idempotent_and_unrelated_results_are_neutral(tracker):
    store, snippet=tracker
    store.record_ingestion("source", "helper.py", 70)
    with attribution_scope("run1", "main.py"):
        store.record_to_session("app", "source", "helper.py")
    with attribution_scope("run2", "other.py"):
        store.record_to_session("app", "source", "helper.py")
    kwargs=dict(run_id="run1", validation={"status":"succeeded"},
                code_files=[{"path":"main.py","content":snippet}],changed_files={"main.py"})
    store.apply_feedback("app", True, **kwargs)
    score=store.get_quality_score("source","helper.py")
    assert score > 70
    store.apply_feedback("app", True, **kwargs)
    assert store.get_quality_score("source","helper.py")==score
    store.apply_feedback("app", False, run_id="run2",validation={"status":"unverified"})
    assert store.get_quality_score("source","helper.py")==score
    row=store._conn.execute("SELECT outcome,evidence FROM rag_attribution WHERE run_id='run1'").fetchone()
    assert row[0]=="positive" and "verified_exact_reuse" in row[1]


def test_legacy_feedback_without_evidence_is_neutral(tracker):
    store,_=tracker
    store.record_ingestion("source","helper.py",70)
    store.record_to_session("app","source","helper.py")
    store.apply_feedback("app",False)
    assert store.get_quality_score("source","helper.py")==70


def test_verified_experience_is_private_idempotent_and_language_scoped(tracker):
    store,_=tracker
    common=dict(run_id="repair1",environment={"language":"python","python":"3.12"},
                symptom="SyntaxError unexpected token",repair="-if True\n+if True:\n",
                validation={"status":"succeeded"})
    assert store.record_verified_repair(**common)
    assert store.record_verified_repair(**common)
    assert store._conn.execute("SELECT COUNT(*) FROM verified_repairs").fetchone()[0]==1
    assert len(store.find_verified_repairs("SyntaxError unexpected token",code_gen_type="python"))==1
    assert not store.find_verified_repairs("SyntaxError unexpected token",code_gen_type="java")
    assert not store.record_verified_repair(**{**common,"repair":"password = 'very-private-value'"})
    assert not store.record_verified_repair(**{**common,"repair":"contact = 'private@example.com'"})
    assert not store.record_verified_repair(**{**common,"validation":{"status":"unverified"}})
