"""Stage 14 acceptance tests for preserved node-visit history."""

from __future__ import annotations

from pathlib import Path
from time import monotonic, sleep

from graduation_exception_agent.api.models import RunStatus, StartRunRequest
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


def test_dynamic_recovery_preserves_each_planner_visit() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    run_id = service.start(StartRunRequest(scenario_id="S7-M01")).run_id
    final = _wait(service, run_id)

    assert final.status is RunStatus.COMPLETED
    planner_visits = final.node_history["planner"]
    assert [visit.attempt for visit in planner_visits] == [1, 2]
    assert all(visit.narrative is not None for visit in planner_visits)
    assert planner_visits[0].narrative.summary != planner_visits[1].narrative.summary
    assert "replan" not in planner_visits[0].narrative.summary.lower()
    assert "replan" in planner_visits[1].narrative.summary.lower()
    assert final.node_details["planner"] == planner_visits[-1]


def test_timeline_events_identify_the_exact_node_visit() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    run_id = service.start(StartRunRequest(scenario_id="S7-M01")).run_id
    final = _wait(service, run_id)

    planner_events = [
        event for event in final.timeline if event.node_id == "planner"
    ]
    assert [event.attempt for event in planner_events] == [1, 2]
    for event in final.timeline:
        assert any(
            visit.attempt == event.attempt
            for visit in final.node_history[event.node_id]
        )


def test_every_latest_detail_matches_its_history_tail() -> None:
    service = RunService(_settings(), node_delay_seconds=0)
    run_id = service.start(StartRunRequest(scenario_id="S7-M01")).run_id
    final = _wait(service, run_id)

    for node_id, latest in final.node_details.items():
        assert final.node_history[node_id][-1] == latest


def test_frontend_selects_exact_visits_and_locks_historical_actions() -> None:
    canvas = Path(
        "frontend/features/main-workspace/AgentGraphCanvas.tsx"
    ).read_text(encoding="utf-8")
    timeline = Path(
        "frontend/features/main-workspace/ExecutionTimeline.tsx"
    ).read_text(encoding="utf-8")
    graph_data = Path(
        "frontend/features/main-workspace/workspace-data.ts"
    ).read_text(encoding="utf-8")
    resize_scheduler = Path(
        "frontend/lib/resize-observer-frame-scheduler.ts"
    ).read_text(encoding="utf-8")

    assert "recorded visits" in canvas
    assert "selectedNodeAttempt" in canvas
    assert "Only the latest visit can accept a decision" in canvas
    assert "onSelectNode(event.nodeId, event.attempt)" in timeline
    assert "Visit {event.attempt}" in timeline
    assert "width: 188" in graph_data and "height: 58" in graph_data
    assert "requestAnimationFrame" in resize_scheduler
    assert "ResizeObserver loop" not in canvas
    assert "hideAttribution" not in canvas
    assert "toLocaleTimeString('en-SG'" in canvas
