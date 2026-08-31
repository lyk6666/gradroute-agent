from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

from graduation_exception_agent.data.real.repository import RealDataRepository
from graduation_exception_agent.data.simulated import (
    SimulatedDataRepository,
    Stage3DataBundle,
    load_generation_manifest,
    load_simulation_scopes,
    validate_stage3_data,
)
from graduation_exception_agent.data.simulated.validator import _record_id
from graduation_exception_agent.errors import DataIntegrityError, DataShapeError
from graduation_exception_agent.models import (
    Approval,
    ApprovalBasis,
    ApprovalStatus,
    AuditBasis,
    AuditOutcome,
    CaseState,
    CompletedCourse,
    CreditStatus,
    DegreeAudit,
    Exemption,
    ExceptionCase,
    ExceptionCaseType,
    EventType,
    ExpectedOutcome,
    GenerationManifest,
    InjectedEvent,
    ObservationCode,
    OfferingState,
    Registration,
    RegistrationPhase,
    RequirementProgress,
    RequirementStatus,
    ResolutionPath,
    ResolutionStep,
    RuntimeOfferingStatus,
    Scenario,
    ScenarioFamily,
    ScenarioGroundTruth,
    ScenarioSplit,
    Semester,
    SimulationScope,
    StateTargetType,
    StateMutation,
    Student,
    TerminalProfile,
    TransactionAction,
    TransactionCode,
    TransactionResult,
    TransactionScript,
)


GENERATOR_VERSION = "stage3-test-1"
GLOBAL_SEED = 20260831
SIMULATION_SCOPE_ID = "scope.aisc.terminal"
SIMULATION_PERIOD_ID = "period.terminal.s1"
STUDENT_ID = "SIM-AISC-001"
AUDIT_ID = "audit.aisc.001"
REGISTRATION_ID = "registration.aisc.001"
CASE_ID = "case.aisc.001"
SCRIPT_ID = "script.aisc.001"
SCENARIO_ID = "scenario.aisc.001"


def _expected_seed(model_name: str, record_id: str) -> int:
    digest = sha256(
        f"{GLOBAL_SEED}|{model_name}|{record_id}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big") % 2_000_000_000


def _generation(
    model_name: str, record_id: str, source_rule_ids: list[str]
) -> dict[str, object]:
    return {
        "generator_version": GENERATOR_VERSION,
        "seed": _expected_seed(model_name, record_id),
        "source_rule_ids": source_rule_ids,
    }


@pytest.fixture(scope="module")
def real_root() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "real"


@pytest.fixture(scope="module")
def real_repository(real_root: Path) -> RealDataRepository:
    return RealDataRepository.from_directory(real_root)


