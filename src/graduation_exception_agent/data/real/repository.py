"""Two-phase loading and cross-file validation for grounded real data."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

from pydantic import Field

from graduation_exception_agent.data.real.loaders import (
    load_course_offerings,
    load_courses,
    load_curricula,
    load_academic_calendar,
    load_policy_corpus,
    load_programmes,
    load_source_manifest,
)
from graduation_exception_agent.errors import DataIntegrityError
from graduation_exception_agent.models import (
    AcademicCalendarDocument,
    Course,
    CourseOffering,
    CourseOfferingCollection,
    Curriculum,
    DomainModel,
    Identifier,
    PolicyDocument,
    PolicyApplicability,
    PolicyDocumentType,
    PolicySection,
    Programme,
    Semester,
    SourceOrigin,
    SourceProvenance,
)


class ConsistencySeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ConsistencyIssue(DomainModel):
    """Stable machine-readable cross-file validation result."""

    code: Identifier
    severity: ConsistencySeverity
    dataset: Identifier
    record_id: Identifier
    field: Identifier
    referenced_id: Identifier | None = None
    message: str = Field(min_length=1, max_length=1000)


@dataclass(frozen=True, slots=True)
class RealDataBundle:
    """Structurally parsed real data before or after integrity validation."""

    sources: tuple[SourceProvenance, ...]
    programmes: tuple[Programme, ...]
    curricula: tuple[Curriculum, ...]
    courses: tuple[Course, ...]
    offering_collection: CourseOfferingCollection
    academic_calendar: AcademicCalendarDocument
    policies: tuple[PolicyDocument, ...]

    @property
    def offerings(self) -> tuple[CourseOffering, ...]:
        return tuple(self.offering_collection.offerings)


class RealDataRepository:
    """Immutable indexed view over one validated local `data/real` tree."""

    def __init__(
        self, bundle: RealDataBundle, *, fail_on_errors: bool = True
    ) -> None:
        issues = validate_real_data(bundle)
        errors = [
            issue for issue in issues if issue.severity is ConsistencySeverity.ERROR
        ]
        if fail_on_errors and errors:
            raise DataIntegrityError(
                "<in-memory-real-data>",
                [issue.model_dump(mode="json") for issue in errors],
            )
        self._consistency_issues = deepcopy(issues)
        self._bundle = deepcopy(bundle)
        self._sources: Mapping[str, SourceProvenance] = MappingProxyType(
            {source.source_id: source for source in self._bundle.sources}
        )
        self._programmes: Mapping[str, Programme] = MappingProxyType(
            {programme.code: programme for programme in self._bundle.programmes}
        )
        self._curricula: Mapping[str, Curriculum] = MappingProxyType(
            {
                curriculum.curriculum_id: curriculum
                for curriculum in self._bundle.curricula
            }
        )
        self._courses: Mapping[str, Course] = MappingProxyType(
            {course.code: course for course in self._bundle.courses}
        )

    @classmethod
    def from_directory(
        cls, root: str | Path, *, fail_on_errors: bool = True
    ) -> RealDataRepository:
        """Parse all required files, then apply deterministic cross-file checks."""

        data_root = Path(root)
        policy_root = data_root / "public_policies"
        sources = load_source_manifest(data_root / "source_manifest.json")
        bundle = RealDataBundle(
            sources=sources,
            programmes=load_programmes(
                data_root / "programmes.json", sources=sources
            ),
            curricula=load_curricula(
                data_root / "curriculum.json", sources=sources
            ),
            courses=load_courses(data_root / "courses.json", sources=sources),
            offering_collection=load_course_offerings(
                data_root / "course_offerings.json", sources=sources
            ),
            academic_calendar=load_academic_calendar(
                data_root / "academic_calendar.md", sources=sources
            ),
            policies=load_policy_corpus(policy_root, sources=sources),
        )
        try:
            return cls(bundle, fail_on_errors=fail_on_errors)
        except DataIntegrityError as exc:
            raise DataIntegrityError(data_root, list(exc.issues)) from exc

    @property
    def bundle(self) -> RealDataBundle:
        return deepcopy(self._bundle)

    @property
    def consistency_issues(self) -> tuple[ConsistencyIssue, ...]:
        return deepcopy(self._consistency_issues)

    @property
    def sources(self) -> tuple[SourceProvenance, ...]:
        return deepcopy(self._bundle.sources)

    @property
    def programmes(self) -> tuple[Programme, ...]:
        return deepcopy(self._bundle.programmes)

    @property
    def curricula(self) -> tuple[Curriculum, ...]:
        return deepcopy(self._bundle.curricula)

    @property
    def courses(self) -> tuple[Course, ...]:
        return deepcopy(self._bundle.courses)

    @property
    def offerings(self) -> tuple[CourseOffering, ...]:
        return deepcopy(self._bundle.offerings)

    @property
    def policies(self) -> tuple[PolicyDocument, ...]:
        return deepcopy(self._bundle.policies)

    def get_source(self, source_id: str) -> SourceProvenance:
        return deepcopy(self._sources[source_id])

    def get_programme(self, programme_code: str) -> Programme:
        return deepcopy(self._programmes[programme_code.upper()])

    def get_curriculum(self, curriculum_id: str) -> Curriculum:
        return deepcopy(self._curricula[curriculum_id])

    def find_curricula(
        self,
        *,
        programme: str,
        admission_cohort: str | None = None,
        effective_academic_year: str | None = None,
    ) -> tuple[Curriculum, ...]:
        matches = tuple(
            curriculum
            for curriculum in self._bundle.curricula
            if curriculum.programme == programme.upper()
            and (
                admission_cohort is None
                or curriculum.admission_cohort == admission_cohort.upper()
            )
            and (
                effective_academic_year is None
                or curriculum.effective_academic_year
                == effective_academic_year.upper()
            )
        )
        return deepcopy(matches)

    def get_course(self, course_code: str) -> Course:
        return deepcopy(self._courses[course_code.upper()])

    def find_offerings(
        self,
        *,
        course_code: str,
        academic_year: str,
        semester: Semester,
    ) -> tuple[CourseOffering, ...]:
        matches = tuple(
            offering
            for offering in self._bundle.offerings
            if offering.course_code == course_code.upper()
            and offering.academic_year == academic_year.upper()
            and offering.semester == semester
        )
        return deepcopy(matches)

    def policy_sections(
        self,
        *,
        policy_type: PolicyDocumentType | None = None,
        origins: frozenset[SourceOrigin] | None = None,
        academic_year: str | None = None,
        admission_cohort: str | None = None,
        include_unscoped: bool = False,
    ) -> tuple[PolicySection, ...]:
        if academic_year is None and admission_cohort is None:
            raise ValueError(
                "policy queries require academic_year or admission_cohort context"
            )
        selected_origins = (
            frozenset({SourceOrigin.VERIFIED_REAL})
            if origins is None
            else origins
        )
        matches = tuple(
            section
            for document in self._bundle.policies
            if policy_type is None or document.document_type is policy_type
            for section in document.sections
            if section.origin in selected_origins
            and _policy_applies(
                section,
                academic_year=academic_year,
                admission_cohort=admission_cohort,
                include_unscoped=include_unscoped,
            )
        )
        return deepcopy(matches)

    def provenance_for(
        self, source_ids: Iterable[str]
    ) -> tuple[SourceProvenance, ...]:
        return deepcopy(tuple(self._sources[source_id] for source_id in source_ids))


def _policy_applies(
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


@dataclass(frozen=True, slots=True)
class _SourceLink:
    dataset: str
    record_id: str
    field: str
    source_ids: tuple[str, ...]
    allowed_types: frozenset[str]
    required_origin: SourceOrigin | None = SourceOrigin.VERIFIED_REAL


def validate_real_data(bundle: RealDataBundle) -> tuple[ConsistencyIssue, ...]:
    """Return all deterministic integrity issues in stable order."""

    issues: list[ConsistencyIssue] = []
    sources = {source.source_id: source for source in bundle.sources}
    programmes = {programme.code: programme for programme in bundle.programmes}
    curricula = {curriculum.curriculum_id: curriculum for curriculum in bundle.curricula}
    courses = {course.code: course for course in bundle.courses}
    links = _source_links(bundle)

    _check_duplicate_programme_codes(bundle, issues)
    _check_duplicate_policy_ids(bundle, issues)
    _check_child_source_declarations(bundle, issues)
    _check_source_links(links, sources, issues)
    _check_policy_source_scopes(bundle, sources, issues)

    for curriculum in bundle.curricula:
        _check_curriculum_au_totals(curriculum, issues)
        if curriculum.programme not in programmes:
            _add_issue(
                issues,
                code="UNKNOWN_PROGRAMME",
                dataset="curricula",
                record_id=curriculum.curriculum_id,
                field="programme",
                referenced_id=curriculum.programme,
                message="curriculum programme has no programmes.json record",
            )
        for source_id in curriculum.source_ids:
            source = sources.get(source_id)
            if source is None:
                continue
            if source.programme is not None and source.programme != curriculum.programme:
                _add_issue(
                    issues,
                    code="SOURCE_PROGRAMME_MISMATCH",
                    dataset="curricula",
                    record_id=curriculum.curriculum_id,
                    field="source_ids",
                    referenced_id=source_id,
                    message="source programme does not match curriculum programme",
                )
            if (
                source.admission_cohort is not None
                and source.admission_cohort != curriculum.admission_cohort
            ):
                _add_issue(
                    issues,
                    code="SOURCE_COHORT_MISMATCH",
                    dataset="curricula",
                    record_id=curriculum.curriculum_id,
                    field="source_ids",
                    referenced_id=source_id,
                    message="source admission cohort does not match curriculum",
                )
            if (
                source.effective_academic_year is not None
                and source.effective_academic_year
                != curriculum.effective_academic_year
            ):
                _add_issue(
                    issues,
                    code="SOURCE_ACADEMIC_YEAR_MISMATCH",
                    dataset="curricula",
                    record_id=curriculum.curriculum_id,
                    field="source_ids",
                    referenced_id=source_id,
                    message="source academic year does not match curriculum",
                )
        for requirement in curriculum.requirements:
            for course_code in requirement.required_courses + requirement.elective_pool:
                if course_code not in courses:
                    _add_issue(
                        issues,
                        code="UNKNOWN_CURRICULUM_COURSE",
                        dataset="curricula",
                        record_id=curriculum.curriculum_id,
                        field="requirements",
                        referenced_id=course_code,
                        message="curriculum course reference is absent from course subset",
                    )

    curriculum_categories: dict[str, set[str]] = {}
    for curriculum in bundle.curricula:
        curriculum_categories.setdefault(curriculum.programme, set()).update(
            requirement.category for requirement in curriculum.requirements
        )

    for course in bundle.courses:
        for source_id in course.source_ids:
            source = sources.get(source_id)
            if (
                source is not None
                and source.programme is not None
                and source.programme not in course.applicable_programmes
            ):
                _add_issue(
                    issues,
                    code="SOURCE_PROGRAMME_MISMATCH",
                    dataset="courses",
                    record_id=f"course.{course.code}",
                    field="source_ids",
                    referenced_id=source_id,
                    message="course source programme is not listed as applicable",
                )
        for programme in course.applicable_programmes:
            if programme not in programmes:
                _add_issue(
                    issues,
                    code="UNKNOWN_PROGRAMME",
                    dataset="courses",
                    record_id=f"course.{course.code}",
                    field="applicable_programmes",
                    referenced_id=programme,
                    message="course applicability references an unknown programme",
                )
        related_codes = (
            course.prerequisites.all_of
            + course.prerequisites.any_of
            + course.exclusions
        )
        for related_code in related_codes:
            if related_code not in courses:
                _add_issue(
                    issues,
                    code="UNKNOWN_COURSE_REFERENCE",
                    dataset="courses",
                    record_id=f"course.{course.code}",
                    field="prerequisites_or_exclusions",
                    referenced_id=related_code,
                    message="course relation is outside the closed catalogue subset",
                )
        for programme, categories in course.programme_categories.items():
            available = curriculum_categories.get(programme, set())
            for category in categories:
                if category not in available:
                    _add_issue(
                        issues,
                        code="UNKNOWN_CURRICULUM_CATEGORY",
                        dataset="courses",
                        record_id=f"course.{course.code}",
                        field="programme_categories",
                        referenced_id=category,
                        message="course category is absent from programme curriculum",
                    )

    for offering in bundle.offerings:
        if offering.course_code not in courses:
            _add_issue(
                issues,
                code="UNKNOWN_OFFERING_COURSE",
                dataset="course_offerings",
                record_id=offering.offering_id,
                field="course_code",
                referenced_id=offering.course_code,
                message="offering references a course outside the catalogue subset",
            )
        for source_id in offering.source_ids:
            source = sources.get(source_id)
            if (
                source is not None
                and source.offering_academic_year is not None
                and source.offering_academic_year != offering.academic_year
            ):
                _add_issue(
                    issues,
                    code="SOURCE_ACADEMIC_YEAR_MISMATCH",
                    dataset="course_offerings",
                    record_id=offering.offering_id,
                    field="source_ids",
                    referenced_id=source_id,
                    message="source offering year does not match offering",
                )

    for source_id in bundle.academic_calendar.source_ids:
        source = sources.get(source_id)
        if (
            source is not None
            and source.effective_academic_year is not None
            and source.effective_academic_year
            != bundle.academic_calendar.academic_year
        ):
            _add_issue(
                issues,
                code="SOURCE_ACADEMIC_YEAR_MISMATCH",
                dataset="academic_calendar",
                record_id=bundle.academic_calendar.document_id,
                field="source_ids",
                referenced_id=source_id,
                message="source academic year does not match calendar",
            )

    _check_manifest_dependencies(bundle, links, sources, issues)

    return tuple(
        sorted(
            issues,
            key=lambda issue: (
                issue.severity,
                issue.code,
                issue.dataset,
                issue.record_id,
                issue.field,
                issue.referenced_id or "",
            ),
        )
    )


def _source_links(bundle: RealDataBundle) -> tuple[_SourceLink, ...]:
    links: list[_SourceLink] = []
    for programme in bundle.programmes:
        links.append(
            _SourceLink(
                "programmes",
                programme.programme_id,
                "source_ids",
                tuple(programme.source_ids),
                frozenset({"programme"}),
            )
        )
    for curriculum in bundle.curricula:
        links.append(
            _SourceLink(
                "curricula",
                curriculum.curriculum_id,
                "source_ids",
                tuple(curriculum.source_ids),
                frozenset({"curriculum"}),
            )
        )
    for course in bundle.courses:
        links.append(
            _SourceLink(
                "courses",
                f"course.{course.code}",
                "source_ids",
                tuple(course.source_ids),
                frozenset({"curriculum", "course_catalogue"}),
            )
        )
    if bundle.offering_collection.source_ids:
        links.append(
            _SourceLink(
                "course_offerings",
                "dataset.course_offerings",
                "source_ids",
                tuple(bundle.offering_collection.source_ids),
                frozenset({"course_offering", "class_schedule", "vacancy_snapshot"}),
            )
        )
    for offering in bundle.offerings:
        links.append(
            _SourceLink(
                "course_offerings",
                offering.offering_id,
                "source_ids",
                tuple(offering.source_ids),
                frozenset({"course_offering", "class_schedule", "vacancy_snapshot"}),
            )
        )
    links.append(
        _SourceLink(
            "academic_calendar",
            bundle.academic_calendar.document_id,
            "source_ids",
            tuple(bundle.academic_calendar.source_ids),
            frozenset({"academic_calendar", "academic_schedule"}),
        )
    )
    for event in bundle.academic_calendar.events:
        if event.source_ids:
            links.append(
                _SourceLink(
                    "academic_calendar",
                    event.event_id,
                    "source_ids",
                    tuple(event.source_ids),
                    frozenset({"academic_calendar", "academic_schedule"}),
                    event.origin,
                )
            )
    allowed_policy_types = frozenset(
        {
            "academic_handbook",
            "academic_schedule",
            "registration_guidance",
            "ccds_guidance",
            "ccds_contacts",
            "exception_guidance",
        }
    )
    for document in bundle.policies:
        if document.source_ids:
            links.append(
                _SourceLink(
                    "public_policies",
                    document.document_id,
                    "source_ids",
                    tuple(document.source_ids),
                    allowed_policy_types,
                )
            )
        for section in document.sections:
            if section.source_ids:
                links.append(
                    _SourceLink(
                        "public_policies",
                        section.section_id,
                        "source_ids",
                        tuple(section.source_ids),
                        allowed_policy_types,
                        section.origin,
                    )
                )
    return tuple(links)


def _check_duplicate_programme_codes(
    bundle: RealDataBundle, issues: list[ConsistencyIssue]
) -> None:
    codes = [programme.code for programme in bundle.programmes]
    for code in sorted({code for code in codes if codes.count(code) > 1}):
        _add_issue(
            issues,
            code="DUPLICATE_PROGRAMME_CODE",
            dataset="programmes",
            record_id=f"programme.{code}",
            field="code",
            referenced_id=code,
            message="programme codes must be unique",
        )


def _check_curriculum_au_totals(
    curriculum: Curriculum, issues: list[ConsistencyIssue]
) -> None:
    requirements = {
        requirement.category: requirement for requirement in curriculum.requirements
    }
    if curriculum.graduation_aus is not None and all(
        requirement.minimum_aus is not None
        for requirement in curriculum.requirements
    ):
        category_total = sum(
            requirement.minimum_aus
            for requirement in curriculum.requirements
            if requirement.minimum_aus is not None
        )
        if category_total != curriculum.graduation_aus:
            _add_issue(
                issues,
                code="CURRICULUM_AU_TOTAL_MISMATCH",
                dataset="curricula",
                record_id=curriculum.curriculum_id,
                field="graduation_aus",
                message=(
                    "graduation_aus does not equal the collected category AU total"
                ),
            )

    for path in curriculum.graduation_paths:
        path_categories = set(path.category_aus) | set(path.minimum_course_counts)
        for category in sorted(path_categories - set(requirements)):
            _add_issue(
                issues,
                code="UNKNOWN_GRADUATION_PATH_CATEGORY",
                dataset="curricula",
                record_id=curriculum.curriculum_id,
                field="graduation_paths",
                referenced_id=category,
                message="graduation path references an unknown requirement category",
            )
        unresolved = [
            requirement.category
            for requirement in curriculum.requirements
            if requirement.minimum_aus is None
            and requirement.category not in path.category_aus
        ]
        for category in unresolved:
            _add_issue(
                issues,
                code="UNRESOLVED_GRADUATION_PATH_AUS",
                dataset="curricula",
                record_id=curriculum.curriculum_id,
                field="graduation_paths",
                referenced_id=category,
                message="path omits AU total for a path-dependent requirement",
            )
        if not unresolved and not (set(path.category_aus) - set(requirements)):
            category_total = sum(
                path.category_aus.get(requirement.category, requirement.minimum_aus)
                for requirement in curriculum.requirements
            )
            if category_total != path.graduation_aus:
                _add_issue(
                    issues,
                    code="GRADUATION_PATH_AU_TOTAL_MISMATCH",
                    dataset="curricula",
                    record_id=curriculum.curriculum_id,
                    field="graduation_paths",
                    referenced_id=path.path_id,
                    message=(
                        "path graduation_aus does not equal its category AU total"
                    ),
                )


def _check_duplicate_policy_ids(
    bundle: RealDataBundle, issues: list[ConsistencyIssue]
) -> None:
    document_ids = [document.document_id for document in bundle.policies]
    for document_id in sorted(
        {value for value in document_ids if document_ids.count(value) > 1}
    ):
        _add_issue(
            issues,
            code="DUPLICATE_POLICY_DOCUMENT_ID",
            dataset="public_policies",
            record_id=document_id,
            field="document_id",
            referenced_id=document_id,
            message="policy document IDs must be unique across the corpus",
        )
    section_ids = [
        section.section_id
        for document in bundle.policies
        for section in document.sections
    ]
    for section_id in sorted(
        {value for value in section_ids if section_ids.count(value) > 1}
    ):
        _add_issue(
            issues,
            code="DUPLICATE_POLICY_SECTION_ID",
            dataset="public_policies",
            record_id=section_id,
            field="section_id",
            referenced_id=section_id,
            message="policy section IDs must be unique across the corpus",
        )


def _check_child_source_declarations(
    bundle: RealDataBundle, issues: list[ConsistencyIssue]
) -> None:
    calendar_sources = set(bundle.academic_calendar.source_ids)
    for event in bundle.academic_calendar.events:
        for source_id in sorted(set(event.source_ids) - calendar_sources):
            _add_issue(
                issues,
                code="SOURCE_NOT_DECLARED_BY_DOCUMENT",
                dataset="academic_calendar",
                record_id=event.event_id,
                field="source_ids",
                referenced_id=source_id,
                message="event source is absent from its document source_ids",
            )
    for document in bundle.policies:
        document_sources = set(document.source_ids)
        for section in document.sections:
            for source_id in sorted(set(section.source_ids) - document_sources):
                _add_issue(
                    issues,
                    code="SOURCE_NOT_DECLARED_BY_DOCUMENT",
                    dataset="public_policies",
                    record_id=section.section_id,
                    field="source_ids",
                    referenced_id=source_id,
                    message="section source is absent from its document source_ids",
                )


def _check_policy_source_scopes(
    bundle: RealDataBundle,
    sources: dict[str, SourceProvenance],
    issues: list[ConsistencyIssue],
) -> None:
    for document in bundle.policies:
        for section in document.sections:
            if section.applicability is not PolicyApplicability.EXPLICIT:
                continue
            for source_id in section.source_ids:
                source = sources.get(source_id)
                if source is None:
                    continue
                if (
                    source.admission_cohort is not None
                    and source.admission_cohort
                    not in section.applicable_admission_cohorts
                ):
                    _add_issue(
                        issues,
                        code="POLICY_SOURCE_COHORT_MISMATCH",
                        dataset="public_policies",
                        record_id=section.section_id,
                        field="applicable_admission_cohorts",
                        referenced_id=source_id,
                        message="typed policy cohort omits its source cohort",
                    )
                if (
                    source.effective_academic_year is not None
                    and section.applicable_academic_years
                    and source.effective_academic_year
                    not in section.applicable_academic_years
                ):
                    _add_issue(
                        issues,
                        code="POLICY_SOURCE_ACADEMIC_YEAR_MISMATCH",
                        dataset="public_policies",
                        record_id=section.section_id,
                        field="applicable_academic_years",
                        referenced_id=source_id,
                        message="typed policy academic year conflicts with its source",
                    )
def _check_source_links(
    links: tuple[_SourceLink, ...],
    sources: dict[str, SourceProvenance],
    issues: list[ConsistencyIssue],
) -> None:
    for link in links:
        for source_id in link.source_ids:
            source = sources.get(source_id)
            if source is None:
                _add_issue(
                    issues,
                    code="UNKNOWN_SOURCE_ID",
                    dataset=link.dataset,
                    record_id=link.record_id,
                    field=link.field,
                    referenced_id=source_id,
                    message="source_id is absent from source_manifest.json",
                )
                continue
            if source.source_type not in link.allowed_types:
                _add_issue(
                    issues,
                    code="SOURCE_TYPE_MISMATCH",
                    dataset=link.dataset,
                    record_id=link.record_id,
                    field=link.field,
                    referenced_id=source_id,
                    message=f"source type {source.source_type} is not valid here",
                )
            if (
                link.required_origin is SourceOrigin.VERIFIED_REAL
                and source.origin is not SourceOrigin.VERIFIED_REAL
            ):
                _add_issue(
                    issues,
                    code="SOURCE_ORIGIN_MISMATCH",
                    dataset=link.dataset,
                    record_id=link.record_id,
                    field=link.field,
                    referenced_id=source_id,
                    message="verified record is not backed by a verified real source",
                )
            if (
                link.required_origin is SourceOrigin.SIMULATED_POLICY
                and source.origin is not SourceOrigin.SIMULATED_POLICY
            ):
                _add_issue(
                    issues,
                    code="SOURCE_ORIGIN_MISMATCH",
                    dataset=link.dataset,
                    record_id=link.record_id,
                    field=link.field,
                    referenced_id=source_id,
                    message="simulated policy references a non-simulated source",
                )


def _check_manifest_dependencies(
    bundle: RealDataBundle,
    links: tuple[_SourceLink, ...],
    sources: dict[str, SourceProvenance],
    issues: list[ConsistencyIssue],
) -> None:
    all_record_ids = {
        programme.programme_id for programme in bundle.programmes
    } | {curriculum.curriculum_id for curriculum in bundle.curricula} | {
        f"course.{course.code}" for course in bundle.courses
    } | {offering.offering_id for offering in bundle.offerings} | {
        bundle.academic_calendar.document_id
    } | {event.event_id for event in bundle.academic_calendar.events} | {
        document.document_id for document in bundle.policies
    } | {
        section.section_id
        for document in bundle.policies
        for section in document.sections
    }
    if bundle.offering_collection.source_ids:
        all_record_ids.add("dataset.course_offerings")

    reverse: dict[str, set[str]] = {source_id: set() for source_id in sources}
    for link in links:
        for source_id in link.source_ids:
            if source_id in reverse:
                reverse[source_id].add(link.record_id)

    for source in bundle.sources:
        declared = set(source.dependent_records)
        for record_id in sorted(declared - all_record_ids):
            _add_issue(
                issues,
                code="UNKNOWN_DEPENDENT_RECORD",
                dataset="source_manifest",
                record_id=source.source_id,
                field="dependent_records",
                referenced_id=record_id,
                message="manifest dependency does not resolve to a loaded record",
            )
        missing = reverse[source.source_id] - declared
        extra = declared - reverse[source.source_id]
        for record_id in sorted(missing):
            _add_issue(
                issues,
                code="MISSING_REVERSE_PROVENANCE",
                dataset="source_manifest",
                record_id=source.source_id,
                field="dependent_records",
                referenced_id=record_id,
                message="referencing record is missing from source dependencies",
            )
        for record_id in sorted(extra & all_record_ids):
            _add_issue(
                issues,
                code="STALE_DEPENDENT_RECORD",
                dataset="source_manifest",
                record_id=source.source_id,
                field="dependent_records",
                referenced_id=record_id,
                message="declared dependency does not reference this source",
            )


def _add_issue(
    issues: list[ConsistencyIssue],
    *,
    code: str,
    dataset: str,
    record_id: str,
    field: str,
    message: str,
    referenced_id: str | None = None,
    severity: ConsistencySeverity = ConsistencySeverity.ERROR,
) -> None:
    issues.append(
        ConsistencyIssue(
            code=code,
            severity=severity,
            dataset=dataset,
            record_id=record_id,
            field=field,
            referenced_id=referenced_id,
            message=message,
        )
    )
