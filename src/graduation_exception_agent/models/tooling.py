"""Typed contracts shared by the deterministic Stage 4 tool boundary."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, JsonValue, field_validator, model_validator

from graduation_exception_agent.models.academic import DataCompleteness
from graduation_exception_agent.models.common import (
    DomainModel,
    Identifier,
    NonEmptyText,
    SourceOrigin,
)
from graduation_exception_agent.models.workflow import (
    ObservationCode,
    StateTargetType,
    TransactionAction,
    TransactionCode,
)


def _unique(values: list[str], field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


def _timezone_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value


class ToolStatus(StrEnum):
    """Normalized outcome of a tool invocation."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PENDING = "PENDING"


class ToolErrorCode(StrEnum):
    """Stable error vocabulary; tool-specific detail belongs in ``details``."""

    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    FORBIDDEN = "FORBIDDEN"
    REQUIRED_INFORMATION_MISSING = "REQUIRED_INFORMATION_MISSING"
    CONSTRAINT_VIOLATION = "CONSTRAINT_VIOLATION"
    MODULE_FULL = "MODULE_FULL"
    CLASS_UNAVAILABLE = "CLASS_UNAVAILABLE"
    PREREQUISITE_FAILURE = "PREREQUISITE_FAILURE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    STALE_STATE = "STALE_STATE"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    SCRIPT_MISMATCH = "SCRIPT_MISMATCH"
    TEMPORARY_FAILURE = "TEMPORARY_FAILURE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ToolProvenance(DomainModel):
    """Compact provenance attached to an agent-visible tool result."""

    source_ids: list[Identifier] = Field(default_factory=list)
    rule_ids: list[Identifier] = Field(default_factory=list)
    derived_from_ids: list[Identifier] = Field(default_factory=list)
    origin: SourceOrigin
    completeness: DataCompleteness
    note: NonEmptyText | None = None

    @field_validator("source_ids", "rule_ids", "derived_from_ids")
    @classmethod
    def unique_references(cls, value: list[str], info: object) -> list[str]:
        return _unique(value, getattr(info, "field_name", "references"))

    @model_validator(mode="after")
    def require_a_traceable_reference(self) -> ToolProvenance:
        if not (self.source_ids or self.rule_ids or self.derived_from_ids):
            raise ValueError(
                "provenance requires a source, rule, or derived-from reference"
            )
        return self


class VersionExpectation(DomainModel):
    """Optimistic-lock precondition for one mutable runtime entity."""

    target_type: StateTargetType
    target_id: Identifier
    expected_version: int = Field(ge=1)


class ToolCallContext(DomainModel):
    """Request identity and write preconditions supplied at every tool boundary."""

    session_id: Identifier
    request_id: Identifier
    case_id: Identifier
    requested_at: datetime
    idempotency_key: Identifier | None = None
    expected_versions: list[VersionExpectation] = Field(default_factory=list)

    @field_validator("requested_at")
    @classmethod
    def timezone_aware_requested_at(cls, value: datetime) -> datetime:
        return _timezone_aware(value, "requested_at")

    @model_validator(mode="after")
    def unique_version_targets(self) -> ToolCallContext:
        targets = [
            (expectation.target_type, expectation.target_id)
            for expectation in self.expected_versions
        ]
        if len(targets) != len(set(targets)):
            raise ValueError("expected_versions must not repeat a target")
        return self


class ToolError(DomainModel):
    """Normalized failure safe to expose to the control plane."""

    code: ToolErrorCode
    message: NonEmptyText
    retryable: bool = False
    details: dict[Identifier, JsonValue] = Field(default_factory=dict)


class ToolObservation(DomainModel):
    """Normalized observation emitted after a simulated write attempt."""

    observation_id: Identifier
    code: ObservationCode
    message: NonEmptyText
    retryable: bool
    occurred_at: datetime
    state_versions: dict[Identifier, int] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def timezone_aware_occurred_at(cls, value: datetime) -> datetime:
        return _timezone_aware(value, "occurred_at")

    @field_validator("state_versions")
    @classmethod
    def positive_state_versions(cls, value: dict[str, int]) -> dict[str, int]:
        if any(version < 1 for version in value.values()):
            raise ValueError("state_versions must be positive")
        return value


class ActionPostcondition(DomainModel):
    """State evidence recorded by an action without interpreting the full goal."""

    postcondition_id: Identifier
    target_type: StateTargetType
    target_id: Identifier
    field_path: NonEmptyText
    expected_value: JsonValue
    observed_value: JsonValue
    satisfied: bool


