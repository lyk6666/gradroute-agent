from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from graduation_exception_agent.evaluation import (
    CampaignMetricsSummary,
    EvaluationRunResult,
    MemoryCondition,
    Stage7EvaluationCampaign,
)


DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
REPOSITORY_ROOT = DATA_ROOT.parent


@pytest.fixture(scope="module")
def campaign() -> Stage7EvaluationCampaign:
    return Stage7EvaluationCampaign(data_root=DATA_ROOT)


def test_campaign_inventory_is_the_frozen_105_case_holdout(
    campaign: Stage7EvaluationCampaign,
) -> None:
    scenario_ids = campaign.evaluation_scenario_ids

    assert len(scenario_ids) == 105
    assert scenario_ids == tuple(sorted(scenario_ids))
    assert all("-E" in scenario_id for scenario_id in scenario_ids)


def test_three_repetitions_cover_memory_conditions_without_changing_correctness(
    campaign: Stage7EvaluationCampaign,
) -> None:
    results = campaign.run(scenario_ids=["S1-E01"], repetitions=3)

    assert [item.memory_condition for item in results] == [
        MemoryCondition.EMPTY,
        MemoryCondition.RELEVANT,
        MemoryCondition.MISLEADING,
    ]
    assert [item.memory_hits for item in results] == [0, 1, 1]
    assert all(item.passed for item in results)
    assert len({item.result_signature for item in results}) == 1


def test_dynamic_failure_is_observed_replanned_and_retried(
    campaign: Stage7EvaluationCampaign,
) -> None:
    result = campaign.run(scenario_ids=["S7-E01"], repetitions=1)[0]

    assert result.passed is True
    assert result.replans == 1
    assert result.tool_retries == 1
    assert result.verifier_post_action[0].value == "CONTINUE_FAILURE"
    assert result.verifier_post_action[-1].value == "DONE"


@pytest.mark.parametrize(
    ("scenario_id", "expected_outcome"),
    [
        ("S3-E01", "CLARIFICATION_REQUIRED"),
        ("S2-E12", "PENDING_APPROVAL"),
    ],
)
def test_interrupt_routes_resume_without_replaying_writes(
    campaign: Stage7EvaluationCampaign,
    scenario_id: str,
    expected_outcome: str,
) -> None:
    result = campaign.run(scenario_ids=[scenario_id], repetitions=1)[0]

    assert result.passed is True
    assert result.actual_outcome.value == expected_outcome
    assert result.checkpoint_paused is True
    assert result.checkpoint_resumed is True


def test_canonical_summary_rejects_partial_campaign(
    campaign: Stage7EvaluationCampaign,
) -> None:
    partial = campaign.run(scenario_ids=["S1-E01"], repetitions=1)

    with pytest.raises(ValueError, match="exactly 315"):
        campaign.summarize(partial)


def test_run_result_rejects_inconsistent_token_totals(
    campaign: Stage7EvaluationCampaign,
) -> None:
    result = campaign.run(scenario_ids=["S1-E01"], repetitions=1)[0]
    payload = result.model_dump(mode="python")
    payload["total_tokens"] = 1

    with pytest.raises(ValidationError, match="total_tokens"):
        EvaluationRunResult.model_validate(payload)


def test_checked_in_fixture_campaign_is_complete_and_accepted(
    campaign: Stage7EvaluationCampaign,
) -> None:
    results = [
        EvaluationRunResult.model_validate_json(line)
        for line in (REPOSITORY_ROOT / "evaluation" / "run_results.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    summary = campaign.summarize(results)
    persisted = CampaignMetricsSummary.model_validate_json(
        (REPOSITORY_ROOT / "evaluation" / "metrics_summary.json").read_text(
            encoding="utf-8"
        )
    )

    assert summary.acceptance_passed is True
    assert summary.passed_runs == 315
    assert summary.scenarios_passing_3_of_3 == 105
    assert summary.violation_counts == {}
    assert persisted == summary


def test_checked_in_live_campaign_is_complete_accepted_and_secret_free() -> None:
    live_root = REPOSITORY_ROOT / "evaluation" / "live"
    summary = CampaignMetricsSummary.model_validate_json(
        (live_root / "metrics_summary.json").read_text(encoding="utf-8")
    )
    run_lines = [
        line
        for line in (live_root / "run_results.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    scenario_lines = (
        (live_root / "scenario_summary.csv")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    serialized_artifacts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in live_root.iterdir()
        if path.is_file()
    ).lower()

    assert summary.acceptance_passed is True
    assert summary.run_count == summary.passed_runs == 315
    assert summary.scenarios_passing_3_of_3 == 105
    assert summary.reasoning_calls == summary.reasoning_successes == 720
    assert summary.reasoning_fallbacks == 0
    assert summary.schema_validation_pass_rate == 1.0
    assert summary.violation_counts == {}
    assert len(run_lines) == 315
    assert len(scenario_lines) == 106  # Header plus one row per scenario.
    assert (live_root / "failures.jsonl").read_text(encoding="utf-8") == ""
    assert "aws_access_key" not in serialized_artifacts
    assert "secret_access_key" not in serialized_artifacts
    assert "session_token" not in serialized_artifacts
