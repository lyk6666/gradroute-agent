"""Academic, student, audit, and registration data contracts."""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from graduation_exception_agent.models.common import (
    AcademicYear,
    AdmissionCohort,
    CourseCode,
    DomainModel,
    GeneratedModel,
    Identifier,
    NonEmptyText,
    ProgrammeCode,
    SyntheticStudentId,
)


def _ensure_unique(values: list[str], field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


class DataCompleteness(StrEnum):
    """Whether a collected field is complete, partial, or not yet known."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class Semester(StrEnum):
    SEMESTER_1 = "SEMESTER_1"
    SEMESTER_2 = "SEMESTER_2"
    SPECIAL_TERM_1 = "SPECIAL_TERM_1"
    SPECIAL_TERM_2 = "SPECIAL_TERM_2"


class DayOfWeek(StrEnum):
    MONDAY = "MONDAY"
    TUESDAY = "TUESDAY"
    WEDNESDAY = "WEDNESDAY"
    THURSDAY = "THURSDAY"
    FRIDAY = "FRIDAY"
    SATURDAY = "SATURDAY"
    SUNDAY = "SUNDAY"


class OfferingStatus(StrEnum):
    OFFERED = "OFFERED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class RegistrationItemStatus(StrEnum):
    REGISTERED = "REGISTERED"
    WAITLISTED = "WAITLISTED"
    PENDING = "PENDING"
    DROPPED = "DROPPED"


class RequirementStatus(StrEnum):
    SATISFIED = "SATISFIED"
    PARTIALLY_SATISFIED = "PARTIALLY_SATISFIED"
    OUTSTANDING = "OUTSTANDING"


class CurriculumRequirement(DomainModel):
    requirement_id: Identifier
    name: NonEmptyText
    category: Identifier
    minimum_aus: Decimal | None = Field(default=None, gt=0)
    minimum_courses: int | None = Field(default=None, gt=0)
    required_courses: list[CourseCode] = Field(default_factory=list)
    elective_pool: list[CourseCode] = Field(default_factory=list)
    constraints: list[NonEmptyText] = Field(default_factory=list)
    course_lists_completeness: DataCompleteness = DataCompleteness.UNKNOWN

    @field_validator("required_courses", "elective_pool")
    @classmethod
    def unique_courses(cls, value: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "courses")
        return _ensure_unique(value, field_name)

    @model_validator(mode="after")
    def validate_requirement(self) -> CurriculumRequirement:
        if set(self.required_courses) & set(self.elective_pool):
            raise ValueError("a course cannot be both required and in the elective pool")
        if (
            self.minimum_aus is None
            and self.minimum_courses is None
            and not self.required_courses
            and not self.constraints
        ):
            raise ValueError("a requirement must define an AU, course, or count condition")
        if (
            (self.required_courses or self.elective_pool)
            and self.course_lists_completeness is DataCompleteness.UNKNOWN
        ):
            raise ValueError(
                "known requirement course lists require COMPLETE or PARTIAL coverage"
            )
        return self


class GraduationPath(DomainModel):
    """One explicit alternative route to a programme's graduation total."""

    path_id: Identifier
    name: NonEmptyText
    graduation_aus: Decimal = Field(gt=0)
    category_aus: dict[Identifier, Decimal] = Field(default_factory=dict)
    minimum_course_counts: dict[Identifier, int] = Field(default_factory=dict)
    required_components: list[NonEmptyText] = Field(default_factory=list)
    constraints: list[NonEmptyText] = Field(default_factory=list)

    @field_validator("category_aus")
    @classmethod
    def positive_category_aus(
        cls, value: dict[str, Decimal]
    ) -> dict[str, Decimal]:
        if any(aus <= 0 for aus in value.values()):
            raise ValueError("category_aus values must be positive")
        return value

    @field_validator("minimum_course_counts")
    @classmethod
    def positive_course_counts(cls, value: dict[str, int]) -> dict[str, int]:
        if any(count <= 0 for count in value.values()):
            raise ValueError("minimum_course_counts values must be positive")
        return value


class Curriculum(DomainModel):
    curriculum_id: Identifier
    programme: ProgrammeCode
    admission_cohort: AdmissionCohort
    effective_academic_year: AcademicYear
    graduation_aus: Decimal | None = Field(default=None, gt=0)
    graduation_paths: list[GraduationPath] = Field(default_factory=list)
    requirements: list[CurriculumRequirement] = Field(min_length=1)
    programme_constraints: list[NonEmptyText] = Field(default_factory=list)
    rules_completeness: DataCompleteness = DataCompleteness.UNKNOWN
    source_ids: list[Identifier] = Field(min_length=1)

    @field_validator("source_ids")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, "source_ids")

    @model_validator(mode="after")
    def unique_requirements(self) -> Curriculum:
        requirement_ids = [item.requirement_id for item in self.requirements]
        _ensure_unique(requirement_ids, "requirement_ids")
        _ensure_unique(
            [item.category for item in self.requirements],
            "requirement_categories",
        )
        _ensure_unique(
            [path.path_id for path in self.graduation_paths],
            "graduation_path_ids",
        )
        if (self.graduation_aus is None) == (not self.graduation_paths):
            raise ValueError(
                "define exactly one fixed graduation_aus or graduation_paths"
            )
        if self.rules_completeness is DataCompleteness.UNKNOWN:
            raise ValueError(
                "a populated curriculum must declare COMPLETE or PARTIAL rule coverage"
            )
        return self


