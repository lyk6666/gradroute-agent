from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START

from graduation_exception_agent.memory import InMemoryExperienceMemory
from graduation_exception_agent.models.orchestration import (
    LoopCaps,
    SpecialistKind,
    WorkflowNode,
    WorkflowState,
)
from graduation_exception_agent.models.runtime import (
    ClarificationImpact,
    VerifierDecisionCode,
)
from graduation_exception_agent.models.workflow import ExceptionCaseType
from graduation_exception_agent.orchestration import (
    GroundedDecisionProvider,
    PreActionAssessment,
    Stage5ControlPlane,
)
from graduation_exception_agent.runtime import ScenarioRuntime, ScenarioRuntimeFactory


DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
SCENARIO_TIME = datetime.fromisoformat("2028-08-25T09:00:00+08:00")


@pytest.fixture(scope="module")
def runtime_factory() -> ScenarioRuntimeFactory:
    return ScenarioRuntimeFactory.from_data_directory(DATA_ROOT)


def _control_plane(
    runtime_factory: ScenarioRuntimeFactory,
    scenario_id: str,
    problem_type: ExceptionCaseType,
    *,
    memory: InMemoryExperienceMemory | None = None,
    decisions: Any | None = None,
    loop_caps: LoopCaps | None = None,
    thread_id: str | None = None,
    submission_ready: bool | None = None,
    unresolved_questions: list[str] | None = None,
) -> tuple[ScenarioRuntime, Stage5ControlPlane, Any]:
    runtime = runtime_factory.build(scenario_id)
    plane = Stage5ControlPlane.build(
        tools=runtime.tools,
        memory=memory,
        decisions=decisions,
        loop_caps=loop_caps,
    )
    intake = plane.create_intake(
        request_text="Resolve this graduation or registration exception safely.",
        problem_type=problem_type,
        received_at=SCENARIO_TIME,
        thread_id=thread_id or f"thread.stage5.{scenario_id.lower()}",
        submission_ready=submission_ready,
        unresolved_questions=unresolved_questions,
    )
    return runtime, plane, intake


def _transition_keys(state: dict[str, Any]) -> list[str]:
    return [str(event["transition_key"]) for event in state["trace"]]


def _edge_pairs(plane: Stage5ControlPlane) -> set[tuple[str, str]]:
    return {
        (edge.source, edge.target)
        for edge in plane.graph.get_graph().edges
    }


def _walk_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_keys(child)


def _checkpoint_payload(snapshot: Any) -> dict[str, Any]:
    """Expose every JSON-bearing checkpoint field to the leakage assertion."""

    return {
        "values": snapshot.values,
        "config": snapshot.config,
        "metadata": snapshot.metadata,
        "next": snapshot.next,
        "tasks": [
            {
                "name": task.name,
                "interrupts": [item.value for item in task.interrupts],
            }
            for task in snapshot.tasks
        ],
    }