@pytest.fixture(scope="module")
def stage3_bundle(
    real_repository: RealDataRepository, real_root: Path
) -> Stage3DataBundle:
    curriculum = real_repository.get_curriculum("curriculum.aisc.ay2025-26")
    source_rule_ids = [
        curriculum.curriculum_id,
        *(requirement.requirement_id for requirement in curriculum.requirements),
    ]
    hash_names = (
        "academic_calendar.md",
        "course_offerings.json",
        "courses.json",
        "coverage.json",
        "curriculum.json",
        "programmes.json",
        "approval_structure.md",
        "exceptions.md",
        "registration.md",
        "source_manifest.json",
    )
    real_hashes = {}
    for name in hash_names:
        matches = list(real_root.rglob(name))
        assert len(matches) == 1
        real_hashes[name] = sha256(matches[0].read_bytes()).hexdigest()

    scope = SimulationScope(
        simulation_scope_id=SIMULATION_SCOPE_ID,
        curriculum_id=curriculum.curriculum_id,
        programme=curriculum.programme,
        admission_cohort=curriculum.admission_cohort,
        simulation_period_id=SIMULATION_PERIOD_ID,
        simulation_academic_year="AY2028-29",
        simulation_semester=Semester.SEMESTER_1,
        template_academic_year="AY2026-27",
        template_semester=Semester.SEMESTER_1,
        terminal_study_year=4,
        student_count=1,
        audit_basis=AuditBasis.SCENARIO_BOUNDED_SIMULATION,
        counterfactual_time_basis="Admission cohort plus terminal study year",
        permitted_graduation_path_ids=[],
        permitted_study_plan_path_labels=[],
        accepted_gap_ids=[],
        assumption_ids=[],
        **_generation(
            "SimulationScope", SIMULATION_SCOPE_ID, [curriculum.curriculum_id]
        ),
    )
    states = tuple(
        OfferingState(
            state_id=f"state.template.{number:04d}",
            simulation_period_id=SIMULATION_PERIOD_ID,
            template_offering_id=offering.offering_id,
            template_index_id=index.index_id,
            template_academic_year=offering.academic_year,
            template_semester=offering.semester,
            capacity=10,
            vacancies=5,
            waitlist_count=0,
            runtime_status=RuntimeOfferingStatus.OPEN,
            available=True,
            unavailable_reason=None,
            version=1,
            **_generation(
                "OfferingState",
                f"state.template.{number:04d}",
                [curriculum.curriculum_id],
            ),
        )
        for number, (offering, index) in enumerate(
            (
                (offering, index)
                for offering in real_repository.offerings
                for index in offering.indexes
            ),
            start=1,
        )
    )
    offering_by_id = {
        str(offering.offering_id): offering
        for offering in real_repository.offerings
    }
    target_course = "SC3098"
    target_state = next(
        state
        for state in states
        if str(offering_by_id[str(state.template_offering_id)].course_code)
        == target_course
    )
    student = Student(
        student_id=STUDENT_ID,
        simulation_scope_id=SIMULATION_SCOPE_ID,
        simulation_period_id=SIMULATION_PERIOD_ID,
        programme=curriculum.programme,
        additional_programmes=[],
        curriculum_id=curriculum.curriculum_id,
        graduation_path_id=None,
        study_plan_path_label=None,
        admission_cohort=curriculum.admission_cohort,
        study_year=4,
        terminal_profile=TerminalProfile.REQUIREMENT_OUTSTANDING,
        academic_standing="GOOD",
        has_outstanding_fees=False,
        completed_courses=[],
        earned_aus="0",
        exemptions=[],
        assumption_ids=[],
        **_generation("Student", STUDENT_ID, [curriculum.curriculum_id]),
    )
    progress = [
        RequirementProgress(
            requirement_id=requirement.requirement_id,
            status=RequirementStatus.OUTSTANDING,
            required_aus=requirement.minimum_aus,
            earned_aus="0",
            completed_courses=[],
            outstanding_courses=[],
            explanation="The requirement remains outstanding in this fixture.",
            evidence_rule_ids=[requirement.requirement_id],
            assumption_ids=[],
            limitations=[],
        )
        for requirement in curriculum.requirements
    ]
    audit = DegreeAudit(
        audit_id=AUDIT_ID,
        student_id=STUDENT_ID,
        simulation_scope_id=SIMULATION_SCOPE_ID,
        simulation_period_id=SIMULATION_PERIOD_ID,
        curriculum_id=curriculum.curriculum_id,
        audit_basis=AuditBasis.SCENARIO_BOUNDED_SIMULATION,
        audit_outcome=AuditOutcome.NOT_READY,
        graduation_path_id=None,
        study_plan_path_label=None,
        simulation_academic_year="AY2028-29",
        semester=Semester.SEMESTER_1,
        requirement_results=progress,
        total_earned_aus="0",
        total_required_aus=curriculum.graduation_aus,
        assumption_ids=[],
        limitations=[],
        **_generation("DegreeAudit", AUDIT_ID, [curriculum.curriculum_id]),
    )
    registration = Registration(
        registration_id=REGISTRATION_ID,
        student_id=STUDENT_ID,
        simulation_scope_id=SIMULATION_SCOPE_ID,
        simulation_period_id=SIMULATION_PERIOD_ID,
        simulation_academic_year="AY2028-29",
        semester=Semester.SEMESTER_1,
        template_academic_year="AY2026-27",
        template_semester=Semester.SEMESTER_1,
        scenario_time="2028-08-15T12:00:00+08:00",
        phase=RegistrationPhase.POST_ADD_DROP,
        registered_courses=[],
        timetable=[],
        workload_aus="0",
        workload_limit_aus="20",
        missing_required_courses=[],
        assumption_ids=[],
        **_generation(
            "Registration", REGISTRATION_ID, [curriculum.curriculum_id]
        ),
    )
    case = ExceptionCase(
        case_id=CASE_ID,
        student_id=STUDENT_ID,
        simulation_scope_id=SIMULATION_SCOPE_ID,
        audit_id=AUDIT_ID,
        registration_id=REGISTRATION_ID,
        scenario_time="2028-08-15T12:00:00+08:00",
        problem_type=ExceptionCaseType.GRADUATION_REQUIREMENT,
        reason="The final audit shows an outstanding requirement.",
        goal="Find a supported resolution or request clarification.",
        requested_action="Review the outstanding requirement.",
        submission_ready=False,
        unresolved_questions=["submission_declaration"],
        policy_section_ids=[],
        assumption_ids=[],
        supporting_documents=[],
        evidence=[],
        state=CaseState.OPEN,
        created_at="2028-08-15T11:00:00+08:00",
        **_generation("ExceptionCase", CASE_ID, [curriculum.curriculum_id]),
    )
    event = {
        "event_id": "event.aisc.001",
        "event_type": EventType.REQUIRED_INFORMATION_MISSING,
        "target_type": StateTargetType.CASE,
        "target_id": CASE_ID,
        "occurs_at": "2028-08-15T12:04:00+08:00",
    }
    transaction = TransactionResult(
        transaction_id="transaction.aisc.001",
        case_id=CASE_ID,
        action=TransactionAction.SUBMIT_EXCEPTION,
        attempt_number=1,
        result_code=TransactionCode.REQUIRED_INFORMATION_MISSING,
        observation=ObservationCode.REQUIRED_INFORMATION_MISSING,
        retryable=False,
        message="The simulator requires additional information.",
        error_code="error.required_information",
        event=event,
        precondition_state_versions={},
        mutations=[],
        occurred_at="2028-08-15T12:05:00+08:00",
        **_generation(
            "TransactionResult",
            "transaction.aisc.001",
            [curriculum.curriculum_id],
        ),
    )
    script = TransactionScript(
        script_id=SCRIPT_ID,
        case_id=CASE_ID,
        simulation_scope_id=SIMULATION_SCOPE_ID,
        steps=[transaction],
        **_generation("TransactionScript", SCRIPT_ID, [curriculum.curriculum_id]),
    )
    scenario = Scenario(
        scenario_id=SCENARIO_ID,
        family=ScenarioFamily.S6_NO_VALID_PATH,
        split=ScenarioSplit.DEVELOPMENT,
        simulation_scope_id=SIMULATION_SCOPE_ID,
        student_id=STUDENT_ID,
        curriculum_id=curriculum.curriculum_id,
        audit_id=AUDIT_ID,
        registration_id=REGISTRATION_ID,
        case_id=CASE_ID,
        offering_state_ids=[target_state.state_id],
        transaction_script_id=SCRIPT_ID,
        initial_state_refs=[
            STUDENT_ID,
            AUDIT_ID,
            REGISTRATION_ID,
            CASE_ID,
            target_state.state_id,
        ],
        initial_state={
            "request_received": True,
            "target_course": target_course,
            "request_time": "2028-08-15T12:00:00+08:00",
            "observed_state_versions": {str(target_state.state_id): 1},
        },
        injected_event=event,
        ground_truth=ScenarioGroundTruth(
            valid_initial_paths=[],
            valid_final_paths=[],
            invalid_paths=[],
            requires_human=False,
            expected_outcome=ExpectedOutcome.CLARIFICATION_REQUIRED,
        ),
        **_generation("Scenario", SCENARIO_ID, [curriculum.curriculum_id]),
    )
    counts = {
        "simulation_scopes": 1,
        "audit_assumptions": 0,
        "prototype_policies": 0,
        "offering_states": len(states),
        "students": 1,
        "degree_audits": 1,
        "current_registrations": 1,
        "exception_cases": 1,
        "approvals": 0,
        "transaction_scripts": 1,
        "scenarios": 1,
    }
    manifest = GenerationManifest(
        manifest_id="manifest.stage3.test",
        generator_version=GENERATOR_VERSION,
        global_seed=GLOBAL_SEED,
        generated_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
        coverage_contract_id=real_repository.coverage.contract_id,
        real_data_hashes=real_hashes,
        source_rule_ids=source_rule_ids,
        simulation_period_ids=[SIMULATION_PERIOD_ID],
        simulation_period_rule="Counterfactual terminal period over AY2026-27 templates",
        prototype_policies=[],
        prototype_policy_versions={},
        record_counts=counts,
    )
    return Stage3DataBundle(
        manifest=manifest,
        simulation_scopes=(scope,),
        audit_assumptions=(),
        offering_states=states,
        students=(student,),
        degree_audits=(audit,),
        current_registrations=(registration,),
        exception_cases=(case,),
        approvals=(),
        transaction_scripts=(script,),
        scenarios=(scenario,),
    )


