"""Deterministic Stage 5 decision ports.

Stage 5 owns control flow, not language-model reasoning.  The default provider
therefore makes only conservative decisions from the observable intake and
Stage 4 tool results.  Stage 6 can replace this provider without changing the
graph, tools, checkpoints, or evaluator boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from graduation_exception_agent.models.orchestration import (
    IntakeContext,
    SpecialistKind,
    WorkflowState,
)
from graduation_exception_agent.models.runtime import (
    ClarificationImpact,
    VerifierDecisionCode,
)
from graduation_exception_agent.models.workflow import ExceptionCaseType


@dataclass(frozen=True, slots=True)
class PreActionAssessment:
    """One deterministic pre-action decision and its audit explanation."""

    decision: VerifierDecisionCode
    reason: str
    clarification_impact: ClarificationImpact = ClarificationImpact.NONE
    violation_codes: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.decision is VerifierDecisionCode.CLARIFY:
            if self.clarification_impact is ClarificationImpact.NONE:
                raise ValueError("CLARIFY requires a clarification impact")
            if not self.missing_fields:
                raise ValueError("CLARIFY requires the fields that must be supplied")
        elif self.clarification_impact is not ClarificationImpact.NONE:
            raise ValueError("clarification impact is valid only for CLARIFY")
        elif self.missing_fields:
            raise ValueError("missing_fields is valid only for CLARIFY")
        if self.decision in {
            VerifierDecisionCode.REPLAN,
            VerifierDecisionCode.CLARIFY,
            VerifierDecisionCode.ESCALATE,
        } and not self.violation_codes:
            raise ValueError(f"{self.decision.value} requires a violation code")


class DecisionProvider(Protocol):
    """Replaceable reasoning seam used by the Stage 5 control plane."""

    def select_specialists(
        self, state: WorkflowState
    ) -> tuple[SpecialistKind, ...]: ...

    def assess_pre_action(self, state: WorkflowState) -> PreActionAssessment: ...


class GroundedDecisionProvider:
    """Conservative rules over agent-safe intake and current tool evidence."""

    def select_specialists(
        self, state: WorkflowState
    ) -> tuple[SpecialistKind, ...]:
        intake = IntakeContext.model_validate(state["intake_context"])
        if intake.problem_type in {
            ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
            ExceptionCaseType.TIMETABLE_CONFLICT,
            ExceptionCaseType.WORKLOAD_OVERLOAD,
        }:
            # These cases need current policy and course feasibility, while a
            # complete degree audit is not required to compare class indexes.
            return (SpecialistKind.POLICY, SpecialistKind.COURSE)
        return (
            SpecialistKind.DEGREE_AUDIT,
            SpecialistKind.POLICY,
            SpecialistKind.COURSE,
        )

    def assess_pre_action(self, state: WorkflowState) -> PreActionAssessment:
        intake = IntakeContext.model_validate(state["intake_context"])
        results = state.get("tool_results", {})

        resolution_error = state.get("resolution_error")
        if resolution_error:
            return PreActionAssessment(
                decision=VerifierDecisionCode.ESCALATE,
                reason=str(
                    resolution_error.get(
                        "message", "No grounded candidate action could be constructed."
                    )
                ),
                violation_codes=(
                    str(resolution_error.get("code", "NO_GROUNDED_CANDIDATE")),
                ),
            )

        plan = state.get("plan", {})
        plan_id = str(plan.get("plan_id", ""))
        current_evidence = [
            item
            for item in state.get("specialist_evidence", [])
            if str(item.get("evidence_id", "")).startswith(f"evidence.{plan_id}.")
        ]
        required_specialists = {
            str(value)
            for value in state.get("specialist_selection", {}).get(
                "required_specialists", []
            )
        }
        observed_specialists = {
            str(item.get("specialist", "")) for item in current_evidence
        }
        if (
            not current_evidence
            or required_specialists != observed_specialists
            or any(
                not bool(item.get("completeness_known"))
                for item in current_evidence
            )
        ):
            return PreActionAssessment(
                decision=VerifierDecisionCode.ESCALATE,
                reason=(
                    "Current specialist evidence is missing, failed, or has unknown "
                    "completeness; a protected write cannot be authorized."
                ),
                violation_codes=("INCOMPLETE_GROUNDED_EVIDENCE",),
            )

        eligibility = _result_data(results, "exception_eligibility")
        documents = _result_data(results, "required_documents")
        policy_keys = (
            "exception_eligibility",
            "approval_requirement",
            "required_documents",
        )
        policy_provenance_valid = True
        for key in policy_keys:
            response = results.get(key)
            if not isinstance(response, dict) or response.get("status") != "SUCCESS":
                policy_provenance_valid = False
                break
            provenance = response.get("provenance")
            if not isinstance(provenance, list) or not provenance:
                policy_provenance_valid = False
                break
            if any(
                not isinstance(item, dict)
                or item.get("origin") not in {"VERIFIED_REAL", "SIMULATED_POLICY"}
                for item in provenance
            ):
                policy_provenance_valid = False
                break
        if not policy_provenance_valid:
            return PreActionAssessment(
                decision=VerifierDecisionCode.ESCALATE,
                reason=(
                    "Policy eligibility, approval, and document decisions require "
                    "explicit verified-real or simulated-policy provenance."
                ),
                violation_codes=("POLICY_PROVENANCE_NOT_AUTHORITATIVE",),
            )
        missing_documents = tuple(
            dict.fromkeys(
                str(value)
                for value in [
                    *eligibility.get("missing_document_ids", []),
                    *documents.get("missing_document_ids", []),
                ]
            )
        )
        if missing_documents or eligibility.get("eligibility") == "INCOMPLETE":
            return PreActionAssessment(
                decision=VerifierDecisionCode.CLARIFY,
                clarification_impact=ClarificationImpact.SMALL_CHANGE,
                reason="Required supporting information is still missing.",
                violation_codes=("REQUIRED_DOCUMENTS_MISSING",),
                missing_fields=(
                    missing_documents
                    if missing_documents
                    else ("required_supporting_information",)
                ),
            )
        if eligibility.get("eligibility") != "ELIGIBLE_FOR_REVIEW":
            return PreActionAssessment(
                decision=VerifierDecisionCode.ESCALATE,
                reason=(
                    "The current policy tools do not establish an eligible, grounded "
                    "review route."
                ),
                violation_codes=("ELIGIBILITY_NOT_GROUNDED",),
            )

        if intake.problem_type is ExceptionCaseType.GRADUATION_REQUIREMENT:
            audit = results.get("degree_audit")
            audit_data = audit.get("data", {}) if isinstance(audit, dict) else {}
            if audit_data.get("audit_outcome") == "INDETERMINATE":
                return PreActionAssessment(
                    decision=VerifierDecisionCode.CLARIFY,
                    clarification_impact=ClarificationImpact.MATERIAL_CHANGE,
                    reason=(
                        "The observable degree audit is indeterminate; the plan "
                        "must be rebuilt after the missing academic facts arrive."
                    ),
                    violation_codes=("INDETERMINATE_DEGREE_AUDIT",),
                    missing_fields=tuple(
                        intake.unresolved_questions
                        or ["academic_requirement_evidence"]
                    ),
                )

        if intake.problem_type is ExceptionCaseType.COURSE_UNAVAILABLE and (
            intake.submission_ready is False or intake.unresolved_questions
        ):
            return PreActionAssessment(
                decision=VerifierDecisionCode.CLARIFY,
                clarification_impact=ClarificationImpact.SMALL_CHANGE,
                reason=(
                    "The route is stable, but a declared submission field is still "
                    "missing and must be supplied before verification can continue."
                ),
                violation_codes=("MISSING_SUBMISSION_INFORMATION",),
                missing_fields=tuple(
                    intake.unresolved_questions or ["submission_declaration"]
                ),
            )

        if "action_candidate" not in state:
            return PreActionAssessment(
                decision=VerifierDecisionCode.ESCALATE,
                reason="No grounded candidate action could be constructed.",
                violation_codes=("NO_GROUNDED_CANDIDATE",),
            )

        candidate = state["action_candidate"]
        if not candidate:
            return PreActionAssessment(
                decision=VerifierDecisionCode.ESCALATE,
                reason="No grounded candidate action could be constructed.",
                violation_codes=("NO_GROUNDED_CANDIDATE",),
            )
        expected_evidence_ids = {
            str(item.get("evidence_id")) for item in current_evidence
        }
        if set(candidate.get("evidence_ids", [])) != expected_evidence_ids:
            return PreActionAssessment(
                decision=VerifierDecisionCode.ESCALATE,
                reason="The candidate is not bound to the complete current evidence set.",
                violation_codes=("CANDIDATE_EVIDENCE_MISMATCH",),
            )
        observed_versions: dict[str, int] = {}
        for response in results.values():
            if not isinstance(response, dict):
                continue
            for target_id, version in response.get("entity_versions", {}).items():
                if isinstance(version, int) and not isinstance(version, bool):
                    observed_versions[str(target_id)] = max(
                        version, observed_versions.get(str(target_id), 0)
                    )
        stale_targets = [
            str(expectation["target_id"])
            for expectation in candidate.get("expected_versions", [])
            if observed_versions.get(str(expectation["target_id"]))
            != expectation["expected_version"]
        ]
        if stale_targets:
            return PreActionAssessment(
                decision=VerifierDecisionCode.REPLAN,
                reason=(
                    "Candidate state versions are absent or stale for: "
                    + ", ".join(sorted(stale_targets))
                ),
                violation_codes=("STALE_OR_UNGROUNDED_VERSION",),
            )

        return PreActionAssessment(
            decision=VerifierDecisionCode.VALID,
            reason=(
                "The candidate is supported by current Stage 4 evidence and carries "
                "the observed versions required by the action gate."
            ),
        )


def _result_data(
    results: dict[str, dict[str, object]], key: str
) -> dict[str, object]:
    response = results.get(key)
    if not isinstance(response, dict):
        return {}
    data = response.get("data")
    return dict(data) if isinstance(data, dict) else {}


__all__ = [
    "DecisionProvider",
    "GroundedDecisionProvider",
    "PreActionAssessment",
]