def test_compiled_graph_has_exact_frozen_nodes_topology_and_no_bypass(
    runtime_factory: ScenarioRuntimeFactory,
) -> None:
    _, plane, _ = _control_plane(
        runtime_factory,
        "S1-D01",
        ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
    )
    graph = plane.graph.get_graph()
    expected_nodes = {START, END, *(node.value for node in WorkflowNode)}
    assert set(graph.nodes) == expected_nodes

    specialist_targets = {
        WorkflowNode.DEGREE_AUDIT_AGENT.value,
        WorkflowNode.POLICY_AGENT.value,
        WorkflowNode.COURSE_AGENT.value,
        WorkflowNode.RESOLUTION_BUILDER.value,
    }
    expected_edges = {
        (START, WorkflowNode.INTAKE_CONTEXT.value),
        (WorkflowNode.INTAKE_CONTEXT.value, WorkflowNode.MEMORY_RETRIEVER.value),
        (WorkflowNode.MEMORY_RETRIEVER.value, WorkflowNode.PLANNER.value),
        (WorkflowNode.PLANNER.value, WorkflowNode.SUPERVISOR_ROUTER.value),
        (WorkflowNode.PLANNER.value, WorkflowNode.HUMAN_ADMIN_REVIEW.value),
        *((WorkflowNode.SUPERVISOR_ROUTER.value, target) for target in specialist_targets),
        *(
            (source, target)
            for source in {
                WorkflowNode.DEGREE_AUDIT_AGENT.value,
                WorkflowNode.POLICY_AGENT.value,
                WorkflowNode.COURSE_AGENT.value,
            }
            for target in specialist_targets
        ),
        (WorkflowNode.RESOLUTION_BUILDER.value, WorkflowNode.VERIFIER.value),
        *(
            (WorkflowNode.VERIFIER.value, target)
            for target in {
                WorkflowNode.ACTION_GATE.value,
                WorkflowNode.PLANNER.value,
                WorkflowNode.CLARIFICATION.value,
                WorkflowNode.HUMAN_ADMIN_REVIEW.value,
                WorkflowNode.MEMORY_UPDATER.value,
                WorkflowNode.FINAL_RESPONSE.value,
            }
        ),
        *(
            (WorkflowNode.CLARIFICATION.value, target)
            for target in {
                WorkflowNode.VERIFIER.value,
                WorkflowNode.PLANNER.value,
                WorkflowNode.HUMAN_ADMIN_REVIEW.value,
            }
        ),
        *(
            (WorkflowNode.ACTION_GATE.value, target)
            for target in {
                WorkflowNode.HUMAN_APPROVAL.value,
                WorkflowNode.TRANSACTION.value,
                WorkflowNode.HUMAN_ADMIN_REVIEW.value,
            }
        ),
        *(
            (WorkflowNode.HUMAN_APPROVAL.value, target)
            for target in {
                WorkflowNode.TRANSACTION.value,
                WorkflowNode.PLANNER.value,
                WorkflowNode.PAUSE_CHECKPOINT.value,
                WorkflowNode.HUMAN_ADMIN_REVIEW.value,
            }
        ),
        (WorkflowNode.PAUSE_CHECKPOINT.value, WorkflowNode.HUMAN_APPROVAL.value),
        (WorkflowNode.TRANSACTION.value, WorkflowNode.OBSERVATION.value),
        (WorkflowNode.TRANSACTION.value, WorkflowNode.HUMAN_ADMIN_REVIEW.value),
        (WorkflowNode.OBSERVATION.value, WorkflowNode.VERIFIER.value),
        (WorkflowNode.HUMAN_ADMIN_REVIEW.value, WorkflowNode.FINAL_RESPONSE.value),
        (WorkflowNode.MEMORY_UPDATER.value, END),
        (WorkflowNode.FINAL_RESPONSE.value, END),
    }
    edges = _edge_pairs(plane)
    assert edges == expected_edges

    forbidden_bypasses = {
        (WorkflowNode.PLANNER.value, WorkflowNode.TRANSACTION.value),
        (WorkflowNode.SUPERVISOR_ROUTER.value, WorkflowNode.ACTION_GATE.value),
        (WorkflowNode.RESOLUTION_BUILDER.value, WorkflowNode.ACTION_GATE.value),
        (WorkflowNode.VERIFIER.value, WorkflowNode.TRANSACTION.value),
        (WorkflowNode.ACTION_GATE.value, WorkflowNode.FINAL_RESPONSE.value),
        (WorkflowNode.HUMAN_APPROVAL.value, WorkflowNode.FINAL_RESPONSE.value),
        (WorkflowNode.TRANSACTION.value, WorkflowNode.FINAL_RESPONSE.value),
        (WorkflowNode.OBSERVATION.value, WorkflowNode.FINAL_RESPONSE.value),
    }
    assert edges.isdisjoint(forbidden_bypasses)


