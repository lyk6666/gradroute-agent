"""Stage 13 acceptance tests for evidence-rich case narration."""

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


def _wait(service: RunService, run_id: str, timeout: float = 15.0):
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


def test_public_waiver_approval_explains_the_actual_decision_basis() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    run_id = service.start(StartRunRequest(scenario_id="S2-M01")).run_id
    waiting = _wait(service, run_id)

    assert waiting.pause is not None and waiting.pause.kind == "approval"
    explanation = waiting.pause.why_needed
    assert "SC4002" in explanation
    assert "128.0 of 131 AUs" in explanation
    assert "SC2001 OR MH1403 OR IE2108" in explanation
    assert "class 14526" in explanation
    assert "policy.exception.exchange.pending_transfer" in explanation
    assert "unofficial transcript" in explanation
    assert "CCDS Undergraduate Office" in explanation
    assert waiting.pause.narrative
    assert any("simulated vacancies" in item for item in waiting.pause.evidence_summary)


def test_simulated_approval_basis_is_not_presented_as_official_policy() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    run_id = service.start(StartRunRequest(scenario_id="S4-M01")).run_id
    waiting = _wait(service, run_id)

    assert waiting.pause is not None and waiting.pause.kind == "approval"
    assert waiting.pause.approval_basis.startswith("Simulated prototype basis")
    assert "not a general official NTU rule" in waiting.pause.why_needed
    course_copy = waiting.node_details["course_agent"].narrative
    assert course_copy is not None
    assert "82001" in course_copy.summary
    assert "timetable check is pass" in course_copy.summary.lower()


def test_replanned_node_explains_what_changed() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    run_id = service.start(StartRunRequest(scenario_id="S7-M01")).run_id
    final = _wait(service, run_id)

    assert final.status is RunStatus.COMPLETED
    planner = final.node_details["planner"]
    assert planner.attempt >= 2
    assert planner.narrative is not None
    assert "replan" in planner.narrative.summary.lower()
    assert any(
        term in planner.narrative.summary.lower()
        for term in ("availab", "vacan", "failed", "changed")
    )


def test_case_overview_merges_progress_and_history() -> None:
    source = Path("frontend/features/main-workspace/MetaInspector.tsx").read_text(
        encoding="utf-8"
    )

    assert 'title="Case overview"' in source
    assert 'title="Current situation"' not in source
    assert 'title="Case history"' not in source
    assert "Recent case developments" in source
    assert "Technical run and checkpoint details" in source


def test_approved_public_route_finishes_with_reasoned_output() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    run_id = service.start(StartRunRequest(scenario_id="S2-M01")).run_id
    waiting = _wait(service, run_id)
    assert waiting.status is RunStatus.WAITING

    service.resume(
        run_id,
        ApprovalResumeRequest(kind="approval", status="APPROVED"),
    )
    final = _wait(service, run_id)

    assert final.status is RunStatus.COMPLETED
    assert final.final_response is not None
    assert final.final_response.reasoning_heading == "Why this is valid"
    joined = " ".join(final.final_response.validity_reasons)
    assert "SC4002" in joined
    assert "approval" in joined.lower()
    assert "final check" in joined.lower()
