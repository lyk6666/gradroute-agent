from __future__ import annotations

import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from graduation_exception_agent.data.real.repository import RealDataRepository
from graduation_exception_agent.data.simulated.repository import SimulatedDataRepository
from graduation_exception_agent.models.runtime import (
    GoalKind,
    GoalOperator,
    GoalPredicate,
)
from graduation_exception_agent.models.tooling import (
    ToolCallContext,
    ToolErrorCode,
    ToolStatus,
    VersionExpectation,
)
from graduation_exception_agent.models.workflow import (
    ApprovalStatus,
    ExpectedOutcome,
    StateTargetType,
    TransactionAction,
    TransactionCode,
)
from graduation_exception_agent.runtime.factory import (
    ScenarioRuntime,
    ScenarioRuntimeFactory,
)
from graduation_exception_agent.tools import (
    ApprovalRequest,
    AvailabilityCheckRequest,
    CasePolicyRequest,
    CourseDetailsRequest,
    CourseSearchRequest,
    CurrentRegistrationRequest,
    CurriculumRequest,
    DegreeAuditRequest,
    ExceptionSubmissionRequest,
    PolicySearchRequest,
    RegistrationSubmissionRequest,
    SemesterOfferingsRequest,
    StudentCourseCheckRequest,
    StudentRecordRequest,
    TimetableCheckRequest,
    TransactionStatusRequest,
    WaiverSubmissionRequest,
    WorkloadCheckRequest,
)


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_IDS = [
    item["scenario_id"]
    for item in json.loads(
        (ROOT / "data" / "tests" / "scenarios.json").read_text(encoding="utf-8")
    )
]


@pytest.fixture(scope="module")
def stage4_repositories():  # type: ignore[no-untyped-def]
    real = RealDataRepository.from_directory(ROOT / "data" / "real")
    simulated = SimulatedDataRepository.from_directory(
        ROOT / "data" / "simulated",
        real_repository=real,
    )
    return real, simulated


@pytest.fixture(scope="module")
def stage4_factory(stage4_repositories):  # type: ignore[no-untyped-def]
    real, simulated = stage4_repositories
    return ScenarioRuntimeFactory(
        real_repository=real,
        simulated_repository=simulated,
    )


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_every_stage3_script_replays_with_durable_stage4_observations(
    stage4_factory: ScenarioRuntimeFactory,
    stage4_repositories,
    scenario_id: str,
) -> None:
    _, simulated = stage4_repositories
    bundle = simulated.bundle
    scenario = next(item for item in bundle.scenarios if item.scenario_id == scenario_id)
    script = next(
        item
        for item in bundle.transaction_scripts
        if item.script_id == scenario.transaction_script_id
    )
    runtime = stage4_factory.build(scenario_id)

    for index, step in enumerate(script.steps, start=1):
        response = _dispatch(runtime, step, index)
        receipt = response.data
        assert isinstance(receipt, dict)
        assert receipt["result_code"] == step.result_code.value
        assert receipt["observation"]["code"] == step.observation.value
        assert receipt["retryable"] is step.retryable
        assert receipt["transaction_id"] != step.transaction_id
        assert not _contains_hidden_key(response.model_dump(mode="json"))
        if step.action is TransactionAction.REQUEST_APPROVAL:
            assert receipt["intermediate"] is True
            assert receipt["goal_effect"] is False

        for mutation in step.mutations:
            if mutation.target_type is StateTargetType.OFFERING_STATE:
                current = runtime.evaluator.offering_state(mutation.target_id)
                assert current.version == mutation.resulting_version
                for field, expected in mutation.changes.items():
                    actual = getattr(current, field)
                    assert getattr(actual, "value", actual) == expected
            elif mutation.target_type is StateTargetType.APPROVAL:
                context = _read_context(runtime, f"request.approval-check.{index}")
                observed = runtime.tools.policy.get_approval_requirement(
                    CasePolicyRequest(context=context, case_id=scenario.case_id)
                )
                assert isinstance(observed.data, dict)
                assert observed.data["observable_status"] == mutation.changes["status"]

    assert runtime.evaluator.complete
    assert runtime.evaluator.consumed_steps == len(script.steps)
    receipts = runtime.evaluator.receipts()
    assert len(receipts) == len(script.steps)
    if scenario.ground_truth.expected_outcome is ExpectedOutcome.RESOLVED:
        assert receipts[-1].goal_effect is True
        assert receipts[-1].postconditions
        assert all(item.satisfied for item in receipts[-1].postconditions)
        assert runtime.evaluator.case().state.value == "RESOLVED"
    else:
        assert receipts[-1].goal_effect is False


