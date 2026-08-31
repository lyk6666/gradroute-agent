"""Course & Scheduling tools with conservative three-valued checks."""

from __future__ import annotations

from pydantic import Field

from graduation_exception_agent.data.real.repository import RealDataRepository
from graduation_exception_agent.models.academic import (
    CreditStatus,
    DataCompleteness,
    TimetableMeeting,
)
from graduation_exception_agent.models.common import (
    CourseCode,
    DomainModel,
    Identifier,
    NonEmptyText,
    ProgrammeCode,
    SyntheticStudentId,
)
from graduation_exception_agent.models.tooling import (
    ToolCallContext,
    ToolError,
    ToolErrorCode,
    ToolResponse,
    ToolStatus,
)
from graduation_exception_agent.rules.prerequisites import (
    PrerequisiteResult,
    evaluate_prerequisite,
)
from graduation_exception_agent.runtime.session import RuntimeSession
from graduation_exception_agent.tools.common import (
    failure,
    real_provenance,
    simulated_provenance,
    success,
    validate_read_context,
)


class CourseSearchRequest(DomainModel):
    context: ToolCallContext
    query: NonEmptyText | None = None
    programme: ProgrammeCode | None = None
    limit: int = Field(default=20, ge=1, le=100)


class CourseDetailsRequest(DomainModel):
    context: ToolCallContext
    course_code: CourseCode


class StudentCourseCheckRequest(DomainModel):
    context: ToolCallContext
    course_code: CourseCode
    student_id: SyntheticStudentId


class SemesterOfferingsRequest(DomainModel):
    context: ToolCallContext
    course_code: CourseCode


class TimetableCheckRequest(DomainModel):
    context: ToolCallContext
    offering_state_id: Identifier
    registration_id: Identifier


class WorkloadCheckRequest(DomainModel):
    context: ToolCallContext
    course_code: CourseCode
    registration_id: Identifier


class AvailabilityCheckRequest(DomainModel):
    context: ToolCallContext
    offering_state_id: Identifier
    expected_version: int | None = Field(default=None, ge=1)