def test_one_verifier_node_runs_both_pre_and_post_action_phases(
    runtime_factory: ScenarioRuntimeFactory,
) -> None:
    _, plane, intake = _control_plane(
        runtime_factory,
        "S1-D01",
        ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
    )
    result = plane.start(intake)

    verifier_nodes = {
        name for name in plane.graph.get_graph().nodes if "verifier" in name
    }
    assert verifier_nodes == {WorkflowNode.VERIFIER.value}
    assert [item["phase"] for item in result["verification_history"]] == [
        "PRE_ACTION",
        "POST_ACTION",
    ]
    assert [item["decision"] for item in result["verification_history"]] == [
        "VALID",
        "DONE",
    ]
    assert {
        event["verifier_phase"]
        for event in result["trace"]
        if str(event["source"]).startswith("VERIFIER_")
    } == {"PRE_ACTION", "POST_ACTION"}


def test_s1_done_fans_out_to_final_response_and_verified_memory_write(
    runtime_factory: ScenarioRuntimeFactory,
) -> None:
    memory = InMemoryExperienceMemory()
    runtime, plane, intake = _control_plane(
        runtime_factory,
        "S1-D01",
        ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
        memory=memory,
    )
    result = plane.start(intake)
    transitions = _transition_keys(result)

    assert result["run_status"] == "COMPLETED"
    assert result["final_outcome"]["status"] == "DONE"
    assert result["goal_evaluation"]["complete"] is True
    assert result["memory_write_completed"] is True
    assert "VERIFIER_POST_ACTION:DONE->FINAL_RESPONSE" in transitions
    assert "VERIFIER_POST_ACTION:DONE->MEMORY_UPDATER" in transitions
    assert runtime.evaluator.consumed_steps == 1
    stored = memory.snapshot()
    assert len(stored) == 1
    assert stored[0].advisory is True
    assert stored[0].goal_complete is True
    assert stored[0].verifier_decision == VerifierDecisionCode.DONE.value


def test_s7_retry_replans_once_and_preserves_repeated_trace_edges(
    runtime_factory: ScenarioRuntimeFactory,
) -> None:
    runtime, plane, intake = _control_plane(
        runtime_factory,
        "S7-D01",
        ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
    )
    result = plane.start(intake)
    transitions = _transition_keys(result)

    assert result["final_outcome"]["status"] == "DONE"
    assert result["loop_counters"] == {
        "replans": 1,
        "tool_retries": 1,
        "total_steps": 10,
    }
    assert len(result["plan_history"]) == 2
    assert len(result["attempted_offering_state_ids"]) == 2
    assert transitions.count("PLANNER:PLAN_READY->SUPERVISOR_ROUTER") == 2
    assert transitions.count("VERIFIER_PRE_ACTION:VALID->ACTION_GATE") == 2
    assert transitions.count("ACTION_GATE:NO_APPROVAL->TRANSACTION") == 2
    assert transitions.count("TRANSACTION:RESULT->OBSERVATION") == 2
    assert transitions.count("OBSERVATION:NORMALIZED->VERIFIER_POST_ACTION") == 2
    assert "VERIFIER_POST_ACTION:CONTINUE_FAILURE->PLANNER" in transitions
    assert "VERIFIER_POST_ACTION:DONE->FINAL_RESPONSE" in transitions
    assert runtime.evaluator.consumed_steps == 2