def test_stale_preflight_rolls_back_without_consuming_script(
    stage4_factory: ScenarioRuntimeFactory,
    stage4_repositories,
) -> None:
    _, simulated = stage4_repositories
    bundle = simulated.bundle
    scenario = next(item for item in bundle.scenarios if item.scenario_id == "S1-D01")
    step = next(
        item
        for item in bundle.transaction_scripts
        if item.script_id == scenario.transaction_script_id
    ).steps[0]
    runtime = stage4_factory.build(scenario.scenario_id)
    state_id = str(step.action_parameters["offering_state_id"])
    before = runtime.evaluator.offering_state(state_id)
    context = ToolCallContext(
        session_id=runtime.tools.session_id,
        request_id="request.stale-preflight",
        case_id=scenario.case_id,
        requested_at=step.occurred_at,
        idempotency_key="idempotency.stale-preflight",
        expected_versions=[
            VersionExpectation(
                target_type=StateTargetType.OFFERING_STATE,
                target_id=state_id,
                expected_version=before.version + 1,
            )
        ],
    )
    response = runtime.tools.actions.submit_registration(
        RegistrationSubmissionRequest(context=context, offering_state_id=state_id)
    )
    assert response.status is ToolStatus.FAILURE
    assert response.error is not None
    assert response.error.code is ToolErrorCode.STALE_STATE
    assert runtime.evaluator.consumed_steps == 0
    assert runtime.evaluator.session_revision == 0
    assert runtime.evaluator.offering_state(state_id) == before

    succeeded = _dispatch(runtime, step, 1)
    assert succeeded.status is ToolStatus.SUCCESS
    assert runtime.evaluator.consumed_steps == 1


def test_idempotency_replays_receipt_once_and_rejects_key_reuse(
    stage4_factory: ScenarioRuntimeFactory,
    stage4_repositories,
) -> None:
    _, simulated = stage4_repositories
    bundle = simulated.bundle
    scenario = next(item for item in bundle.scenarios if item.scenario_id == "S1-D02")
    step = next(
        item
        for item in bundle.transaction_scripts
        if item.script_id == scenario.transaction_script_id
    ).steps[0]
    runtime = stage4_factory.build(scenario.scenario_id)
    first = _dispatch(runtime, step, 1)
    revision = runtime.evaluator.session_revision
    second = _dispatch(runtime, step, 1)
    assert first.data["receipt_id"] == second.data["receipt_id"]  # type: ignore[index]
    assert second.data["replayed"] is True  # type: ignore[index]
    assert runtime.evaluator.session_revision == revision
    assert runtime.evaluator.consumed_steps == 1

    changed_context = _write_context(runtime, step, 1).model_copy(
        update={"expected_versions": []}
    )
    conflict = runtime.tools.actions.submit_registration(
        RegistrationSubmissionRequest(
            context=changed_context,
            offering_state_id=step.action_parameters["offering_state_id"],
        )
    )
    assert conflict.error is not None
    assert conflict.error.code is ToolErrorCode.IDEMPOTENCY_CONFLICT