class CourseSchedulingTools:
    """Grounded course lookup plus current per-session feasibility checks."""

    def __init__(
        self, *, session: RuntimeSession, real_repository: RealDataRepository
    ) -> None:
        self._session = session
        self._real = real_repository
        self._offering_by_id = {
            offering.offering_id: offering for offering in real_repository.offerings
        }

    def search_courses(self, request: CourseSearchRequest) -> ToolResponse:
        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        query = "" if request.query is None else request.query.lower()
        matches = [
            course
            for course in self._real.courses
            if (
                not query
                or query in course.code.lower()
                or query in course.title.lower()
            )
            and (
                request.programme is None
                or request.programme in course.applicable_programmes
            )
        ]
        matches = sorted(matches, key=lambda item: item.code)[: request.limit]
        provenance = [
            entry
            for course in matches
            for entry in real_provenance(
                self._real,
                course.source_ids,
                completeness=course.applicability_completeness,
            )
        ]
        return success(
            request.context,
            {
                "result_count": len(matches),
                "courses": [
                    {
                        "course_code": course.code,
                        "title": course.title,
                        "aus": str(course.aus),
                        "applicable_programmes": list(course.applicable_programmes),
                        "programme_categories": course.programme_categories,
                        "applicability_completeness": (
                            course.applicability_completeness.value
                        ),
                    }
                    for course in matches
                ],
            },
            provenance=provenance,
        )

    def get_course_details(self, request: CourseDetailsRequest) -> ToolResponse:
        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        try:
            course = self._real.get_course(request.course_code)
        except KeyError:
            return failure(
                request.context,
                ToolErrorCode.NOT_FOUND,
                "No grounded course has that code.",
            )
        completeness = _least_complete(
            course.prerequisites_completeness,
            course.exclusions_completeness,
            course.applicability_completeness,
            course.constraints_completeness,
        )
        return success(
            request.context,
            course.model_dump(mode="json"),
            provenance=real_provenance(
                self._real,
                course.source_ids,
                completeness=completeness,
            ),
        )

    def check_prerequisite(
        self, request: StudentCourseCheckRequest
    ) -> ToolResponse:
        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        try:
            student = self._session.get_student(request.student_id)
            course = self._real.get_course(request.course_code)
        except KeyError:
            return failure(
                request.context,
                ToolErrorCode.NOT_FOUND,
                "The student or course is not available in this session.",
            )
        completed = {
            item.course_code
            for item in student.completed_courses
            if item.credit_status is CreditStatus.EARNED
        } | {
            exemption.course_code
            for exemption in student.exemptions
            if exemption.course_code is not None
        }
        prerequisite = course.prerequisites
        missing_all = sorted(set(prerequisite.all_of) - completed)
        satisfied_any = sorted(set(prerequisite.any_of) & completed)
        if prerequisite.raw_text:
            result = evaluate_prerequisite(
                prerequisite.raw_text,
                completed_courses=completed,
                study_year=student.study_year,
            )
            reason = "The catalogue raw prerequisite text was evaluated conservatively."
        elif missing_all:
            result = PrerequisiteResult.FAIL
            reason = "One or more mandatory prerequisite courses are missing."
        elif prerequisite.any_of and not satisfied_any:
            result = PrerequisiteResult.FAIL
            reason = "None of the alternative prerequisite courses is complete."
        elif (
            prerequisite.minimum_study_year is not None
            and student.study_year < prerequisite.minimum_study_year
        ):
            result = PrerequisiteResult.FAIL
            reason = "The minimum study-year standing is not met."
        elif course.prerequisites_completeness in {
            DataCompleteness.UNKNOWN,
            DataCompleteness.UNAVAILABLE,
        }:
            result = PrerequisiteResult.UNKNOWN
            reason = "The prerequisite source is not complete enough for a safe pass."
        else:
            result = PrerequisiteResult.PASS
            reason = "All explicitly represented prerequisite conditions pass."
        return success(
            request.context,
            {
                "course_code": course.code,
                "student_id": student.student_id,
                "result": result.value,
                "reason": reason,
                "missing_all_of": missing_all,
                "satisfied_any_of": satisfied_any,
                "completeness": course.prerequisites_completeness.value,
            },
            provenance=real_provenance(
                self._real,
                course.source_ids,
                completeness=course.prerequisites_completeness,
            ),
        )

    def check_exclusion(self, request: StudentCourseCheckRequest) -> ToolResponse:
        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        try:
            student = self._session.get_student(request.student_id)
            course = self._real.get_course(request.course_code)
        except KeyError:
            return failure(
                request.context,
                ToolErrorCode.NOT_FOUND,
                "The student or course is not available in this session.",
            )
        registration = self._session.get_registration(
            self._session.context.registration_id
        )
        credited = {
            item.course_code
            for item in student.completed_courses
            if item.credit_status is CreditStatus.EARNED
        } | {
            exemption.course_code
            for exemption in student.exemptions
            if exemption.course_code is not None
        } | {item.course_code for item in registration.registered_courses}
        conflicts = sorted(set(course.exclusions) & credited)
        if conflicts:
            result = "FAIL"
            reason = "A credited or registered exclusion is present."
        elif course.exclusions_completeness is DataCompleteness.COMPLETE:
            result = "PASS"
            reason = "No exclusion is present in the complete represented list."
        else:
            result = "UNKNOWN"
            reason = "No represented conflict was found, but exclusion data is incomplete."
        return success(
            request.context,
            {
                "course_code": course.code,
                "student_id": student.student_id,
                "result": result,
                "reason": reason,
                "conflicting_course_codes": conflicts,
                "completeness": course.exclusions_completeness.value,
            },
            provenance=real_provenance(
                self._real,
                course.source_ids,
                completeness=course.exclusions_completeness,
            ),
        )

    def get_semester_offerings(
        self, request: SemesterOfferingsRequest
    ) -> ToolResponse:
        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        registration = self._session.get_registration(
            self._session.context.registration_id
        )
        offerings = self._real.find_offerings(
            course_code=request.course_code,
            academic_year=registration.template_academic_year,
            semester=registration.template_semester,
        )
        offering_ids = {offering.offering_id for offering in offerings}
        states = [
            state
            for state in self._session.offering_states()
            if state.template_offering_id in offering_ids
        ]
        provenance = [
            entry
            for offering in offerings
            for entry in real_provenance(
                self._real,
                offering.source_ids,
                completeness=offering.scope_completeness,
            )
        ] + [
            simulated_provenance(
                record_id=state.state_id,
                rule_ids=state.source_rule_ids,
                note="Current availability is simulated; timetable identity is sourced.",
            )
            for state in states
        ]
        return success(
            request.context,
            {
                "course_code": request.course_code,
                "template_academic_year": registration.template_academic_year,
                "template_semester": registration.template_semester.value,
                "offerings": [item.model_dump(mode="json") for item in offerings],
                "runtime_states": [
                    item.model_dump(
                        mode="json", exclude={"generator_version", "seed"}
                    )
                    for item in states
                ],
            },
            provenance=provenance,
            entity_versions={state.state_id: state.version for state in states},
        )

    def check_timetable(self, request: TimetableCheckRequest) -> ToolResponse:
        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        try:
            state = self._session.get_offering_state(request.offering_state_id)
            registration = self._session.get_registration(request.registration_id)
            offering = self._offering_by_id[state.template_offering_id]
            index = next(
                item
                for item in offering.indexes
                if item.index_id == state.template_index_id
            )
        except (KeyError, StopIteration):
            return failure(
                request.context,
                ToolErrorCode.NOT_FOUND,
                "The class index or registration is not visible in this session.",
            )
        conflicts: list[dict[str, str]] = []
        unknown = False
        for candidate in index.meetings:
            for existing in registration.timetable:
                overlaps = _meetings_overlap(candidate, existing.meeting)
                if overlaps is True:
                    conflicts.append(
                        {
                            "candidate_class_type": candidate.class_type,
                            "conflicting_course_code": existing.course_code,
                            "conflicting_meeting_id": existing.meeting_id,
                        }
                    )
                elif overlaps is None:
                    unknown = True
        if conflicts:
            result = "FAIL"
        elif unknown:
            result = "UNKNOWN"
        else:
            result = "PASS"
        return success(
            request.context,
            {
                "offering_state_id": state.state_id,
                "result": result,
                "conflicts": conflicts,
                "contains_unresolved_meeting": unknown,
            },
            provenance=real_provenance(
                self._real,
                offering.source_ids,
                completeness=offering.scope_completeness,
            ),
            entity_versions={state.state_id: state.version},
        )

    def check_workload(self, request: WorkloadCheckRequest) -> ToolResponse:
        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        try:
            course = self._real.get_course(request.course_code)
            registration = self._session.get_registration(request.registration_id)
        except KeyError:
            return failure(
                request.context,
                ToolErrorCode.NOT_FOUND,
                "The course or registration is not visible in this session.",
            )
        resulting = registration.workload_aus + course.aus
        passes = resulting <= registration.workload_limit_aus
        return success(
            request.context,
            {
                "course_code": course.code,
                "current_workload_aus": str(registration.workload_aus),
                "course_aus": str(course.aus),
                "resulting_workload_aus": str(resulting),
                "workload_limit_aus": str(registration.workload_limit_aus),
                "result": "PASS" if passes else "FAIL",
            },
            provenance=real_provenance(
                self._real,
                course.source_ids,
                completeness=DataCompleteness.COMPLETE,
            ),
            entity_versions={
                registration.registration_id: self._session.entity_version(
                    registration.registration_id
                )
            },
        )

    def check_availability(
        self, request: AvailabilityCheckRequest
    ) -> ToolResponse:
        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        try:
            state = self._session.get_offering_state(request.offering_state_id)
        except KeyError:
            return failure(
                request.context,
                ToolErrorCode.NOT_FOUND,
                "The offering state is not visible in this session.",
            )
        if request.expected_version is not None and request.expected_version != state.version:
            return ToolResponse(
                request_id=request.context.request_id,
                status=ToolStatus.FAILURE,
                error=ToolError(
                    code=ToolErrorCode.STALE_STATE,
                    message="The observed offering-state version is stale.",
                    retryable=True,
                    details={"current_version": state.version},
                ),
                entity_versions={state.state_id: state.version},
            )
        available = (
            state.runtime_status.value == "OPEN"
            and state.available
            and state.vacancies > 0
        )
        return success(
            request.context,
            {
                "offering_state_id": state.state_id,
                "available": available,
                "runtime_status": state.runtime_status.value,
                "vacancies": state.vacancies,
                "waitlist_count": state.waitlist_count,
                "version": state.version,
                "unavailable_reason": state.unavailable_reason,
            },
            provenance=[
                simulated_provenance(
                    record_id=state.state_id,
                    rule_ids=state.source_rule_ids,
                    note="Live capacity and vacancy are controlled simulated state.",
                )
            ],
            entity_versions={state.state_id: state.version},
        )