def test_approval_approved_executes_but_rejected_replans_before_admin(
    runtime_factory: ScenarioRuntimeFactory,
) -> None:
    approved_runtime, approved_plane, approved_intake = _control_plane(
        runtime_factory,
        "S2-D01",
        ExceptionCaseType.PREREQUISITE_WAIVER,
    )
    approved = approved_plane.start(approved_intake)
    approved_trace = _transition_keys(approved)
    assert approved["final_outcome"]["status"] == "DONE"
    assert "ACTION_GATE:APPROVAL_REQUIRED->HUMAN_APPROVAL" in approved_trace
    assert "HUMAN_APPROVAL:APPROVED->TRANSACTION" in approved_trace
    assert approved_runtime.evaluator.consumed_steps == 2

    rejected_memory = InMemoryExperienceMemory()
    rejected_runtime, rejected_plane, rejected_intake = _control_plane(
        runtime_factory,
        "S2-E04",
        ExceptionCaseType.PREREQUISITE_WAIVER,
        memory=rejected_memory,
    )
    rejected = rejected_plane.start(rejected_intake)
    rejected_trace = _transition_keys(rejected)
    rejected_index = rejected_trace.index("HUMAN_APPROVAL:REJECTED->PLANNER")
    admin_index = rejected_trace.index(
        "PLANNER:NO_SAFE_ROUTE->HUMAN_ADMIN_REVIEW"
    )
    assert rejected["final_outcome"]["status"] == "ADMIN_HANDOFF"
    assert rejected_index < admin_index
    assert not any(key.endswith("->TRANSACTION") for key in rejected_trace)
    assert rejected["loop_counters"]["replans"] == 1
    assert rejected_runtime.evaluator.consumed_steps == 1
    assert rejected_memory.snapshot() == ()


def test_pending_approval_checkpoints_and_resume_is_idempotent(
    runtime_factory: ScenarioRuntimeFactory,
) -> None:
    memory = InMemoryExperienceMemory()
    runtime, plane, intake = _control_plane(
        runtime_factory,
        "S2-E12",
        ExceptionCaseType.PREREQUISITE_WAIVER,
        memory=memory,
    )
    first_result = plane.start(intake)
    first_snapshot = plane.state(intake.thread_id)
    before = deepcopy(first_snapshot.values)
    pause = before["approval_pause"]

    assert first_snapshot.next == (WorkflowNode.PAUSE_CHECKPOINT.value,)
    assert first_snapshot.interrupts[0].value["kind"] == "APPROVAL"
    assert first_result["__interrupt__"][0].value["approval_id"] == pause["approval_id"]
    assert before["run_status"] == "WAITING_FOR_APPROVAL"
    assert "final_outcome" not in before
    assert runtime.evaluator.consumed_steps == 1
    assert len(runtime.evaluator.receipts()) == 1

    second_result = plane.resume(
        thread_id=intake.thread_id,
        payload={
            "approval_id": pause["approval_id"],
            "expected_version": pause["approval_version"],
            "observed_version": pause["approval_version"],
            "status": "PENDING",
            "observed_at": "2028-08-25T10:00:00+08:00",
        },
    )
    second_snapshot = plane.state(intake.thread_id)
    after = second_snapshot.values

    assert second_snapshot.next == (WorkflowNode.PAUSE_CHECKPOINT.value,)
    assert second_result["__interrupt__"][0].value["kind"] == "APPROVAL"
    assert after["plan"] == before["plan"]
    assert after["plan_history"] == before["plan_history"]
    assert after["action_candidate"] == before["action_candidate"]
    assert after["scenario_context"] == before["scenario_context"]
    assert after["intake_context"] == before["intake_context"]
    assert after["tool_results"]["approval_request"] == (
        before["tool_results"]["approval_request"]
    )
    assert after["approval_pause"]["approval_version"] == pause["approval_version"]
    assert after["loop_counters"]["replans"] == before["loop_counters"]["replans"]
    assert after["loop_counters"]["tool_retries"] == before["loop_counters"]["tool_retries"]
    assert after["loop_counters"]["total_steps"] >= before["loop_counters"]["total_steps"]
    assert runtime.evaluator.consumed_steps == 1
    assert len(runtime.evaluator.receipts()) == 1
    assert [item["receipt_id"] for item in after["action_receipts"]] == [
        item["receipt_id"] for item in before["action_receipts"]
    ]
    assert _transition_keys(after)[-2:] == [
        "PAUSE_CHECKPOINT:APPROVAL_OBSERVED->HUMAN_APPROVAL",
        "HUMAN_APPROVAL:PENDING->PAUSE_CHECKPOINT",
    ]
    assert memory.snapshot() == ()


