"""Stage 11 acceptance tests for varied cases and human-readable presentation."""

from __future__ import annotations

from time import monotonic, sleep

from graduation_exception_agent.api.models import (
    ApprovalResumeRequest,
    RunStatus,
    StartRunRequest,
)
from graduation_exception_agent.api.service import RunService
from graduation_exception_agent.config import AppSettings, ExecutionMode
from graduation_exception_agent.data.simulated import load_exception_cases, load_scenarios


def _settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        execution_mode=ExecutionMode.FIXTURE,
        data_dir="data",
        evaluation_dir="evaluation",
        frontend_origin="http://localhost:3000",
    )


def _wait(service: RunService, run_id: str, timeout: float = 12.0):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        snapshot = service.snapshot(run_id)
        if snapshot.status in {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.WAITING,
        }:
            return snapshot
        sleep(0.02)
    raise AssertionError("run did not reach a stable state")


def _approve_and_wait(service: RunService, run_id: str):
    waiting = _wait(service, run_id)
    assert waiting.pause is not None and waiting.pause.kind == "approval"
    service.resume(
        run_id,
        ApprovalResumeRequest(kind="approval", status="APPROVED"),
    )
    return _wait(service, run_id)


def test_generated_cases_and_expected_responses_are_materially_varied() -> None:
    cases = load_exception_cases("data/simulated/exception_cases.json")
    scenarios = load_scenarios("data/tests/scenarios.json")

    assert len(cases) == 140
    assert len({case.reason for case in cases}) >= 130
    assert len({case.goal for case in cases}) >= 70
    assert len({case.requested_action for case in cases}) >= 75
    assert all("Terminal-stage registration or graduation exception" not in case.reason for case in cases)
    assert all(scenario.ground_truth.expected_response for scenario in scenarios)
    assert len({scenario.ground_truth.expected_response for scenario in scenarios}) >= 90
    assert all(
        "expected_response" not in scenario.to_agent_context().model_dump(mode="json")
        for scenario in scenarios
    )


def test_demo_expected_response_is_visible_but_evaluation_answer_is_hidden() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    catalogue = service.scenarios()

    demos = [item for item in catalogue if item.split == "demo"]
    evaluations = [item for item in catalogue if item.split == "evaluation"]
    assert len(demos) == 7
    assert len(evaluations) == 105
    assert all(item.expected_response for item in demos)
    assert all(item.expected_response is None for item in evaluations)
    assert len({item.request_text for item in demos}) == 7
    assert len({item.request_text for item in evaluations}) >= 100


def test_runtime_presentation_uses_case_facts_instead_of_legacy_templates() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    run_id = service.start(StartRunRequest(scenario_id="S2-M01")).run_id
    final = _approve_and_wait(service, run_id)

    assert final.status is RunStatus.COMPLETED
    assert "SC4002" in final.working_state.plan_rationale
    assert all(
        "Collected " not in evidence.summary
        and "typed Stage 4 response" not in evidence.summary
        for evidence in final.working_state.evidence
    )
    assert "optimistic-lock" not in final.working_state.candidate_resolution
    assert final.node_details["policy_agent"].narrative is not None
    assert "SC4002" in final.node_details["policy_agent"].narrative.output
    assert final.final_response is not None
    assert "receipt.runtime" not in final.final_response.transaction_summary
    assert all(item.label not in {"Approval Id", "Curriculum Id"} for item in final.final_response.action_parameters)