class CoursePrerequisite(DomainModel):
    all_of: list[CourseCode] = Field(default_factory=list)
    any_of: list[CourseCode] = Field(default_factory=list)
    minimum_study_year: int | None = Field(default=None, ge=1, le=8)
    raw_text: NonEmptyText | None = None

    @field_validator("all_of", "any_of")
    @classmethod
    def unique_prerequisites(cls, value: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "prerequisites")
        return _ensure_unique(value, field_name)

    @model_validator(mode="after")
    def no_overlap(self) -> CoursePrerequisite:
        if set(self.all_of) & set(self.any_of):
            raise ValueError("a prerequisite cannot appear in both all_of and any_of")
        return self


class Course(DomainModel):
    code: CourseCode
    title: NonEmptyText
    aus: Decimal = Field(gt=0, le=20)
    prerequisites: CoursePrerequisite = Field(default_factory=CoursePrerequisite)
    exclusions: list[CourseCode] = Field(default_factory=list)
    applicable_programmes: list[ProgrammeCode] = Field(default_factory=list)
    programme_categories: dict[ProgrammeCode, list[Identifier]] = Field(
        default_factory=dict
    )
    documented_constraints: list[NonEmptyText] = Field(default_factory=list)
    prerequisites_completeness: DataCompleteness = DataCompleteness.UNKNOWN
    exclusions_completeness: DataCompleteness = DataCompleteness.UNKNOWN
    applicability_completeness: DataCompleteness = DataCompleteness.UNKNOWN
    constraints_completeness: DataCompleteness = DataCompleteness.UNKNOWN
    source_ids: list[Identifier] = Field(min_length=1)

    @field_validator("exclusions", "applicable_programmes", "source_ids")
    @classmethod
    def unique_lists(cls, value: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "values")
        return _ensure_unique(value, field_name)

    @field_validator("programme_categories")
    @classmethod
    def unique_categories(
        cls, value: dict[str, list[str]]
    ) -> dict[str, list[str]]:
        for programme, categories in value.items():
            _ensure_unique(categories, f"programme_categories[{programme}]")
        return value

    @model_validator(mode="after")
    def validate_course_relations(self) -> Course:
        if self.code in self.exclusions:
            raise ValueError("a course cannot exclude itself")
        if self.code in self.prerequisites.all_of or self.code in self.prerequisites.any_of:
            raise ValueError("a course cannot be its own prerequisite")
        unknown_programmes = set(self.programme_categories) - set(
            self.applicable_programmes
        )
        if unknown_programmes:
            raise ValueError(
                "programme_categories contains programmes not listed as applicable"
            )
        has_prerequisite_data = bool(
            self.prerequisites.all_of
            or self.prerequisites.any_of
            or self.prerequisites.minimum_study_year is not None
            or self.prerequisites.raw_text is not None
        )
        if (
            has_prerequisite_data
            and self.prerequisites_completeness is DataCompleteness.UNKNOWN
        ):
            raise ValueError(
                "known prerequisite data requires COMPLETE or PARTIAL coverage"
            )
        if self.exclusions and self.exclusions_completeness is DataCompleteness.UNKNOWN:
            raise ValueError("known exclusions require COMPLETE or PARTIAL coverage")
        if (
            (self.applicable_programmes or self.programme_categories)
            and self.applicability_completeness is DataCompleteness.UNKNOWN
        ):
            raise ValueError(
                "known programme applicability requires COMPLETE or PARTIAL coverage"
            )
        if (
            self.documented_constraints
            and self.constraints_completeness is DataCompleteness.UNKNOWN
        ):
            raise ValueError("known constraints require COMPLETE or PARTIAL coverage")
        return self


