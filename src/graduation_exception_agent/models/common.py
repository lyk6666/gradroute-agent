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


class SourceAccessStatus(StrEnum):
    """Outcome of the most recent attempt to collect a source."""

    RETRIEVED = "RETRIEVED"
    PARTIALLY_RETRIEVED = "PARTIALLY_RETRIEVED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"


class SourceClassification(StrEnum):
    """Handling/access classification stated or implied by the source host."""

    PUBLIC = "PUBLIC"
    PUBLIC_RESTRICTED = "PUBLIC_RESTRICTED"
    AUTHENTICATED = "AUTHENTICATED"
    UNKNOWN = "UNKNOWN"


class ChecksumScope(StrEnum):
    """Bytes represented by a provenance checksum."""

    SOURCE_BYTES = "SOURCE_BYTES"
    NORMALIZED_EXTRACTION = "NORMALIZED_EXTRACTION"


class ProgrammeKind(StrEnum):
    """Kind of CCDS degree or named pathway in the public inventory."""

    SINGLE_DEGREE = "SINGLE_DEGREE"
    DOUBLE_DEGREE = "DOUBLE_DEGREE"
    SECOND_MAJOR = "SECOND_MAJOR"
    JOINT_DEGREE = "JOINT_DEGREE"
    PART_TIME_DEGREE = "PART_TIME_DEGREE"


class StudyMode(StrEnum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"


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
    checked_at: datetime | None = None
    version: NonEmptyText
    origin: SourceOrigin
    access_status: SourceAccessStatus | None = None
    classification: SourceClassification | None = None
    retrieval_method: Identifier | None = None
    request_parameters: dict[Identifier, NonEmptyText] = Field(default_factory=dict)
    content_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    checksum_scope: ChecksumScope | None = None
    access_note: NonEmptyText | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    dependent_records: list[Identifier] = Field(default_factory=list)

    @field_validator("retrieved_at", "checked_at")
    @classmethod
    def require_timezone(cls, value: datetime | None, info: object) -> datetime | None:
        if value is not None and value.tzinfo is None:
            field_name = getattr(info, "field_name", "timestamp")
            raise ValueError(f"{field_name} must include a timezone")
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
            if self.source_url is None or (
                self.checked_at is None and self.retrieved_at is None
            ):
                raise ValueError(
                    "verified real sources require source_url and a checked/retrieved time"
                )
        if (
            self.checked_at is not None
            and self.retrieved_at is not None
            and self.retrieved_at > self.checked_at
        ):
            raise ValueError("retrieved_at must not be after checked_at")
        if self.access_status in {
            SourceAccessStatus.RETRIEVED,
            SourceAccessStatus.PARTIALLY_RETRIEVED,
        }:
            if self.retrieved_at is None:
                raise ValueError("retrieved sources require retrieved_at")
            if self.retrieval_method is None:
                raise ValueError("retrieved sources require retrieval_method")
            if self.content_sha256 is None or self.checksum_scope is None:
                raise ValueError(
                    "retrieved sources require content_sha256 and checksum_scope"
                )
            if (
                self.access_status is SourceAccessStatus.PARTIALLY_RETRIEVED
                and self.access_note is None
            ):
                raise ValueError("partially retrieved sources require access_note")
        if self.access_status in {
            SourceAccessStatus.AUTHENTICATION_REQUIRED,
            SourceAccessStatus.UNAVAILABLE,
        }:
            if self.access_note is None:
                raise ValueError("inaccessible sources require access_note")
            if self.content_sha256 is not None or self.checksum_scope is not None:
                raise ValueError(
                    "inaccessible sources cannot claim a retrieved-content checksum"
                )
        if (self.content_sha256 is None) != (self.checksum_scope is None):
            raise ValueError(
                "content_sha256 and checksum_scope must be provided together"
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
    programme_kind: ProgrammeKind = ProgrammeKind.SINGLE_DEGREE
    study_mode: StudyMode = StudyMode.FULL_TIME
    ccds_base_programmes: list[ProgrammeCode] = Field(default_factory=list)
    external_identifiers: dict[Identifier, NonEmptyText] = Field(default_factory=dict)
    active: bool = True
    source_ids: list[Identifier] = Field(min_length=1)

    @field_validator("source_ids", "ccds_base_programmes")
    @classmethod
    def unique_sources(cls, value: list[str], info: object) -> list[str]:
        if len(value) != len(set(value)):
            field_name = getattr(info, "field_name", "values")
            raise ValueError(f"{field_name} must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_pathway_metadata(self) -> Programme:
        if self.code in self.ccds_base_programmes:
            raise ValueError("a programme cannot be its own CCDS base programme")
        if (
            self.programme_kind is ProgrammeKind.SECOND_MAJOR
            and len(self.ccds_base_programmes) != 1
        ):
            raise ValueError(
                "second-major pathways require exactly one CCDS base programme"
            )
        if (
            self.programme_kind is ProgrammeKind.PART_TIME_DEGREE
            and self.study_mode is not StudyMode.PART_TIME
        ):
            raise ValueError("part-time degrees require PART_TIME study mode")
        if len(self.external_identifiers.values()) != len(
            set(self.external_identifiers.values())
        ):
            raise ValueError("external identifier values must not contain duplicates")
        return self
