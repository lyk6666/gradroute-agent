from __future__ import annotations

import json
from copy import deepcopy
from typing import get_type_hints

import pytest
from pydantic import ValidationError

from graduation_exception_agent.memory import (
    ExperienceMemoryQuery,
    ExperienceMemoryRecord,
    InMemoryExperienceMemory,
    MemoryWriteStatus,
    NullExperienceMemory,
)
from graduation_exception_agent.models.orchestration import (
    ActionCandidate,
    ApprovalPause,
    ApprovalResumePayload,
    ClarificationPause,
    FinalOutcome,
    IntakeContext,
    LoopCaps,
    LoopCounters,
    ResolutionPlan,
    SpecialistEvidence,
    SpecialistSelection,
    TraceEvent,
    WorkflowState,
    merge_errors,
    merge_evidence,
    merge_receipts,
    merge_trace,
)
from graduation_exception_agent.models.runtime import (
    GoalEvaluation,
    GoalKind,
    GoalOperator,
    GoalPredicate,
    PredicateEvaluation,
)


TIMESTAMP = "2028-08-30T12:00:00+08:00"


def _predicate(predicate_id: str = "predicate.registered") -> GoalPredicate:
    return GoalPredicate(
        predicate_id=predicate_id,
        goal_kind=GoalKind.COURSE_REGISTERED,
        target_type="REGISTRATION",
        target_ids=["registration.sim.001"],
        field_path="items.course_code",
        operator=GoalOperator.CONTAINS,
        expected_value="SC4001",
        description="The target registration contains the required course.",
    )


def _memory(memory_id: str = "memory.recovery.001") -> ExperienceMemoryRecord:
    return ExperienceMemoryRecord(
        memory_id=memory_id,
        case_type="DYNAMIC_REGISTRATION_RECOVERY",
        goal_kind="COURSE_REGISTERED",
        successful_strategy="Revalidate constraints before retrying an idempotent write.",
        recovery_steps=[
            "Observe the normalized failure.",
            "Replan and revalidate a safe alternative.",
        ],
        failed_strategy_patterns=["Do not retry a stale candidate unchanged."],
        applicability="Advisory when a write fails after pre-action verification.",
        tags=["DYNAMIC_FAILURE", "REPLAN"],
        verification_receipt_ids=["receipt.verified.001"],
        verified_at=TIMESTAMP,
    )


def test_intake_is_observable_strict_and_has_no_evaluator_channels() -> None:
    intake = IntakeContext(
        case_id="case.s6-001",
        session_id="session.s6-001",
        thread_id="thread.s6-001",
        anonymous_student_id="SIM-CS-0001",
        programme_code="CS",
        admission_cohort="2023",
        request_text="Help resolve the outstanding registration issue.",
        problem_type="REGISTRATION_AFTER_DEADLINE",
        submission_ready=False,
        unresolved_questions=["Confirm whether the student wants an admin handoff."],
        case_state="OPEN",
        goal_predicates=[_predicate()],
        received_at=TIMESTAMP,
    )
    assert intake.problem_type.value == "REGISTRATION_AFTER_DEADLINE"
    assert intake.submission_ready is False

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        IntakeContext.model_validate(
            {**intake.model_dump(mode="python"), "expected_outcome": "ESCALATED"}
        )
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        IntakeContext.model_validate(
            {
                **intake.model_dump(mode="python"),
                "unresolved_questions": ["Confirm route.", "Confirm route."],
            }
        )

    forbidden = {
        "scenario_id",
        "family",
        "split",
        "ground_truth",
        "scripts",
        "contracts",
        "events",
    }
    assert forbidden.isdisjoint(get_type_hints(WorkflowState, include_extras=True))