class TimetableMeeting(DomainModel):
    class_type: Identifier
    day: DayOfWeek
    start_time: time
    end_time: time
    venue: NonEmptyText | None = None
    teaching_weeks: list[int] = Field(default_factory=list)

    @field_validator("teaching_weeks")
    @classmethod
    def valid_weeks(cls, value: list[int]) -> list[int]:
        if any(week < 1 or week > 20 for week in value):
            raise ValueError("teaching weeks must be between 1 and 20")
        if len(value) != len(set(value)):
            raise ValueError("teaching_weeks must not contain duplicates")
        return sorted(value)

    @model_validator(mode="after")
    def end_after_start(self) -> TimetableMeeting:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class CourseIndex(DomainModel):
    index_id: Identifier
    meetings: list[TimetableMeeting] = Field(default_factory=list)
    capacity: int | None = Field(default=None, ge=0)
    vacancies: int | None = Field(default=None, ge=0)
    waitlist_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def vacancies_within_capacity(self) -> CourseIndex:
        if (
            self.capacity is not None
            and self.vacancies is not None
            and self.vacancies > self.capacity
        ):
            raise ValueError("vacancies cannot exceed capacity")
        return self


class CourseOffering(DomainModel):
    offering_id: Identifier
    course_code: CourseCode
    academic_year: AcademicYear
    semester: Semester
    status: OfferingStatus
    indexes: list[CourseIndex] = Field(default_factory=list)
    snapshot_at: datetime | None = None
    source_ids: list[Identifier] = Field(min_length=1)

    @field_validator("snapshot_at")
    @classmethod
    def timezone_aware_snapshot(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("snapshot_at must include a timezone")
        return value

    @field_validator("source_ids")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, "source_ids")

    @model_validator(mode="after")
    def validate_indexes(self) -> CourseOffering:
        index_ids = [item.index_id for item in self.indexes]
        _ensure_unique(index_ids, "index_ids")
        if self.status is OfferingStatus.OFFERED and not self.indexes:
            raise ValueError("an offered course must contain at least one index")
        return self


class OfferingState(GeneratedModel):
    """Mutable simulated availability, separate from the sourced offering."""

    state_id: Identifier
    offering_id: Identifier
    index_id: Identifier
    capacity: int = Field(ge=0)
    vacancies: int = Field(ge=0)
    waitlist_count: int = Field(default=0, ge=0)
    available: bool
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_runtime_capacity(self) -> OfferingState:
        if self.vacancies > self.capacity:
            raise ValueError("vacancies cannot exceed capacity")
        if self.available != (self.vacancies > 0):
            raise ValueError("available must reflect whether vacancies are positive")
        return self


class CompletedCourse(DomainModel):
    course_code: CourseCode
    grade: NonEmptyText
    aus_earned: Decimal = Field(ge=0, le=20)
    academic_year: AcademicYear
    semester: Semester
    attempt: int = Field(default=1, ge=1)


class Exemption(DomainModel):
    exemption_id: Identifier
    aus_awarded: Decimal = Field(default=Decimal("0"), ge=0)
    course_code: CourseCode | None = None
    category: Identifier | None = None
    reason: NonEmptyText

    @model_validator(mode="after")
    def identify_exemption_target(self) -> Exemption:
        if self.course_code is None and self.category is None:
            raise ValueError("an exemption requires a course_code or category")
        return self


