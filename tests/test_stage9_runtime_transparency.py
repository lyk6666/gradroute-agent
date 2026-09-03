"""Stage 9 runtime transparency and manual-intake acceptance tests."""

from __future__ import annotations

from time import monotonic, sleep

from fastapi.testclient import TestClient

from graduation_exception_agent.api.app import create_app
from graduation_exception_agent.api.models import ManualRunRequest, RunStatus, StartRunRequest
from graduation_exception_agent.api.service import RunService
from graduation_exception_agent.config import AppSettings, ExecutionMode


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
        if snapshot.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.WAITING}:
            return snapshot
        sleep(0.02)
    raise AssertionError("run did not reach a stable state")


def test_runtime_snapshot_exposes_processed_node_state_and_resolution() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    accepted = service.start(StartRunRequest(scenario_id="S2-M01"))
    final = _wait(service, accepted.run_id)

    assert final.status is RunStatus.COMPLETED
    planner = final.node_details["planner"]
    assert planner.input_items
    assert planner.output_items
    assert any(item.label == "Plan" for item in planner.output_items)
    assert planner.state_changes
    assert final.node_details["policy_agent"].tool_names

    assert final.working_state.plan_steps
    assert len(final.working_state.evidence) == 3
    assert final.working_state.action == "SUBMIT_WAIVER"
    assert final.thread_memory.events
    assert final.thread_memory.approval_details

    response = final.final_response
    assert response is not None
    assert response.headline == "Prerequisite waiver request verified"
    assert "SC4002" in response.request_summary
    assert "exchange course FX2001" in response.request_summary
    assert response.action_parameters
    assert response.academic_basis
    assert response.policy_basis
    assert "transaction receipt" in response.transaction_summary
    assert "receipt.runtime" not in response.transaction_summary
    assert response.next_steps
    assert response.limitations


def test_manual_case_uses_validated_profile_and_custom_request() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    profile = next(item for item in service.scenarios() if item.scenario_id == "S1-M01")
    custom_request = "Please resolve my late registration request for the required course."
    accepted = service.start_manual(
        ManualRunRequest(
            profile_scenario_id=profile.scenario_id,
            student_id=profile.student_id,
            programme=profile.programme,
            cohort=profile.cohort,
            study_year=profile.study_year,
            problem_type=profile.case_type,
            request_text=custom_request,
            notes="The request was entered manually for this run.",
        )
    )
    final = _wait(service, accepted.run_id)

    assert accepted.scenario_id.startswith("MANUAL-")
    assert final.final_response is not None
    assert custom_request in final.final_response.request_summary
    assert "entered manually" in final.final_response.request_summary
    assert final.node_details["student_case"].input_items[0].value == "Manual case"


def test_manual_endpoint_rejects_profile_mismatch() -> None:
    client = TestClient(create_app(_settings()))
    profile = client.get("/api/v1/scenarios", params={"split": "demo"}).json()[0]
    response = client.post(
        "/api/v1/runs/manual",
        json={
            "profile_scenario_id": profile["scenario_id"],
            "student_id": profile["student_id"],
            "programme": "NOT-THE-PROFILE",
            "cohort": profile["cohort"],
            "study_year": profile["study_year"],
            "problem_type": profile["case_type"],
            "request_text": "Please process this complete manually entered exception request.",
            "notes": None,
            "mode": "normal",
        },
    )

    assert response.status_code == 422
    assert "selected validated synthetic profile" in response.json()["detail"]