def test_plan_selection_evidence_and_action_candidate_are_consistent() -> None:
    plan = ResolutionPlan(
        plan_id="plan.case.001.v1",
        goal_predicates=[_predicate()],
        steps=[
            {
                "step_id": "step.audit",
                "ordinal": 1,
                "purpose": "Confirm the outstanding requirement.",
                "specialist": "DEGREE_AUDIT",
            },
            {
                "step_id": "step.course",
                "ordinal": 2,
                "purpose": "Check the candidate offering.",
                "specialist": "COURSE",
                "depends_on": ["step.audit"],
            },
        ],
        rationale="Use only the specialist evidence needed for this request.",
        created_at=TIMESTAMP,
    )
    selection = SpecialistSelection(
        selection_id="selection.case.001.v1",
        plan_id=plan.plan_id,
        required_specialists=["DEGREE_AUDIT", "COURSE"],
        rationale="Academic and offering feasibility both need verification.",
    )
    evidence = SpecialistEvidence(
        evidence_id="evidence.course.001",
        specialist="COURSE",
        summary="The candidate was checked through the course tool boundary.",
        tool_request_ids=["request.course.001"],
        entity_versions={"offering-state.sc4001.10001": 1},
        completeness_known=True,
    )
    candidate = ActionCandidate(
        candidate_id="candidate.case.001.v1",
        plan_id=plan.plan_id,
        action="SUBMIT_REGISTRATION",
        parameters={"offering_state_id": "offering-state.sc4001.10001"},
        expected_versions=[
            {
                "target_type": "OFFERING_STATE",
                "target_id": "offering-state.sc4001.10001",
                "expected_version": 1,
            }
        ],
        goal_predicates=[_predicate()],
        evidence_ids=[evidence.evidence_id],
        requires_approval=False,
        idempotency_key="idempotency.case.001.v1",
        rationale="The candidate satisfies the grounded checks.",
    )
    assert selection.plan_id == candidate.plan_id

    invalid = candidate.model_dump(mode="python")
    invalid["approval_id"] = "approval.case.001"
    with pytest.raises(ValidationError, match="approval_id is invalid"):
        ActionCandidate.model_validate(invalid)


def test_trace_key_and_reducer_preserve_repeated_routes() -> None:
    first = TraceEvent(
        sequence=1,
        source="VERIFIER_POST_ACTION",
        outcome="continue_failure",
        destination="PLANNER",
        verifier_phase="POST_ACTION",
    ).model_dump(mode="json")
    second = TraceEvent(
        sequence=2,
        source="VERIFIER_POST_ACTION",
        outcome="continue_failure",
        destination="PLANNER",
        verifier_phase="POST_ACTION",
    ).model_dump(mode="json")
    assert first["transition_key"] == (
        "VERIFIER_POST_ACTION:CONTINUE_FAILURE->PLANNER"
    )
    assert merge_trace([first], [second]) == [first, second]
    assert merge_trace([first], [deepcopy(first)]) == [first]

    conflicting = deepcopy(first)
    conflicting["note"] = "Different event content."
    with pytest.raises(ValueError, match="conflicting trace"):
        merge_trace([first], [conflicting])


def test_loop_caps_use_frozen_defaults_and_fail_closed() -> None:
    caps = LoopCaps()
    counters = LoopCounters()
    assert (caps.max_replans, caps.max_tool_retries, caps.max_total_steps) == (4, 2, 20)
    for _ in range(5):
        counters = counters.advanced(replan=True)
    assert counters.exceeded_cap(caps) == "MAX_REPLANS"
    with pytest.raises(ValueError, match="MAX_REPLANS"):
        counters.require_within(caps)


def test_pause_and_resume_payloads_preserve_route_and_version() -> None:
    clarification = ClarificationPause(
        clarification_id="clarification.case.001",
        case_id="case.001",
        question="Which declaration should be used?",
        missing_fields=["requested_declaration"],
        impact="MATERIAL_CHANGE",
        resume_target="PLANNER",
        requested_at=TIMESTAMP,
    )
    assert clarification.resume_target.value == "PLANNER"
    with pytest.raises(ValidationError, match="must resume"):
        ClarificationPause.model_validate(
            {
                **clarification.model_dump(mode="python"),
                "resume_target": "PRE_ACTION_VERIFIER",
            }
        )

    pause = ApprovalPause(
        approval_id="approval.case.001",
        case_id="case.001",
        approval_version=2,
        approver_role="School undergraduate office",
        requested_action="SUBMIT_EXCEPTION",
        requested_at=TIMESTAMP,
    )
    resumed = ApprovalResumePayload(
        approval_id=pause.approval_id,
        expected_version=pause.approval_version,
        observed_version=3,
        status="APPROVED",
        observed_at=TIMESTAMP,
    )
    assert resumed.observed_version > pause.approval_version

    with pytest.raises(ValidationError, match="older than the checkpoint"):
        ApprovalResumePayload(
            approval_id=pause.approval_id,
            expected_version=3,
            observed_version=2,
            status="PENDING",
            observed_at=TIMESTAMP,
        )


