"""Run and review all seven demo workflows with configured live narration.

This script spends real model requests. It never sends demo expected responses to
the runtime; those are used only after execution for the saved review artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from time import monotonic, sleep
from typing import Any

from graduation_exception_agent.api.models import (
    ApprovalResumeRequest,
    RunSnapshot,
    RunStatus,
    StartRunRequest,
)
from graduation_exception_agent.api.narration import (
    RuntimeNarration,
    RuntimeNarrator,
    runtime_narrator_from_settings,
)
from graduation_exception_agent.api.service import RunService
from graduation_exception_agent.config import ExecutionMode, load_settings


DEMO_IDS = [f"S{family}-M01" for family in range(1, 8)]
FORBIDDEN_PRESENTATION_TERMS = (
    "ground_truth",
    "transaction_script",
    "expected_response",
    "context_id",
    "evidence_id",
    "tool_results",
    "json",
    "schema",
    "token count",
)


class RecordingNarrator:
    """Record provider failures while preserving the runtime fallback boundary."""

    def __init__(self, delegate: RuntimeNarrator) -> None:
        self._delegate = delegate
        self.model_id = delegate.model_id
        self.errors: list[dict[str, str]] = []
        self.calls: list[str] = []

    def narrate(self, payload: dict[str, Any]) -> RuntimeNarration:
        self.calls.append(str(payload.get("node", {}).get("name", "unknown")))
        try:
            return self._delegate.narrate(payload)
        except Exception as exc:
            self.errors.append(
                {
                    "node": str(payload.get("node", {}).get("name", "unknown")),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            raise


def wait_for_stable(
    service: RunService, run_id: str, *, timeout_seconds: float = 600.0
) -> RunSnapshot:
    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        snapshot = service.snapshot(run_id)
        if snapshot.status in {
            RunStatus.WAITING,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
        } and not service._records[run_id].worker_active:
            return snapshot
        sleep(0.1)
    raise TimeoutError(f"{run_id} did not reach a stable state")


def node_copy(snapshot: RunSnapshot, node_id: str) -> str | None:
    detail = snapshot.node_details.get(node_id)
    return detail.narrative.summary if detail and detail.narrative else None


def review_snapshot(
    snapshot: RunSnapshot, *, target: str, live_call_count: int
) -> dict[str, Any]:
    executed = [
        detail
        for detail in snapshot.node_details.values()
        if detail.status.value in {"completed", "waiting"}
    ]
    narrated = [detail for detail in executed if detail.narrative]
    live_narrated = [
        detail
        for detail in narrated
        if detail.narrative and detail.narrative.model_id != "deterministic-presentation"
    ]
    all_copy = " ".join(
        detail.narrative.summary
        for detail in narrated
        if detail.narrative
    )
    if snapshot.pause:
        all_copy += " " + " ".join(
            filter(
                None,
                [
                    snapshot.pause.message,
                    snapshot.pause.why_needed,
                    snapshot.pause.decision_depends_on,
                    snapshot.pause.narrative,
                    *snapshot.pause.evidence_summary,
                ],
            )
        )
    if snapshot.final_response:
        all_copy += " " + " ".join(
            filter(
                None,
                [
                    snapshot.final_response.narrative,
                    snapshot.final_response.resolution_summary,
                    *snapshot.final_response.validity_reasons,
                ],
            )
        )
    lowered = all_copy.lower()
    node_fit = {
        "planner": bool(node_copy(snapshot, "planner") and "plan" in node_copy(snapshot, "planner").lower()),
        "degree_audit": bool(
            not node_copy(snapshot, "degree_audit_agent")
            or target.lower() in node_copy(snapshot, "degree_audit_agent").lower()
        ),
        "policy": bool(
            not node_copy(snapshot, "policy_agent")
            or any(
                term in node_copy(snapshot, "policy_agent").lower()
                for term in ("policy", "route", "approval", "eligible")
            )
        ),
        "course": bool(
            not node_copy(snapshot, "course_agent")
            or (
                target.lower() in node_copy(snapshot, "course_agent").lower()
                and any(
                    term in node_copy(snapshot, "course_agent").lower()
                    for term in ("prerequisite", "class", "timetable", "workload")
                )
            )
        ),
    }
    final_or_pause_specific = bool(
        target.lower() in lowered
        and (snapshot.final_response is not None or snapshot.pause is not None)
    )
    live_ratio = len(live_narrated) / len(narrated) if narrated else 0.0
    criteria = {
        "live_model_called_for_every_executed_node": live_call_count >= len(executed),
        "live_narration_accepted_when_grounding_guard_passed": live_ratio >= 0.5,
        "target_course_is_visible": target.lower() in lowered,
        "node_copy_fits_role": all(node_fit.values()),
        "final_or_human_boundary_is_case_specific": final_or_pause_specific,
        "no_internal_or_expected_answer_terms": not any(
            term in lowered for term in FORBIDDEN_PRESENTATION_TERMS
        ),
        "safe_terminal_state": snapshot.status in {
            RunStatus.COMPLETED,
            RunStatus.WAITING,
        },
    }
    return {
        "passed": all(criteria.values()),
        "criteria": criteria,
        "node_fit": node_fit,
        "executed_nodes": len(executed),
        "narrated_nodes": len(narrated),
        "live_narrated_nodes": len(live_narrated),
        "live_narration_ratio": round(live_ratio, 3),
        "live_model_calls": live_call_count,
        "fallback_nodes": [
            detail.node_id
            for detail in narrated
            if detail.narrative
            and detail.narrative.model_id == "deterministic-presentation"
        ],
    }


def main() -> None:
    settings = load_settings()
    if settings.execution_mode is not ExecutionMode.BEDROCK:
        raise RuntimeError("Stage 13 live review requires EXECUTION_MODE=bedrock")
    if not settings.ui_narration_enabled:
        raise RuntimeError("Stage 13 live review requires UI_NARRATION_ENABLED=1")

    configured_narrator = runtime_narrator_from_settings(settings)
    if configured_narrator is None:
        raise RuntimeError("No configured live narrator is available")
    narrator = RecordingNarrator(configured_narrator)
    service = RunService(settings, node_delay_seconds=0, narrator=narrator)
    catalogue = {item.scenario_id: item for item in service.scenarios()}
    results: list[dict[str, Any]] = []

    for scenario_id in DEMO_IDS:
        scenario = catalogue[scenario_id]
        error_start = len(narrator.errors)
        call_start = len(narrator.calls)
        print(f"Running {scenario_id}: {scenario.title}", flush=True)
        accepted = service.start(StartRunRequest(scenario_id=scenario_id))
        snapshot = wait_for_stable(service, accepted.run_id)
        decisions: list[str] = []
        while snapshot.status is RunStatus.WAITING and snapshot.pause:
            if snapshot.pause.kind == "approval":
                service.resume(
                    snapshot.run_id,
                    ApprovalResumeRequest(
                        kind="approval",
                        status="APPROVED",
                    ),
                )
                decisions.append("approved simulated human checkpoint")
                snapshot = wait_for_stable(service, snapshot.run_id)
                continue
            decisions.append("left clarification for the user, as required by the scenario")
            break

        initial = service._records[snapshot.run_id].values.get("scenario_context", {})
        target = str(initial.get("initial_state", {}).get("target_course", "requested course"))
        review = review_snapshot(
            snapshot,
            target=target,
            live_call_count=len(narrator.calls) - call_start,
        )
        scenario_errors = narrator.errors[error_start:]
        results.append(
            {
                "scenario_id": scenario_id,
                "title": scenario.title,
                "target_course": target,
                "status": snapshot.status.value,
                "human_decisions": decisions,
                "expected_response_for_post_run_review_only": scenario.expected_response,
                "review": review,
                "narration_errors": scenario_errors,
                "representative_output": {
                    "planner": node_copy(snapshot, "planner"),
                    "degree_audit": node_copy(snapshot, "degree_audit_agent"),
                    "policy": node_copy(snapshot, "policy_agent"),
                    "course": node_copy(snapshot, "course_agent"),
                    "human_boundary": snapshot.pause.model_dump(mode="json") if snapshot.pause else None,
                    "final_response": snapshot.final_response.model_dump(mode="json") if snapshot.final_response else None,
                    "case_overview": snapshot.working_state.narrative,
                    "case_developments": snapshot.thread_memory.narrative_highlights,
                    "past_lessons": [
                        {
                            "label": item.label,
                            "narrative": item.narrative,
                            "applicability": item.applicability,
                        }
                        for item in snapshot.long_term_memory[:2]
                    ],
                },
            }
        )
        print(
            f"  {snapshot.status.value}; live narration "
            f"{review['live_narrated_nodes']}/{review['narrated_nodes']}; "
            f"review {'PASS' if review['passed'] else 'NEEDS REVIEW'}",
            flush=True,
        )
        for error in scenario_errors[:3]:
            print(
                f"    {error['node']}: {error['error_type']} — {error['message'][:240]}",
                flush=True,
            )

    artifact = {
        "stage": 13,
        "execution_mode": settings.execution_mode.value,
        "model_id": settings.bedrock_model_id,
        "scenarios": results,
        "summary": {
            "passed": sum(item["review"]["passed"] for item in results),
            "total": len(results),
            "all_passed": all(item["review"]["passed"] for item in results),
        },
    }
    output = Path("evaluation/stage13_demo_narration_review.json")
    output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {output}", flush=True)
    print(json.dumps(artifact["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
