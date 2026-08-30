"""Administrative case, approval, transaction, and scenario contracts."""

from __future__ import annotations

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
    """The exact eight controlled simulator event types from the specification."""

    VACANCY_BECOMES_ZERO = "VACANCY_BECOMES_ZERO"
    CLASS_BECOMES_UNAVAILABLE = "CLASS_BECOMES_UNAVAILABLE"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    TEMPORARY_TRANSACTION_FAILURE = "TEMPORARY_TRANSACTION_FAILURE"
    STATE_CHANGED_BEFORE_COMMIT = "STATE_CHANGED_BEFORE_COMMIT"
    REQUIRED_INFORMATION_MISSING = "REQUIRED_INFORMATION_MISSING"


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
    """Agent-facing case information with no hidden expected decision fields."""

    case_id: Identifier
    student_id: SyntheticStudentId
    problem_type: ExceptionCaseType
    reason: NonEmptyText
    goal: NonEmptyText
    requested_action: NonEmptyText
    supporting_documents: list[SupportingDocument] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    state: CaseState
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def timezone_aware_created_at(cls, value: datetime) -> datetime:
        validated = _timezone_aware(value, "created_at")
        assert validated is not None
        return validated

    @model_validator(mode="after")
    def unique_case_references(self) -> ExceptionCase:
        _unique(
            [item.document_id for item in self.supporting_documents],
            "document_ids",
        )
        _unique([item.evidence_id for item in self.evidence], "evidence_ids")
        return self


class Approval(GeneratedModel):
    approval_id: Identifier
    case_id: Identifier
    approver_role: NonEmptyText
    requested_action: NonEmptyText
    status: ApprovalStatus
    required_document_ids: list[Identifier] = Field(default_factory=list)
    decision_reason: NonEmptyText | None = None
    requested_at: datetime
    decided_at: datetime | None = None

    @field_validator("required_document_ids")
    @classmethod
    def unique_documents(cls, value: list[str]) -> list[str]:
        return _unique(value, "required_document_ids")

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


class TransactionResult(GeneratedModel):
    transaction_id: Identifier
    case_id: Identifier
    action: TransactionAction
    attempt_number: int = Field(ge=1)
    result_code: TransactionCode
    observation: ObservationCode
    retryable: bool
    message: NonEmptyText
    error_code: Identifier | None = None
    state_changes: dict[str, JsonValue] = Field(default_factory=dict)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def timezone_aware_occurred_at(cls, value: datetime) -> datetime:
        validated = _timezone_aware(value, "occurred_at")
        assert validated is not None
        return validated

    @model_validator(mode="after")
    def validate_result(self) -> TransactionResult:
        successful = self.result_code in {
            TransactionCode.SUCCESS,
            TransactionCode.EXCEPTION_SUBMISSION_SUCCESS,
        }
        if successful:
            if self.error_code is not None or self.retryable:
                raise ValueError(
                    "successful transactions cannot be retryable or contain error_code"
                )
            if self.observation is not ObservationCode.TRANSACTION_SUCCESS:
                raise ValueError(
                    "successful transactions require TRANSACTION_SUCCESS observation"
                )
        elif self.error_code is None:
            raise ValueError("failed transactions require an explicit error_code")
        return self


class TransactionScript(GeneratedModel):
    script_id: Identifier
    case_id: Identifier
    steps: list[TransactionResult] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_steps(self) -> TransactionScript:
        if any(step.case_id != self.case_id for step in self.steps):
            raise ValueError("every transaction step must reference the script case")
        attempts = [step.attempt_number for step in self.steps]
        expected = list(range(1, len(self.steps) + 1))
        if attempts != expected:
            raise ValueError("transaction attempts must be ordered consecutively from 1")
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

    @model_validator(mode="after")
    def disjoint_path_sets(self) -> ScenarioGroundTruth:
        groups = [
            self.valid_initial_paths,
            self.valid_final_paths,
            self.invalid_paths,
        ]
        path_ids = [[path.path_id for path in group] for group in groups]
        for ids in path_ids:
            _unique(ids, "path_ids")
        all_ids = [path_id for ids in path_ids for path_id in ids]
        _unique(all_ids, "path_ids across ground-truth groups")
        return self


class ScenarioContext(DomainModel):
    """Safe subset that may be supplied to the future agent."""

    scenario_id: Identifier
    student_id: SyntheticStudentId
    case_id: Identifier
    initial_state_refs: list[Identifier]
    initial_state: dict[str, JsonValue]


class Scenario(GeneratedModel):
    scenario_id: Identifier
    family: ScenarioFamily
    split: ScenarioSplit
    student_id: SyntheticStudentId
    case_id: Identifier
    transaction_script_id: Identifier
    initial_state_refs: list[Identifier] = Field(min_length=1)
    initial_state: dict[str, JsonValue] = Field(default_factory=dict)
    injected_event: EventType | None = None
    ground_truth: ScenarioGroundTruth

    @field_validator("initial_state_refs")
    @classmethod
    def unique_state_refs(cls, value: list[str]) -> list[str]:
        return _unique(value, "initial_state_refs")

    @model_validator(mode="after")
    def validate_scenario(self) -> Scenario:
        if self.family is ScenarioFamily.S7_DYNAMIC_FAILURE and self.injected_event is None:
            raise ValueError("S7 scenarios require an injected event")
        approval_events = {
            EventType.APPROVAL_GRANTED,
            EventType.APPROVAL_REJECTED,
            EventType.APPROVAL_PENDING,
        }
        if self.injected_event in approval_events and not self.ground_truth.requires_human:
            raise ValueError("approval events require human involvement in ground truth")
        return self

    def to_agent_context(self) -> ScenarioContext:
        """Return only observable initial references and state."""

        return ScenarioContext(
            scenario_id=self.scenario_id,
            student_id=self.student_id,
            case_id=self.case_id,
            initial_state_refs=list(self.initial_state_refs),
            initial_state=dict(self.initial_state),
        )
