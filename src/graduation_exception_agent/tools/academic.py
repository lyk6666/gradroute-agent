"""Academic & Student tools over grounded and isolated observable records."""

from __future__ import annotations

from graduation_exception_agent.data.real.repository import RealDataRepository
from graduation_exception_agent.models.academic import DataCompleteness
from graduation_exception_agent.models.common import (
    DomainModel,
    Identifier,
    SyntheticStudentId,
)
from graduation_exception_agent.models.tooling import (
    ToolCallContext,
    ToolErrorCode,
    ToolResponse,
)
from graduation_exception_agent.runtime.session import RuntimeSession
from graduation_exception_agent.tools.common import (
    failure,
    real_provenance,
    simulated_provenance,
    success,
    validate_read_context,
)


class StudentRecordRequest(DomainModel):
    context: ToolCallContext
    student_id: SyntheticStudentId


class CurrentRegistrationRequest(DomainModel):
    context: ToolCallContext
    registration_id: Identifier


class CurriculumRequest(DomainModel):
    context: ToolCallContext
    curriculum_id: Identifier


class DegreeAuditRequest(DomainModel):
    context: ToolCallContext
    audit_id: Identifier


class AcademicStudentTools:
    """Read-only typed API for student, audit, registration, and curriculum facts."""

    def __init__(
        self, *, session: RuntimeSession, real_repository: RealDataRepository
    ) -> None:
        self._session = session
        self._real = real_repository

    def get_student_record(self, request: StudentRecordRequest) -> ToolResponse:
        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        try:
            student = self._session.get_student(request.student_id)
        except KeyError:
            return failure(
                request.context,
                ToolErrorCode.NOT_FOUND,
                "The student record is not visible in this case session.",
            )
        return success(
            request.context,
            student.model_dump(mode="json"),
            provenance=[
                simulated_provenance(
                    record_id=student.student_id,
                    rule_ids=student.source_rule_ids,
                )
            ],
        )

    def get_current_registration(
        self, request: CurrentRegistrationRequest
    ) -> ToolResponse:
        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        try:
            registration = self._session.get_registration(request.registration_id)
        except KeyError:
            return failure(
                request.context,
                ToolErrorCode.NOT_FOUND,
                "The registration record is not visible in this case session.",
            )
        return success(
            request.context,
            registration.model_dump(
                mode="json", exclude={"generator_version", "seed"}
            ),
            provenance=[
                simulated_provenance(
                    record_id=registration.registration_id,
                    rule_ids=registration.source_rule_ids,
                )
            ],
            entity_versions={
                registration.registration_id: self._session.entity_version(
                    registration.registration_id
                )
            },
        )

    def get_curriculum(self, request: CurriculumRequest) -> ToolResponse:
        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        try:
            curriculum = self._real.get_curriculum(request.curriculum_id)
        except KeyError:
            return failure(
                request.context,
                ToolErrorCode.NOT_FOUND,
                "No grounded curriculum has that identifier.",
            )
        completeness = curriculum.rules_completeness
        return success(
            request.context,
            curriculum.model_dump(mode="json"),
            provenance=real_provenance(
                self._real,
                curriculum.source_ids,
                completeness=completeness,
            ),
        )

    def run_degree_audit(self, request: DegreeAuditRequest) -> ToolResponse:
        """Return the frozen, explicitly scenario-bounded deterministic audit."""

        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        try:
            audit = self._session.get_audit(request.audit_id)
        except KeyError:
            return failure(
                request.context,
                ToolErrorCode.NOT_FOUND,
                "The degree audit is not visible in this case session.",
            )
        completeness = (
            DataCompleteness.PARTIAL
            if audit.limitations
            else DataCompleteness.COMPLETE
        )
        return success(
            request.context,
            audit.model_dump(mode="json", exclude={"generator_version", "seed"}),
            provenance=[
                simulated_provenance(
                    record_id=audit.audit_id,
                    rule_ids=audit.source_rule_ids,
                    completeness=completeness,
                    note=(
                        "Scenario-bounded deterministic degree audit; limitations and "
                        "assumptions remain visible in the result."
                    ),
                )
            ],
        )


__all__ = [
    "AcademicStudentTools",
    "CurrentRegistrationRequest",
    "CurriculumRequest",
    "DegreeAuditRequest",
    "StudentRecordRequest",
]