def test_final_outcome_allows_memory_only_after_verified_done() -> None:
    evaluation = GoalEvaluation(
        evaluation_id="evaluation.case.001",
        goal_kind="COURSE_REGISTERED",
        complete=True,
        predicate_results=[
            PredicateEvaluation(
                predicate_id="predicate.registered",
                required=True,
                satisfied=True,
                observed_value="SC4001",
                reason="The post-action registration contains the course.",
                evidence_ids=["receipt.verified.001"],
            )
        ],
        evaluated_at=TIMESTAMP,
    )
    outcome = FinalOutcome(
        outcome_id="outcome.case.001",
        case_id="case.001",
        status="DONE",
        message="The requested outcome was verified.",
        goal_evaluation=evaluation,
        evidence_ids=["receipt.verified.001"],
        memory_write_permitted=True,
        completed_at=TIMESTAMP,
    )
    assert outcome.memory_write_permitted

    with pytest.raises(ValidationError, match="only after verified DONE"):
        FinalOutcome(
            outcome_id="outcome.case.002",
            case_id="case.002",
            status="SAFE_FAILURE",
            message="The case stopped safely.",
            memory_write_permitted=True,
            completed_at=TIMESTAMP,
        )


def test_workflow_state_channels_and_model_dumps_are_json_serializable() -> None:
    trace = TraceEvent(
        sequence=1,
        source="INTAKE",
        outcome="CONTEXT_READY",
        destination="MEMORY_RETRIEVER",
    ).model_dump(mode="json")
    state: WorkflowState = {
        "schema_version": "1.0",
        "thread_id": "thread.case.001",
        "session_id": "session.case.001",
        "case_id": "case.001",
        "loop_caps": LoopCaps().model_dump(mode="json"),
        "loop_counters": LoopCounters().model_dump(mode="json"),
        "trace": [trace],
        "specialist_evidence": [],
        "action_receipts": [],
        "errors": [],
        "run_status": "RUNNING",
    }
    assert json.loads(json.dumps(state))["trace"][0]["transition_key"].startswith(
        "INTAKE:"
    )

    evidence = {"evidence_id": "evidence.001", "summary": "checked"}
    assert merge_evidence([], [evidence]) == [evidence]
    receipt = {"receipt_id": "receipt.001", "status": "SUCCESS"}
    assert merge_receipts([], [receipt]) == [receipt]


def test_memory_is_bounded_deidentified_advisory_and_done_gated() -> None:
    record = _memory()
    dumped = record.model_dump(mode="json")
    assert dumped["verifier_decision"] == "DONE"
    assert dumped["goal_complete"] is True
    assert dumped["advisory"] is True
    assert "student_id" not in dumped

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExperienceMemoryRecord.model_validate(
            {**dumped, "ground_truth": {"expected": "RESOLVED"}}
        )
    with pytest.raises(ValidationError, match="PII, evaluator data"):
        ExperienceMemoryRecord.model_validate(
            {**dumped, "successful_strategy": "Email alice@example.com for help."}
        )
    with pytest.raises(ValidationError, match="PII, evaluator data"):
        ExperienceMemoryRecord.model_validate(
            {**dumped, "applicability": "Use the current policy as final truth."}
        )
    with pytest.raises(ValidationError):
        ExperienceMemoryRecord.model_validate(
            {**dumped, "verifier_decision": "FAILURE"}
        )