def _least_complete(*values: DataCompleteness) -> DataCompleteness:
    rank = {
        DataCompleteness.COMPLETE: 3,
        DataCompleteness.PARTIAL: 2,
        DataCompleteness.UNKNOWN: 1,
        DataCompleteness.UNAVAILABLE: 0,
    }
    return min(values, key=lambda value: rank[value])


def _meetings_overlap(
    left: TimetableMeeting, right: TimetableMeeting
) -> bool | None:
    parsed_left = (left.day, left.start_time, left.end_time)
    parsed_right = (right.day, right.start_time, right.end_time)
    if not all(value is not None for value in parsed_left + parsed_right):
        return None
    if left.day != right.day:
        return False
    if left.teaching_weeks and right.teaching_weeks:
        if set(left.teaching_weeks).isdisjoint(right.teaching_weeks):
            return False
    assert left.start_time is not None and left.end_time is not None
    assert right.start_time is not None and right.end_time is not None
    overlaps = left.start_time < right.end_time and right.start_time < left.end_time
    if not overlaps:
        return False
    if not left.teaching_weeks or not right.teaching_weeks:
        return None
    return True


__all__ = [
    "AvailabilityCheckRequest",
    "CourseDetailsRequest",
    "CourseSchedulingTools",
    "CourseSearchRequest",
    "SemesterOfferingsRequest",
    "StudentCourseCheckRequest",
    "TimetableCheckRequest",
    "WorkloadCheckRequest",
]
