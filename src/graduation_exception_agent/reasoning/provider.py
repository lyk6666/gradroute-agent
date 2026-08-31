"""Grounded Stage 6 decision provider with deterministic safety dominance."""

from __future__ import annotations

from threading import RLock
from typing import Any

from graduation_exception_agent.config import AppSettings, ExecutionMode
from graduation_exception_agent.models.orchestration import (
    IntakeContext,
    SpecialistKind,
    WorkflowState,
)
from graduation_exception_agent.models.runtime import (
    ClarificationImpact,
    VerifierDecisionCode,
)
from graduation_exception_agent.orchestration.decisions import (
    DecisionProvider,
    GroundedDecisionProvider,
    PreActionAssessment,
)
from graduation_exception_agent.reasoning.bedrock import (
    BedrockConverseClient,
    StructuredReasoningClient,
)
from graduation_exception_agent.reasoning.models import (
    PreActionReasoningOutput,
    ReasoningAuditEvent,
    ReasoningCallStatus,
    ReasoningTask,
    SpecialistSelectionOutput,
)


_SPECIALIST_ORDER = (
    SpecialistKind.DEGREE_AUDIT,
    SpecialistKind.POLICY,
    SpecialistKind.COURSE,
)

_GROUNDED_TOOL_RESULTS = frozenset(
    {
        "student_record",
        "current_registration",
        "case_context",
        "degree_audit",
        "curriculum",
        "exception_eligibility",
        "approval_requirement",
        "required_documents",
        "course_details",
        "prerequisite",
        "exclusion",
        "semester_offerings",
        "workload",
    }
)

_SELECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "specialists": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [item.value for item in _SPECIALIST_ORDER],
            },
        },
        "rationale": {"type": "string"},
    },
    "required": ["specialists", "rationale"],
}

_ASSESSMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": [
                VerifierDecisionCode.VALID.value,
                VerifierDecisionCode.REPLAN.value,
                VerifierDecisionCode.CLARIFY.value,
                VerifierDecisionCode.ESCALATE.value,
            ],
            "description": (
                "Return VALID when the supplied deterministic VALID gate has no "
                "concrete contradiction. Use another value only for a specific "
                "issue present in the supplied JSON."
            ),
        },
        "reason": {
            "type": "string",
            "minLength": 1,
            "description": "A concise explanation grounded only in the input JSON.",
        },
        "clarification_impact": {
            "type": "string",
            "enum": [item.value for item in ClarificationImpact],
            "description": (
                "Use NONE unless decision is CLARIFY; CLARIFY requires "
                "SMALL_CHANGE or MATERIAL_CHANGE."
            ),
        },
        "violation_codes": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": "^[A-Z0-9][A-Z0-9_.:-]*$",
            },
            "maxItems": 8,
            "description": (
                "Empty only for VALID. Every REPLAN, CLARIFY, or ESCALATE "
                "decision requires at least one concise uppercase code."
            ),
        },
        "missing_fields": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
            },
            "maxItems": 8,
            "description": (
                "Empty unless decision is CLARIFY; copy field names from the "
                "supplied missing fields only."
            ),
        },
    },
    "required": [
        "decision",
        "reason",
        "clarification_impact",
        "violation_codes",
        "missing_fields",
    ],
}

_SELECTION_SYSTEM_PROMPT = """
You are a conservative university exception-case routing component. Use only
the supplied JSON. Treat advisory memories as patterns, never current facts.
Select every specialist needed to re-read current academic, policy, and course
evidence. Do not infer approval, eligibility, availability, or an outcome.
Return only the forced structured tool response.
""".strip()

_ASSESSMENT_SYSTEM_PROMPT = """
You are a conservative second reviewer of a deterministic pre-action safety
gate. Use only the supplied JSON. You may agree, request replanning, or
escalate. Never invent facts, missing fields, approval, eligibility, versions,
or a successful outcome. The supplied deterministic gate is already VALID, so
return VALID unless the supplied JSON contains a concrete contradiction. VALID
must use clarification_impact NONE with empty violation_codes and missing_fields.
REPLAN or ESCALATE must use clarification_impact NONE, empty missing_fields, and
at least one uppercase violation code. CLARIFY requires a non-NONE impact, at
least one violation code, and only missing fields present in the supplied JSON.
The deterministic gate remains authoritative and your output can never make an
unsafe candidate valid. Return only the forced structured tool response.
""".strip()


