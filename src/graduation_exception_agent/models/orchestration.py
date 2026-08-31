"""Typed, checkpoint-safe contracts for the Stage 5 control plane.

The Pydantic models validate values at node boundaries.  ``WorkflowState``
intentionally stores their ``model_dump(mode="json")`` representations so a
LangGraph checkpointer never depends on Python object pickling.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, TypedDict

from pydantic import Field, JsonValue, computed_field, field_validator, model_validator

from graduation_exception_agent.models.common import (
    AdmissionCohort,
    DomainModel,
    Identifier,
    NonEmptyText,
    ProgrammeCode,
    SyntheticStudentId,
)
from graduation_exception_agent.models.runtime import (
    ClarificationImpact,
    ClarificationResume,
    GoalEvaluation,
    GoalPredicate,
    VerifierDecision,
    VerifierPhase,
)
from graduation_exception_agent.models.tooling import VersionExpectation
from graduation_exception_agent.models.workflow import (
    ApprovalStatus,
    CaseState,
    ExceptionCaseType,
    TransactionAction,
)


# The architecture uses this more explicit name.  Keep it an alias so Stage 4
# and Stage 5 share one optimistic-lock contract rather than diverging types.
StateVersionExpectation = VersionExpectation

MAX_REPLANS = 4
MAX_TOOL_RETRIES = 2
MAX_TOTAL_STEPS = 20


JsonObject = dict[str, JsonValue]


def _unique(values: list[str], field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


def _timezone_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value


class WorkflowNode(StrEnum):
    """Concrete node names used by the compiled Stage 5 graph."""

    INTAKE_CONTEXT = "intake_context"
    MEMORY_RETRIEVER = "memory_retriever"
    PLANNER = "planner"
    SUPERVISOR_ROUTER = "supervisor_router"
    DEGREE_AUDIT_AGENT = "degree_audit_agent"
    POLICY_AGENT = "policy_agent"
    COURSE_AGENT = "course_agent"
    RESOLUTION_BUILDER = "resolution_builder"
    VERIFIER = "verifier"
    CLARIFICATION = "clarification"
    ACTION_GATE = "action_gate"
    HUMAN_APPROVAL = "human_approval"
    HUMAN_ADMIN_REVIEW = "human_admin_review"
    TRANSACTION = "transaction"
    OBSERVATION = "observation"
    MEMORY_UPDATER = "memory_updater"
    FINAL_RESPONSE = "final_response"
    PAUSE_CHECKPOINT = "pause_checkpoint"


class TransitionEndpoint(StrEnum):
    """Canonical endpoint vocabulary used by evaluator trace comparisons."""

    INTAKE = "INTAKE"
    MEMORY_RETRIEVER = "MEMORY_RETRIEVER"
    PLANNER = "PLANNER"
    SUPERVISOR_ROUTER = "SUPERVISOR_ROUTER"
    DEGREE_AUDIT_AGENT = "DEGREE_AUDIT_AGENT"
    POLICY_AGENT = "POLICY_AGENT"
    COURSE_AGENT = "COURSE_AGENT"
    RESOLUTION_BUILDER = "RESOLUTION_BUILDER"
    VERIFIER_PRE_ACTION = "VERIFIER_PRE_ACTION"
    VERIFIER_POST_ACTION = "VERIFIER_POST_ACTION"
    CLARIFICATION = "CLARIFICATION"
    ACTION_GATE = "ACTION_GATE"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    HUMAN_ADMIN_REVIEW = "HUMAN_ADMIN_REVIEW"
    TRANSACTION = "TRANSACTION"
    OBSERVATION = "OBSERVATION"
    MEMORY_UPDATER = "MEMORY_UPDATER"
    FINAL_RESPONSE = "FINAL_RESPONSE"
    PAUSE_CHECKPOINT = "PAUSE_CHECKPOINT"
    PAUSE = "PAUSE"
    END = "END"


class SpecialistKind(StrEnum):
    DEGREE_AUDIT = "DEGREE_AUDIT"
    POLICY = "POLICY"
    COURSE = "COURSE"


class FinalOutcomeStatus(StrEnum):
    DONE = "DONE"
    ADMIN_HANDOFF = "ADMIN_HANDOFF"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    WAITING_FOR_CLARIFICATION = "WAITING_FOR_CLARIFICATION"
    SAFE_FAILURE = "SAFE_FAILURE"


class IntakeContext(DomainModel):
    """Minimal observable intake; evaluator and simulator controls are absent."""

    case_id: Identifier
    session_id: Identifier
    thread_id: Identifier
    anonymous_student_id: SyntheticStudentId
    programme_code: ProgrammeCode
    admission_cohort: AdmissionCohort
    request_text: NonEmptyText
    problem_type: ExceptionCaseType
    submission_ready: bool | None = None
    unresolved_questions: list[NonEmptyText] = Field(default_factory=list)
    case_state: CaseState
    goal_predicates: list[GoalPredicate] = Field(min_length=1)
    registration_id: Identifier | None = None
    audit_id: Identifier | None = None
    received_at: datetime

    @field_validator("received_at")
    @classmethod
    def timezone_aware_received_at(cls, value: datetime) -> datetime:
        return _timezone_aware(value, "received_at")

    @field_validator("unresolved_questions")
    @classmethod
    def unique_unresolved_questions(cls, value: list[str]) -> list[str]:
        return _unique(value, "unresolved_questions")

    @model_validator(mode="after")
    def unique_goal_predicates(self) -> IntakeContext:
        _unique(
            [predicate.predicate_id for predicate in self.goal_predicates],
            "goal predicate_ids",
        )
        return self


class PlanStep(DomainModel):
    step_id: Identifier
    ordinal: int = Field(ge=1)
    purpose: NonEmptyText
    specialist: SpecialistKind | None = None
    tool_name: Identifier | None = None
    depends_on: list[Identifier] = Field(default_factory=list)

    @field_validator("depends_on")
    @classmethod
    def unique_dependencies(cls, value: list[str]) -> list[str]:
        return _unique(value, "depends_on")

    @model_validator(mode="after")
    def reject_self_dependency(self) -> PlanStep:
        if self.step_id in self.depends_on:
            raise ValueError("a plan step cannot depend on itself")
        return self


class ResolutionPlan(DomainModel):
    plan_id: Identifier
    version: int = Field(default=1, ge=1)
    goal_predicates: list[GoalPredicate] = Field(min_length=1)
    steps: list[PlanStep] = Field(min_length=1, max_length=20)
    rationale: NonEmptyText
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def timezone_aware_created_at(cls, value: datetime) -> datetime:
        return _timezone_aware(value, "created_at")

    @model_validator(mode="after")
    def validate_plan_graph(self) -> ResolutionPlan:
        predicate_ids = [item.predicate_id for item in self.goal_predicates]
        _unique(predicate_ids, "goal predicate_ids")
        step_ids = [item.step_id for item in self.steps]
        _unique(step_ids, "step_ids")
        if [item.ordinal for item in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("plan step ordinals must be contiguous and ordered from 1")
        known: set[str] = set()
        for step in self.steps:
            unknown = set(step.depends_on) - known
            if unknown:
                raise ValueError(
                    "plan steps may depend only on earlier steps: "
                    + ", ".join(sorted(unknown))
                )
            known.add(step.step_id)
        return self


class SpecialistSelection(DomainModel):
    selection_id: Identifier
    plan_id: Identifier
    required_specialists: list[SpecialistKind] = Field(min_length=1, max_length=3)
    rationale: NonEmptyText

    @field_validator("required_specialists")
    @classmethod
    def unique_specialists(
        cls, value: list[SpecialistKind]
    ) -> list[SpecialistKind]:
        if len(value) != len(set(value)):
            raise ValueError("required_specialists must not contain duplicates")
        return value


class SpecialistEvidence(DomainModel):
    evidence_id: Identifier
    specialist: SpecialistKind
    summary: NonEmptyText
    source_ids: list[Identifier] = Field(default_factory=list)
    rule_ids: list[Identifier] = Field(default_factory=list)
    tool_request_ids: list[Identifier] = Field(default_factory=list)
    entity_versions: dict[Identifier, int] = Field(default_factory=dict)
    completeness_known: bool

    @field_validator("source_ids", "rule_ids", "tool_request_ids")
    @classmethod
    def unique_evidence_links(cls, value: list[str], info: object) -> list[str]:
        return _unique(value, getattr(info, "field_name", "links"))

    @field_validator("entity_versions")
    @classmethod
    def positive_entity_versions(cls, value: dict[str, int]) -> dict[str, int]:
        if any(version < 1 for version in value.values()):
            raise ValueError("entity_versions must be positive")
        return value

    @model_validator(mode="after")
    def require_grounding_link(self) -> SpecialistEvidence:
        if not (self.source_ids or self.rule_ids or self.tool_request_ids):
            raise ValueError("specialist evidence requires at least one grounding link")
        return self


class ActionCandidate(DomainModel):
    candidate_id: Identifier
    plan_id: Identifier
    action: TransactionAction
    parameters: dict[Identifier, JsonValue] = Field(default_factory=dict)
    expected_versions: list[StateVersionExpectation] = Field(default_factory=list)
    goal_predicates: list[GoalPredicate] = Field(min_length=1)
    evidence_ids: list[Identifier] = Field(min_length=1)
    requires_approval: bool
    approval_id: Identifier | None = None
    idempotency_key: Identifier
    rationale: NonEmptyText

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence_ids(cls, value: list[str]) -> list[str]:
        return _unique(value, "evidence_ids")

    @model_validator(mode="after")
    def validate_candidate(self) -> ActionCandidate:
        targets = [
            (expectation.target_type, expectation.target_id)
            for expectation in self.expected_versions
        ]
        if len(targets) != len(set(targets)):
            raise ValueError("expected_versions must not repeat a state target")
        _unique(
            [predicate.predicate_id for predicate in self.goal_predicates],
            "goal predicate_ids",
        )
        if not self.requires_approval and self.approval_id is not None:
            raise ValueError("approval_id is invalid when approval is not required")
        return self


class TraceEvent(DomainModel):
    """One canonical control transition, safe for exact trace assertions."""

    sequence: int = Field(ge=1)
    source: TransitionEndpoint
    outcome: Identifier
    destination: TransitionEndpoint
    verifier_phase: VerifierPhase | None = None
    note: NonEmptyText | None = None

    @field_validator("outcome", mode="before")
    @classmethod
    def canonicalize_outcome(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_verifier_phase(self) -> TraceEvent:
        expected_phase = {
            TransitionEndpoint.VERIFIER_PRE_ACTION: VerifierPhase.PRE_ACTION,
            TransitionEndpoint.VERIFIER_POST_ACTION: VerifierPhase.POST_ACTION,
        }.get(self.source)
        if expected_phase is None and self.verifier_phase is not None:
            raise ValueError("verifier_phase is valid only for verifier transitions")
        if expected_phase is not None and self.verifier_phase is not expected_phase:
            raise ValueError(
                f"{self.source.value} requires verifier_phase={expected_phase.value}"
            )
        return self

    @computed_field
    @property
    def transition_key(self) -> str:
        return f"{self.source.value}:{self.outcome}->{self.destination.value}"


class LoopCaps(DomainModel):
    max_replans: int = Field(default=MAX_REPLANS, ge=0)
    max_tool_retries: int = Field(default=MAX_TOOL_RETRIES, ge=0)
    max_total_steps: int = Field(default=MAX_TOTAL_STEPS, ge=1)


class LoopCounters(DomainModel):
    replans: int = Field(default=0, ge=0)
    tool_retries: int = Field(default=0, ge=0)
    total_steps: int = Field(default=0, ge=0)

    def advanced(
        self, *, replan: bool = False, tool_retry: bool = False
    ) -> LoopCounters:
        """Return counters for the next node without mutating checkpoint state."""

        return self.model_copy(
            update={
                "replans": self.replans + int(replan),
                "tool_retries": self.tool_retries + int(tool_retry),
                "total_steps": self.total_steps + 1,
            }
        )

    def exceeded_cap(self, caps: LoopCaps) -> Literal[
        "MAX_REPLANS", "MAX_TOOL_RETRIES", "MAX_TOTAL_STEPS"
    ] | None:
        if self.replans > caps.max_replans:
            return "MAX_REPLANS"
        if self.tool_retries > caps.max_tool_retries:
            return "MAX_TOOL_RETRIES"
        if self.total_steps > caps.max_total_steps:
            return "MAX_TOTAL_STEPS"
        return None

    def require_within(self, caps: LoopCaps) -> None:
        exceeded = self.exceeded_cap(caps)
        if exceeded is not None:
            raise ValueError(f"workflow loop cap exceeded: {exceeded}")


class ClarificationPause(DomainModel):
    clarification_id: Identifier
    case_id: Identifier
    question: NonEmptyText
    missing_fields: list[Identifier] = Field(min_length=1)
    impact: ClarificationImpact
    resume_target: ClarificationResume
    requested_at: datetime

    @field_validator("missing_fields")
    @classmethod
    def unique_missing_fields(cls, value: list[str]) -> list[str]:
        return _unique(value, "missing_fields")

    @field_validator("requested_at")
    @classmethod
    def timezone_aware_requested_at(cls, value: datetime) -> datetime:
        return _timezone_aware(value, "requested_at")

    @model_validator(mode="after")
    def validate_resume_route(self) -> ClarificationPause:
        expected = {
            ClarificationImpact.SMALL_CHANGE: ClarificationResume.PRE_ACTION_VERIFIER,
            ClarificationImpact.MATERIAL_CHANGE: ClarificationResume.PLANNER,
        }.get(self.impact)
        if expected is None:
            raise ValueError("a clarification pause requires a non-NONE impact")
        if self.resume_target is not expected:
            raise ValueError(
                f"{self.impact.value} must resume at {expected.value}"
            )
        return self


class ClarificationResumePayload(DomainModel):
    clarification_id: Identifier
    answers: dict[Identifier, JsonValue] = Field(min_length=1)
    impact: ClarificationImpact
    responded_at: datetime

    @field_validator("responded_at")
    @classmethod
    def timezone_aware_responded_at(cls, value: datetime) -> datetime:
        return _timezone_aware(value, "responded_at")

    @model_validator(mode="after")
    def require_actionable_impact(self) -> ClarificationResumePayload:
        if self.impact is ClarificationImpact.NONE:
            raise ValueError("a clarification response requires a non-NONE impact")
        return self


class ApprovalPause(DomainModel):
    approval_id: Identifier
    case_id: Identifier
    approval_version: int = Field(ge=1)
    approver_role: NonEmptyText
    requested_action: TransactionAction
    status: Literal[ApprovalStatus.PENDING] = ApprovalStatus.PENDING
    requested_at: datetime

    @field_validator("requested_at")
    @classmethod
    def timezone_aware_requested_at(cls, value: datetime) -> datetime:
        return _timezone_aware(value, "requested_at")


class ApprovalResumePayload(DomainModel):
    approval_id: Identifier
    expected_version: int = Field(ge=1)
    observed_version: int = Field(ge=1)
    status: ApprovalStatus
    decision_reason: NonEmptyText | None = None
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def timezone_aware_observed_at(cls, value: datetime) -> datetime:
        return _timezone_aware(value, "observed_at")

    @model_validator(mode="after")
    def validate_resume(self) -> ApprovalResumePayload:
        if self.observed_version < self.expected_version:
            raise ValueError("observed approval version is older than the checkpoint")
        if self.status is ApprovalStatus.REJECTED and not self.decision_reason:
            raise ValueError("a rejected approval requires decision_reason")
        if self.status is not ApprovalStatus.REJECTED and self.decision_reason:
            raise ValueError("decision_reason is reserved for rejected approval")
        return self


class AdminHandoff(DomainModel):
    handoff_id: Identifier
    case_id: Identifier
    required_role: NonEmptyText
    reason: NonEmptyText
    attempted_plan_ids: list[Identifier] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(min_length=1)
    recommended_next_step: NonEmptyText
    created_at: datetime

    @field_validator("attempted_plan_ids", "evidence_ids")
    @classmethod
    def unique_handoff_links(cls, value: list[str], info: object) -> list[str]:
        return _unique(value, getattr(info, "field_name", "links"))

    @field_validator("created_at")
    @classmethod
    def timezone_aware_created_at(cls, value: datetime) -> datetime:
        return _timezone_aware(value, "created_at")


class FinalOutcome(DomainModel):
    outcome_id: Identifier
    case_id: Identifier
    status: FinalOutcomeStatus
    message: NonEmptyText
    goal_evaluation: GoalEvaluation | None = None
    evidence_ids: list[Identifier] = Field(default_factory=list)
    admin_handoff_id: Identifier | None = None
    memory_write_permitted: bool = False
    completed_at: datetime

    @field_validator("evidence_ids")
    @classmethod
    def unique_final_evidence(cls, value: list[str]) -> list[str]:
        return _unique(value, "evidence_ids")

    @field_validator("completed_at")
    @classmethod
    def timezone_aware_completed_at(cls, value: datetime) -> datetime:
        return _timezone_aware(value, "completed_at")

    @model_validator(mode="after")
    def validate_terminal_state(self) -> FinalOutcome:
        if self.status is FinalOutcomeStatus.DONE:
            if self.goal_evaluation is None or not self.goal_evaluation.complete:
                raise ValueError("DONE requires a complete goal evaluation")
        elif self.memory_write_permitted:
            raise ValueError("memory writes are permitted only after verified DONE")
        if self.status is FinalOutcomeStatus.ADMIN_HANDOFF:
            if self.admin_handoff_id is None:
                raise ValueError("ADMIN_HANDOFF requires admin_handoff_id")
        elif self.admin_handoff_id is not None:
            raise ValueError("admin_handoff_id is valid only for ADMIN_HANDOFF")
        return self


def merge_trace(left: list[JsonObject], right: list[JsonObject]) -> list[JsonObject]:
    """Append trace fragments while making exact checkpoint replay idempotent."""

    # A recovery may legitimately traverse the same transition more than once;
    # sequence is the event identity while transition_key describes its route.
    return _merge_unique(left, right, "sequence", "trace")


def merge_evidence(
    left: list[JsonObject], right: list[JsonObject]
) -> list[JsonObject]:
    return _merge_unique(left, right, "evidence_id", "specialist evidence")


def merge_receipts(
    left: list[JsonObject], right: list[JsonObject]
) -> list[JsonObject]:
    return _merge_unique(left, right, "receipt_id", "action receipts")


def merge_errors(left: list[JsonObject], right: list[JsonObject]) -> list[JsonObject]:
    """Merge errors without duplicating checkpoint replays.

    New producers may provide an ``error_id`` as stable event identity.  The
    current advisory-memory producer predates that field, so legacy errors use
    their canonical JSON content as a replay identity.  Distinct legacy error
    payloads are preserved even when they share an error code.
    """

    merged: list[JsonObject] = []
    explicit: dict[str | int, JsonObject] = {}
    implicit: set[str] = set()

    for item in [*left, *right]:
        if "error_id" in item:
            identity = item["error_id"]
            if not isinstance(identity, (str, int)) or isinstance(identity, bool):
                raise ValueError("error error_id must be a string or integer")
            if isinstance(identity, str) and not identity.strip():
                raise ValueError("error error_id must not be blank")
            existing = explicit.get(identity)
            if existing is None:
                explicit[identity] = item
                merged.append(item)
            elif existing != item:
                raise ValueError(
                    f"conflicting error item for error_id={identity!r}"
                )
            continue

        # JsonObject values are JSON-compatible by contract.  Canonical JSON
        # makes an unchanged legacy fragment stable across checkpoint replay.
        identity = json.dumps(item, sort_keys=True, separators=(",", ":"))
        if identity not in implicit:
            implicit.add(identity)
            merged.append(item)

    return merged


def _merge_unique(
    left: list[JsonObject],
    right: list[JsonObject],
    key: str,
    label: str,
) -> list[JsonObject]:
    merged = [*left]
    seen: dict[str | int, JsonObject] = {}
    for item in left:
        if key not in item:
            raise ValueError(f"{label} item is missing {key}")
        identity = item[key]
        if not isinstance(identity, (str, int)) or isinstance(identity, bool):
            raise ValueError(f"{label} {key} must be a string or integer")
        seen[identity] = item
    for item in right:
        if key not in item:
            raise ValueError(f"{label} item is missing {key}")
        identity = item[key]
        if not isinstance(identity, (str, int)) or isinstance(identity, bool):
            raise ValueError(f"{label} {key} must be a string or integer")
        existing = seen.get(identity)
        if existing is None:
            seen[identity] = item
            merged.append(item)
        elif existing != item:
            raise ValueError(f"conflicting {label} item for {key}={identity!r}")
    return merged


class WorkflowState(TypedDict, total=False):
    """JSON-only state persisted by LangGraph checkpoint savers.

    Node code validates each object with the model above, then writes a JSON
    dump here.  Hidden evaluator controls have deliberately no state channel.
    """

    schema_version: str
    thread_id: str
    session_id: str
    case_id: str
    start_request: JsonObject
    intake_context: JsonObject
    scenario_context: JsonObject
    intake_error: JsonObject
    advisory_memories: list[JsonObject]
    reasoning_audit: list[JsonObject]
    plan: JsonObject
    plan_history: list[JsonObject]
    specialist_selection: JsonObject
    pending_specialists: list[str]
    specialist_evidence: Annotated[list[JsonObject], merge_evidence]
    action_candidate: JsonObject
    resolution_error: JsonObject
    verification_phase: str
    verifier_decision: JsonObject
    verification_history: list[JsonObject]
    clarification_pause: JsonObject
    clarification_response: JsonObject
    approval_pause: JsonObject
    approval_response: JsonObject
    approval_requirement: JsonObject
    action_receipts: Annotated[list[JsonObject], merge_receipts]
    tool_results: dict[str, JsonObject]
    observation: JsonObject
    goal_evaluation: JsonObject
    admin_handoff: JsonObject
    final_outcome: JsonObject
    loop_caps: JsonObject
    loop_counters: JsonObject
    limit_reason: str
    route: str
    run_status: str
    attempted_offering_state_ids: list[str]
    errors: Annotated[list[JsonObject], merge_errors]
    trace: Annotated[list[JsonObject], merge_trace]
    memory_write_completed: bool
    memory_write_result: JsonObject
