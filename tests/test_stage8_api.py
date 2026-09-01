"""Stage 8 API projection and live-run integration tests."""

from __future__ import annotations

from time import monotonic, sleep

from fastapi.testclient import TestClient

from graduation_exception_agent.api.app import create_app
from graduation_exception_agent.api.models import (
    ClarificationResumeRequest,
    RunMode,
    RunStatus,
    StartRunRequest,
)
from graduation_exception_agent.api.service import RunService
from graduation_exception_agent.config import AppSettings, ExecutionMode


def _settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        execution_mode=ExecutionMode.FIXTURE,
        data_dir="data",
        frontend_origin="http://localhost:3000",
    )


def _wait_for(
    service: RunService,
    run_id: str,
    *statuses: RunStatus,
    timeout: float = 12.0,
):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        snapshot = service.snapshot(run_id)
        if snapshot.status in statuses:
            return snapshot
        sleep(0.03)
    raise AssertionError(f"run did not reach {statuses!r} before timeout")


def test_catalogue_projects_only_runnable_fields() -> None:
    service = RunService(_settings(), node_delay_seconds=0)

    scenarios = service.scenarios()

    assert len(scenarios) == 112
    assert {item.split for item in scenarios} == {"demo", "evaluation"}
    serialized = "".join(item.model_dump_json() for item in scenarios)
    assert "ground_truth" not in serialized
    assert "transaction_script" not in serialized
    assert "expected_outcome" not in serialized


def test_normal_run_streams_both_verifier_phases_and_final_response() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    accepted = service.start(StartRunRequest(scenario_id="S7-M01"))

    final = _wait_for(service, accepted.run_id, RunStatus.COMPLETED)

    node_ids = [item.node_id for item in final.timeline]
    assert "pre_action_verifier" in node_ids
    assert "post_action_verifier" in node_ids
    assert node_ids.count("transaction") == 2
    assert "e-post-planner" in final.traversed_edges
    assert "e-post-final" in final.traversed_edges
    assert final.final_response is not None
    assert final.final_response.status == "DONE"
    assert final.final_response.academic_verified is True
    assert final.error is None


def test_step_run_waits_for_explicit_advance() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    accepted = service.start(
        StartRunRequest(scenario_id="S1-M01", mode=RunMode.STEP)
    )
    deadline = monotonic() + 4.0
    while monotonic() < deadline:
        current = service.snapshot(accepted.run_id)
        if current.timeline and current.can_advance:
            break
        sleep(0.02)
    before = service.snapshot(accepted.run_id)
    assert len(before.timeline) == 1
    sleep(0.15)
    assert len(service.snapshot(accepted.run_id).timeline) == 1

    service.advance(accepted.run_id)

    deadline = monotonic() + 4.0
    while monotonic() < deadline:
        after = service.snapshot(accepted.run_id)
        if len(after.timeline) >= 2:
            break
        sleep(0.02)
    assert len(after.timeline) == 2


def test_clarification_checkpoint_resumes_with_validated_answers() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    accepted = service.start(StartRunRequest(scenario_id="S6-M01"))
    waiting = _wait_for(service, accepted.run_id, RunStatus.WAITING)
    assert waiting.pause is not None
    assert waiting.pause.kind == "clarification"
    assert "resume_token" not in waiting.model_dump_json()

    answers = {field: True for field in waiting.pause.fields}
    service.resume(
        accepted.run_id,
        ClarificationResumeRequest(kind="clarification", answers=answers),
    )

    terminal = _wait_for(
        service, accepted.run_id, RunStatus.COMPLETED, RunStatus.WAITING
    )
    assert terminal.thread_memory.clarifications == 1


def test_fastapi_health_and_scenario_contract() -> None:
    client = TestClient(create_app(_settings()))

    health = client.get(
        "/api/v1/health", headers={"Origin": "http://localhost:3000"}
    )
    scenarios = client.get("/api/v1/scenarios", params={"split": "demo"})

    assert health.status_code == 200
    assert health.json()["status"] == "operational"
    assert health.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert scenarios.status_code == 200
    assert len(scenarios.json()) == 7