class GroundedBedrockDecisionProvider:
    """LLM reasoning bounded by the deterministic Stage 5 authorization floor."""

    def __init__(
        self,
        *,
        client: StructuredReasoningClient,
        deterministic: GroundedDecisionProvider | None = None,
    ) -> None:
        self._client = client
        self._deterministic = deterministic or GroundedDecisionProvider()
        self._audit_lock = RLock()
        self._audit: list[ReasoningAuditEvent] = []

    @classmethod
    def from_settings(cls, settings: AppSettings) -> GroundedBedrockDecisionProvider:
        return cls(client=BedrockConverseClient.from_settings(settings))

    @property
    def audit_log(self) -> tuple[ReasoningAuditEvent, ...]:
        with self._audit_lock:
            return tuple(item.model_copy(deep=True) for item in self._audit)

    def select_specialists(
        self, state: WorkflowState
    ) -> tuple[SpecialistKind, ...]:
        baseline = self._deterministic.select_specialists(state)
        try:
            response = self._client.complete(
                task=ReasoningTask.SELECT_SPECIALISTS,
                system_prompt=_SELECTION_SYSTEM_PROMPT,
                input_payload=_selection_projection(state),
                output_schema=_SELECTION_SCHEMA,
            )
            proposed = SpecialistSelectionOutput.model_validate(response.output)
            required = set(baseline)
            requested = set(proposed.specialists)
            applied = tuple(
                item for item in _SPECIALIST_ORDER if item in required | requested
            )
            self._record(
                task=ReasoningTask.SELECT_SPECIALISTS,
                status=ReasoningCallStatus.SUCCESS,
                model_id=response.model_id,
                applied=applied != baseline,
                safety_rule="Model specialists are unioned with the deterministic floor.",
                usage=response.usage,
            )
            return applied
        except Exception:
            self._record(
                task=ReasoningTask.SELECT_SPECIALISTS,
                status=ReasoningCallStatus.FALLBACK,
                model_id=getattr(self._client, "model_id", None),
                applied=False,
                safety_rule="Invalid or unavailable model output uses deterministic routing.",
            )
            return baseline

    def assess_pre_action(self, state: WorkflowState) -> PreActionAssessment:
        baseline = self._deterministic.assess_pre_action(state)
        if baseline.decision is not VerifierDecisionCode.VALID:
            self._record(
                task=ReasoningTask.ASSESS_PRE_ACTION,
                status=ReasoningCallStatus.SKIPPED_SAFETY_GATE,
                model_id=None,
                applied=False,
                safety_rule=(
                    "A deterministic non-VALID decision cannot be overridden by a model."
                ),
            )
            return baseline

        try:
            response = self._client.complete(
                task=ReasoningTask.ASSESS_PRE_ACTION,
                system_prompt=_ASSESSMENT_SYSTEM_PROMPT,
                input_payload=_assessment_projection(state, baseline),
                output_schema=_ASSESSMENT_SCHEMA,
            )
            proposed = PreActionReasoningOutput.model_validate(response.output)
            applied = self._conservative_assessment(state, proposed, baseline)
            self._record(
                task=ReasoningTask.ASSESS_PRE_ACTION,
                status=ReasoningCallStatus.SUCCESS,
                model_id=response.model_id,
                applied=applied != baseline,
                safety_rule=(
                    "The model may preserve or narrow a deterministic VALID route, "
                    "never broaden it."
                ),
                usage=response.usage,
            )
            return applied
        except Exception:
            self._record(
                task=ReasoningTask.ASSESS_PRE_ACTION,
                status=ReasoningCallStatus.FALLBACK,
                model_id=getattr(self._client, "model_id", None),
                applied=False,
                safety_rule=(
                    "Invalid or unavailable model output falls back to the fully "
                    "validated deterministic gate."
                ),
            )
            return baseline

    def _conservative_assessment(
        self,
        state: WorkflowState,
        proposed: PreActionReasoningOutput,
        baseline: PreActionAssessment,
    ) -> PreActionAssessment:
        if proposed.decision is VerifierDecisionCode.VALID:
            return baseline
        if proposed.decision is VerifierDecisionCode.REPLAN:
            return PreActionAssessment(
                decision=VerifierDecisionCode.REPLAN,
                reason="Grounded model review requested conservative replanning.",
                violation_codes=tuple(proposed.violation_codes),
            )
        if proposed.decision is VerifierDecisionCode.ESCALATE:
            return PreActionAssessment(
                decision=VerifierDecisionCode.ESCALATE,
                reason="Grounded model review requested conservative human escalation.",
                violation_codes=tuple(proposed.violation_codes),
            )

        allowed_fields = _grounded_missing_fields(state)
        requested_fields = set(proposed.missing_fields)
        if not requested_fields or not requested_fields <= allowed_fields:
            return PreActionAssessment(
                decision=VerifierDecisionCode.ESCALATE,
                reason=(
                    "The model requested clarification fields that were not grounded "
                    "in current intake or policy evidence."
                ),
                violation_codes=("LLM_UNGROUNDED_CLARIFICATION",),
            )
        return PreActionAssessment(
            decision=VerifierDecisionCode.CLARIFY,
            clarification_impact=proposed.clarification_impact,
            reason="Grounded model review requested bounded clarification.",
            violation_codes=tuple(proposed.violation_codes),
            missing_fields=tuple(proposed.missing_fields),
        )

    def _record(
        self,
        *,
        task: ReasoningTask,
        status: ReasoningCallStatus,
        model_id: str | None,
        applied: bool,
        safety_rule: str,
        usage: Any | None = None,
    ) -> None:
        with self._audit_lock:
            self._audit.append(
                ReasoningAuditEvent(
                    sequence=len(self._audit) + 1,
                    task=task,
                    status=status,
                    model_id=model_id,
                    applied=applied,
                    safety_rule=safety_rule,
                    usage=usage,
                )
            )