class Student(GeneratedModel):
    student_id: SyntheticStudentId
    programme: ProgrammeCode
    additional_programmes: list[ProgrammeCode] = Field(default_factory=list)
    curriculum_ids: list[Identifier] = Field(min_length=1)
    admission_cohort: AdmissionCohort
    study_year: int = Field(ge=1, le=8)
    completed_courses: list[CompletedCourse] = Field(default_factory=list)
    earned_aus: Decimal = Field(ge=0)
    exemptions: list[Exemption] = Field(default_factory=list)

    @field_validator("additional_programmes", "curriculum_ids")
    @classmethod
    def unique_programme_links(cls, value: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "values")
        return _ensure_unique(value, field_name)

    @model_validator(mode="after")
    def validate_student_history(self) -> Student:
        if self.programme in self.additional_programmes:
            raise ValueError("primary programme cannot also be an additional programme")
        attempts = [
            (item.course_code, item.academic_year, item.semester, item.attempt)
            for item in self.completed_courses
        ]
        if len(attempts) != len(set(attempts)):
            raise ValueError("completed course attempts must be unique")
        exemption_ids = [item.exemption_id for item in self.exemptions]
        _ensure_unique(exemption_ids, "exemption_ids")
        return self


class RequirementProgress(DomainModel):
    requirement_id: Identifier
    status: RequirementStatus
    required_aus: Decimal = Field(ge=0)
    earned_aus: Decimal = Field(ge=0)
    completed_courses: list[CourseCode] = Field(default_factory=list)
    outstanding_courses: list[CourseCode] = Field(default_factory=list)
    explanation: NonEmptyText

    @field_validator("completed_courses", "outstanding_courses")
    @classmethod
    def unique_progress_courses(cls, value: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "courses")
        return _ensure_unique(value, field_name)

    @model_validator(mode="after")
    def validate_progress(self) -> RequirementProgress:
        if set(self.completed_courses) & set(self.outstanding_courses):
            raise ValueError("a course cannot be both completed and outstanding")
        if (
            self.status is RequirementStatus.SATISFIED
            and self.required_aus > 0
            and self.earned_aus < self.required_aus
        ):
            raise ValueError("a satisfied AU requirement must meet its required AUs")
        return self


class DegreeAudit(GeneratedModel):
    audit_id: Identifier
    student_id: SyntheticStudentId
    curriculum_ids: list[Identifier] = Field(min_length=1)
    academic_year: AcademicYear
    semester: Semester
    requirement_results: list[RequirementProgress] = Field(min_length=1)
    total_earned_aus: Decimal = Field(ge=0)
    total_required_aus: Decimal = Field(gt=0)
    graduation_ready: bool

    @field_validator("curriculum_ids")
    @classmethod
    def unique_curricula(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, "curriculum_ids")

    @model_validator(mode="after")
    def validate_audit_result(self) -> DegreeAudit:
        requirement_ids = [item.requirement_id for item in self.requirement_results]
        _ensure_unique(requirement_ids, "requirement_ids")
        computed_ready = self.total_earned_aus >= self.total_required_aus and all(
            item.status is RequirementStatus.SATISFIED
            for item in self.requirement_results
        )
        if self.graduation_ready != computed_ready:
            raise ValueError(
                "graduation_ready must agree with AU and requirement completion"
            )
        return self


class RegistrationItem(DomainModel):
    course_code: CourseCode
    index_id: Identifier
    aus: Decimal = Field(gt=0, le=20)
    status: RegistrationItemStatus


class Registration(GeneratedModel):
    registration_id: Identifier
    student_id: SyntheticStudentId
    academic_year: AcademicYear
    semester: Semester
    registered_courses: list[RegistrationItem] = Field(default_factory=list)
    timetable: list[TimetableMeeting] = Field(default_factory=list)
    workload_aus: Decimal = Field(ge=0)
    missing_required_courses: list[CourseCode] = Field(default_factory=list)

    @field_validator("missing_required_courses")
    @classmethod
    def unique_missing_courses(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, "missing_required_courses")

    @model_validator(mode="after")
    def validate_registration(self) -> Registration:
        registrations = [
            (item.course_code, item.index_id) for item in self.registered_courses
        ]
        if len(registrations) != len(set(registrations)):
            raise ValueError("registered course/index pairs must be unique")
        calculated_workload = sum(
            (item.aus for item in self.registered_courses), Decimal("0")
        )
        if calculated_workload != self.workload_aus:
            raise ValueError("workload_aus must equal registered course AUs")
        return self