def test_small_bundle_passes_when_fixed_scale_is_disabled(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    assert validate_stage3_data(
        real_repository,
        stage3_bundle,
        real_directory=real_root,
        enforce_expected_counts=False,
    ) == ()


def _validation_codes(
    real_repository: RealDataRepository,
    real_root: Path,
    bundle: Stage3DataBundle,
) -> set[str]:
    return {
        issue.code
        for issue in validate_stage3_data(
            real_repository,
            bundle,
            real_directory=real_root,
            enforce_expected_counts=False,
        )
    }


def test_validator_recomputes_top_level_and_nested_generated_seeds(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    student = stage3_bundle.students[0]
    bad_student = student.model_copy(update={"seed": student.seed + 1})
    top_level = replace(stage3_bundle, students=(bad_student,))
    assert "GENERATED_SEED_MISMATCH" in _validation_codes(
        real_repository, real_root, top_level
    )

    script = stage3_bundle.transaction_scripts[0]
    transaction = script.steps[0]
    bad_transaction = transaction.model_copy(
        update={"seed": transaction.seed + 1}
    )
    nested = replace(
        stage3_bundle,
        transaction_scripts=(
            script.model_copy(update={"steps": [bad_transaction]}),
        ),
    )
    assert "GENERATED_SEED_MISMATCH" in _validation_codes(
        real_repository, real_root, nested
    )


def test_validator_resolves_case_events_and_derives_expected_outcome(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    scenario = stage3_bundle.scenarios[0]
    script = stage3_bundle.transaction_scripts[0]
    event = scenario.injected_event
    assert event is not None
    bad_event = event.model_copy(update={"target_id": "case.unknown"})
    bad_step = script.steps[0].model_copy(update={"event": bad_event})
    bad_target = replace(
        stage3_bundle,
        transaction_scripts=(script.model_copy(update={"steps": [bad_step]}),),
        scenarios=(scenario.model_copy(update={"injected_event": bad_event}),),
    )
    target_codes = _validation_codes(real_repository, real_root, bad_target)
    assert "UNKNOWN_EVENT_TARGET" in target_codes
    assert "S6_EVENT_TARGET_MISMATCH" in target_codes

    bad_truth = scenario.ground_truth.model_copy(
        update={"expected_outcome": ExpectedOutcome.ESCALATED}
    )
    bad_outcome = replace(
        stage3_bundle,
        scenarios=(scenario.model_copy(update={"ground_truth": bad_truth}),),
    )
    assert "EXPECTED_OUTCOME_MISMATCH" in _validation_codes(
        real_repository, real_root, bad_outcome
    )


def test_validator_resolves_every_resolution_path_parameter(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    scenario = stage3_bundle.scenarios[0]
    invalid_path = ResolutionPath(
        path_id="path.fixture.invalid-references",
        steps=[
            ResolutionStep(
                step_id="step.fixture.invalid-references",
                action="Attempt invalid references.",
                parameters={
                    "offering_state_id": "state.unknown",
                    "approval_id": "approval.unknown",
                    "curriculum_id": "curriculum.unknown",
                    "graduation_path_id": "graduation_path.unknown",
                    "course_code": "SC9999",
                },
            )
        ],
        rationale="Mutation fixture for semantic referential integrity.",
        source_rule_ids=[str(scenario.curriculum_id)],
    )
    truth = scenario.ground_truth.model_copy(update={"invalid_paths": [invalid_path]})
    changed = replace(
        stage3_bundle,
        scenarios=(scenario.model_copy(update={"ground_truth": truth}),),
    )
    codes = _validation_codes(real_repository, real_root, changed)
    assert {
        "UNKNOWN_PATH_OFFERING_STATE",
        "UNKNOWN_PATH_APPROVAL",
        "PATH_CURRICULUM_MISMATCH",
        "UNKNOWN_PATH_GRADUATION_PATH",
        "UNKNOWN_PATH_COURSE",
    }.issubset(codes)


def test_validator_enforces_s2_and_s5_family_grounding(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    scenario = stage3_bundle.scenarios[0]
    s2_state = scenario.model_copy(
        update={
            "family": ScenarioFamily.S2_PREREQUISITE_EXCEPTION,
            "initial_state": {
                **scenario.initial_state,
                "target_course": "SC2000",
            },
        }
    )
    s2 = replace(stage3_bundle, scenarios=(s2_state,))
    assert "S2_TARGET_WITHOUT_PREREQUISITE" in _validation_codes(
        real_repository, real_root, s2
    )

    s5_state = scenario.model_copy(
        update={"family": ScenarioFamily.S5_CROSS_PROGRAMME}
    )
    s5 = replace(stage3_bundle, scenarios=(s5_state,))
    s5_codes = _validation_codes(real_repository, real_root, s5)
    assert "S5_GRADUATION_PATH_REQUIRED" in s5_codes
    assert "S5_PRIMARY_BASE_CURRICULUM" in s5_codes


def _resolved_registration_bundle(
    stage3_bundle: Stage3DataBundle,
    *,
    preconditions: dict[str, int],
    action_course: str = "SC3098",
) -> Stage3DataBundle:
    scenario = stage3_bundle.scenarios[0]
    script = stage3_bundle.transaction_scripts[0]
    transaction = script.steps[0]
    state_id = str(scenario.offering_state_ids[0])
    resolved_step = transaction.model_copy(
        update={
            "action": TransactionAction.SUBMIT_REGISTRATION,
            "action_parameters": {
                "offering_state_id": state_id,
                "course_code": action_course,
            },
            "result_code": TransactionCode.SUCCESS,
            "observation": ObservationCode.TRANSACTION_SUCCESS,
            "retryable": False,
            "error_code": None,
            "event": None,
            "precondition_state_versions": preconditions,
            "mutations": [],
        }
    )
    path = ResolutionPath(
        path_id="path.fixture.register",
        steps=[
            ResolutionStep(
                step_id="step.fixture.register",
                action="Register the grounded target.",
                parameters={
                    "offering_state_id": state_id,
                    "course_code": "SC3098",
                },
            )
        ],
        rationale="The state is open and the prerequisite passes.",
        source_rule_ids=[str(scenario.curriculum_id)],
    )
    truth = scenario.ground_truth.model_copy(
        update={
            "valid_initial_paths": [path],
            "expected_outcome": ExpectedOutcome.RESOLVED,
        }
    )
    resolved_scenario = scenario.model_copy(
        update={
            "family": ScenarioFamily.S3_MULTI_SOURCE,
            "injected_event": None,
            "ground_truth": truth,
        }
    )
    return replace(
        stage3_bundle,
        transaction_scripts=(
            script.model_copy(update={"steps": [resolved_step]}),
        ),
        scenarios=(resolved_scenario,),
    )


def test_submit_registration_binds_state_version_and_template_course(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    missing_precondition = _resolved_registration_bundle(
        stage3_bundle, preconditions={}
    )
    assert "REGISTRATION_STATE_PRECONDITION_MISSING" in _validation_codes(
        real_repository, real_root, missing_precondition
    )

    state_id = str(stage3_bundle.scenarios[0].offering_state_ids[0])
    wrong_course = _resolved_registration_bundle(
        stage3_bundle,
        preconditions={state_id: 1},
        action_course="SC2000",
    )
    codes = _validation_codes(real_repository, real_root, wrong_course)
    assert "ACTION_STATE_COURSE_MISMATCH" in codes
    assert "ACTION_TARGET_COURSE_MISMATCH" in codes


def _approved_workflow_bundle(
    stage3_bundle: Stage3DataBundle,
    *,
    observable_change: bool | None,
    followup_preconditions: dict[str, int] | None = None,
) -> Stage3DataBundle:
    scenario = stage3_bundle.scenarios[0]
    original_script = stage3_bundle.transaction_scripts[0]
    approval_id = "approval.aisc.001"
    approval = Approval(
        approval_id=approval_id,
        case_id=CASE_ID,
        simulation_scope_id=SIMULATION_SCOPE_ID,
        approver_role="CCDS Undergraduate Office",
        requested_action="Review the simulated exception.",
        status=ApprovalStatus.APPROVED,
        observable=False,
        basis=ApprovalBasis.VERIFIED_PUBLIC_ROUTE,
        basis_rule_ids=[str(scenario.curriculum_id)],
        version=1,
        required_document_ids=[],
        requested_at="2028-08-15T12:00:00+08:00",
        decided_at="2028-08-15T12:04:00+08:00",
        **_generation("Approval", approval_id, [str(scenario.curriculum_id)]),
    )
    event = InjectedEvent(
        event_id="event.approval.aisc.001",
        event_type=EventType.APPROVAL_GRANTED,
        target_type=StateTargetType.APPROVAL,
        target_id=approval_id,
        expected_version=1,
        occurs_at="2028-08-15T12:04:00+08:00",
    )
    changes: dict[str, object] = {"status": ApprovalStatus.APPROVED.value}
    if observable_change is not None:
        changes["observable"] = observable_change
    first_id = "transaction.aisc.001"
    first = TransactionResult(
        transaction_id=first_id,
        case_id=CASE_ID,
        action=TransactionAction.REQUEST_APPROVAL,
        action_parameters={"approval_id": approval_id},
        attempt_number=1,
        result_code=TransactionCode.SUCCESS,
        observation=ObservationCode.TRANSACTION_SUCCESS,
        retryable=False,
        message="The simulated approval is granted.",
        event=event,
        precondition_state_versions={approval_id: 1},
        mutations=[
            StateMutation(
                mutation_id="mutation.approval.aisc.001",
                target_type=StateTargetType.APPROVAL,
                target_id=approval_id,
                expected_version=1,
                resulting_version=2,
                changes=changes,
            )
        ],
        occurred_at="2028-08-15T12:04:00+08:00",
        **_generation(
            "TransactionResult", first_id, [str(scenario.curriculum_id)]
        ),
    )
    steps = [first]
    if followup_preconditions is not None:
        second_id = "transaction.aisc.002"
        steps.append(
            TransactionResult(
                transaction_id=second_id,
                case_id=CASE_ID,
                action=TransactionAction.SUBMIT_WAIVER,
                action_parameters={
                    "approval_id": approval_id,
                    "course_code": "SC3098",
                },
                attempt_number=2,
                result_code=TransactionCode.SUCCESS,
                observation=ObservationCode.TRANSACTION_SUCCESS,
                retryable=False,
                message="The approved follow-up succeeds.",
                precondition_state_versions=followup_preconditions,
                mutations=[],
                occurred_at="2028-08-15T12:05:00+08:00",
                **_generation(
                    "TransactionResult", second_id, [str(scenario.curriculum_id)]
                ),
            )
        )
    script = original_script.model_copy(update={"steps": steps})
    approval_path = ResolutionPath(
        path_id="path.fixture.approval",
        steps=[
            ResolutionStep(
                step_id="step.fixture.approval",
                action="Request the declared approval.",
                parameters={"approval_id": approval_id},
                requires_approval=True,
            )
        ],
        rationale="The declared approval resolves the simulated exception.",
        source_rule_ids=[str(scenario.curriculum_id)],
    )
    truth = scenario.ground_truth.model_copy(
        update={
            "valid_initial_paths": [approval_path],
            "requires_human": True,
            "expected_outcome": ExpectedOutcome.RESOLVED,
        }
    )
    approval_scenario = scenario.model_copy(
        update={
            "family": ScenarioFamily.S2_PREREQUISITE_EXCEPTION,
            "injected_event": event,
            "ground_truth": truth,
        }
    )
    counts = dict(stage3_bundle.manifest.record_counts)
    counts["approvals"] = 1
    return replace(
        stage3_bundle,
        manifest=stage3_bundle.manifest.model_copy(
            update={"record_counts": counts}
        ),
        approvals=(approval,),
        transaction_scripts=(script,),
        scenarios=(approval_scenario,),
    )


def test_approval_event_exposes_decision_and_followup_requires_version_two(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    hidden = _approved_workflow_bundle(
        stage3_bundle,
        observable_change=None,
    )
    assert "APPROVAL_EVENT_NOT_OBSERVABLE" in _validation_codes(
        real_repository, real_root, hidden
    )

    missing_version = _approved_workflow_bundle(
        stage3_bundle,
        observable_change=True,
        followup_preconditions={},
    )
    assert "APPROVAL_FOLLOWUP_PRECONDITION_MISMATCH" in _validation_codes(
        real_repository, real_root, missing_version
    )


def test_validator_replays_only_valid_mutable_state_changes(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    approved = _approved_workflow_bundle(
        stage3_bundle,
        observable_change=True,
        followup_preconditions={"approval.aisc.001": 2},
    )
    approval_script = approved.transaction_scripts[0]
    approval_step = approval_script.steps[0]
    approval_mutation = approval_step.mutations[0]
    immutable_change = approval_mutation.model_copy(
        update={
            "changes": {
                **approval_mutation.changes,
                "case_id": "case.changed",
            }
        }
    )
    immutable_step = approval_step.model_copy(
        update={"mutations": [immutable_change]}
    )
    immutable_bundle = replace(
        approved,
        transaction_scripts=(
            approval_script.model_copy(
                update={"steps": [immutable_step, *approval_script.steps[1:]]}
            ),
        ),
    )
    assert "MUTATION_FIELD_NOT_MUTABLE" in _validation_codes(
        real_repository, real_root, immutable_bundle
    )

    scenario = stage3_bundle.scenarios[0]
    state_id = str(scenario.offering_state_ids[0])
    invalid_mutation = StateMutation(
        mutation_id="mutation.fixture.invalid-vacancies",
        target_type=StateTargetType.OFFERING_STATE,
        target_id=state_id,
        expected_version=1,
        resulting_version=2,
        changes={"vacancies": -1},
    )
    script = stage3_bundle.transaction_scripts[0]
    invalid_step = script.steps[0].model_copy(
        update={
            "precondition_state_versions": {state_id: 1},
            "mutations": [invalid_mutation],
        }
    )
    invalid_bundle = replace(
        stage3_bundle,
        transaction_scripts=(script.model_copy(update={"steps": [invalid_step]}),),
    )
    assert "INVALID_MUTATION_RESULT_STATE" in _validation_codes(
        real_repository, real_root, invalid_bundle
    )


def test_transaction_chronology_and_approval_followup_time_are_enforced(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    approved = _approved_workflow_bundle(
        stage3_bundle,
        observable_change=True,
        followup_preconditions={"approval.aisc.001": 2},
    )
    script = approved.transaction_scripts[0]
    assert len(script.steps) == 2
    backdated_followup = script.steps[1].model_copy(
        update={
            "occurred_at": datetime.fromisoformat(
                "2028-08-15T12:04:00+08:00"
            )
        }
    )
    invalid_steps = [script.steps[0], backdated_followup]

    with pytest.raises(
        ValueError,
        match="transaction step times must increase strictly",
    ):
        TransactionScript.model_validate(
            {
                **script.model_dump(mode="python"),
                "steps": invalid_steps,
            }
        )

    changed = replace(
        approved,
        transaction_scripts=(script.model_copy(update={"steps": invalid_steps}),),
    )
    codes = _validation_codes(real_repository, real_root, changed)
    assert "TRANSACTION_STEP_TIME_ORDER" in codes
    assert "APPROVAL_FOLLOWUP_TIME_ORDER" in codes


def test_nonterminal_failure_must_be_retryable(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    script = stage3_bundle.transaction_scripts[0]
    failed = script.steps[0]
    continued_id = "transaction.aisc.002"
    continued = failed.model_copy(
        update={
            "transaction_id": continued_id,
            "attempt_number": 2,
            "result_code": TransactionCode.SUCCESS,
            "observation": ObservationCode.TRANSACTION_SUCCESS,
            "retryable": False,
            "error_code": None,
            "event": None,
            "precondition_state_versions": {},
            "mutations": [],
            "occurred_at": datetime.fromisoformat(
                "2028-08-15T12:06:00+08:00"
            ),
            "seed": _expected_seed("TransactionResult", continued_id),
        }
    )
    invalid_steps = [failed, continued]

    with pytest.raises(
        ValueError,
        match="failed step followed by another attempt must be retryable",
    ):
        TransactionScript.model_validate(
            {
                **script.model_dump(mode="python"),
                "steps": invalid_steps,
            }
        )

    changed = replace(
        stage3_bundle,
        transaction_scripts=(script.model_copy(update={"steps": invalid_steps}),),
    )
    assert "NONTERMINAL_FAILURE_NOT_RETRYABLE" in _validation_codes(
        real_repository, real_root, changed
    )


def test_initial_context_refs_versions_and_time_are_exact(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    scenario = stage3_bundle.scenarios[0]
    state_id = str(scenario.offering_state_ids[0])
    leaked_ref = scenario.model_copy(
        update={
            "initial_state_refs": [
                *scenario.initial_state_refs,
                "state.template.0002",
            ]
        }
    )
    leaked = replace(stage3_bundle, scenarios=(leaked_ref,))
    assert "EXTRANEOUS_INITIAL_REFERENCE" in _validation_codes(
        real_repository, real_root, leaked
    )

    bad_versions = scenario.model_copy(
        update={
            "initial_state": {
                **scenario.initial_state,
                "observed_state_versions": {state_id: 999},
            }
        }
    )
    versioned = replace(stage3_bundle, scenarios=(bad_versions,))
    assert "OBSERVED_STATE_VERSION_MISMATCH" in _validation_codes(
        real_repository, real_root, versioned
    )

    bad_time = scenario.model_copy(
        update={
            "initial_state": {
                **scenario.initial_state,
                "request_time": "2028-08-15T12:01:00+08:00",
            }
        }
    )
    timed = replace(stage3_bundle, scenarios=(bad_time,))
    assert "SCENARIO_REQUEST_TIME_MISMATCH" in _validation_codes(
        real_repository, real_root, timed
    )


def test_default_validation_enforces_stage3_scale(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    with pytest.raises(DataIntegrityError) as caught:
        SimulatedDataRepository(
            real_repository,
            stage3_bundle,
            real_directory=real_root,
        )
    assert any(
        issue["code"] == "STAGE3_COUNT_MISMATCH" for issue in caught.value.issues
    )


def test_repository_returns_defensive_context_and_entities(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    repository = SimulatedDataRepository(
        real_repository,
        stage3_bundle,
        real_directory=real_root,
        enforce_expected_counts=False,
    )
    student = repository.get_student(STUDENT_ID)
    student.academic_standing = "CHANGED"
    assert repository.get_student(STUDENT_ID).academic_standing == "GOOD"

    context = repository.to_agent_context(SCENARIO_ID)
    context.initial_state["request_received"] = False
    assert repository.to_agent_context(SCENARIO_ID).initial_state == {
        "request_received": True,
        "target_course": "SC3098",
        "request_time": "2028-08-15T12:00:00+08:00",
        "observed_state_versions": {
            str(stage3_bundle.scenarios[0].offering_state_ids[0]): 1
        },
    }
    assert "ground_truth" not in context.model_dump(mode="json")
    assert "transaction_script_id" not in context.model_dump(mode="json")


def test_validator_reports_actionable_unknown_reference(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    bad_case = stage3_bundle.exception_cases[0].model_copy(
        update={"student_id": "SIM-UNKNOWN-001"}
    )
    changed = replace(stage3_bundle, exception_cases=(bad_case,))
    issues = validate_stage3_data(
        real_repository,
        changed,
        real_directory=real_root,
        enforce_expected_counts=False,
    )
    assert any(
        issue.code == "UNKNOWN_STUDENT"
        and issue.dataset == "exception_cases"
        and issue.field == "student_id"
        for issue in issues
    )


def test_loaders_enforce_top_level_shape_and_duplicate_ids(
    tmp_path: Path, stage3_bundle: Stage3DataBundle
) -> None:
    object_path = tmp_path / "manifest.json"
    object_path.write_text("[]", encoding="utf-8")
    with pytest.raises(DataShapeError, match="expected a JSON object"):
        load_generation_manifest(object_path)

    scopes_path = tmp_path / "scopes.json"
    payload = stage3_bundle.simulation_scopes[0].model_dump_json()
    scopes_path.write_text(f"[{payload},{payload}]", encoding="utf-8")
    with pytest.raises(DataShapeError, match="duplicate simulation_scope_id"):
        load_simulation_scopes(scopes_path)


def test_missing_offering_state_breaks_exact_template_coverage(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    changed = replace(
        stage3_bundle,
        offering_states=stage3_bundle.offering_states[1:],
    )
    issues = validate_stage3_data(
        real_repository,
        changed,
        real_directory=real_root,
        enforce_expected_counts=False,
    )
    assert any(issue.code == "MISSING_OFFERING_STATE" for issue in issues)


def test_reverse_dependencies_use_each_entity_primary_id(
    stage3_bundle: Stage3DataBundle,
) -> None:
    assert _record_id(stage3_bundle.students[0]) == STUDENT_ID
    assert _record_id(stage3_bundle.degree_audits[0]) == AUDIT_ID
    assert _record_id(stage3_bundle.current_registrations[0]) == REGISTRATION_ID
    assert _record_id(stage3_bundle.exception_cases[0]) == CASE_ID
    assert _record_id(stage3_bundle.transaction_scripts[0]) == SCRIPT_ID
    assert _record_id(stage3_bundle.scenarios[0]) == SCENARIO_ID


def test_validator_rejects_requirement_ledger_drift(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    audit = stage3_bundle.degree_audits[0]
    first = audit.requirement_results[0]
    assert first.required_aus is not None
    changed_first = first.model_copy(
        update={
            "earned_aus": first.earned_aus + 1,
            "required_aus": first.required_aus + 1,
        }
    )
    bad_audit = audit.model_copy(
        update={
            "requirement_results": [
                changed_first,
                *audit.requirement_results[1:],
            ]
        }
    )
    changed = replace(stage3_bundle, degree_audits=(bad_audit,))

    issues = validate_stage3_data(
        real_repository,
        changed,
        real_directory=real_root,
        enforce_expected_counts=False,
    )
    codes = {issue.code for issue in issues}

    assert "AUDIT_EARNED_LEDGER_MISMATCH" in codes
    assert "AUDIT_REQUIRED_LEDGER_MISMATCH" in codes


def test_validator_reconciles_category_exemptions_per_requirement(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    curriculum = real_repository.get_curriculum("curriculum.aisc.ay2025-26")
    source_requirement, other_requirement = curriculum.requirements[:2]
    credit = Decimal("3")
    student = stage3_bundle.students[0]
    audit = stage3_bundle.degree_audits[0]
    exemption = Exemption(
        exemption_id="exemption.sim-aisc-001.category-credit",
        aus_awarded=credit,
        category=source_requirement.category,
        reason="Test-only category credit.",
    )
    aligned_student = student.model_copy(
        update={"earned_aus": credit, "exemptions": [exemption]}
    )
    aligned_results = [
        result.model_copy(update={"earned_aus": credit})
        if result.requirement_id == source_requirement.requirement_id
        else result
        for result in audit.requirement_results
    ]
    aligned_audit = audit.model_copy(
        update={"requirement_results": aligned_results, "total_earned_aus": credit}
    )
    aligned = replace(
        stage3_bundle,
        students=(aligned_student,),
        degree_audits=(aligned_audit,),
    )

    aligned_issues = validate_stage3_data(
        real_repository,
        aligned,
        real_directory=real_root,
        enforce_expected_counts=False,
    )
    assert not {
        "AUDIT_REQUIREMENT_CREDIT_MISMATCH",
        "AUDIT_CATEGORY_EXEMPTION_OVERALLOCATION",
        "AUDIT_UNALLOCATED_STUDENT_CREDIT",
    } & {issue.code for issue in aligned_issues}

    misplaced_exemption = exemption.model_copy(
        update={"category": other_requirement.category}
    )
    misplaced_student = aligned_student.model_copy(
        update={"exemptions": [misplaced_exemption]}
    )
    misplaced = replace(aligned, students=(misplaced_student,))
    misplaced_codes = {
        issue.code
        for issue in validate_stage3_data(
            real_repository,
            misplaced,
            real_directory=real_root,
            enforce_expected_counts=False,
        )
    }

    assert "AUDIT_REQUIREMENT_CREDIT_MISMATCH" in misplaced_codes
    assert "AUDIT_CATEGORY_EXEMPTION_OVERALLOCATION" in misplaced_codes


def test_validator_requires_each_earned_course_in_requirement_progress(
    real_repository: RealDataRepository,
    real_root: Path,
    stage3_bundle: Stage3DataBundle,
) -> None:
    curriculum = real_repository.get_curriculum("curriculum.aisc.ay2025-26")
    plan_item = next(
        item
        for item in curriculum.study_plan
        if item.course_code is not None and item.requirement_id is not None
    )
    course = real_repository.get_course(str(plan_item.course_code))
    completed = CompletedCourse(
        course_code=course.code,
        grade="B+",
        aus_earned=course.aus,
        credit_status=CreditStatus.EARNED,
        academic_year="AY2027-28",
        semester=Semester.SEMESTER_2,
        attempt=1,
    )
    student = stage3_bundle.students[0].model_copy(
        update={"completed_courses": [completed], "earned_aus": course.aus}
    )
    audit = stage3_bundle.degree_audits[0]
    aligned_results = [
        result.model_copy(
            update={"earned_aus": course.aus, "completed_courses": [course.code]}
        )
        if result.requirement_id == plan_item.requirement_id
        else result
        for result in audit.requirement_results
    ]
    aligned_audit = audit.model_copy(
        update={
            "requirement_results": aligned_results,
            "total_earned_aus": course.aus,
        }
    )
    aligned = replace(
        stage3_bundle,
        students=(student,),
        degree_audits=(aligned_audit,),
    )
    aligned_codes = {
        issue.code
        for issue in validate_stage3_data(
            real_repository,
            aligned,
            real_directory=real_root,
            enforce_expected_counts=False,
        )
    }
    assert "AUDIT_CREDITED_COURSE_NOT_ALLOCATED" not in aligned_codes
    assert "AUDIT_REQUIREMENT_CREDIT_MISMATCH" not in aligned_codes

    omitted_results = [
        result.model_copy(update={"completed_courses": []})
        if result.requirement_id == plan_item.requirement_id
        else result
        for result in aligned_audit.requirement_results
    ]
    omitted_audit = aligned_audit.model_copy(
        update={"requirement_results": omitted_results}
    )
    omitted = replace(aligned, degree_audits=(omitted_audit,))
    omitted_codes = {
        issue.code
        for issue in validate_stage3_data(
            real_repository,
            omitted,
            real_directory=real_root,
            enforce_expected_counts=False,
        )
    }

    assert "AUDIT_CREDITED_COURSE_NOT_ALLOCATED" in omitted_codes
