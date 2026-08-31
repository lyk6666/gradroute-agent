"""Typed Stage 6 structured-reasoning contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from graduation_exception_agent.models.common import DomainModel, Identifier
from graduation_exception_agent.models.orchestration import SpecialistKind
from graduation_exception_agent.models.runtime import (
    ClarificationImpact,
    VerifierDecisionCode,
)


class ReasoningTask(StrEnum):
    SELECT_SPECIALISTS = "select_specialists"
    ASSESS_PRE_ACTION = "assess_pre_action"


class ReasoningCallStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FALLBACK = "FALLBACK"
    SKIPPED_SAFETY_GATE = "SKIPPED_SAFETY_GATE"


class ReasoningUsage(DomainModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def total_matches_parts(self) -> ReasoningUsage:
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens must equal input_tokens plus output_tokens")
        return self


class StructuredReasoningResponse(DomainModel):
    task: ReasoningTask
    model_id: str = Field(min_length=1, max_length=256)
    output: dict[str, Any]
    stop_reason: str = Field(min_length=1, max_length=128)
    request_id: str | None = Field(default=None, max_length=256)
    latency_ms: int | None = Field(default=None, ge=0)
    usage: ReasoningUsage


class SpecialistSelectionOutput(DomainModel):
    specialists: list[SpecialistKind] = Field(min_length=1, max_length=3)
    rationale: str = Field(min_length=1, max_length=800)

    @field_validator("specialists")
    @classmethod
    def unique_specialists(
        cls, value: list[SpecialistKind]
    ) -> list[SpecialistKind]:
        if len(value) != len(set(value)):
            raise ValueError("specialists must not contain duplicates")
        return value


class PreActionReasoningOutput(DomainModel):
    decision: Literal[
        VerifierDecisionCode.VALID,
        VerifierDecisionCode.REPLAN,
        VerifierDecisionCode.CLARIFY,
        VerifierDecisionCode.ESCALATE,
    ]
    reason: str = Field(min_length=1, max_length=800)
    clarification_impact: ClarificationImpact = ClarificationImpact.NONE
    violation_codes: list[Identifier] = Field(default_factory=list, max_length=8)
    missing_fields: list[Identifier] = Field(default_factory=list, max_length=8)

    @field_validator("violation_codes", "missing_fields")
    @classmethod
    def unique_identifiers(cls, value: list[str], info: object) -> list[str]:
        if len(value) != len(set(value)):
            field_name = getattr(info, "field_name", "identifiers")
            raise ValueError(f"{field_name} must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_decision_shape(self) -> PreActionReasoningOutput:
        if self.decision is VerifierDecisionCode.VALID:
            if (
                self.clarification_impact is not ClarificationImpact.NONE
                or self.violation_codes
                or self.missing_fields
            ):
                raise ValueError("VALID cannot carry violations or clarification data")
            return self
        if not self.violation_codes:
            raise ValueError("a non-VALID decision requires a violation code")
        if self.decision is VerifierDecisionCode.CLARIFY:
            if self.clarification_impact is ClarificationImpact.NONE:
                raise ValueError("CLARIFY requires a clarification impact")
            if not self.missing_fields:
                raise ValueError("CLARIFY requires missing fields")
        elif (
            self.clarification_impact is not ClarificationImpact.NONE
            or self.missing_fields
        ):
            raise ValueError(
                "clarification data is permitted only for a CLARIFY decision"
            )
        return self


class ReasoningAuditEvent(DomainModel):
    sequence: int = Field(ge=1)
    task: ReasoningTask
    status: ReasoningCallStatus
    model_id: str | None = Field(default=None, max_length=256)
    applied: bool
    safety_rule: str = Field(min_length=1, max_length=256)
    usage: ReasoningUsage | None = None


__all__ = [
    "PreActionReasoningOutput",
    "ReasoningAuditEvent",
    "ReasoningCallStatus",
    "ReasoningTask",
    "ReasoningUsage",
    "SpecialistSelectionOutput",
    "StructuredReasoningResponse",
]
