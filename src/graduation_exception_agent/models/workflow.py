"""Administrative case, approval, transaction, and scenario contracts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from enum import StrEnum

from pydantic import Field, JsonValue, field_validator, model_validator

from graduation_exception_agent.models.common import (
    DomainModel,
    GeneratedModel,
    Identifier,
    NonEmptyText,
    SyntheticStudentId,
)


def _unique(values: list[str], field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


def _timezone_aware(value: datetime | None, field_name: str) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value


_LEAKAGE_KEYS = {
    "approval_decision",
    "approval_status",
    "decision_reason",
    "event_type",
    "expected_outcome",
    "family",
    "final_state",
    "future_event",
    "ground_truth",
    "injected_event",
    "invalid_paths",
    "post_event_state",
    "scenario_id",
    "script_id",
    "split",
    "terminal_profile",
    "transaction_script",
    "transaction_script_id",
    "valid_final_paths",
    "valid_initial_paths",
}


def _reject_recursive_leakage(value: JsonValue, path: str = "initial_state") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = key.strip().lower()
            if normalized in _LEAKAGE_KEYS:
                raise ValueError(f"{path} contains evaluator-only key {key!r}")
            _reject_recursive_leakage(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_recursive_leakage(nested, f"{path}[{index}]")


class ExceptionCaseType(StrEnum):
    GRADUATION_REQUIREMENT = "GRADUATION_REQUIREMENT"
    REGISTRATION_AFTER_DEADLINE = "REGISTRATION_AFTER_DEADLINE"
    PREREQUISITE_WAIVER = "PREREQUISITE_WAIVER"
    WORKLOAD_OVERLOAD = "WORKLOAD_OVERLOAD"
    COURSE_UNAVAILABLE = "COURSE_UNAVAILABLE"
    TIMETABLE_CONFLICT = "TIMETABLE_CONFLICT"
    CROSS_PROGRAMME = "CROSS_PROGRAMME"
    OTHER = "OTHER"


class CaseState(StrEnum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    WAITING_FOR_STUDENT = "WAITING_FOR_STUDENT"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    READY_FOR_ACTION = "READY_FOR_ACTION"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    CLOSED = "CLOSED"


class ApprovalStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


class ApprovalBasis(StrEnum):
    VERIFIED_PUBLIC_ROUTE = "VERIFIED_PUBLIC_ROUTE"
    SIMULATED_POLICY = "SIMULATED_POLICY"
    UNKNOWN_PUBLIC_ROUTE = "UNKNOWN_PUBLIC_ROUTE"


class TransactionAction(StrEnum):
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    SUBMIT_REGISTRATION = "SUBMIT_REGISTRATION"
    SUBMIT_EXCEPTION = "SUBMIT_EXCEPTION"
    SUBMIT_WAIVER = "SUBMIT_WAIVER"


class TransactionCode(StrEnum):
    SUCCESS = "SUCCESS"
    EXCEPTION_SUBMISSION_SUCCESS = "EXCEPTION_SUBMISSION_SUCCESS"
    MODULE_FULL = "MODULE_FULL"
    CLASS_UNAVAILABLE = "CLASS_UNAVAILABLE"
    PREREQUISITE_FAILURE = "PREREQUISITE_FAILURE"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    STALE_STATE = "STALE_STATE"
    TEMPORARY_SYSTEM_FAILURE = "TEMPORARY_SYSTEM_FAILURE"
    REQUIRED_INFORMATION_MISSING = "REQUIRED_INFORMATION_MISSING"


class ObservationCode(StrEnum):
    TRANSACTION_SUCCESS = "TRANSACTION_SUCCESS"
    MODULE_FULL = "MODULE_FULL"
    CLASS_UNAVAILABLE = "CLASS_UNAVAILABLE"
    PREREQUISITE_FAILURE = "PREREQUISITE_FAILURE"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    STALE_STATE = "STALE_STATE"
    TEMPORARY_FAILURE = "TEMPORARY_FAILURE"
    REQUIRED_INFORMATION_MISSING = "REQUIRED_INFORMATION_MISSING"


class EventType(StrEnum):
    """The exact eight controlled simulator event types."""

    VACANCY_BECOMES_ZERO = "VACANCY_BECOMES_ZERO"
    CLASS_BECOMES_UNAVAILABLE = "CLASS_BECOMES_UNAVAILABLE"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    TEMPORARY_TRANSACTION_FAILURE = "TEMPORARY_TRANSACTION_FAILURE"
    STATE_CHANGED_BEFORE_COMMIT = "STATE_CHANGED_BEFORE_COMMIT"
    REQUIRED_INFORMATION_MISSING = "REQUIRED_INFORMATION_MISSING"


class StateTargetType(StrEnum):
    OFFERING_STATE = "OFFERING_STATE"
    APPROVAL = "APPROVAL"
    REGISTRATION = "REGISTRATION"
    CASE = "CASE"
    TRANSACTION = "TRANSACTION"


class ScenarioFamily(StrEnum):
    S1_NORMAL_RECOVERY = "S1"
    S2_PREREQUISITE_EXCEPTION = "S2"
    S3_MULTI_SOURCE = "S3"
    S4_CONSTRAINT_HEAVY = "S4"
    S5_CROSS_PROGRAMME = "S5"
    S6_NO_VALID_PATH = "S6"
    S7_DYNAMIC_FAILURE = "S7"


class ScenarioSplit(StrEnum):
    DEVELOPMENT = "development"
    DEMO = "demo"
    EVALUATION = "evaluation"


class ExpectedOutcome(StrEnum):
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    FAILED = "FAILED"


class SupportingDocument(DomainModel):
    document_id: Identifier
    document_type: Identifier
    provided: bool
    verified: bool | None = None

    @model_validator(mode="after")
    def verification_requires_document(self) -> SupportingDocument:
        if not self.provided and self.verified is not None:
            raise ValueError("an absent document cannot have a verification result")
        return self


class EvidenceReference(DomainModel):
    evidence_id: Identifier
    evidence_type: Identifier
    reference: NonEmptyText
    source_id: Identifier | None = None


class ExceptionCase(GeneratedModel):
    """Observable case facts; expected decisions remain evaluator-only."""

    case_id: Identifier
    student_id: SyntheticStudentId
    simulation_scope_id: Identifier
    audit_id: Identifier
    registration_id: Identifier
    scenario_time: datetime
    problem_type: ExceptionCaseType
    reason: NonEmptyText
    goal: NonEmptyText
    requested_action: NonEmptyText
    submission_ready: bool | None = None
    unresolved_questions: list[Identifier] = Field(default_factory=list)
    policy_section_ids: list[Identifier] = Field(default_factory=list)
    assumption_ids: list[Identifier] = Field(default_factory=list)
    supporting_documents: list[SupportingDocument] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    state: CaseState
    created_at: datetime

    @field_validator("scenario_time", "created_at")
    @classmethod
    def timezone_aware_case_times(cls, value: datetime, info: object) -> datetime:
        field_name = getattr(info, "field_name", "timestamp")
        validated = _timezone_aware(value, field_name)
        assert validated is not None
        return validated

    @field_validator(
        "unresolved_questions",
        "policy_section_ids",
        "assumption_ids",
    )
    @classmethod
    def unique_case_links(cls, value: list[str], info: object) -> list[str]:
        return _unique(value, getattr(info, "field_name", "links"))

    @model_validator(mode="after")
    def validate_case(self) -> ExceptionCase:
        _unique(
            [item.document_id for item in self.supporting_documents],
            "document_ids",
        )
        _unique([item.evidence_id for item in self.evidence], "evidence_ids")
        if self.created_at > self.scenario_time:
            raise ValueError("created_at must not follow scenario_time")
        if self.submission_ready is False and not self.unresolved_questions:
            raise ValueError(
                "an incomplete submission requires at least one unresolved question"
            )
        if self.submission_ready is not False and self.unresolved_questions:
            raise ValueError(
                "unresolved questions require submission_ready to be false"
            )
        return self


class Approval(GeneratedModel):
    approval_id: Identifier
    case_id: Identifier
    simulation_scope_id: Identifier
    approver_role: NonEmptyText
    requested_action: NonEmptyText
    status: ApprovalStatus
    observable: bool
    basis: ApprovalBasis
    basis_rule_ids: list[Identifier] = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    required_document_ids: list[Identifier] = Field(default_factory=list)
    decision_reason: NonEmptyText | None = None
    requested_at: datetime
    decided_at: datetime | None = None

    @field_validator("required_document_ids", "basis_rule_ids")
    @classmethod
    def unique_approval_links(cls, value: list[str], info: object) -> list[str]:
        return _unique(value, getattr(info, "field_name", "links"))

    @field_validator("requested_at")
    @classmethod
    def timezone_aware_requested_at(cls, value: datetime) -> datetime:
        validated = _timezone_aware(value, "requested_at")
        assert validated is not None
        return validated

    @field_validator("decided_at")
    @classmethod
    def timezone_aware_decided_at(cls, value: datetime | None) -> datetime | None:
        return _timezone_aware(value, "decided_at")

    @model_validator(mode="after")
    def validate_decision(self) -> Approval:
        if self.status is ApprovalStatus.REJECTED and not self.decision_reason:
            raise ValueError("a rejected approval requires decision_reason")
        if self.status is ApprovalStatus.PENDING:
            if self.decided_at is not None or self.decision_reason is not None:
                raise ValueError("a pending approval cannot contain a final decision")
        elif self.decided_at is None:
            raise ValueError("an approved or rejected approval requires decided_at")
        if self.decided_at and self.decided_at < self.requested_at:
            raise ValueError("decided_at must not precede requested_at")
        return self


class StateMutation(DomainModel):
    mutation_id: Identifier
    target_type: StateTargetType
    target_id: Identifier
    expected_version: int | None = Field(default=None, ge=1)
    resulting_version: int | None = Field(default=None, ge=1)
    changes: dict[Identifier, JsonValue] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_versions(self) -> StateMutation:
        if (self.expected_version is None) != (self.resulting_version is None):
            raise ValueError("mutation versions must be provided together")
        if (
            self.expected_version is not None
            and self.resulting_version != self.expected_version + 1
        ):
            raise ValueError("resulting_version must increment expected_version by one")
        return self


class InjectedEvent(DomainModel):
    event_id: Identifier
    event_type: EventType
    target_type: StateTargetType
    target_id: Identifier
    expected_version: int | None = Field(default=None, ge=1)
    occurs_at: datetime

    @field_validator("occurs_at")
    @classmethod
    def timezone_aware_event_time(cls, value: datetime) -> datetime:
        validated = _timezone_aware(value, "occurs_at")
        assert validated is not None
        return validated

    @model_validator(mode="after")
    def validate_target(self) -> InjectedEvent:
        offering_events = {
            EventType.VACANCY_BECOMES_ZERO,
            EventType.CLASS_BECOMES_UNAVAILABLE,
            EventType.STATE_CHANGED_BEFORE_COMMIT,
        }
        approval_events = {
            EventType.APPROVAL_GRANTED,
            EventType.APPROVAL_REJECTED,
            EventType.APPROVAL_PENDING,
        }
        if self.event_type in offering_events:
            if self.target_type is not StateTargetType.OFFERING_STATE:
                raise ValueError("offering events must target OFFERING_STATE")
            if self.expected_version is None:
                raise ValueError("versioned offering events require expected_version")
        if self.event_type in approval_events:
            if self.target_type is not StateTargetType.APPROVAL:
                raise ValueError("approval events must target APPROVAL")
            if self.expected_version is None:
                raise ValueError("approval events require expected_version")
        return self


_EXPECTED_OBSERVATION = {
    TransactionCode.SUCCESS: ObservationCode.TRANSACTION_SUCCESS,
    TransactionCode.EXCEPTION_SUBMISSION_SUCCESS: ObservationCode.TRANSACTION_SUCCESS,
    TransactionCode.MODULE_FULL: ObservationCode.MODULE_FULL,
    TransactionCode.CLASS_UNAVAILABLE: ObservationCode.CLASS_UNAVAILABLE,
    TransactionCode.PREREQUISITE_FAILURE: ObservationCode.PREREQUISITE_FAILURE,
    TransactionCode.APPROVAL_REJECTED: ObservationCode.APPROVAL_REJECTED,
    TransactionCode.APPROVAL_PENDING: ObservationCode.APPROVAL_PENDING,
    TransactionCode.STALE_STATE: ObservationCode.STALE_STATE,
    TransactionCode.TEMPORARY_SYSTEM_FAILURE: ObservationCode.TEMPORARY_FAILURE,
    TransactionCode.REQUIRED_INFORMATION_MISSING: (
        ObservationCode.REQUIRED_INFORMATION_MISSING
    ),
}


class TransactionResult(GeneratedModel):
    transaction_id: Identifier
    case_id: Identifier
    action: TransactionAction
    action_parameters: dict[Identifier, JsonValue] = Field(default_factory=dict)
    attempt_number: int = Field(ge=1)
    result_code: TransactionCode
    observation: ObservationCode
    retryable: bool
    message: NonEmptyText
    error_code: Identifier | None = None
    event: InjectedEvent | None = None
    precondition_state_versions: dict[Identifier, int] = Field(default_factory=dict)
    mutations: list[StateMutation] = Field(default_factory=list)
    occurred_at: datetime

    @field_validator("precondition_state_versions")
    @classmethod
    def positive_state_versions(cls, value: dict[str, int]) -> dict[str, int]:
        if any(version < 1 for version in value.values()):
            raise ValueError("precondition state versions must be positive")
        return value

    @field_validator("occurred_at")
    @classmethod
    def timezone_aware_occurred_at(cls, value: datetime) -> datetime:
        validated = _timezone_aware(value, "occurred_at")
        assert validated is not None
        return validated

    @model_validator(mode="after")
    def validate_result(self) -> TransactionResult:
        expected_observation = _EXPECTED_OBSERVATION[self.result_code]
        if self.observation is not expected_observation:
            raise ValueError(
                f"{self.result_code.value} requires {expected_observation.value} observation"
            )
        successful = self.result_code in {
            TransactionCode.SUCCESS,
            TransactionCode.EXCEPTION_SUBMISSION_SUCCESS,
        }
        if successful:
            if self.error_code is not None or self.retryable:
                raise ValueError(
                    "successful transactions cannot be retryable or contain error_code"
                )
        elif self.error_code is None:
            raise ValueError("failed transactions require an explicit error_code")
        if self.result_code in {
            TransactionCode.STALE_STATE,
            TransactionCode.TEMPORARY_SYSTEM_FAILURE,
        } and not self.retryable:
            raise ValueError("stale and temporary failures must be retryable")
        _unique([mutation.mutation_id for mutation in self.mutations], "mutation_ids")
        if self.event is None:
            return self
        if self.event.occurs_at > self.occurred_at:
            raise ValueError("event cannot occur after its transaction result")
        if self.event.expected_version is not None:
            actual = self.precondition_state_versions.get(self.event.target_id)
            if actual != self.event.expected_version:
                raise ValueError("event expected_version must match the precondition")
        self._validate_event_coherence()
        return self

    def _validate_event_coherence(self) -> None:
        assert self.event is not None
        expectations: dict[EventType, TransactionCode] = {
            EventType.VACANCY_BECOMES_ZERO: TransactionCode.MODULE_FULL,
            EventType.CLASS_BECOMES_UNAVAILABLE: TransactionCode.CLASS_UNAVAILABLE,
            EventType.APPROVAL_GRANTED: TransactionCode.SUCCESS,
            EventType.APPROVAL_REJECTED: TransactionCode.APPROVAL_REJECTED,
            EventType.APPROVAL_PENDING: TransactionCode.APPROVAL_PENDING,
            EventType.TEMPORARY_TRANSACTION_FAILURE: (
                TransactionCode.TEMPORARY_SYSTEM_FAILURE
            ),
            EventType.STATE_CHANGED_BEFORE_COMMIT: TransactionCode.STALE_STATE,
            EventType.REQUIRED_INFORMATION_MISSING: (
                TransactionCode.REQUIRED_INFORMATION_MISSING
            ),
        }
        if self.result_code is not expectations[self.event.event_type]:
            raise ValueError("event type and transaction result are inconsistent")
        mutation_required = self.event.event_type in {
            EventType.VACANCY_BECOMES_ZERO,
            EventType.CLASS_BECOMES_UNAVAILABLE,
            EventType.APPROVAL_GRANTED,
            EventType.APPROVAL_REJECTED,
            EventType.APPROVAL_PENDING,
            EventType.STATE_CHANGED_BEFORE_COMMIT,
        }
        targeted = [
            mutation
            for mutation in self.mutations
            if mutation.target_type is self.event.target_type
            and mutation.target_id == self.event.target_id
        ]
        if mutation_required and not targeted:
            raise ValueError("state-changing events require a targeted mutation")
        if not mutation_required and self.mutations:
            raise ValueError("non-mutating failure events cannot contain mutations")
        if self.event.event_type is EventType.VACANCY_BECOMES_ZERO:
            if not any(mutation.changes.get("vacancies") == 0 for mutation in targeted):
                raise ValueError("vacancy event must set vacancies to zero")
        if self.event.event_type is EventType.CLASS_BECOMES_UNAVAILABLE:
            if not any(
                mutation.changes.get("runtime_status") == "UNAVAILABLE"
                and mutation.changes.get("available") is False
                for mutation in targeted
            ):
                raise ValueError("class-unavailable event must set unavailable state")
        if self.event.event_type is EventType.STATE_CHANGED_BEFORE_COMMIT:
            if not targeted:
                raise ValueError("stale-state event must advance the targeted state")
        approval_status = {
            EventType.APPROVAL_GRANTED: "APPROVED",
            EventType.APPROVAL_REJECTED: "REJECTED",
            EventType.APPROVAL_PENDING: "PENDING",
        }.get(self.event.event_type)
        if approval_status is not None and not any(
            mutation.changes.get("status") == approval_status for mutation in targeted
        ):
            raise ValueError("approval event must set its matching approval status")


class TransactionScript(GeneratedModel):
    script_id: Identifier
    case_id: Identifier
    simulation_scope_id: Identifier
    steps: list[TransactionResult] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_steps(self) -> TransactionScript:
        if any(step.case_id != self.case_id for step in self.steps):
            raise ValueError("every transaction step must reference the script case")
        attempts = [step.attempt_number for step in self.steps]
        if attempts != list(range(1, len(self.steps) + 1)):
            raise ValueError("transaction attempts must be ordered consecutively from 1")
        if any(
            later.occurred_at <= earlier.occurred_at
            for earlier, later in zip(self.steps, self.steps[1:])
        ):
            raise ValueError(
                "transaction step times must increase strictly in attempt order"
            )
        successful = {
            TransactionCode.SUCCESS,
            TransactionCode.EXCEPTION_SUBMISSION_SUCCESS,
        }
        if any(
            step.result_code not in successful and not step.retryable
            for step in self.steps[:-1]
        ):
            raise ValueError(
                "a failed step followed by another attempt must be retryable"
            )
        _unique([step.transaction_id for step in self.steps], "transaction_ids")
        return self


class ResolutionStep(DomainModel):
    step_id: Identifier
    action: NonEmptyText
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    requires_approval: bool = False


class ResolutionPath(DomainModel):
    path_id: Identifier
    steps: list[ResolutionStep] = Field(min_length=1)
    rationale: NonEmptyText
    source_rule_ids: list[Identifier] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_path(self) -> ResolutionPath:
        _unique([step.step_id for step in self.steps], "step_ids")
        _unique(self.source_rule_ids, "source_rule_ids")
        return self


class ScenarioGroundTruth(DomainModel):
    """Hidden evaluator-only expectations, never exposed through agent context."""

    valid_initial_paths: list[ResolutionPath] = Field(default_factory=list)
    valid_final_paths: list[ResolutionPath] = Field(default_factory=list)
    invalid_paths: list[ResolutionPath] = Field(default_factory=list)
    requires_human: bool
    expected_outcome: ExpectedOutcome
    expected_response: NonEmptyText

    @model_validator(mode="after")
    def disjoint_path_sets(self) -> ScenarioGroundTruth:
        groups = [self.valid_initial_paths, self.valid_final_paths, self.invalid_paths]
        path_ids = [[path.path_id for path in group] for group in groups]
        for ids in path_ids:
            _unique(ids, "path_ids")
        _unique(
            [path_id for ids in path_ids for path_id in ids],
            "path_ids across ground-truth groups",
        )
        return self


class ScenarioContext(DomainModel):
    """Safe, observable subset that may be supplied to the future agent."""

    context_id: Identifier
    simulation_scope_id: Identifier
    student_id: SyntheticStudentId
    curriculum_id: Identifier
    audit_id: Identifier
    registration_id: Identifier
    case_id: Identifier
    offering_state_ids: list[Identifier]
    initial_state_refs: list[Identifier]
    initial_state: dict[str, JsonValue]

    @model_validator(mode="after")
    def reject_hidden_context(self) -> ScenarioContext:
        _reject_recursive_leakage(self.initial_state)
        return self


class Scenario(GeneratedModel):
    scenario_id: Identifier
    family: ScenarioFamily
    split: ScenarioSplit
    simulation_scope_id: Identifier
    student_id: SyntheticStudentId
    curriculum_id: Identifier
    audit_id: Identifier
    registration_id: Identifier
    case_id: Identifier
    offering_state_ids: list[Identifier] = Field(min_length=1)
    transaction_script_id: Identifier
    initial_state_refs: list[Identifier] = Field(min_length=1)
    initial_state: dict[str, JsonValue] = Field(default_factory=dict)
    injected_event: InjectedEvent | None = None
    ground_truth: ScenarioGroundTruth

    @field_validator("offering_state_ids", "initial_state_refs")
    @classmethod
    def unique_state_refs(cls, value: list[str], info: object) -> list[str]:
        return _unique(value, getattr(info, "field_name", "state_refs"))

    @model_validator(mode="after")
    def validate_scenario(self) -> Scenario:
        _reject_recursive_leakage(self.initial_state)
        if self.transaction_script_id in self.initial_state_refs:
            raise ValueError("transaction script cannot be exposed as initial state")
        dynamic_events = {
            EventType.VACANCY_BECOMES_ZERO,
            EventType.CLASS_BECOMES_UNAVAILABLE,
            EventType.TEMPORARY_TRANSACTION_FAILURE,
            EventType.STATE_CHANGED_BEFORE_COMMIT,
        }
        if self.family is ScenarioFamily.S7_DYNAMIC_FAILURE:
            if self.injected_event is None:
                raise ValueError("S7 scenarios require an injected event")
            if self.injected_event.event_type not in dynamic_events:
                raise ValueError("S7 scenarios require a dynamic failure event")
        approval_events = {
            EventType.APPROVAL_GRANTED,
            EventType.APPROVAL_REJECTED,
            EventType.APPROVAL_PENDING,
        }
        if (
            self.injected_event is not None
            and self.injected_event.event_type in approval_events
            and not self.ground_truth.requires_human
        ):
            raise ValueError("approval events require human involvement in ground truth")
        if (
            self.injected_event is not None
            and self.injected_event.target_type is StateTargetType.OFFERING_STATE
            and self.injected_event.target_id not in self.offering_state_ids
        ):
            raise ValueError("offering event target must be linked by the scenario")
        if self.ground_truth.expected_outcome is ExpectedOutcome.RESOLVED:
            if not (
                self.ground_truth.valid_initial_paths
                or self.ground_truth.valid_final_paths
            ):
                raise ValueError("resolved scenarios require a valid resolution path")
            if self.family is ScenarioFamily.S7_DYNAMIC_FAILURE and not (
                self.ground_truth.valid_initial_paths
                and self.ground_truth.valid_final_paths
            ):
                raise ValueError("resolved S7 scenarios require initial and final paths")
        return self

    def to_agent_context(self) -> ScenarioContext:
        """Return only observable initial references and a defensive state copy."""

        return ScenarioContext(
            context_id=f"context.{self.case_id}",
            simulation_scope_id=self.simulation_scope_id,
            student_id=self.student_id,
            curriculum_id=self.curriculum_id,
            audit_id=self.audit_id,
            registration_id=self.registration_id,
            case_id=self.case_id,
            offering_state_ids=list(self.offering_state_ids),
            initial_state_refs=list(self.initial_state_refs),
            initial_state=deepcopy(self.initial_state),
        )