@pytest.mark.parametrize(
    ("field_name", "unsafe_value"),
    [
        ("memory_id", "memory.SIM-CS-0001"),
        ("memory_id", "memory.scenario_id.S1-D01"),
        ("memory_id", "memory.current_policy.001"),
        ("memory_id", "memory.6591234567"),
        ("tags", "CURRENT_POLICY"),
        ("tags", "case.sim-aisc-001"),
        ("tags", "GROUND_TRUTH"),
        ("tags", "N1234567A"),
        ("verification_receipt_ids", "receipt.SIM-CS-0001"),
        ("verification_receipt_ids", "receipt.evaluator_only.S1-D01"),
        ("verification_receipt_ids", "receipt.current_capacity.10"),
        ("verification_receipt_ids", "receipt.N1234567A"),
        ("verification_receipt_ids", "6591234567"),
        (
            "verification_receipt_ids",
            "receipt.runtime.case.sim-aisc-0001.1",
        ),
    ],
)
def test_memory_identifier_fields_reject_sensitive_content(
    field_name: str, unsafe_value: str
) -> None:
    payload = _memory().model_dump(mode="python")
    payload[field_name] = (
        [unsafe_value]
        if field_name in {"tags", "verification_receipt_ids"}
        else unsafe_value
    )
    with pytest.raises(ValidationError, match="PII, evaluator data"):
        ExperienceMemoryRecord.model_validate(payload)


def test_memory_accepts_generated_memory_and_runtime_receipt_ids() -> None:
    record = _memory("memory.pattern.submit_registration.0123456789abcdef").model_copy(
        update={
            "verification_receipt_ids": ["receipt.runtime.case.sim-aisc-001.1"]
        }
    )

    # Revalidate the copied model so the assertion exercises field validators.
    validated = ExperienceMemoryRecord.model_validate(
        record.model_dump(mode="python")
    )
    assert validated.memory_id.startswith("memory.pattern.submit_registration")
    assert validated.verification_receipt_ids == [
        "receipt.runtime.case.sim-aisc-001.1"
    ]


def test_memory_query_filters_cannot_reintroduce_sensitive_identifiers() -> None:
    with pytest.raises(ValidationError, match="PII, evaluator data"):
        ExperienceMemoryQuery(tags=["GROUND_TRUTH"])
    with pytest.raises(ValidationError, match="PII, evaluator data"):
        ExperienceMemoryQuery(exclude_memory_ids=["memory.case.sim-aisc-001"])


def test_error_reducer_is_identity_aware_and_checkpoint_replay_safe() -> None:
    identified = {
        "error_id": "error.memory-write.001",
        "code": "MEMORY_WRITE_FAILED",
        "message": "Advisory store unavailable.",
    }
    legacy = {
        "code": "MEMORY_WRITE_FAILED",
        "message": "Legacy advisory store unavailable.",
    }
    replayed = merge_errors(
        [identified, legacy], [deepcopy(identified), deepcopy(legacy)]
    )
    assert replayed == [
        identified,
        legacy,
    ]

    distinct_legacy = {**legacy, "message": "A different store failure."}
    assert merge_errors([legacy], [distinct_legacy]) == [legacy, distinct_legacy]

    conflicting = {**identified, "message": "Conflicting payload."}
    with pytest.raises(ValueError, match="conflicting error item"):
        merge_errors([identified], [conflicting])
    with pytest.raises(ValueError, match="must not be blank"):
        merge_errors([], [{**legacy, "error_id": "  "}])


def test_null_and_in_memory_ports_are_deterministic_and_idempotent() -> None:
    record = _memory()
    query = ExperienceMemoryQuery(
        case_type=record.case_type,
        tags=["REPLAN"],
        limit=1,
    )
    null = NullExperienceMemory()
    assert null.retrieve(query) == []
    assert null.write(record).status is MemoryWriteStatus.DISABLED

    memory = InMemoryExperienceMemory()
    assert memory.write(record).status is MemoryWriteStatus.STORED
    assert memory.write(record).status is MemoryWriteStatus.ALREADY_STORED
    assert memory.retrieve(query) == [record]
    assert memory.retrieve(
        ExperienceMemoryQuery(exclude_memory_ids=[record.memory_id])
    ) == []
    assert memory.snapshot() == (record,)
