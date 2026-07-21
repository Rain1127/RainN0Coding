from pathlib import Path

from agent_eval.dataset import load_cases
from agent_eval.runner import evaluate_dataset


GOLDEN_DEV = Path(__file__).parents[1] / "agent_eval" / "golden" / "dev"


def test_seeded_golden_cases_have_unique_ids_and_required_agent_coverage():
    cases = load_cases(GOLDEN_DEV)

    assert {case.agent for case in cases} == {"intent", "reviewer", "supervisor"}
    assert len({case.id for case in cases}) == len(cases)
    assert len([case for case in cases if case.agent == "supervisor"]) >= 3


def test_all_seeded_supervisor_cases_pass_against_production_router():
    report = evaluate_dataset(GOLDEN_DEV, agent="supervisor")

    assert report["summary"]["cases"] >= 3
    assert report["summary"]["pass_rate"] == 1.0