class ActionReceipt(DomainModel):
    """Durable, idempotently replayable result of an action tool call.

    ``goal_effect`` is deliberately explicit: a successful approval request is
    an intermediate action and therefore cannot by itself prove completion.
    """

    receipt_id: Identifier
    transaction_id: Identifier
    session_id: Identifier
    request_id: Identifier
    idempotency_key: Identifier
    case_id: Identifier
    action: TransactionAction
    status: ToolStatus
    result_code: TransactionCode
    observation: ToolObservation
    message: NonEmptyText
    error: ToolError | None = None
    mutation_ids: list[Identifier] = Field(default_factory=list)
    entity_versions: dict[Identifier, int] = Field(default_factory=dict)
    postconditions: list[ActionPostcondition] = Field(default_factory=list)
    committed: bool
    intermediate: bool
    retryable: bool
    goal_effect: bool = False
    session_revision: int = Field(ge=1)
    committed_at: datetime
    replayed: bool = False

    @field_validator("committed_at")
    @classmethod
    def timezone_aware_committed_at(cls, value: datetime) -> datetime:
        return _timezone_aware(value, "committed_at")

    @field_validator("mutation_ids")
    @classmethod
    def unique_receipt_links(cls, value: list[str], info: object) -> list[str]:
        return _unique(value, getattr(info, "field_name", "links"))

    @field_validator("entity_versions")
    @classmethod
    def positive_resulting_versions(cls, value: dict[str, int]) -> dict[str, int]:
        if any(version < 1 for version in value.values()):
            raise ValueError("entity_versions must be positive")
        return value

    @model_validator(mode="after")
    def validate_outcome_coherence(self) -> ActionReceipt:
        successful_codes = {
            TransactionCode.SUCCESS,
            TransactionCode.EXCEPTION_SUBMISSION_SUCCESS,
        }
        expected_observations = {
            TransactionCode.SUCCESS: ObservationCode.TRANSACTION_SUCCESS,
            TransactionCode.EXCEPTION_SUBMISSION_SUCCESS: (
                ObservationCode.TRANSACTION_SUCCESS
            ),
            TransactionCode.MODULE_FULL: ObservationCode.MODULE_FULL,
            TransactionCode.CLASS_UNAVAILABLE: ObservationCode.CLASS_UNAVAILABLE,
            TransactionCode.PREREQUISITE_FAILURE: (
                ObservationCode.PREREQUISITE_FAILURE
            ),
            TransactionCode.APPROVAL_REJECTED: ObservationCode.APPROVAL_REJECTED,
            TransactionCode.APPROVAL_PENDING: ObservationCode.APPROVAL_PENDING,
            TransactionCode.STALE_STATE: ObservationCode.STALE_STATE,
            TransactionCode.TEMPORARY_SYSTEM_FAILURE: (
                ObservationCode.TEMPORARY_FAILURE
            ),
            TransactionCode.REQUIRED_INFORMATION_MISSING: (
                ObservationCode.REQUIRED_INFORMATION_MISSING
            ),
        }
        if self.observation.code is not expected_observations[self.result_code]:
            raise ValueError("result_code and observation code must agree")
        if self.result_code is TransactionCode.APPROVAL_PENDING:
            expected_status = ToolStatus.PENDING
        elif self.result_code in successful_codes:
            expected_status = ToolStatus.SUCCESS
        else:
            expected_status = ToolStatus.FAILURE
        if self.status is not expected_status:
            raise ValueError(
                f"{self.result_code.value} requires {expected_status.value} status"
            )
        if self.status is ToolStatus.SUCCESS and self.error is not None:
            raise ValueError("successful receipts cannot contain an error")
        if self.status is not ToolStatus.SUCCESS and self.error is None:
            raise ValueError("non-successful receipts require a normalized error")
        if self.retryable != self.observation.retryable:
            raise ValueError("receipt and observation retryability must agree")
        if self.error is not None and self.retryable != self.error.retryable:
            raise ValueError("observation and error retryability must agree")
        if self.status is not ToolStatus.SUCCESS and self.goal_effect:
            raise ValueError("a non-successful action cannot claim a goal effect")
        if self.action is TransactionAction.REQUEST_APPROVAL:
            if not self.intermediate:
                raise ValueError("requesting approval must be marked intermediate")
            if self.goal_effect:
                raise ValueError(
                    "requesting approval is intermediate, not goal completion"
                )
        if self.goal_effect and not self.postconditions:
            raise ValueError("goal_effect requires at least one postcondition")
        postcondition_ids = [item.postcondition_id for item in self.postconditions]
        _unique(postcondition_ids, "postcondition_ids")
        if self.goal_effect and not all(item.satisfied for item in self.postconditions):
            raise ValueError("goal_effect requires every postcondition to be satisfied")
        return self


class ToolResponse(DomainModel):
    """Uniform envelope for deterministic read/check tools."""

    request_id: Identifier
    status: ToolStatus
    data: JsonValue | None = None
    provenance: list[ToolProvenance] = Field(default_factory=list)
    error: ToolError | None = None
    observations: list[ToolObservation] = Field(default_factory=list)
    entity_versions: dict[Identifier, int] = Field(default_factory=dict)

    @field_validator("entity_versions")
    @classmethod
    def positive_response_versions(cls, value: dict[str, int]) -> dict[str, int]:
        if any(version < 1 for version in value.values()):
            raise ValueError("entity_versions must be positive")
        return value

    @model_validator(mode="after")
    def validate_status(self) -> ToolResponse:
        if self.status is ToolStatus.SUCCESS and self.error is not None:
            raise ValueError("successful tool responses cannot contain an error")
        if self.status is ToolStatus.FAILURE and self.error is None:
            raise ValueError("failed tool responses require a normalized error")
        return self