def test_approval_gate_and_visibility_are_distinct_from_admin_review(
    stage4_factory: ScenarioRuntimeFactory,
    stage4_repositories,
) -> None:
    _, simulated = stage4_repositories
    bundle = simulated.bundle
    scenario = next(item for item in bundle.scenarios if item.scenario_id == "S2-D01")
    script = next(
        item
        for item in bundle.transaction_scripts
        if item.script_id == scenario.transaction_script_id
    )
    approval_step, waiver_step = script.steps
    runtime = stage4_factory.build(scenario.scenario_id)

    read_context = _read_context(runtime, "request.approval-before")
    before = runtime.tools.policy.get_approval_requirement(
        CasePolicyRequest(context=read_context, case_id=scenario.case_id)
    )
    assert isinstance(before.data, dict)
    assert before.data["required"] is True
    assert "observable_status" not in before.data
    assert "decision_reason" not in before.data

    blocked = runtime.tools.actions.submit_waiver(
        WaiverSubmissionRequest(
            context=_write_context(runtime, waiver_step, 2),
            **waiver_step.action_parameters,
        )
    )
    assert blocked.error is not None
    assert blocked.error.code is ToolErrorCode.APPROVAL_REQUIRED
    assert runtime.evaluator.consumed_steps == 0

    approved = _dispatch(runtime, approval_step, 1)
    assert approved.status is ToolStatus.SUCCESS
    assert approved.data["goal_effect"] is False  # type: ignore[index]
    after = runtime.tools.policy.get_approval_requirement(
        CasePolicyRequest(
            context=_read_context(runtime, "request.approval-after"),
            case_id=scenario.case_id,
        )
    )
    assert after.data["observable_status"] == ApprovalStatus.APPROVED.value  # type: ignore[index]
    assert after.data["version"] == 2  # type: ignore[index]
    assert after.entity_versions[approval_step.action_parameters["approval_id"]] == 2
    completed = _dispatch(runtime, waiver_step, 2)
    assert completed.data["goal_effect"] is True  # type: ignore[index]


def test_factory_builds_isolated_sessions_and_preserves_frozen_repository(
    stage4_factory: ScenarioRuntimeFactory,
    stage4_repositories,
) -> None:
    _, simulated = stage4_repositories
    bundle = simulated.bundle
    scenario = next(item for item in bundle.scenarios if item.scenario_id == "S1-D03")
    step = next(
        item
        for item in bundle.transaction_scripts
        if item.script_id == scenario.transaction_script_id
    ).steps[0]
    state_id = str(step.action_parameters["offering_state_id"])
    first = stage4_factory.build(scenario.scenario_id)
    second = stage4_factory.build(scenario.scenario_id)
    initial = simulated.get_offering_state(state_id)
    _dispatch(first, step, 1)
    assert first.evaluator.offering_state(state_id).version == initial.version + 1
    assert second.evaluator.offering_state(state_id) == initial
    assert simulated.get_offering_state(state_id) == initial


def test_goal_evaluation_uses_postconditions_not_transaction_success_alone(
    stage4_factory: ScenarioRuntimeFactory,
    stage4_repositories,
) -> None:
    _, simulated = stage4_repositories
    bundle = simulated.bundle
    scenario = next(item for item in bundle.scenarios if item.scenario_id == "S2-D02")
    script = next(
        item
        for item in bundle.transaction_scripts
        if item.script_id == scenario.transaction_script_id
    )
    runtime = stage4_factory.build(scenario.scenario_id)
    course_code = str(script.steps[-1].action_parameters["course_code"])
    predicate = GoalPredicate(
        predicate_id="predicate.waiver-receipt",
        goal_kind=GoalKind.WAIVER_SUBMITTED,
        field_path="action",
        operator=GoalOperator.EQUALS,
        expected_value=TransactionAction.SUBMIT_WAIVER.value,
        description="A committed waiver receipt must exist.",
    )
    _dispatch(runtime, script.steps[0], 1)
    intermediate = runtime.tools.evaluate_goal(
        goal_kind=GoalKind.WAIVER_SUBMITTED,
        predicates=[predicate],
        evaluation_id="evaluation.waiver.intermediate",
    )
    assert intermediate.complete is False
    _dispatch(runtime, script.steps[1], 2)
    complete = runtime.tools.evaluate_goal(
        goal_kind=GoalKind.WAIVER_SUBMITTED,
        predicates=[predicate],
        evaluation_id="evaluation.waiver.complete",
    )
    assert complete.complete is True
    assert course_code