def test_resume_rejects_terminal_or_mismatched_persisted_interrupt(
    runtime_factory: ScenarioRuntimeFactory,
) -> None:
    _, terminal_plane, terminal_intake = _control_plane(
        runtime_factory,
        "S1-D01",
        ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
    )
    terminal_plane.start(terminal_intake)
    with pytest.raises(ValueError, match="exactly one active persisted interrupt"):
        terminal_plane.resume(
            thread_id=terminal_intake.thread_id,
            payload={
                "clarification_id": "clarification.not-active",
                "answers": {"missing": "value"},
                "impact": "MATERIAL_CHANGE",
                "responded_at": "2028-08-25T10:00:00+08:00",
            },
        )

    runtime, pending_plane, pending_intake = _control_plane(
        runtime_factory,
        "S2-E12",
        ExceptionCaseType.PREREQUISITE_WAIVER,
    )
    pending_plane.start(pending_intake)
    before = deepcopy(pending_plane.state(pending_intake.thread_id).values)
    pause = before["approval_pause"]
    with pytest.raises(ValueError, match="does not match the checkpoint"):
        pending_plane.resume(
            thread_id=pending_intake.thread_id,
            payload={
                "approval_id": "approval.wrong-owner",
                "expected_version": pause["approval_version"],
                "observed_version": pause["approval_version"],
                "status": "PENDING",
                "observed_at": "2028-08-25T10:00:00+08:00",
            },
        )
    assert pending_plane.state(pending_intake.thread_id).values == before
    assert runtime.evaluator.consumed_steps == 1


def test_s3_material_clarification_resumes_at_planner(
    runtime_factory: ScenarioRuntimeFactory,
) -> None:
    runtime, plane, intake = _control_plane(
        runtime_factory,
        "S3-D01",
        ExceptionCaseType.GRADUATION_REQUIREMENT,
        unresolved_questions=["academic_requirement_evidence"],
    )
    first = plane.start(intake)
    pause = first["clarification_pause"]
    assert first["__interrupt__"][0].value["kind"] == "CLARIFICATION"
    assert pause["impact"] == "MATERIAL_CHANGE"
    assert pause["resume_target"] == "PLANNER"

    resumed = plane.resume(
        thread_id=intake.thread_id,
        payload={
            "clarification_id": pause["clarification_id"],
            "answers": {"academic_requirement_evidence": "Provided for re-audit."},
            "impact": "MATERIAL_CHANGE",
            "responded_at": "2028-08-25T10:00:00+08:00",
        },
    )
    state = plane.state(intake.thread_id).values
    transitions = _transition_keys(state)
    edge_index = transitions.index("CLARIFICATION:MATERIAL_CHANGE->PLANNER")
    assert transitions[edge_index + 1] == "PLANNER:PLAN_READY->SUPERVISOR_ROUTER"
    assert len(state["plan_history"]) == 2
    assert state["loop_counters"]["replans"] == 1
    assert resumed["__interrupt__"][0].value["kind"] == "CLARIFICATION"
    assert runtime.evaluator.consumed_steps == 0


