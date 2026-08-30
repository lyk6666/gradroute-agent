"""Shared identifiers, provenance, and base domain contracts."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    ),
]
ProgrammeCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        min_length=2,
        max_length=16,
        pattern=r"^[A-Z][A-Z0-9-]*$",
    ),
]
SyntheticStudentId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        min_length=8,
        max_length=64,
        pattern=r"^SIM-[A-Z0-9]+(?:-[A-Z0-9]+)+$",
    ),
]
CourseCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        min_length=4,
        max_length=12,
        pattern=r"^[A-Z]{2,6}[0-9]{3,5}[A-Z]?$",
    ),
]
AcademicYear = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        pattern=r"^AY[0-9]{4}(?:[-/][0-9]{2,4})?$",
    ),
]
AdmissionCohort = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        pattern=r"^(?:AY)?[0-9]{4}(?:[-/][0-9]{2,4})?$",
    ),
]
NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
]


class DomainModel(BaseModel):
    """Strict-on-shape base model used for all persisted contracts."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        validate_default=True,
    )


class SourceOrigin(StrEnum):
    """Provenance classification that prevents policy masquerading."""

    VERIFIED_REAL = "VERIFIED_REAL"
    UNVERIFIED_REAL = "UNVERIFIED_REAL"
    SIMULATED_POLICY = "SIMULATED_POLICY"
    UNKNOWN = "UNKNOWN"


class SourceProvenance(DomainModel):
    """Traceable source metadata for every grounded record."""

    source_id: Identifier
    source_type: Identifier
    programme: ProgrammeCode | None = None
    admission_cohort: AdmissionCohort | None = None
    effective_academic_year: AcademicYear | None = None
    offering_academic_year: AcademicYear | None = None
    source_url: AnyHttpUrl | None = None
    retrieved_at: datetime | None = None
    version: NonEmptyText
    origin: SourceOrigin
    effective_from: date | None = None
    effective_to: date | None = None
    dependent_records: list[Identifier] = Field(default_factory=list)

    @field_validator("retrieved_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("retrieved_at must include a timezone")
        return value

    @field_validator("dependent_records")
    @classmethod
    def unique_dependents(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("dependent_records must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_provenance(self) -> SourceProvenance:
        if self.origin is SourceOrigin.VERIFIED_REAL:
            if self.source_url is None or self.retrieved_at is None:
                raise ValueError(
                    "verified real sources require source_url and retrieved_at"
                )
        if self.effective_from and self.effective_to:
            if self.effective_to < self.effective_from:
                raise ValueError("effective_to must not precede effective_from")
        return self


class GeneratedModel(DomainModel):
    """Metadata required on every deterministically generated entity."""

    generator_version: NonEmptyText
    seed: int = Field(ge=0)
    source_rule_ids: list[Identifier] = Field(min_length=1)

    @field_validator("source_rule_ids")
    @classmethod
    def unique_source_rules(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("source_rule_ids must not contain duplicates")
        return value


class Programme(DomainModel):
    """One CCDS programme without claiming the current list is exhaustive."""

    programme_id: Identifier
    code: ProgrammeCode
    name: NonEmptyText
    college: NonEmptyText = "College of Computing and Data Science"
    active: bool = True
    source_ids: list[Identifier] = Field(min_length=1)

    @field_validator("source_ids")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("source_ids must not contain duplicates")
        return value
