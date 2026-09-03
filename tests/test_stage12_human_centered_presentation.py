"""Stage 12 acceptance tests for concise explanations and genuine human gates."""

from __future__ import annotations

from pathlib import Path
from time import monotonic, sleep

from graduation_exception_agent.api.models import (
    ApprovalResumeRequest,
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
        evaluation_dir="evaluation",
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
        sleep(0.02)
    raise AssertionError(f"run did not reach {statuses!r}")


def test_approval_case_waits_for_a_described_human_decision() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    accepted = service.start(StartRunRequest(scenario_id="S2-M01"))

    waiting = _wait_for(service, accepted.run_id, RunStatus.WAITING)

    assert waiting.pause is not None
    assert waiting.pause.kind == "approval"
    assert waiting.pause.approver_role == "CCDS Undergraduate Office"
    assert waiting.pause.requested_action == "prerequisite waiver request"
    assert waiting.pause.approval_basis
    assert waiting.pause.evidence_summary
    assert "requires permission" in waiting.pause.why_needed
    assert "rejection returns" in waiting.pause.decision_depends_on
    assert "transaction" not in [item.node_id for item in waiting.timeline]


def test_pending_stays_paused_then_approval_allows_only_the_verified_action() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    run_id = service.start(StartRunRequest(scenario_id="S2-M01")).run_id
    _wait_for(service, run_id, RunStatus.WAITING)

    service.resume(
        run_id,
        ApprovalResumeRequest(kind="approval", status="PENDING"),
    )
    pending = _wait_for(service, run_id, RunStatus.WAITING)
    assert pending.pause is not None and pending.pause.kind == "approval"

    service.resume(
        run_id,
        ApprovalResumeRequest(kind="approval", status="APPROVED"),
    )
    final = _wait_for(service, run_id, RunStatus.COMPLETED, RunStatus.FAILED)

    assert final.status is RunStatus.COMPLETED
    assert "e-approval-transaction" in final.traversed_edges
    assert final.final_response is not None
    assert final.final_response.reasoning_heading == "Why this is valid"
    assert final.final_response.validity_reasons
    assert any("final check" in item.lower() for item in final.final_response.validity_reasons)


def test_rejected_approval_returns_to_planning_with_a_reason() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    run_id = service.start(StartRunRequest(scenario_id="S2-M01")).run_id
    _wait_for(service, run_id, RunStatus.WAITING)

    service.resume(
        run_id,
        ApprovalResumeRequest(
            kind="approval",
            status="REJECTED",
            decision_reason="The submitted mapping is not sufficient for approval.",
        ),
    )
    final = _wait_for(service, run_id, RunStatus.COMPLETED, RunStatus.FAILED)

    assert final.status is RunStatus.COMPLETED
    assert "e-approval-planner" in final.traversed_edges
    assert "e-approval-transaction" not in final.traversed_edges
    assert final.final_response is not None
    assert final.final_response.reasoning_heading == "Why human review is required"


def test_clarification_explains_why_the_answer_changes_the_decision() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    run_id = service.start(StartRunRequest(scenario_id="S6-M01")).run_id
    waiting = _wait_for(service, run_id, RunStatus.WAITING)

    assert waiting.pause is not None and waiting.pause.kind == "clarification"
    assert "cannot safely determine" in waiting.pause.why_needed
    assert waiting.pause.decision_depends_on
    assert waiting.pause.fields


def test_primary_frontend_copy_omits_repeated_node_templates_and_tools() -> None:
    graph = Path("frontend/features/main-workspace/AgentGraphCanvas.tsx").read_text(
        encoding="utf-8"
    )
    meta = Path("frontend/features/main-workspace/MetaInspector.tsx").read_text(
        encoding="utf-8"
    )

    assert "What came in" not in graph
    assert "What this step found" not in graph
    assert "What changed" not in graph
    assert "node-tool-summary" not in graph
    assert 'title="Tools"' not in meta
    assert "Relevant past lessons" in meta