def test_concurrent_duplicate_action_commits_once(
    stage4_factory: ScenarioRuntimeFactory,
    stage4_repositories,
) -> None:
    _, simulated = stage4_repositories
    bundle = simulated.bundle
    scenario = next(item for item in bundle.scenarios if item.scenario_id == "S1-D04")
    step = next(
        item
        for item in bundle.transaction_scripts
        if item.script_id == scenario.transaction_script_id
    ).steps[0]
    runtime = stage4_factory.build(scenario.scenario_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(lambda _: _dispatch(runtime, step, 1), range(2))
        )
    assert all(response.status is ToolStatus.SUCCESS for response in responses)
    assert {response.data["receipt_id"] for response in responses} == {  # type: ignore[index]
        f"receipt.runtime.{scenario.case_id}.1"
    }
    assert sum(bool(response.data["replayed"]) for response in responses) == 1  # type: ignore[index]
    assert runtime.evaluator.consumed_steps == 1
    assert runtime.evaluator.session_revision == 1
    assert len(runtime.evaluator.receipts()) == 1


def test_all_read_tool_domains_return_typed_grounded_results(
    stage4_factory: ScenarioRuntimeFactory,
) -> None:
    runtime = stage4_factory.build("S1-D01")
    context = runtime.tools.context

    def read(request_id: str) -> ToolCallContext:
        return _read_context(runtime, request_id)

    responses = [
        runtime.tools.academic.get_student_record(
            StudentRecordRequest(
                context=read("request.read.student"), student_id=context.student_id
            )
        ),
        runtime.tools.academic.get_current_registration(
            CurrentRegistrationRequest(
                context=read("request.read.registration"),
                registration_id=context.registration_id,
            )
        ),
        runtime.tools.academic.get_curriculum(
            CurriculumRequest(
                context=read("request.read.curriculum"),
                curriculum_id=context.curriculum_id,
            )
        ),
        runtime.tools.academic.run_degree_audit(
            DegreeAuditRequest(
                context=read("request.read.audit"), audit_id=context.audit_id
            )
        ),
        runtime.tools.policy.search_policy(
            PolicySearchRequest(
                context=read("request.read.policy"), query="registration exception"
            )
        ),
        runtime.tools.policy.check_exception_eligibility(
            CasePolicyRequest(
                context=read("request.read.eligibility"), case_id=context.case_id
            )
        ),
        runtime.tools.policy.get_approval_requirement(
            CasePolicyRequest(
                context=read("request.read.requirement"), case_id=context.case_id
            )
        ),
        runtime.tools.policy.get_required_documents(
            CasePolicyRequest(
                context=read("request.read.documents"), case_id=context.case_id
            )
        ),
        runtime.tools.course.search_courses(
            CourseSearchRequest(
                context=read("request.read.course-search"), query="SC2000"
            )
        ),
        runtime.tools.course.get_course_details(
            CourseDetailsRequest(
                context=read("request.read.course"), course_code="SC2000"
            )
        ),
        runtime.tools.course.check_prerequisite(
            StudentCourseCheckRequest(
                context=read("request.read.prerequisite"),
                course_code="SC2000",
                student_id=context.student_id,
            )
        ),
        runtime.tools.course.check_exclusion(
            StudentCourseCheckRequest(
                context=read("request.read.exclusion"),
                course_code="SC2000",
                student_id=context.student_id,
            )
        ),
        runtime.tools.course.get_semester_offerings(
            SemesterOfferingsRequest(
                context=read("request.read.offerings"), course_code="SC2000"
            )
        ),
        runtime.tools.course.check_timetable(
            TimetableCheckRequest(
                context=read("request.read.timetable"),
                offering_state_id=context.offering_state_ids[-1],
                registration_id=context.registration_id,
            )
        ),
        runtime.tools.course.check_workload(
            WorkloadCheckRequest(
                context=read("request.read.workload"),
                course_code="SC2000",
                registration_id=context.registration_id,
            )
        ),
        runtime.tools.course.check_availability(
            AvailabilityCheckRequest(
                context=read("request.read.availability"),
                offering_state_id=context.offering_state_ids[-1],
                expected_version=1,
            )
        ),
    ]
    assert all(response.status is ToolStatus.SUCCESS for response in responses)
    assert all(not _contains_hidden_key(response.model_dump(mode="json")) for response in responses)
    assert all(response.provenance for response in responses if response.data)


