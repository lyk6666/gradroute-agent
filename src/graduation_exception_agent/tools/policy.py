"""Policy & Exception tools with explicit real/simulated provenance."""

from __future__ import annotations

import re

from pydantic import Field

from graduation_exception_agent.data.real.repository import RealDataRepository
from graduation_exception_agent.models.academic import DataCompleteness
from graduation_exception_agent.models.common import (
    DomainModel,
    Identifier,
    NonEmptyText,
    SourceOrigin,
)
from graduation_exception_agent.models.grounding import PolicyDocumentType
from graduation_exception_agent.models.simulation import PrototypePolicy
from graduation_exception_agent.models.tooling import (
    ToolCallContext,
    ToolErrorCode,
    ToolProvenance,
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


class PolicySearchRequest(DomainModel):
    context: ToolCallContext
    query: NonEmptyText
    policy_type: PolicyDocumentType | None = None
    include_simulated: bool = True
    limit: int = Field(default=10, ge=1, le=50)


class CasePolicyRequest(DomainModel):
    context: ToolCallContext
    case_id: Identifier


class PolicyExceptionTools:
    """Deterministic policy search and case requirement checks."""

    def __init__(
        self,
        *,
        session: RuntimeSession,
        real_repository: RealDataRepository,
        prototype_policies: tuple[PrototypePolicy, ...] = (),
    ) -> None:
        self._session = session
        self._real = real_repository
        self._prototype_policies = tuple(
            policy.model_copy(deep=True) for policy in prototype_policies
        )

    def search_policy(self, request: PolicySearchRequest) -> ToolResponse:
        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        student = self._session.get_student(self._session.context.student_id)
        registration = self._session.get_registration(
            self._session.context.registration_id
        )
        terms = _terms(request.query)
        sections = self._real.policy_sections(
            policy_type=request.policy_type,
            origins=frozenset(
                {
                    SourceOrigin.VERIFIED_REAL,
                    SourceOrigin.UNVERIFIED_REAL,
                    SourceOrigin.UNKNOWN,
                }
            ),
            academic_year=registration.template_academic_year,
            admission_cohort=student.admission_cohort,
            include_unscoped=True,
        )
        ranked: list[tuple[int, str, dict[str, object], list[ToolProvenance]]] = []
        for section in sections:
            haystack = f"{section.title}\n{section.body_markdown}".lower()
            score = sum(term in haystack for term in terms)
            if terms and score == 0:
                continue
            if section.source_ids:
                provenance = real_provenance(
                    self._real,
                    section.source_ids,
                    completeness=(
                        DataCompleteness.COMPLETE
                        if section.origin is SourceOrigin.VERIFIED_REAL
                        else DataCompleteness.PARTIAL
                    ),
                )
            else:
                provenance = [
                    ToolProvenance(
                        source_ids=[],
                        derived_from_ids=[section.section_id],
                        origin=section.origin,
                        completeness=DataCompleteness.UNKNOWN,
                        note="The public document contains no source-backed rule here.",
                    )
                ]
            ranked.append(
                (
                    score,
                    section.section_id,
                    {
                        "policy_id": section.section_id,
                        "title": section.title,
                        "body_markdown": section.body_markdown,
                        "origin": section.origin.value,
                        "applicability": section.applicability.value,
                        "source_ids": list(section.source_ids),
                        "simulated": False,
                    },
                    provenance,
                )
            )

        if request.include_simulated:
            for policy in self._prototype_policies:
                if (
                    policy.applicable_academic_years
                    and registration.simulation_academic_year
                    not in policy.applicable_academic_years
                ):
                    continue
                if (
                    policy.applicable_admission_cohorts
                    and student.admission_cohort
                    not in policy.applicable_admission_cohorts
                ):
                    continue
                haystack = f"{policy.title}\n{policy.body_markdown}".lower()
                score = sum(term in haystack for term in terms)
                if terms and score == 0:
                    continue
                ranked.append(
                    (
                        score,
                        policy.policy_id,
                        {
                            "policy_id": policy.policy_id,
                            "title": policy.title,
                            "body_markdown": policy.body_markdown,
                            "origin": policy.origin.value,
                            "applicability_note": policy.applicability_note,
                            "source_ids": [],
                            "simulated": True,
                        },
                        [
                            simulated_provenance(
                                record_id=policy.policy_id,
                                rule_ids=policy.source_rule_ids,
                                origin=policy.origin,
                                note=(
                                    "Explicitly simulated prototype policy; it is not an "
                                    "NTU public rule."
                                ),
                            )
                        ],
                    )
                )

        selected = sorted(ranked, key=lambda item: (-item[0], item[1]))[
            : request.limit
        ]
        return success(
            request.context,
            {
                "query": request.query,
                "result_count": len(selected),
                "results": [item[2] for item in selected],
            },
            provenance=[entry for item in selected for entry in item[3]],
        )

    def check_exception_eligibility(
        self, request: CasePolicyRequest
    ) -> ToolResponse:
        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        try:
            case = self._session.get_case(request.case_id)
        except KeyError:
            return failure(
                request.context,
                ToolErrorCode.NOT_FOUND,
                "The exception case is not visible in this session.",
            )
        requirement = self._session.approval_requirement(case.case_id)
        missing = [
            document.document_id
            for document in case.supporting_documents
            if not document.provided
        ]
        if missing:
            eligibility = "INCOMPLETE"
            reason = "Required supporting information is missing."
        elif requirement is not None or case.policy_section_ids:
            eligibility = "ELIGIBLE_FOR_REVIEW"
            reason = (
                "A declared review route exists; this does not predict or grant approval."
            )
        else:
            eligibility = "UNKNOWN"
            reason = "No sufficiently grounded autonomous exception route is available."
        return success(
            request.context,
            {
                "case_id": case.case_id,
                "problem_type": case.problem_type.value,
                "submission_ready": case.submission_ready,
                "unresolved_questions": list(case.unresolved_questions),
                "eligibility": eligibility,
                "reason": reason,
                "missing_document_ids": missing,
                "approval_required": requirement is not None,
            },
            provenance=[
                simulated_provenance(
                    record_id=case.case_id,
                    rule_ids=case.source_rule_ids,
                    origin=SourceOrigin.SIMULATED_POLICY,
                    completeness=(
                        DataCompleteness.PARTIAL
                        if eligibility == "UNKNOWN"
                        else DataCompleteness.COMPLETE
                    ),
                )
            ],
            entity_versions={case.case_id: self._session.entity_version(case.case_id)},
        )

    def get_approval_requirement(self, request: CasePolicyRequest) -> ToolResponse:
        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        try:
            case = self._session.get_case(request.case_id)
            requirement = self._session.approval_requirement(request.case_id)
        except KeyError:
            return failure(
                request.context,
                ToolErrorCode.NOT_FOUND,
                "The exception case is not visible in this session.",
            )
        if requirement is None:
            return success(
                request.context,
                {"case_id": case.case_id, "required": False},
                provenance=[
                    simulated_provenance(
                        record_id=case.case_id,
                        rule_ids=case.source_rule_ids,
                        origin=SourceOrigin.SIMULATED_POLICY,
                    )
                ],
            )
        data = {"required": True, **requirement.to_dict()}
        visible = self._session.observable_approval(case.case_id)
        if visible is not None:
            data["version"] = visible.version
            data["observable_status"] = visible.status.value
            data["decision_reason"] = visible.decision_reason
            data["decided_at"] = (
                None if visible.decided_at is None else visible.decided_at.isoformat()
            )
        return success(
            request.context,
            data,
            provenance=[
                simulated_provenance(
                    record_id=requirement.approval_id,
                    rule_ids=requirement.basis_rule_ids,
                    origin=(
                        SourceOrigin.SIMULATED_POLICY
                        if requirement.basis.value == "SIMULATED_POLICY"
                        else SourceOrigin.VERIFIED_REAL
                        if requirement.basis.value == "VERIFIED_PUBLIC_ROUTE"
                        else SourceOrigin.UNKNOWN
                    ),
                    note=(
                        "Approval-route metadata is visible; the outcome remains hidden "
                        "until the simulated decision is observed."
                    ),
                )
            ],
            entity_versions={
                requirement.approval_id: (
                    requirement.version if visible is None else visible.version
                )
            },
        )

    def get_required_documents(self, request: CasePolicyRequest) -> ToolResponse:
        invalid = validate_read_context(self._session, request.context)
        if invalid is not None:
            return invalid
        try:
            case = self._session.get_case(request.case_id)
            requirement = self._session.approval_requirement(request.case_id)
        except KeyError:
            return failure(
                request.context,
                ToolErrorCode.NOT_FOUND,
                "The exception case is not visible in this session.",
            )
        documents = {
            document.document_id: document.model_dump(mode="json")
            for document in case.supporting_documents
        }
        required_ids = (
            [] if requirement is None else list(requirement.required_document_ids)
        )
        for document_id in required_ids:
            documents.setdefault(
                document_id,
                {
                    "document_id": document_id,
                    "document_type": "DECLARED_BY_APPROVAL_ROUTE",
                    "provided": False,
                    "verified": None,
                },
            )
        return success(
            request.context,
            {
                "case_id": case.case_id,
                "required_document_ids": required_ids,
                "documents": [documents[key] for key in sorted(documents)],
                "missing_document_ids": [
                    key
                    for key in sorted(documents)
                    if not bool(documents[key]["provided"])
                ],
            },
            provenance=[
                simulated_provenance(
                    record_id=case.case_id,
                    rule_ids=(
                        case.source_rule_ids
                        if requirement is None
                        else requirement.basis_rule_ids
                    ),
                    # Document presence belongs to the simulated student/case
                    # record even when the requirement itself has a verified
                    # public basis.
                    origin=SourceOrigin.SIMULATED_POLICY,
                )
            ],
        )


def _terms(query: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            token.lower()
            for token in re.findall(r"[A-Za-z0-9_-]+", query)
            if len(token) >= 2
        )
    )


__all__ = ["CasePolicyRequest", "PolicyExceptionTools", "PolicySearchRequest"]