def test_s6_small_clarification_returns_to_same_pre_action_verifier(
    runtime_factory: ScenarioRuntimeFactory,
) -> None:
    runtime, plane, intake = _control_plane(
        runtime_factory,
        "S6-D01",
        ExceptionCaseType.COURSE_UNAVAILABLE,
        submission_ready=False,
        unresolved_questions=["submission_declaration"],
    )
    first = plane.start(intake)
    pause = first["clarification_pause"]
    assert pause["impact"] == "SMALL_CHANGE"
    assert pause["resume_target"] == "PRE_ACTION_VERIFIER"

    state = plane.resume(
        thread_id=intake.thread_id,
        payload={
            "clarification_id": pause["clarification_id"],
            "answers": {"submission_declaration": True},
            "impact": "SMALL_CHANGE",
            "responded_at": "2028-08-25T10:00:00+08:00",
        },
    )
    transitions = _transition_keys(state)
    edge_index = transitions.index(
        "CLARIFICATION:SMALL_CHANGE->VERIFIER_PRE_ACTION"
    )
    assert transitions[edge_index + 1] == "VERIFIER_PRE_ACTION:VALID->ACTION_GATE"
    assert len(state["plan_history"]) == 1
    assert [item["decision"] for item in state["verification_history"][:2]] == [
        "CLARIFY",
        "VALID",
    ]
    assert runtime.evaluator.consumed_steps == 1


def test_s6_direct_admin_handoff_does_not_conflate_approval_review(
    runtime_factory: ScenarioRuntimeFactory,
) -> None:
    memory = InMemoryExperienceMemory()
    runtime, plane, intake = _control_plane(
        runtime_factory,
        "S6-D02",
        ExceptionCaseType.COURSE_UNAVAILABLE,
        submission_ready=True,
        memory=memory,
    )
    result = plane.start(intake)
    transitions = _transition_keys(result)

    assert result["final_outcome"]["status"] == "ADMIN_HANDOFF"
    assert "ACTION_GATE:NO_APPROVAL->TRANSACTION" in transitions
    assert "VERIFIER_POST_ACTION:CONTINUE_FAILURE->PLANNER" in transitions
    assert "PLANNER:NO_SAFE_ROUTE->HUMAN_ADMIN_REVIEW" in transitions
    assert "HUMAN_ADMIN_REVIEW:HANDOFF_PREPARED->FINAL_RESPONSE" in transitions
    assert not any("HUMAN_APPROVAL" in key for key in transitions)
    assert not any(item["action"] == "REQUEST_APPROVAL" for item in result["action_receipts"])
    assert runtime.evaluator.consumed_steps == 1
    assert memory.snapshot() == ()


def test_specialist_selection_is_selective_for_registration_and_complete_for_graduation(
    runtime_factory: ScenarioRuntimeFactory,
) -> None:
    _, registration_plane, registration_intake = _control_plane(
        runtime_factory,
        "S1-D01",
        ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
    )
    registration = registration_plane.start(registration_intake)
    assert registration["specialist_selection"]["required_specialists"] == [
        SpecialistKind.POLICY.value,
        SpecialistKind.COURSE.value,
    ]
    assert not any(
        event["source"] == "DEGREE_AUDIT_AGENT"
        or event["destination"] == "DEGREE_AUDIT_AGENT"
        for event in registration["trace"]
    )

    _, graduation_plane, graduation_intake = _control_plane(
        runtime_factory,
        "S3-D01",
        ExceptionCaseType.GRADUATION_REQUIREMENT,
        unresolved_questions=["academic_requirement_evidence"],
    )
    graduation = graduation_plane.start(graduation_intake)
    assert graduation["specialist_selection"]["required_specialists"] == [
        SpecialistKind.DEGREE_AUDIT.value,
        SpecialistKind.POLICY.value,
        SpecialistKind.COURSE.value,
    ]
    assert "DEGREE_AUDIT_AGENT:EVIDENCE_READY->POLICY_AGENT" in _transition_keys(
        graduation
    )


class _AlwaysReplan:
    def select_specialists(
        self, state: WorkflowState
    ) -> tuple[SpecialistKind, ...]:
        return GroundedDecisionProvider().select_specialists(state)

    def assess_pre_action(self, state: WorkflowState) -> PreActionAssessment:
        return PreActionAssessment(
            decision=VerifierDecisionCode.REPLAN,
            reason="Exercise the deterministic replan safety cap.",
            violation_codes=("TEST_REPLAN_CAP",),
        )