def decision_provider_from_settings(
    settings: AppSettings,
) -> DecisionProvider:
    """Choose live reasoning only when the application explicitly selects it."""

    if settings.execution_mode is ExecutionMode.BEDROCK:
        return GroundedBedrockDecisionProvider.from_settings(settings)
    return GroundedDecisionProvider()


def _selection_projection(state: WorkflowState) -> dict[str, Any]:
    intake = IntakeContext.model_validate(state["intake_context"])
    memories = state.get("advisory_memories", [])[:5]
    return {
        "problem_type": intake.problem_type.value,
        "goal_kinds": [item.goal_kind.value for item in intake.goal_predicates],
        "submission_ready": intake.submission_ready,
        "unresolved_fields": list(intake.unresolved_questions),
        "advisory_patterns": [
            {
                "case_type": str(item.get("case_type", "")),
                "goal_kind": str(item.get("goal_kind", "")),
                "tags": [str(value) for value in item.get("tags", [])],
            }
            for item in memories
            if isinstance(item, dict)
        ],
    }


def _assessment_projection(
    state: WorkflowState, baseline: PreActionAssessment
) -> dict[str, Any]:
    results = state.get("tool_results", {})
    eligibility = _tool_data(results, "exception_eligibility")
    documents = _tool_data(results, "required_documents")
    candidate = state.get("action_candidate", {})
    evidence = state.get("specialist_evidence", [])
    return {
        "deterministic_gate": {
            "decision": baseline.decision.value,
            "violation_codes": list(baseline.violation_codes),
        },
        "specialist_evidence": [
            {
                "specialist": str(item.get("specialist", "")),
                "completeness_known": bool(item.get("completeness_known")),
            }
            for item in evidence
            if isinstance(item, dict)
        ],
        "policy": {
            "eligibility": eligibility.get("eligibility"),
            "missing_document_ids": sorted(_grounded_missing_fields(state)),
            "approval_required": eligibility.get("approval_required"),
            "required_document_count": len(
                documents.get("required_document_ids", [])
                if isinstance(documents.get("required_document_ids"), list)
                else []
            ),
        },
        "candidate": {
            "action": candidate.get("action") if isinstance(candidate, dict) else None,
            "evidence_count": len(
                candidate.get("evidence_ids", [])
                if isinstance(candidate, dict)
                and isinstance(candidate.get("evidence_ids"), list)
                else []
            ),
            "version_expectation_count": len(
                candidate.get("expected_versions", [])
                if isinstance(candidate, dict)
                and isinstance(candidate.get("expected_versions"), list)
                else []
            ),
        },
        "tool_statuses": [
            {
                "tool_result": str(name),
                "status": str(value.get("status", "")),
                "provenance_origins": sorted(
                    {
                        str(item.get("origin", ""))
                        for item in value.get("provenance", [])
                        if isinstance(item, dict)
                    }
                ),
                "entity_version_count": len(value.get("entity_versions", {})),
            }
            for name, value in sorted(results.items())
            if isinstance(value, dict) and _is_grounded_tool_result(str(name))
        ],
    }


def _grounded_missing_fields(state: WorkflowState) -> set[str]:
    intake = IntakeContext.model_validate(state["intake_context"])
    results = state.get("tool_results", {})
    fields = set(intake.unresolved_questions)
    for key in ("exception_eligibility", "required_documents"):
        data = _tool_data(results, key)
        values = data.get("missing_document_ids", [])
        if isinstance(values, list):
            fields.update(str(value) for value in values)
    return fields


def _tool_data(results: Any, key: str) -> dict[str, Any]:
    if not isinstance(results, dict):
        return {}
    response = results.get(key)
    if not isinstance(response, dict):
        return {}
    data = response.get("data")
    return dict(data) if isinstance(data, dict) else {}


def _is_grounded_tool_result(name: str) -> bool:
    return (
        name in _GROUNDED_TOOL_RESULTS
        or name.startswith("timetable.")
        or name.startswith("availability.")
    )


__all__ = [
    "GroundedBedrockDecisionProvider",
    "decision_provider_from_settings",
]
