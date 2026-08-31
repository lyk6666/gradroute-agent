"""Grounded calendar, policy, and collection contracts."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from graduation_exception_agent.models.academic import CourseOffering, Semester
from graduation_exception_agent.models.common import (
    AcademicYear,
    AdmissionCohort,
    DomainModel,
    Identifier,
    NonEmptyText,
    SourceOrigin,
)


def _unique(values: list[str], field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


class DocumentStatus(StrEnum):
    """How complete a collected document or dataset is."""

    AVAILABLE = "AVAILABLE"
    COLLECTED = "COLLECTED"
    PARTIAL = "PARTIAL"
    PLACEHOLDER = "PLACEHOLDER"


class PolicyDocumentType(StrEnum):
    REGISTRATION = "REGISTRATION"
    EXCEPTIONS = "EXCEPTIONS"
    APPROVAL_STRUCTURE = "APPROVAL_STRUCTURE"


class PolicyApplicability(StrEnum):
    """Whether a policy section has a typed temporal/cohort scope."""

    EXPLICIT = "EXPLICIT"
    SOURCE_SCOPE_UNSPECIFIED = "SOURCE_SCOPE_UNSPECIFIED"
    UNKNOWN = "UNKNOWN"


class CalendarEventType(StrEnum):
    TEACHING = "TEACHING"
    RECESS = "RECESS"
    REVISION_EXAMINATION = "REVISION_EXAMINATION"
    VACATION = "VACATION"
    SPECIAL_TERM = "SPECIAL_TERM"
    INTERNSHIP = "INTERNSHIP"
    COURSE_REGISTRATION = "COURSE_REGISTRATION"
    ADD_DROP = "ADD_DROP"
    SCHEDULE_RELEASE = "SCHEDULE_RELEASE"
    ALLOCATION_RESULTS = "ALLOCATION_RESULTS"
    RESULTS = "RESULTS"
    FGO = "FGO"
    RESULT_REVIEW = "RESULT_REVIEW"
    CONVOCATION_CUTOFF = "CONVOCATION_CUTOFF"


class DatePrecision(StrEnum):
    EXACT = "EXACT"
    GENERAL = "GENERAL"
    UNKNOWN = "UNKNOWN"


class PolicySection(DomainModel):
    """One independently sourced policy statement parsed from Markdown."""

    section_id: Identifier
    title: NonEmptyText
    origin: SourceOrigin
    source_ids: list[Identifier] = Field(default_factory=list)
    applicability: PolicyApplicability
    applicable_academic_years: list[AcademicYear] = Field(default_factory=list)
    applicable_admission_cohorts: list[AdmissionCohort] = Field(default_factory=list)
    applicability_note: NonEmptyText
    body_markdown: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @field_validator(
        "source_ids", "applicable_academic_years", "applicable_admission_cohorts"
    )
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        return _unique(value, "source_ids")

    @model_validator(mode="after")
    def protect_policy_origin(self) -> PolicySection:
        if self.end_line < self.start_line:
            raise ValueError("end_line must not precede start_line")
        if self.origin is SourceOrigin.VERIFIED_REAL and not self.source_ids:
            raise ValueError("verified policy sections require source_ids")
        has_typed_scope = bool(
            self.applicable_academic_years or self.applicable_admission_cohorts
        )
        if self.applicability is PolicyApplicability.EXPLICIT and not has_typed_scope:
            raise ValueError("explicit policy applicability requires a year or cohort")
        if (
            self.applicability is not PolicyApplicability.EXPLICIT
            and has_typed_scope
        ):
            raise ValueError("only explicit applicability may contain typed scopes")
        if self.origin is SourceOrigin.UNKNOWN:
            if self.applicability is not PolicyApplicability.UNKNOWN:
                raise ValueError("unknown policy sections require UNKNOWN applicability")
        elif self.applicability is PolicyApplicability.UNKNOWN:
            raise ValueError("known-origin policy sections cannot have UNKNOWN applicability")
        if (
            self.origin is SourceOrigin.SIMULATED_POLICY
            and self.applicability is not PolicyApplicability.EXPLICIT
        ):
            raise ValueError("simulated policy sections require explicit applicability")
        if self.origin is SourceOrigin.SIMULATED_POLICY:
            first_content_line = next(
                (
                    line.strip()
                    for line in self.body_markdown.splitlines()
                    if line.strip()
                ),
                "",
            )
            if first_content_line != "SIMULATED POLICY FOR PROTOTYPE":
                raise ValueError(
                    "simulated policy sections must start with the exact "
                    "SIMULATED POLICY FOR PROTOTYPE banner"
                )
        return self


class PolicyDocument(DomainModel):
    """A policy Markdown document with raw text and section-level provenance."""

    document_id: Identifier
    document_type: PolicyDocumentType
    title: NonEmptyText
    status: DocumentStatus
    source_ids: list[Identifier] = Field(default_factory=list)
    sections: list[PolicySection] = Field(default_factory=list)
    raw_markdown: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    placeholder_reason: NonEmptyText | None = None

    @field_validator("source_ids")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        return _unique(value, "source_ids")

    @model_validator(mode="after")
    def validate_document_state(self) -> PolicyDocument:
        if self.status is DocumentStatus.COLLECTED:
            raise ValueError("COLLECTED status is reserved for offering collections")
        _unique([section.section_id for section in self.sections], "section_ids")
        undeclared_sources = {
            source_id
            for section in self.sections
            for source_id in section.source_ids
            if source_id not in self.source_ids
        }
        if undeclared_sources:
            raise ValueError(
                "section source_ids must be declared by the policy document: "
                f"{sorted(undeclared_sources)}"
            )
        if self.status is DocumentStatus.AVAILABLE and any(
            section.origin
            in {
                SourceOrigin.UNKNOWN,
                SourceOrigin.UNVERIFIED_REAL,
                SourceOrigin.SIMULATED_POLICY,
            }
            for section in self.sections
        ):
            raise ValueError(
                "documents with unknown, unverified, or simulated sections must be PARTIAL"
            )
        if self.status is DocumentStatus.PLACEHOLDER:
            if self.placeholder_reason is None:
                raise ValueError("placeholder documents require placeholder_reason")
            if any(
                section.origin
                in {SourceOrigin.VERIFIED_REAL, SourceOrigin.SIMULATED_POLICY}
                for section in self.sections
            ):
                raise ValueError(
                    "placeholder documents cannot contain actionable policy sections"
                )
        elif self.placeholder_reason is not None:
            raise ValueError("only placeholder documents may have placeholder_reason")
        return self

    def sections_with_origins(
        self, origins: frozenset[SourceOrigin]
    ) -> tuple[PolicySection, ...]:
        """Return only explicitly requested origins; never infer one from prose."""

        return tuple(section for section in self.sections if section.origin in origins)

    def verified_sections(
        self,
        *,
        academic_year: str | None = None,
        admission_cohort: str | None = None,
        include_unscoped: bool = False,
    ) -> tuple[PolicySection, ...]:
        """Return context-compatible verified statements only."""

        if academic_year is None and admission_cohort is None:
            raise ValueError(
                "verified policy selection requires academic_year or "
                "admission_cohort context"
            )
        return tuple(
            section
            for section in self.sections
            if section.origin is SourceOrigin.VERIFIED_REAL
            and _matches_policy_context(
                section,
                academic_year=academic_year,
                admission_cohort=admission_cohort,
                include_unscoped=include_unscoped,
            )
        )


def _matches_policy_context(
    section: PolicySection,
    *,
    academic_year: str | None,
    admission_cohort: str | None,
    include_unscoped: bool,
) -> bool:
    if section.applicability is not PolicyApplicability.EXPLICIT:
        return include_unscoped
    if section.applicable_academic_years:
        if academic_year is None:
            return False
        if academic_year.upper() not in section.applicable_academic_years:
            return False
    if section.applicable_admission_cohorts:
        if admission_cohort is None:
            return False
        if admission_cohort.upper() not in section.applicable_admission_cohorts:
            return False
    return True


class CalendarEvent(DomainModel):
    """One sourced or explicitly unknown academic-calendar window."""

    event_id: Identifier
    event_type: CalendarEventType
    name: NonEmptyText
    semester: Semester | None = None
    start_date: date | None = None
    end_date: date | None = None
    date_precision: DatePrecision
    description: NonEmptyText
    origin: SourceOrigin
    source_ids: list[Identifier] = Field(default_factory=list)

    @field_validator("source_ids")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        return _unique(value, "source_ids")

    @model_validator(mode="after")
    def validate_dates_and_origin(self) -> CalendarEvent:
        if self.origin is SourceOrigin.SIMULATED_POLICY:
            raise ValueError("real academic calendars cannot contain simulated events")
        if self.origin is SourceOrigin.VERIFIED_REAL and not self.source_ids:
            raise ValueError("verified calendar events require source_ids")
        if self.date_precision is DatePrecision.EXACT:
            if self.start_date is None or self.end_date is None:
                raise ValueError("exact calendar events require start_date and end_date")
        if self.date_precision is DatePrecision.UNKNOWN:
            if self.origin is not SourceOrigin.UNKNOWN:
                raise ValueError("unknown date precision requires UNKNOWN origin")
            if self.start_date is not None or self.end_date is not None:
                raise ValueError("unknown calendar dates must remain null")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        return self


class AcademicCalendarDocument(DomainModel):
    """Parsed academic calendar with its original Markdown retained."""

    document_id: Identifier
    title: NonEmptyText
    status: DocumentStatus
    academic_year: AcademicYear
    timezone: str = Field(pattern=r"^Asia/Singapore$")
    source_ids: list[Identifier] = Field(min_length=1)
    events: list[CalendarEvent] = Field(min_length=1)
    raw_markdown: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    placeholder_reason: NonEmptyText | None = None

    @field_validator("source_ids")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        return _unique(value, "source_ids")

    @model_validator(mode="after")
    def validate_document(self) -> AcademicCalendarDocument:
        if self.status is DocumentStatus.COLLECTED:
            raise ValueError("COLLECTED status is reserved for offering collections")
        _unique([event.event_id for event in self.events], "event_ids")
        undeclared_sources = {
            source_id
            for event in self.events
            for source_id in event.source_ids
            if source_id not in self.source_ids
        }
        if undeclared_sources:
            raise ValueError(
                "event source_ids must be declared by the calendar document: "
                f"{sorted(undeclared_sources)}"
            )
        if self.status is DocumentStatus.AVAILABLE and any(
            event.origin in {SourceOrigin.UNKNOWN, SourceOrigin.UNVERIFIED_REAL}
            for event in self.events
        ):
            raise ValueError(
                "calendars with unknown or unverified events must be PARTIAL"
            )
        if self.status is DocumentStatus.PLACEHOLDER:
            if self.placeholder_reason is None:
                raise ValueError("placeholder calendars require placeholder_reason")
            if any(event.origin is SourceOrigin.VERIFIED_REAL for event in self.events):
                raise ValueError(
                    "placeholder calendars cannot contain verified calendar events"
                )
        elif self.placeholder_reason is not None:
            raise ValueError("only placeholder calendars may have placeholder_reason")
        return self


class CourseOfferingCollection(DomainModel):
    """Collection distinguishing unavailable data from a verified empty set."""

    status: DocumentStatus
    source_ids: list[Identifier] = Field(default_factory=list)
    offerings: list[CourseOffering] = Field(default_factory=list)
    placeholder_reason: NonEmptyText | None = None

    @field_validator("source_ids")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        return _unique(value, "source_ids")

    @model_validator(mode="after")
    def validate_collection(self) -> CourseOfferingCollection:
        _unique(
            [offering.offering_id for offering in self.offerings], "offering_ids"
        )
        if self.status is DocumentStatus.PLACEHOLDER:
            if self.placeholder_reason is None:
                raise ValueError("placeholder collections require placeholder_reason")
            if self.offerings:
                raise ValueError("placeholder collections cannot contain offerings")
        elif self.placeholder_reason is not None:
            raise ValueError("only placeholder collections may have placeholder_reason")
        if self.status is DocumentStatus.COLLECTED:
            if not self.source_ids or not self.offerings:
                raise ValueError(
                    "collected offering collections require sources and offerings"
                )
        return self