@pytest.mark.parametrize(
    ("scenario_id", "problem_type", "caps", "decisions", "expected_transition"),
    [
        (
            "S1-D01",
            ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
            LoopCaps(max_replans=0),
            _AlwaysReplan(),
            "PLANNER:MAX_REPLANS->HUMAN_ADMIN_REVIEW",
        ),
        (
            "S7-D01",
            ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
            LoopCaps(max_tool_retries=0),
            None,
            "PLANNER:MAX_TOOL_RETRIES->HUMAN_ADMIN_REVIEW",
        ),
        (
            "S1-D01",
            ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
            LoopCaps(max_total_steps=1),
            None,
            "VERIFIER_PRE_ACTION:MAX_TOTAL_STEPS->HUMAN_ADMIN_REVIEW",
        ),
    ],
)
def test_loop_caps_fail_closed_to_safe_admin_handoff(
    runtime_factory: ScenarioRuntimeFactory,
    scenario_id: str,
    problem_type: ExceptionCaseType,
    caps: LoopCaps,
    decisions: Any | None,
    expected_transition: str,
) -> None:
    _, plane, intake = _control_plane(
        runtime_factory,
        scenario_id,
        problem_type,
        loop_caps=caps,
        decisions=decisions,
    )
    result = plane.start(intake)

    assert result["final_outcome"]["status"] == "ADMIN_HANDOFF"
    assert expected_transition in _transition_keys(result)
    assert result["admin_handoff"]["reason"].startswith(
        "Workflow stopped safely at MAX_"
    )


def test_one_plane_rejects_second_thread_restart_and_foreign_access(
    runtime_factory: ScenarioRuntimeFactory,
) -> None:
    runtime = runtime_factory.build("S3-D01")
    checkpointer = InMemorySaver()
    plane = Stage5ControlPlane.build(
        tools=runtime.tools,
        checkpointer=checkpointer,
    )
    intake_a = plane.create_intake(
        request_text="Resolve case in thread A.",
        problem_type=ExceptionCaseType.GRADUATION_REQUIREMENT,
        received_at=SCENARIO_TIME,
        thread_id="thread.stage5.isolation.a",
        unresolved_questions=["academic_requirement_evidence"],
    )
    intake_b = plane.create_intake(
        request_text="Resolve case in thread B.",
        problem_type=ExceptionCaseType.GRADUATION_REQUIREMENT,
        received_at=SCENARIO_TIME,
        thread_id="thread.stage5.isolation.b",
        unresolved_questions=["academic_requirement_evidence"],
    )
    first = plane.start(intake_a)
    assert first["__interrupt__"][0].value["kind"] == "CLARIFICATION"

    with pytest.raises(ValueError, match="already owns external thread"):
        plane.start(intake_b)
    with pytest.raises(ValueError, match="has already been started"):
        plane.start(intake_a)
    with pytest.raises(ValueError, match="does not belong"):
        plane.state(intake_b.thread_id)
    with pytest.raises(ValueError, match="does not belong"):
        plane.history(intake_b.thread_id)
    with pytest.raises(ValueError, match="does not belong"):
        plane.resume(
            thread_id=intake_b.thread_id,
            payload={
                "clarification_id": "clarification.foreign",
                "answers": {"academic_requirement_evidence": "Foreign."},
                "impact": "MATERIAL_CHANGE",
                "responded_at": "2028-08-25T10:00:00+08:00",
            },
        )

    replacement = Stage5ControlPlane.build(
        tools=runtime.tools,
        checkpointer=checkpointer,
    )
    with pytest.raises(ValueError, match="persisted checkpoint already exists"):
        replacement.start(intake_a)
    with pytest.raises(ValueError, match="has not started a thread"):
        replacement.state(intake_a.thread_id)


