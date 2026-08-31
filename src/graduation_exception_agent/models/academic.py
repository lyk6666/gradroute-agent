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
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class Semester(StrEnum):
    SEMESTER_1 = "SEMESTER_1"
    SEMESTER_2 = "SEMESTER_2"
    SPECIAL_TERM_1 = "SPECIAL_TERM_1"
    SPECIAL_TERM_2 = "SPECIAL_TERM_2"


class CurriculumConfigurationKind(StrEnum):
    """Whether a curriculum is a base degree plan or an additive overlay."""

    BASE = "BASE"
    OVERLAY = "OVERLAY"


class CourseCatalogueContext(StrEnum):
    """Meaning of one course appearance in the official catalogue UI."""

    PROGRAMME = "PROGRAMME"
    BDE_POOL = "BDE_POOL"
    AUXILIARY = "AUXILIARY"


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
    INDETERMINATE = "INDETERMINATE"


class AuditBasis(StrEnum):
    """What an audit result is allowed to claim."""

    SCENARIO_BOUNDED_SIMULATION = "SCENARIO_BOUNDED_SIMULATION"


class AuditOutcome(StrEnum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    INDETERMINATE = "INDETERMINATE"


class TerminalProfile(StrEnum):
    REQUIREMENT_OUTSTANDING = "REQUIREMENT_OUTSTANDING"
    INDEX_TIMETABLE_WORKLOAD_CONSTRAINED = (
        "INDEX_TIMETABLE_WORKLOAD_CONSTRAINED"
    )
    PREREQUISITE_OR_EVIDENCE_DEPENDENT = (
        "PREREQUISITE_OR_EVIDENCE_DEPENDENT"
    )
    NO_VERIFIED_RESOLUTION = "NO_VERIFIED_RESOLUTION"


class CreditStatus(StrEnum):
    EARNED = "EARNED"
    NOT_EARNED = "NOT_EARNED"
    PENDING_TRANSFER = "PENDING_TRANSFER"


class RegistrationPhase(StrEnum):
    NORMAL_REGISTRATION = "NORMAL_REGISTRATION"
    ADD_DROP = "ADD_DROP"
    POST_ADD_DROP = "POST_ADD_DROP"


class RuntimeOfferingStatus(StrEnum):
    OPEN = "OPEN"
    UNAVAILABLE = "UNAVAILABLE"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN = "UNKNOWN"


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
            and self.course_lists_completeness
            not in {DataCompleteness.COMPLETE, DataCompleteness.PARTIAL}
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


class CurriculumCoursePlanItem(DomainModel):
    """One source-order row from a published curriculum study plan."""

    plan_item_id: Identifier
    study_year: int = Field(ge=1, le=8)
    semester: Semester
    position: int = Field(ge=1)
    path_label: NonEmptyText | None = None
    course_code: CourseCode | None = None
    raw_course_code: NonEmptyText | None = None
    label: NonEmptyText
    category: Identifier
    aus: Decimal | None = Field(default=None, ge=0, le=40)
    requirement_id: Identifier | None = None
    notes: list[NonEmptyText] = Field(default_factory=list)
    source_ids: list[Identifier] = Field(min_length=1)

    @field_validator("notes", "source_ids")
    @classmethod
    def unique_plan_lists(cls, value: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "values")
        return _ensure_unique(value, field_name)


class Curriculum(DomainModel):
    curriculum_id: Identifier
    name: NonEmptyText | None = None
    programme: ProgrammeCode
    configuration_kind: CurriculumConfigurationKind = (
        CurriculumConfigurationKind.BASE
    )
    additional_applicable_programmes: list[ProgrammeCode] = Field(
        default_factory=list
    )
    admission_cohort: AdmissionCohort
    effective_academic_year: AcademicYear
    graduation_aus: Decimal | None = Field(default=None, gt=0)
    graduation_paths: list[GraduationPath] = Field(default_factory=list)
    requirements: list[CurriculumRequirement] = Field(default_factory=list)
    study_plan: list[CurriculumCoursePlanItem] = Field(default_factory=list)
    programme_constraints: list[NonEmptyText] = Field(default_factory=list)
    rules_completeness: DataCompleteness = DataCompleteness.UNKNOWN
    known_gaps: list[NonEmptyText] = Field(default_factory=list)
    unavailable_reason: NonEmptyText | None = None
    source_ids: list[Identifier] = Field(min_length=1)

    @field_validator(
        "source_ids",
        "additional_applicable_programmes",
        "known_gaps",
    )
    @classmethod
    def unique_sources(cls, value: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "values")
        return _ensure_unique(value, field_name)

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
        _ensure_unique(
            [item.plan_item_id for item in self.study_plan],
            "plan_item_ids",
        )
        plan_positions = [
            (item.study_year, item.semester, item.position, item.path_label)
            for item in self.study_plan
        ]
        if len(plan_positions) != len(set(plan_positions)):
            raise ValueError(
                "study_plan positions must be unique within year and semester"
            )
        undeclared_plan_sources = {
            source_id
            for item in self.study_plan
            for source_id in item.source_ids
            if source_id not in self.source_ids
        }
        if undeclared_plan_sources:
            raise ValueError(
                "study-plan source_ids must be declared by the curriculum: "
                f"{sorted(undeclared_plan_sources)}"
            )
        known_requirement_ids = {
            requirement.requirement_id for requirement in self.requirements
        }
        unknown_plan_requirements = {
            item.requirement_id
            for item in self.study_plan
            if item.requirement_id is not None
            and item.requirement_id not in known_requirement_ids
        }
        if unknown_plan_requirements:
            raise ValueError(
                "study_plan requirement_id must resolve within the curriculum: "
                f"{sorted(unknown_plan_requirements)}"
            )
        if self.programme in self.additional_applicable_programmes:
            raise ValueError(
                "additional_applicable_programmes cannot repeat the primary programme"
            )
        has_fixed_total = self.graduation_aus is not None
        has_paths = bool(self.graduation_paths)
        if has_fixed_total and has_paths:
            raise ValueError(
                "define at most one fixed graduation_aus or graduation_paths"
            )
        if self.rules_completeness is DataCompleteness.UNKNOWN:
            raise ValueError(
                "a curriculum must declare COMPLETE, PARTIAL, or UNAVAILABLE coverage"
            )
        if self.rules_completeness is DataCompleteness.COMPLETE:
            if self.name is None:
                raise ValueError("complete curricula require a name")
            if not (has_fixed_total or has_paths):
                raise ValueError(
                    "complete curricula require exactly one graduation total or paths"
                )
            if not self.requirements:
                raise ValueError("complete curricula require requirements")
            if self.known_gaps:
                raise ValueError("complete curricula cannot contain known_gaps")
            if self.unavailable_reason is not None:
                raise ValueError(
                    "complete curricula cannot contain unavailable_reason"
                )
        elif self.rules_completeness is DataCompleteness.PARTIAL:
            if self.name is None:
                raise ValueError("partial curricula require a name")
            has_rule_payload = bool(
                has_fixed_total
                or has_paths
                or self.requirements
                or self.study_plan
                or self.programme_constraints
            )
            if not has_rule_payload:
                raise ValueError("partial curricula require at least one sourced rule")
            if not self.known_gaps:
                raise ValueError("partial curricula require known_gaps")
            if self.unavailable_reason is not None:
                raise ValueError(
                    "partial curricula cannot contain unavailable_reason"
                )
        elif self.rules_completeness is DataCompleteness.UNAVAILABLE:
            has_rule_payload = bool(
                has_fixed_total
                or has_paths
                or self.requirements
                or self.study_plan
                or self.programme_constraints
            )
            if has_rule_payload:
                raise ValueError(
                    "unavailable curricula cannot contain unverified rule payloads"
                )
            if self.unavailable_reason is None:
                raise ValueError(
                    "unavailable curricula require unavailable_reason"
                )
            if self.known_gaps:
                raise ValueError(
                    "unavailable curricula use unavailable_reason, not known_gaps"
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


class CourseCatalogueAppearance(DomainModel):
    """Observed catalogue presence; it is not a live class offering."""

    academic_year: AcademicYear
    semester: Semester
    catalogue_context: CourseCatalogueContext = CourseCatalogueContext.PROGRAMME
    programme: ProgrammeCode | None = None
    study_years: list[int] = Field(default_factory=list)
    source_ids: list[Identifier] = Field(min_length=1)

    @field_validator("study_years")
    @classmethod
    def valid_study_years(cls, value: list[int]) -> list[int]:
        if any(year < 1 or year > 8 for year in value):
            raise ValueError("study years must be between 1 and 8")
        if len(value) != len(set(value)):
            raise ValueError("study_years must not contain duplicates")
        return sorted(value)

    @field_validator("source_ids")
    @classmethod
    def unique_appearance_sources(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, "source_ids")

    @model_validator(mode="after")
    def validate_context(self) -> CourseCatalogueAppearance:
        if (
            self.catalogue_context is CourseCatalogueContext.PROGRAMME
            and self.programme is None
        ):
            raise ValueError("PROGRAMME catalogue appearances require programme")
        return self


class Course(DomainModel):
    code: CourseCode
    title: NonEmptyText
    aus: Decimal = Field(ge=0, le=20)
    prerequisites: CoursePrerequisite = Field(default_factory=CoursePrerequisite)
    exclusions: list[CourseCode] = Field(default_factory=list)
    exclusions_raw_text: NonEmptyText | None = None
    catalogue_appearances: list[CourseCatalogueAppearance] = Field(
        default_factory=list
    )
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
        appearance_keys = [
            (
                appearance.academic_year,
                appearance.semester,
                appearance.catalogue_context,
                appearance.programme,
            )
            for appearance in self.catalogue_appearances
        ]
        if len(appearance_keys) != len(set(appearance_keys)):
            raise ValueError("catalogue appearances must be unique by observed context")
        declared_sources = set(self.source_ids)
        undeclared_appearance_sources = {
            source_id
            for appearance in self.catalogue_appearances
            for source_id in appearance.source_ids
            if source_id not in declared_sources
        }
        if undeclared_appearance_sources:
            raise ValueError(
                "catalogue-appearance source_ids must be declared by the course: "
                f"{sorted(undeclared_appearance_sources)}"
            )
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
            and self.prerequisites_completeness
            not in {DataCompleteness.COMPLETE, DataCompleteness.PARTIAL}
        ):
            raise ValueError(
                "known prerequisite data requires COMPLETE or PARTIAL coverage"
            )
        has_exclusion_data = bool(self.exclusions or self.exclusions_raw_text)
        if (
            has_exclusion_data
            and self.exclusions_completeness
            not in {DataCompleteness.COMPLETE, DataCompleteness.PARTIAL}
        ):
            raise ValueError("known exclusions require COMPLETE or PARTIAL coverage")
        if (
            (self.applicable_programmes or self.programme_categories)
            and self.applicability_completeness
            not in {DataCompleteness.COMPLETE, DataCompleteness.PARTIAL}
        ):
            raise ValueError(
                "known programme applicability requires COMPLETE or PARTIAL coverage"
            )
        if (
            self.documented_constraints
            and self.constraints_completeness
            not in {DataCompleteness.COMPLETE, DataCompleteness.PARTIAL}
        ):
            raise ValueError("known constraints require COMPLETE or PARTIAL coverage")
        return self


class TimetableMeeting(DomainModel):
    class_type: NonEmptyText
    group: NonEmptyText | None = None
    day: DayOfWeek | None = None
    start_time: time | None = None
    end_time: time | None = None
    raw_day: NonEmptyText | None = None
    raw_time: NonEmptyText | None = None
    venue: NonEmptyText | None = None
    remark: NonEmptyText | None = None
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
        parsed_values = (self.day, self.start_time, self.end_time)
        if any(value is not None for value in parsed_values) and not all(
            value is not None for value in parsed_values
        ):
            raise ValueError(
                "day, start_time, and end_time must be provided or omitted together"
            )
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("end_time must be after start_time")
        if all(value is None for value in parsed_values) and not (
            self.raw_day or self.raw_time or self.remark
        ):
            raise ValueError(
                "unparsed/TBA meetings require raw_day, raw_time, or remark"
            )
        return self


class CourseIndex(DomainModel):
    index_id: Identifier
    meetings: list[TimetableMeeting] = Field(default_factory=list)
    observed_programmes: list[ProgrammeCode] = Field(default_factory=list)
    capacity: int | None = Field(default=None, ge=0)
    vacancies: int | None = Field(default=None, ge=0)
    waitlist_count: int | None = Field(default=None, ge=0)

    @field_validator("observed_programmes")
    @classmethod
    def unique_observed_programmes(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, "observed_programmes")

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
    observed_programmes: list[ProgrammeCode] = Field(default_factory=list)
    scope_completeness: DataCompleteness = DataCompleteness.UNKNOWN
    indexes: list[CourseIndex] = Field(default_factory=list)
    snapshot_at: datetime | None = None
    source_ids: list[Identifier] = Field(min_length=1)

    @field_validator("snapshot_at")
    @classmethod
    def timezone_aware_snapshot(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("snapshot_at must include a timezone")
        return value

    @field_validator("source_ids", "observed_programmes")
    @classmethod
    def unique_sources(cls, value: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "values")
        return _ensure_unique(value, field_name)

    @model_validator(mode="after")
    def validate_indexes(self) -> CourseOffering:
        index_ids = [item.index_id for item in self.indexes]
        _ensure_unique(index_ids, "index_ids")
        if self.status is OfferingStatus.OFFERED and not self.indexes:
            raise ValueError("an offered course must contain at least one index")
        if self.observed_programmes and self.scope_completeness not in {
            DataCompleteness.COMPLETE,
            DataCompleteness.PARTIAL,
        }:
            raise ValueError(
                "observed programme scope requires COMPLETE or PARTIAL coverage"
            )
        offering_scope = set(self.observed_programmes)
        for index in self.indexes:
            if set(index.observed_programmes) - offering_scope:
                raise ValueError(
                    "index observed_programmes must be within offering scope"
                )
        return self


class OfferingState(GeneratedModel):
    """Mutable simulated availability, separate from the sourced offering."""

    state_id: Identifier
    simulation_period_id: Identifier
    template_offering_id: Identifier
    template_index_id: Identifier
    template_academic_year: AcademicYear
    template_semester: Semester
    capacity: int = Field(ge=0)
    vacancies: int = Field(ge=0)
    waitlist_count: int = Field(default=0, ge=0)
    runtime_status: RuntimeOfferingStatus
    available: bool
    unavailable_reason: NonEmptyText | None = None
    version: int = Field(default=1, ge=1)
    assumption_ids: list[Identifier] = Field(default_factory=list)

    @field_validator("assumption_ids")
    @classmethod
    def unique_assumptions(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, "assumption_ids")

    @model_validator(mode="after")
    def validate_runtime_capacity(self) -> OfferingState:
        if self.vacancies > self.capacity:
            raise ValueError("vacancies cannot exceed capacity")
        unavailable = self.runtime_status in {
            RuntimeOfferingStatus.UNAVAILABLE,
            RuntimeOfferingStatus.CLOSED,
            RuntimeOfferingStatus.CANCELLED,
        }
        if unavailable and self.unavailable_reason is None:
            raise ValueError(
                "unavailable, closed, or cancelled states require unavailable_reason"
            )
        if not unavailable and self.unavailable_reason is not None:
            raise ValueError("open states cannot contain unavailable_reason")
        expected_available = (
            self.runtime_status is RuntimeOfferingStatus.OPEN and self.vacancies > 0
        )
        if self.available is not expected_available:
            raise ValueError(
                "available must equal runtime_status == OPEN and vacancies > 0"
            )
        return self


class CompletedCourse(DomainModel):
    course_code: CourseCode
    grade: NonEmptyText
    aus_earned: Decimal = Field(ge=0, le=20)
    credit_status: CreditStatus
    academic_year: AcademicYear
    semester: Semester
    attempt: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_credit(self) -> CompletedCourse:
        if self.credit_status is not CreditStatus.EARNED and self.aus_earned != 0:
            raise ValueError("only EARNED attempts may award AUs")
        return self


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
    simulation_scope_id: Identifier
    simulation_period_id: Identifier
    programme: ProgrammeCode
    additional_programmes: list[ProgrammeCode] = Field(default_factory=list)
    curriculum_id: Identifier
    graduation_path_id: Identifier | None = None
    study_plan_path_label: NonEmptyText | None = None
    admission_cohort: AdmissionCohort
    study_year: int = Field(ge=1, le=8)
    terminal_profile: TerminalProfile
    academic_standing: NonEmptyText
    has_outstanding_fees: bool
    completed_courses: list[CompletedCourse] = Field(default_factory=list)
    earned_aus: Decimal = Field(ge=0)
    exemptions: list[Exemption] = Field(default_factory=list)
    assumption_ids: list[Identifier] = Field(default_factory=list)

    @field_validator("additional_programmes", "assumption_ids")
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
        earned_attempts = [
            item.course_code
            for item in self.completed_courses
            if item.credit_status is CreditStatus.EARNED
        ]
        _ensure_unique(earned_attempts, "earned course credits")
        exempt_course_codes = {
            exemption.course_code
            for exemption in self.exemptions
            if exemption.course_code is not None
        }
        duplicate_credit = exempt_course_codes & set(earned_attempts)
        if duplicate_credit:
            raise ValueError(
                "course credit cannot be both earned and exempted: "
                f"{sorted(duplicate_credit)}"
            )
        calculated_aus = sum(
            (
                item.aus_earned
                for item in self.completed_courses
                if item.credit_status is CreditStatus.EARNED
            ),
            Decimal("0"),
        ) + sum(
            (item.aus_awarded for item in self.exemptions),
            Decimal("0"),
        )
        if calculated_aus != self.earned_aus:
            raise ValueError(
                "earned_aus must equal earned course AUs plus exemption AUs"
            )
        return self


class ObservableStudent(DomainModel):
    """Agent-safe student record with evaluator-only profile metadata removed."""

    student_id: SyntheticStudentId
    simulation_scope_id: Identifier
    simulation_period_id: Identifier
    programme: ProgrammeCode
    additional_programmes: list[ProgrammeCode] = Field(default_factory=list)
    curriculum_id: Identifier
    graduation_path_id: Identifier | None = None
    study_plan_path_label: NonEmptyText | None = None
    admission_cohort: AdmissionCohort
    study_year: int = Field(ge=1, le=8)
    academic_standing: NonEmptyText
    has_outstanding_fees: bool
    completed_courses: list[CompletedCourse] = Field(default_factory=list)
    earned_aus: Decimal = Field(ge=0)
    exemptions: list[Exemption] = Field(default_factory=list)
    assumption_ids: list[Identifier] = Field(default_factory=list)
    source_rule_ids: list[Identifier] = Field(default_factory=list)

    @classmethod
    def from_student(cls, student: Student) -> ObservableStudent:
        return cls.model_validate(
            student.model_dump(
                exclude={"terminal_profile", "generator_version", "seed"}
            )
        )


class RequirementProgress(DomainModel):
    requirement_id: Identifier
    status: RequirementStatus
    required_aus: Decimal | None = Field(default=None, ge=0)
    earned_aus: Decimal = Field(ge=0)
    completed_courses: list[CourseCode] = Field(default_factory=list)
    outstanding_courses: list[CourseCode] = Field(default_factory=list)
    explanation: NonEmptyText
    evidence_rule_ids: list[Identifier] = Field(min_length=1)
    assumption_ids: list[Identifier] = Field(default_factory=list)
    limitations: list[NonEmptyText] = Field(default_factory=list)

    @field_validator(
        "completed_courses",
        "outstanding_courses",
        "evidence_rule_ids",
        "assumption_ids",
        "limitations",
    )
    @classmethod
    def unique_progress_courses(cls, value: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "courses")
        return _ensure_unique(value, field_name)

    @model_validator(mode="after")
    def validate_progress(self) -> RequirementProgress:
        if set(self.completed_courses) & set(self.outstanding_courses):
            raise ValueError("a course cannot be both completed and outstanding")
        if self.required_aus is None and self.status is not RequirementStatus.INDETERMINATE:
            raise ValueError("unknown required_aus requires INDETERMINATE status")
        if (
            self.status is RequirementStatus.SATISFIED
            and self.required_aus is not None
            and self.required_aus > 0
            and self.earned_aus < self.required_aus
        ):
            raise ValueError("a satisfied AU requirement must meet its required AUs")
        if (
            self.status is RequirementStatus.INDETERMINATE
            and not self.limitations
        ):
            raise ValueError("indeterminate requirements require limitations")
        return self


class DegreeAudit(GeneratedModel):
    audit_id: Identifier
    student_id: SyntheticStudentId
    simulation_scope_id: Identifier
    simulation_period_id: Identifier
    curriculum_id: Identifier
    audit_basis: AuditBasis
    audit_outcome: AuditOutcome
    graduation_path_id: Identifier | None = None
    study_plan_path_label: NonEmptyText | None = None
    simulation_academic_year: AcademicYear
    semester: Semester
    requirement_results: list[RequirementProgress] = Field(min_length=1)
    total_earned_aus: Decimal = Field(ge=0)
    total_required_aus: Decimal | None = Field(default=None, gt=0)
    assumption_ids: list[Identifier] = Field(default_factory=list)
    limitations: list[NonEmptyText] = Field(default_factory=list)

    @field_validator("assumption_ids", "limitations")
    @classmethod
    def unique_audit_lists(cls, value: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "values")
        return _ensure_unique(value, field_name)

    @model_validator(mode="after")
    def validate_audit_result(self) -> DegreeAudit:
        requirement_ids = [item.requirement_id for item in self.requirement_results]
        _ensure_unique(requirement_ids, "requirement_ids")
        indeterminate = self.total_required_aus is None or any(
            item.status is RequirementStatus.INDETERMINATE
            for item in self.requirement_results
        )
        if indeterminate:
            expected = AuditOutcome.INDETERMINATE
        else:
            assert self.total_required_aus is not None
            ready = self.total_earned_aus >= self.total_required_aus and all(
                item.status is RequirementStatus.SATISFIED
                for item in self.requirement_results
            )
            expected = AuditOutcome.READY if ready else AuditOutcome.NOT_READY
        if self.audit_outcome is not expected:
            raise ValueError(
                "audit_outcome must agree with AU and requirement completion"
            )
        if self.audit_outcome is AuditOutcome.INDETERMINATE and not self.limitations:
            raise ValueError("indeterminate audits require limitations")
        return self


class RegistrationItem(DomainModel):
    registration_item_id: Identifier
    course_code: CourseCode
    template_offering_id: Identifier
    template_index_id: Identifier
    offering_state_id: Identifier
    expected_state_version: int = Field(ge=1)
    aus: Decimal = Field(ge=0, le=20)
    status: RegistrationItemStatus
    eligibility: EligibilityStatus
    eligibility_reason: NonEmptyText


class RegistrationMeeting(DomainModel):
    meeting_id: Identifier
    registration_item_id: Identifier
    course_code: CourseCode
    template_offering_id: Identifier
    template_index_id: Identifier
    meeting: TimetableMeeting


class Registration(GeneratedModel):
    registration_id: Identifier
    student_id: SyntheticStudentId
    simulation_scope_id: Identifier
    simulation_period_id: Identifier
    simulation_academic_year: AcademicYear
    semester: Semester
    template_academic_year: AcademicYear
    template_semester: Semester
    scenario_time: datetime
    phase: RegistrationPhase
    registered_courses: list[RegistrationItem] = Field(default_factory=list)
    timetable: list[RegistrationMeeting] = Field(default_factory=list)
    workload_aus: Decimal = Field(ge=0)
    workload_limit_aus: Decimal = Field(ge=0)
    missing_required_courses: list[CourseCode] = Field(default_factory=list)
    assumption_ids: list[Identifier] = Field(default_factory=list)

    @field_validator("scenario_time")
    @classmethod
    def timezone_aware_scenario_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("scenario_time must include a timezone")
        return value

    @field_validator("missing_required_courses", "assumption_ids")
    @classmethod
    def unique_registration_lists(
        cls, value: list[str], info: object
    ) -> list[str]:
        field_name = getattr(info, "field_name", "values")
        return _ensure_unique(value, field_name)

    @model_validator(mode="after")
    def validate_registration(self) -> Registration:
        registrations = [item.registration_item_id for item in self.registered_courses]
        if len(registrations) != len(set(registrations)):
            raise ValueError("registration_item_ids must be unique")
        course_indexes = [
            (item.course_code, item.template_offering_id, item.template_index_id)
            for item in self.registered_courses
        ]
        if len(course_indexes) != len(set(course_indexes)):
            raise ValueError("registered course/offering/index triples must be unique")
        calculated_workload = sum(
            (item.aus for item in self.registered_courses), Decimal("0")
        )
        if calculated_workload != self.workload_aus:
            raise ValueError("workload_aus must equal registered course AUs")
        if self.workload_aus > self.workload_limit_aus:
            raise ValueError("workload_aus cannot exceed workload_limit_aus")
        by_id = {item.registration_item_id: item for item in self.registered_courses}
        meeting_ids = [item.meeting_id for item in self.timetable]
        _ensure_unique(meeting_ids, "meeting_ids")
        for attributed in self.timetable:
            registration_item = by_id.get(attributed.registration_item_id)
            if registration_item is None:
                raise ValueError(
                    "timetable registration_item_id must resolve in registered_courses"
                )
            if (
                attributed.course_code != registration_item.course_code
                or attributed.template_offering_id
                != registration_item.template_offering_id
                or attributed.template_index_id
                != registration_item.template_index_id
            ):
                raise ValueError(
                    "timetable attribution must match its registration item"
                )
        return self
