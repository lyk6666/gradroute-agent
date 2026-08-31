"""Stage 4 goal, verification, and evaluator-only execution contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from graduation_exception_agent.models.common import (
    DomainModel,
    Identifier,
    NonEmptyText,
)
from graduation_exception_agent.models.workflow import (
    ApprovalBasis,
    ApprovalStatus,
    ExpectedOutcome,
    ObservationCode,
    StateTargetType,
    TransactionAction,
)


def _unique(values: list[str], field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


def _timezone_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value


class HumanRoute(StrEnum):
    """Approval and administrative escalation are intentionally distinct."""

    NONE = "NONE"
    APPROVAL = "APPROVAL"
    ADMIN_REVIEW = "ADMIN_REVIEW"


class ClarificationImpact(StrEnum):
    """Effect of a clarification on an already-built candidate plan."""

    NONE = "NONE"
    SMALL_CHANGE = "SMALL_CHANGE"
    MATERIAL_CHANGE = "MATERIAL_CHANGE"


class ClarificationResume(StrEnum):
    """Control-plane destination after clarification is incorporated."""

    NONE = "NONE"
    PRE_ACTION_VERIFIER = "PRE_ACTION_VERIFIER"
    PLANNER = "PLANNER"


class VerifierPhase(StrEnum):
    PRE_ACTION = "PRE_ACTION"
    POST_ACTION = "POST_ACTION"


class VerifierDecisionCode(StrEnum):
    VALID = "VALID"
    REPLAN = "REPLAN"
    CLARIFY = "CLARIFY"
    ESCALATE = "ESCALATE"
    DONE = "DONE"
    CONTINUE = "CONTINUE"
    FAILURE = "FAILURE"
    CONTINUE_FAILURE = "CONTINUE_FAILURE"


_PRE_ACTION_DECISIONS = {
    VerifierDecisionCode.VALID,
    VerifierDecisionCode.REPLAN,
    VerifierDecisionCode.CLARIFY,
    VerifierDecisionCode.ESCALATE,
}
_POST_ACTION_DECISIONS = {
    VerifierDecisionCode.DONE,
    VerifierDecisionCode.CONTINUE,
    VerifierDecisionCode.FAILURE,
    VerifierDecisionCode.CONTINUE_FAILURE,
}
_POST_ACTION_EXPECTATIONS = {
    *_POST_ACTION_DECISIONS,
    VerifierDecisionCode.CONTINUE_FAILURE,
}


class VerifierDecision(DomainModel):
    """One typed verifier result; the phase determines valid decision codes."""

    decision_id: Identifier
    phase: VerifierPhase
    decision: VerifierDecisionCode
    reason: NonEmptyText
    candidate_path_id: Identifier | None = None
    violation_codes: list[Identifier] = Field(default_factory=list)
    checked_predicate_ids: list[Identifier] = Field(default_factory=list)
    entity_versions: dict[Identifier, int] = Field(default_factory=dict)
    decided_at: datetime

    @field_validator("decided_at")
    @classmethod
    def timezone_aware_decided_at(cls, value: datetime) -> datetime:
        return _timezone_aware(value, "decided_at")

    @field_validator("violation_codes", "checked_predicate_ids")
    @classmethod
    def unique_decision_links(cls, value: list[str], info: object) -> list[str]:
        return _unique(value, getattr(info, "field_name", "links"))

    @field_validator("entity_versions")
    @classmethod
    def positive_entity_versions(cls, value: dict[str, int]) -> dict[str, int]:
        if any(version < 1 for version in value.values()):
            raise ValueError("entity_versions must be positive")
        return value

    @model_validator(mode="after")
    def validate_phase_decision(self) -> VerifierDecision:
        allowed = (
            _PRE_ACTION_DECISIONS
            if self.phase is VerifierPhase.PRE_ACTION
            else _POST_ACTION_DECISIONS
        )
        if self.decision not in allowed:
            raise ValueError(
                f"{self.decision.value} is not valid during {self.phase.value}"
            )
        if self.decision in {
            VerifierDecisionCode.REPLAN,
            VerifierDecisionCode.CLARIFY,
            VerifierDecisionCode.ESCALATE,
            VerifierDecisionCode.FAILURE,
            VerifierDecisionCode.CONTINUE_FAILURE,
        } and not self.violation_codes:
            raise ValueError(
                f"{self.decision.value} requires at least one violation_code"
            )
        return self


class GoalKind(StrEnum):
    """Supported deterministic terminal effects for the prototype."""

    COURSE_REGISTERED = "COURSE_REGISTERED"
    WAIVER_SUBMITTED = "WAIVER_SUBMITTED"
    EXCEPTION_SUBMITTED = "EXCEPTION_SUBMITTED"
    APPROVAL_OBSERVED = "APPROVAL_OBSERVED"
    INFORMATION_REQUESTED = "INFORMATION_REQUESTED"
    ADMIN_HANDOFF_CREATED = "ADMIN_HANDOFF_CREATED"
    CASE_STATE_REACHED = "CASE_STATE_REACHED"


class GoalOperator(StrEnum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    CONTAINS = "CONTAINS"
    EXISTS = "EXISTS"
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"


class GoalPredicate(DomainModel):
    """A deterministic query/value assertion evaluated against runtime state."""

    predicate_id: Identifier
    goal_kind: GoalKind
    target_type: StateTargetType | None = None
    target_ids: list[Identifier] = Field(default_factory=list)
    field_path: NonEmptyText
    operator: GoalOperator
    expected_value: JsonValue = None
    required: bool = True
    description: NonEmptyText

    @field_validator("target_ids")
    @classmethod
    def unique_targets(cls, value: list[str]) -> list[str]:
        return _unique(value, "target_ids")

    @model_validator(mode="after")
    def validate_query(self) -> GoalPredicate:
        if (self.target_type is None) != (not self.target_ids):
            raise ValueError(
                "target_type and target_ids must either both be supplied or both omitted"
            )
        if self.operator is not GoalOperator.EXISTS and self.expected_value is None:
            raise ValueError("non-EXISTS predicates require expected_value")
        return self


class PredicateEvaluation(DomainModel):
    predicate_id: Identifier
    required: bool
    satisfied: bool
    observed_value: JsonValue = None
    reason: NonEmptyText
    evidence_ids: list[Identifier] = Field(default_factory=list)

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence(cls, value: list[str]) -> list[str]:
        return _unique(value, "evidence_ids")


class GoalEvaluation(DomainModel):
    """Aggregate completion result; every required predicate must hold."""

    evaluation_id: Identifier
    goal_kind: GoalKind
    complete: bool
    predicate_results: list[PredicateEvaluation] = Field(min_length=1)
    evaluated_at: datetime

    @field_validator("evaluated_at")
    @classmethod
    def timezone_aware_evaluated_at(cls, value: datetime) -> datetime:
        return _timezone_aware(value, "evaluated_at")

    @model_validator(mode="after")
    def validate_completion(self) -> GoalEvaluation:
        predicate_ids = [result.predicate_id for result in self.predicate_results]
        _unique(predicate_ids, "predicate_ids")
        required = [result for result in self.predicate_results if result.required]
        if not required:
            raise ValueError("at least one predicate result must be required")
        expected_complete = all(result.satisfied for result in required)
        if self.complete != expected_complete:
            raise ValueError(
                "complete must equal satisfaction of every required predicate"
            )
        return self


class ExecutionEdge(DomainModel):
    source: Identifier
    destination: Identifier

    @model_validator(mode="after")
    def reject_self_loop(self) -> ExecutionEdge:
        if self.source == self.destination:
            raise ValueError("execution edges cannot be self-loops")
        return self

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.destination)


class LoopBudgets(DomainModel):
    max_replans: int = Field(default=4, ge=0)
    max_tool_retries: int = Field(default=2, ge=0)
    max_total_steps: int = Field(default=20, ge=1)


class LoopExpectations(DomainModel):
    replans: int = Field(default=0, ge=0)
    tool_retries: int = Field(default=0, ge=0)
    total_steps: int = Field(default=0, ge=0)


class ExecutionContract(DomainModel):
    """Hidden Stage 4 oracle for one scenario's safe execution behavior.

    This model belongs only to evaluator repositories. ``evaluator_only`` is a
    literal guard so an accidental false label cannot make the record appear
    agent-safe.
    """

    contract_id: Identifier
    schema_version: NonEmptyText = "1.0"
    evaluator_only: Literal[True] = True
    scenario_id: Identifier
    case_id: Identifier
    required_edges: list[ExecutionEdge] = Field(default_factory=list)
    forbidden_edges: list[ExecutionEdge] = Field(default_factory=list)
    pre_action_decisions: list[VerifierDecisionCode] = Field(min_length=1)
    post_action_decisions: list[VerifierDecisionCode] = Field(default_factory=list)
    clarification_impact: ClarificationImpact = ClarificationImpact.NONE
    clarification_resume: ClarificationResume = ClarificationResume.NONE
    human_route: HumanRoute = HumanRoute.NONE
    approval_required: bool = False
    expected_approval_status: ApprovalStatus | None = None
    approval_basis: ApprovalBasis | None = None
    approval_basis_rule_ids: list[Identifier] = Field(default_factory=list)
    admin_review_expected: bool = False
    checkpoint_required: bool = False
    expected_actions: list[TransactionAction] = Field(default_factory=list)
    required_observations: list[ObservationCode] = Field(default_factory=list)
    goal_kind: GoalKind
    goal_predicates: list[GoalPredicate] = Field(min_length=1)
    postconditions: list[GoalPredicate] = Field(default_factory=list)
    expected_outcome: ExpectedOutcome
    memory_update_allowed: bool = False
    loop_budgets: LoopBudgets = Field(default_factory=LoopBudgets)
    loop_expectations: LoopExpectations = Field(default_factory=LoopExpectations)

    @property
    def pre_action_decision(self) -> VerifierDecisionCode:
        """First PRE_ACTION decision, retained as a read-only convenience."""

        return self.pre_action_decisions[0]

    @property
    def post_action_decision(self) -> VerifierDecisionCode | None:
        """Terminal POST_ACTION decision, retained as a read-only convenience."""

        return self.post_action_decisions[-1] if self.post_action_decisions else None

    @model_validator(mode="after")
    def validate_oracle(self) -> ExecutionContract:
        if any(
            decision not in _PRE_ACTION_DECISIONS
            for decision in self.pre_action_decisions
        ):
            raise ValueError("pre_action_decisions must contain PRE_ACTION decisions")
        if any(
            decision not in _POST_ACTION_EXPECTATIONS
            for decision in self.post_action_decisions
        ):
            raise ValueError("post_action_decisions must contain POST_ACTION decisions")

        required_edges = [edge.key for edge in self.required_edges]
        forbidden_edges = [edge.key for edge in self.forbidden_edges]
        if len(required_edges) != len(set(required_edges)):
            raise ValueError("required_edges must not contain duplicates")
        if len(forbidden_edges) != len(set(forbidden_edges)):
            raise ValueError("forbidden_edges must not contain duplicates")
        if set(required_edges) & set(forbidden_edges):
            raise ValueError("required_edges and forbidden_edges must be disjoint")

        clarification_expected = VerifierDecisionCode.CLARIFY in self.pre_action_decisions
        if clarification_expected:
            if self.clarification_impact is ClarificationImpact.NONE:
                raise ValueError("CLARIFY requires a clarification impact")
            expected_resume = (
                ClarificationResume.PRE_ACTION_VERIFIER
                if self.clarification_impact is ClarificationImpact.SMALL_CHANGE
                else ClarificationResume.PLANNER
            )
            if self.clarification_resume is not expected_resume:
                raise ValueError(
                    f"{self.clarification_impact.value} must resume at "
                    f"{expected_resume.value}"
                )
        elif (
            self.clarification_impact is not ClarificationImpact.NONE
            or self.clarification_resume is not ClarificationResume.NONE
        ):
            raise ValueError(
                "clarification metadata is allowed only for a CLARIFY decision"
            )

        if self.approval_required:
            if self.human_route is not HumanRoute.APPROVAL:
                raise ValueError("approval_required must use the APPROVAL route")
            if self.expected_approval_status is None:
                raise ValueError(
                    "approval_required requires expected_approval_status"
                )
            if self.approval_basis is None or not self.approval_basis_rule_ids:
                raise ValueError(
                    "approval_required requires approval_basis and "
                    "approval_basis_rule_ids"
                )
        elif (
            self.expected_approval_status is not None
            or self.approval_basis is not None
            or self.approval_basis_rule_ids
        ):
            raise ValueError("approval metadata is invalid when approval is not required")
        _unique(self.approval_basis_rule_ids, "approval_basis_rule_ids")
        if self.human_route is HumanRoute.ADMIN_REVIEW:
            if not self.admin_review_expected:
                raise ValueError("ADMIN_REVIEW route must expect administrative review")
            if self.approval_required:
                raise ValueError("administrative review is not approval")
        if self.admin_review_expected and self.human_route is HumanRoute.NONE:
            raise ValueError("administrative review requires a human route")
        if self.checkpoint_required and (
            self.expected_approval_status is not ApprovalStatus.PENDING
        ):
            raise ValueError("checkpoint_required is reserved for pending approval")
        if self.expected_approval_status is ApprovalStatus.PENDING:
            if not self.checkpoint_required:
                raise ValueError("pending approval requires a checkpoint")

        predicate_ids = [item.predicate_id for item in self.goal_predicates]
        _unique(predicate_ids, "goal predicate_ids")
        postcondition_ids = [item.predicate_id for item in self.postconditions]
        _unique(postcondition_ids, "postcondition predicate_ids")
        if any(item.goal_kind is not self.goal_kind for item in self.goal_predicates):
            raise ValueError("every goal predicate must match goal_kind")
        if any(item.goal_kind is not self.goal_kind for item in self.postconditions):
            raise ValueError("every postcondition must match goal_kind")

        if VerifierDecisionCode.DONE in self.post_action_decisions:
            if self.expected_outcome is not ExpectedOutcome.RESOLVED:
                raise ValueError("DONE requires the RESOLVED expected outcome")
            if not self.postconditions:
                raise ValueError("DONE requires action-specific postconditions")
        if self.memory_update_allowed and (
            self.post_action_decision is not VerifierDecisionCode.DONE
        ):
            raise ValueError("memory update is allowed only after verified DONE")

        if self.loop_expectations.replans > self.loop_budgets.max_replans:
            raise ValueError("expected replans exceed max_replans")
        if self.loop_expectations.tool_retries > self.loop_budgets.max_tool_retries:
            raise ValueError("expected tool retries exceed max_tool_retries")
        if self.loop_expectations.total_steps > self.loop_budgets.max_total_steps:
            raise ValueError("expected total steps exceed max_total_steps")
        return self