def test_shared_checkpointer_is_namespaced_for_separate_session_planes(
    runtime_factory: ScenarioRuntimeFactory,
) -> None:
    checkpointer = InMemorySaver()
    runtime_a = runtime_factory.build("S3-D01")
    runtime_b = runtime_factory.build("S3-D02")
    plane_a = Stage5ControlPlane.build(
        tools=runtime_a.tools,
        checkpointer=checkpointer,
    )
    plane_b = Stage5ControlPlane.build(
        tools=runtime_b.tools,
        checkpointer=checkpointer,
    )
    public_thread_id = "thread.stage5.shared-public-id"
    intake_a = plane_a.create_intake(
        request_text="Resolve the case owned by session A.",
        problem_type=ExceptionCaseType.GRADUATION_REQUIREMENT,
        received_at=SCENARIO_TIME,
        thread_id=public_thread_id,
        unresolved_questions=["academic_requirement_evidence"],
    )
    intake_b = plane_b.create_intake(
        request_text="Resolve the case owned by session B.",
        problem_type=ExceptionCaseType.GRADUATION_REQUIREMENT,
        received_at=SCENARIO_TIME,
        thread_id=public_thread_id,
        unresolved_questions=["academic_requirement_evidence"],
    )
    plane_a.start(intake_a)
    plane_b.start(intake_b)
    before_b = deepcopy(plane_b.state(public_thread_id).values)
    pause_a = plane_a.state(public_thread_id).values["clarification_pause"]

    plane_a.resume(
        thread_id=public_thread_id,
        payload={
            "clarification_id": pause_a["clarification_id"],
            "answers": {"academic_requirement_evidence": "Session A only."},
            "impact": "MATERIAL_CHANGE",
            "responded_at": "2028-08-25T10:00:00+08:00",
        },
    )

    after_a = plane_a.state(public_thread_id)
    after_b = plane_b.state(public_thread_id)
    assert after_a.values["thread_id"] == public_thread_id
    assert after_b.values["thread_id"] == public_thread_id
    assert after_b.values == before_b
    assert after_a.values["session_id"] != after_b.values["session_id"]
    assert after_a.values["case_id"] != after_b.values["case_id"]
    assert (
        after_a.config["configurable"]["thread_id"]
        != after_b.config["configurable"]["thread_id"]
    )
    assert public_thread_id in after_a.config["configurable"]["thread_id"]
    assert public_thread_id in after_b.config["configurable"]["thread_id"]
    assert after_a.next == after_b.next == (WorkflowNode.CLARIFICATION.value,)


def test_evaluator_control_keys_never_enter_final_or_checkpointed_graph_state(
    runtime_factory: ScenarioRuntimeFactory,
) -> None:
    forbidden = {
        "scenario_id",
        "family",
        "split",
        "ground_truth",
        "test_ground_truth",
        "expected_outcome",
        "expected_valid_resolution",
        "transaction_script_id",
        "scripts",
        "contracts",
        "execution_contract",
        "evaluator_only",
        "required_transitions",
        "forbidden_transitions",
    }

    _, done_plane, done_intake = _control_plane(
        runtime_factory,
        "S1-D01",
        ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
    )
    done = done_plane.start(done_intake)
    done_snapshots = [
        done_plane.state(done_intake.thread_id),
        *done_plane.history(done_intake.thread_id),
    ]
    checked_values: list[Any] = [
        done,
        done["final_outcome"],
        done["trace"],
        *(_checkpoint_payload(snapshot) for snapshot in done_snapshots),
    ]

    _, pending_plane, pending_intake = _control_plane(
        runtime_factory,
        "S2-E12",
        ExceptionCaseType.PREREQUISITE_WAIVER,
    )
    pending = pending_plane.start(pending_intake)
    pending_snapshots = [
        pending_plane.state(pending_intake.thread_id),
        *pending_plane.history(pending_intake.thread_id),
    ]
    checked_values.extend(
        [pending, *(_checkpoint_payload(snapshot) for snapshot in pending_snapshots)]
    )

    for value in checked_values:
        leaked = forbidden.intersection(_walk_keys(value))
        assert leaked == set()