def test_transaction_status_returns_the_same_durable_receipt(
    stage4_factory: ScenarioRuntimeFactory,
    stage4_repositories,
) -> None:
    _, simulated = stage4_repositories
    bundle = simulated.bundle
    scenario = next(item for item in bundle.scenarios if item.scenario_id == "S1-M01")
    step = next(
        item
        for item in bundle.transaction_scripts
        if item.script_id == scenario.transaction_script_id
    ).steps[0]
    runtime = stage4_factory.build(scenario.scenario_id)
    response = _dispatch(runtime, step, 1)
    receipt_id = response.data["receipt_id"]  # type: ignore[index]
    status = runtime.tools.actions.get_transaction_status(
        TransactionStatusRequest(
            context=_read_context(runtime, "request.transaction-status"),
            receipt_id=receipt_id,
        )
    )
    assert status.status is ToolStatus.SUCCESS
    assert status.data["receipt_id"] == receipt_id  # type: ignore[index]
    assert status.data["postconditions"] == response.data["postconditions"]  # type: ignore[index]


def test_factory_can_load_the_complete_local_data_package() -> None:
    factory = ScenarioRuntimeFactory.from_data_directory(ROOT / "data")
    runtime = factory.build("S1-D01")
    assert runtime.tools.context.case_id == "case.sim-aisc-001"
    assert runtime.evaluator.session_revision == 0


def _dispatch(runtime: ScenarioRuntime, step, index: int):  # type: ignore[no-untyped-def]
    context = _write_context(runtime, step, index)
    parameters = dict(step.action_parameters)
    if step.action is TransactionAction.REQUEST_APPROVAL:
        return runtime.tools.actions.request_approval(
            ApprovalRequest(context=context, **parameters)
        )
    if step.action is TransactionAction.SUBMIT_REGISTRATION:
        return runtime.tools.actions.submit_registration(
            RegistrationSubmissionRequest(context=context, **parameters)
        )
    if step.action is TransactionAction.SUBMIT_WAIVER:
        return runtime.tools.actions.submit_waiver(
            WaiverSubmissionRequest(context=context, **parameters)
        )
    return runtime.tools.actions.submit_exception(
        ExceptionSubmissionRequest(context=context, **parameters)
    )


def _write_context(
    runtime: ScenarioRuntime, step, index: int
) -> ToolCallContext:  # type: ignore[no-untyped-def]
    versions = []
    for target_id, expected_version in step.precondition_state_versions.items():
        target_type = (
            StateTargetType.OFFERING_STATE
            if target_id in runtime.tools.context.offering_state_ids
            else StateTargetType.APPROVAL
        )
        versions.append(
            VersionExpectation(
                target_type=target_type,
                target_id=target_id,
                expected_version=expected_version,
            )
        )
    return ToolCallContext(
        session_id=runtime.tools.session_id,
        request_id=f"request.runtime.{index}",
        case_id=runtime.tools.context.case_id,
        requested_at=step.occurred_at,
        idempotency_key=f"idempotency.runtime.{index}",
        expected_versions=versions,
    )


def _read_context(runtime: ScenarioRuntime, request_id: str) -> ToolCallContext:
    return ToolCallContext(
        session_id=runtime.tools.session_id,
        request_id=request_id,
        case_id=runtime.tools.context.case_id,
        requested_at=runtime.evaluator.case().scenario_time,
    )


def _contains_hidden_key(value: Any) -> bool:
    forbidden = {
        "scenario_id",
        "script_id",
        "transaction_script",
        "transaction_script_id",
        "injected_event",
        "future_event",
        "ground_truth",
        "expected_outcome",
        "valid_initial_paths",
        "valid_final_paths",
        "invalid_paths",
        "terminal_profile",
        "generator_version",
        "seed",
    }
    if isinstance(value, dict):
        return bool(set(value) & forbidden) or any(
            _contains_hidden_key(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_hidden_key(item) for item in value)
    return False
