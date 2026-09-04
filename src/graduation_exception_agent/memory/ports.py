"""Advisory long-term-memory contracts for Stage 5.

This store contains deidentified experience patterns, never authoritative
academic data.  Every record is gated by a verified ``DONE`` decision.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

from pydantic import Field, field_validator, model_validator

from graduation_exception_agent.models.common import (
    DomainModel,
    Identifier,
    NonEmptyText,
)
from graduation_exception_agent.models.runtime import GoalKind


MAX_MEMORY_RESULTS = 10
MAX_MEMORY_STEPS = 8
MAX_MEMORY_TAGS = 12
MAX_MEMORY_TEXT_CHARS = 4_000


_PROHIBITED_CONTENT = re.compile(
    r"(?:"
    r"scenario[_\s-]?id|scenario[_\s-]?family|ground[_\s-]?truth|"
    r"expected[_\s-]?outcome|evaluator(?:[_\s-]?only)?|"
    r"transaction[_\s-]?script|hidden[_\s-]?event|injected[_\s-]?event|"
    r"student[_\s-]?id|matriculation(?:[_\s-]?(?:number|id))?|"
    r"current(?:ly)?[_\s-]?(?:policy|academic|course|registration|"
    r"requirement|prerequisite|exclusion|offering|timetable|workload|"
    r"vacancy|capacity|availability|approval|status)|"
    r"live[_\s-]?(?:availability|vacancy|capacity)|"
    r"(?:is|are)[_\s-]?currently[_\s-]?(?:available|approved|eligible|"
    r"open|full|vacant)"
    r")",
    flags=re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_SYNTHETIC_STUDENT_ID = re.compile(r"\bSIM-[A-Z0-9]+(?:-[A-Z0-9]+)+\b", re.IGNORECASE)
_SYNTHETIC_ENTITY_ID = re.compile(
    r"\b(?:case|student|registration|audit|approval|offering(?:-state)?|scenario)"
    r"[._-]sim(?:[._-][A-Z0-9]+)+\b",
    re.IGNORECASE,
)
_EVALUATOR_SCENARIO_CODE = re.compile(r"\bS[1-9][0-9]*-[DE][0-9]{2,}\b", re.IGNORECASE)
_MATRICULATION_ID = re.compile(r"\b[UNG][0-9]{7}[A-Z]\b", re.IGNORECASE)
_SINGAPORE_PHONE = re.compile(r"(?<!\d)(?:\+?65[ -]?)?[689][0-9]{7}(?!\d)")

# Runtime receipts are opaque operational references emitted by the transaction
# runtime. Their fixed namespace happens to contain a simulated case identifier,
# so permit the complete generated shape rather than weakening the synthetic-ID
# filter.
_RUNTIME_RECEIPT_ID = re.compile(
    r"^receipt\.runtime\.case\.sim-[A-Z][A-Z0-9]*-[0-9]{3}\.[1-9][0-9]*$",
    re.IGNORECASE,
)


def _timezone_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value


def _unique(values: list[str], field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


def _reject_sensitive_or_authoritative_text(value: str, field_name: str) -> str:
    patterns = (
        _PROHIBITED_CONTENT,
        _EMAIL,
        _SYNTHETIC_STUDENT_ID,
        _SYNTHETIC_ENTITY_ID,
        _EVALUATOR_SCENARIO_CODE,
        _MATRICULATION_ID,
        _SINGAPORE_PHONE,
    )
    if any(pattern.search(value) for pattern in patterns):
        raise ValueError(
            f"{field_name} contains PII, evaluator data, or an authoritative current fact"
        )
    return value


def _reject_sensitive_identifier(
    value: str,
    field_name: str,
    *,
    allow_runtime_receipt: bool = False,
) -> str:
    """Apply memory privacy rules to identifier-shaped content.

    Pydantic's generic ``Identifier`` type checks syntax, not provenance or
    sensitivity.  Keep this second validation boundary explicit, including a
    narrow exception for receipts produced by the runtime itself.
    """

    if allow_runtime_receipt and _RUNTIME_RECEIPT_ID.fullmatch(value):
        # The fixed receipt grammar is itself deidentified.  Still retain the
        # non-synthetic checks here so future grammar changes cannot turn this
        # exception into a general PII/evaluator bypass.
        for pattern in (
            _PROHIBITED_CONTENT,
            _EMAIL,
            _EVALUATOR_SCENARIO_CODE,
            _MATRICULATION_ID,
            _SINGAPORE_PHONE,
        ):
            if pattern.search(value):
                raise ValueError(
                    f"{field_name} contains PII, evaluator data, or an "
                    "authoritative current fact"
                )
        return value
    return _reject_sensitive_or_authoritative_text(value, field_name)


class MemorySensitivity(StrEnum):
    DEIDENTIFIED_ADVISORY = "DEIDENTIFIED_ADVISORY"


class MemoryWriteStatus(StrEnum):
    STORED = "STORED"
    ALREADY_STORED = "ALREADY_STORED"
    DISABLED = "DISABLED"


class ExperienceMemoryRecord(DomainModel):
    """Compact, bounded, deidentified advice from a verified completed run."""

    memory_id: Identifier
    schema_version: Literal["1.0"] = "1.0"
    advisory: Literal[True] = True
    sensitivity: Literal[MemorySensitivity.DEIDENTIFIED_ADVISORY] = (
        MemorySensitivity.DEIDENTIFIED_ADVISORY
    )
    case_type: Identifier
    goal_kind: GoalKind
    successful_strategy: NonEmptyText
    recovery_steps: list[NonEmptyText] = Field(
        default_factory=list, max_length=MAX_MEMORY_STEPS
    )
    failed_strategy_patterns: list[NonEmptyText] = Field(
        default_factory=list, max_length=MAX_MEMORY_STEPS
    )
    applicability: NonEmptyText
    tags: list[Identifier] = Field(default_factory=list, max_length=MAX_MEMORY_TAGS)
    verification_receipt_ids: list[Identifier] = Field(min_length=1, max_length=8)
    verifier_decision: Literal["DONE"] = "DONE"
    goal_complete: Literal[True] = True
    verified_at: datetime
    invalidated_at: datetime | None = None
    invalidation_reason: NonEmptyText | None = None

    @field_validator("memory_id")
    @classmethod
    def safe_memory_id(cls, value: str) -> str:
        return _reject_sensitive_identifier(value, "memory_id")

    @field_validator("verified_at", "invalidated_at")
    @classmethod
    def timezone_aware_times(
        cls, value: datetime | None, info: object
    ) -> datetime | None:
        if value is None:
            return None
        return _timezone_aware(value, getattr(info, "field_name", "timestamp"))

    @field_validator("tags", "verification_receipt_ids")
    @classmethod
    def unique_links(cls, value: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "links")
        _unique(value, field_name)
        for item in value:
            _reject_sensitive_identifier(
                item,
                field_name,
                allow_runtime_receipt=field_name == "verification_receipt_ids",
            )
        return value

    @field_validator(
        "case_type",
        "successful_strategy",
        "applicability",
        "invalidation_reason",
    )
    @classmethod
    def safe_scalar_text(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return _reject_sensitive_or_authoritative_text(
            value, getattr(info, "field_name", "text")
        )

    @field_validator("recovery_steps", "failed_strategy_patterns")
    @classmethod
    def safe_text_lists(cls, value: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "text")
        for item in value:
            _reject_sensitive_or_authoritative_text(item, field_name)
        return value

    @model_validator(mode="after")
    def validate_record(self) -> ExperienceMemoryRecord:
        if self.invalidated_at is None and self.invalidation_reason is not None:
            raise ValueError("invalidation_reason requires invalidated_at")
        if self.invalidated_at is not None:
            if self.invalidation_reason is None:
                raise ValueError("invalidated_at requires invalidation_reason")
            if self.invalidated_at < self.verified_at:
                raise ValueError("invalidated_at must not precede verified_at")
        text_size = sum(
            len(item)
            for item in [
                self.case_type,
                self.successful_strategy,
                self.applicability,
                *self.recovery_steps,
                *self.failed_strategy_patterns,
            ]
        )
        if text_size > MAX_MEMORY_TEXT_CHARS:
            raise ValueError(
                f"memory text exceeds the {MAX_MEMORY_TEXT_CHARS}-character bound"
            )
        return self

    @property
    def active(self) -> bool:
        return self.invalidated_at is None


class ExperienceMemoryQuery(DomainModel):
    """Retrieval query made only from observable case intent."""

    case_type: Identifier | None = None
    goal_kind: GoalKind | None = None
    tags: list[Identifier] = Field(default_factory=list, max_length=MAX_MEMORY_TAGS)
    exclude_memory_ids: list[Identifier] = Field(
        default_factory=list, max_length=MAX_MEMORY_RESULTS
    )
    limit: int = Field(default=5, ge=1, le=MAX_MEMORY_RESULTS)

    @field_validator("tags", "exclude_memory_ids")
    @classmethod
    def unique_filters(cls, value: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "filters")
        _unique(value, field_name)
        for item in value:
            _reject_sensitive_identifier(item, field_name)
        return value


class MemoryWriteResult(DomainModel):
    memory_id: Identifier
    status: MemoryWriteStatus
    stored: bool
    reason: NonEmptyText

    @field_validator("memory_id")
    @classmethod
    def safe_memory_id(cls, value: str) -> str:
        return _reject_sensitive_identifier(value, "memory_id")

    @field_validator("reason")
    @classmethod
    def safe_reason(cls, value: str) -> str:
        return _reject_sensitive_or_authoritative_text(value, "reason")

    @model_validator(mode="after")
    def validate_status(self) -> MemoryWriteResult:
        expected = self.status is MemoryWriteStatus.STORED
        if self.stored != expected:
            raise ValueError("stored must be true exactly when status is STORED")
        return self


@runtime_checkable
class ExperienceMemoryReader(Protocol):
    def retrieve(self, query: ExperienceMemoryQuery) -> list[ExperienceMemoryRecord]:
        """Return bounded advisory records, never current academic truth."""


@runtime_checkable
class ExperienceMemoryWriter(Protocol):
    def write(self, record: ExperienceMemoryRecord) -> MemoryWriteResult:
        """Persist an already validated, verified-DONE experience."""


@runtime_checkable
class ExperienceMemoryStore(ExperienceMemoryReader, ExperienceMemoryWriter, Protocol):
    pass
