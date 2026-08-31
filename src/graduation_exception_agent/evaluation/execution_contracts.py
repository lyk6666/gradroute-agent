"""Strict evaluator-only loader for frozen Stage 4 execution contracts.

Nothing in this module is part of the agent's observation or tool surface.  The
models intentionally mirror ``data/tests/execution_contracts.json`` so an
evaluator can reject drift before comparing a Stage 5 graph trace with its
hidden oracle.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path
import re
from typing import Annotated, Literal

from pydantic import Field, JsonValue, StringConstraints, field_validator, model_validator

from graduation_exception_agent.models.common import (
    CourseCode,
    DomainModel,
    Identifier,
)
from graduation_exception_agent.models.runtime import VerifierDecisionCode
from graduation_exception_agent.models.workflow import (
    ApprovalBasis,
    ApprovalStatus,
    ExpectedOutcome,
    TransactionAction,
)


Sha256Digest = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{64}$"),
]
TransitionText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=7,
        max_length=160,
        pattern=r"^[A-Z][A-Z_]*:[A-Z][A-Z_]*->[A-Z][A-Z_]*$",
    ),
]

_TRANSITION_PATTERN = re.compile(
    r"^(?P<source>[A-Z][A-Z_]*):(?P<outcome>[A-Z][A-Z_]*)"
    r"->(?P<destination>[A-Z][A-Z_]*)$"
)
_SOURCE_ARTIFACT_PATHS = {
    "approvals.json": Path("simulated") / "approvals.json",
    "scenarios.json": Path("tests") / "scenarios.json",
    "transaction_results.json": Path("simulated") / "transaction_results.json",
}


class GoalKind(StrEnum):
    """Goal kinds represented by the checked-in evaluator package."""

    COURSE_REGISTERED = "COURSE_REGISTERED"
    EXCEPTION_SUBMITTED = "EXCEPTION_SUBMITTED"
    WAIVER_SUBMITTED = "WAIVER_SUBMITTED"


class CompletionPredicateType(StrEnum):
    REGISTRATION_CONTAINS_COURSE = "REGISTRATION_CONTAINS_COURSE"
    COMMITTED_ACTION_RECEIPT = "COMMITTED_ACTION_RECEIPT"


class ClarificationImpact(StrEnum):
    MATERIAL = "MATERIAL"
    SMALL = "SMALL"


class ClarificationResumeTarget(StrEnum):
    PLANNER = "PLANNER"
    VERIFIER_PRE_ACTION = "VERIFIER_PRE_ACTION"


class CheckpointResumeTrigger(StrEnum):
    APPROVAL_STATUS_CHANGED = "APPROVAL_STATUS_CHANGED"


class CheckpointResumeTarget(StrEnum):
    HUMAN_APPROVAL = "HUMAN_APPROVAL"


class RegistrationExpected(DomainModel):
    course_code: CourseCode
    offering_state_id: Identifier | None = None


class CommittedActionExpected(DomainModel):
    action: TransactionAction
    action_parameters: dict[Identifier, JsonValue] = Field(default_factory=dict)
    status: Literal["COMMITTED"]

    @model_validator(mode="after")
    def action_must_be_a_terminal_submission(self) -> CommittedActionExpected:
        if self.action not in {
            TransactionAction.SUBMIT_EXCEPTION,
            TransactionAction.SUBMIT_WAIVER,
        }:
            raise ValueError("committed receipt must describe an exception or waiver")
        return self


class RegistrationCompletionPredicate(DomainModel):
    type: Literal[CompletionPredicateType.REGISTRATION_CONTAINS_COURSE]
    subject_id: Identifier
    expected: RegistrationExpected


class CommittedActionCompletionPredicate(DomainModel):
    type: Literal[CompletionPredicateType.COMMITTED_ACTION_RECEIPT]
    subject_id: Identifier
    expected: CommittedActionExpected


CompletionPredicate = Annotated[
    RegistrationCompletionPredicate | CommittedActionCompletionPredicate,
    Field(discriminator="type"),
]


class GoalExpectation(DomainModel):
    kind: GoalKind
    completion_predicate: CompletionPredicate
    expected_satisfied: bool
    approval_request_is_completion: Literal[False]

    @model_validator(mode="after")
    def predicate_matches_goal(self) -> GoalExpectation:
        registration_goal = self.kind is GoalKind.COURSE_REGISTERED
        registration_predicate = isinstance(
            self.completion_predicate, RegistrationCompletionPredicate
        )
        if registration_goal != registration_predicate:
            raise ValueError("completion predicate type must match the goal kind")
        if isinstance(self.completion_predicate, CommittedActionCompletionPredicate):
            expected_action = (
                TransactionAction.SUBMIT_WAIVER
                if self.kind is GoalKind.WAIVER_SUBMITTED
                else TransactionAction.SUBMIT_EXCEPTION
            )
            if self.completion_predicate.expected.action is not expected_action:
                raise ValueError("committed action must match the goal kind")
        return self


class ApprovalBasisExpectation(DomainModel):
    basis: ApprovalBasis
    basis_rule_ids: list[Identifier] = Field(min_length=1)

    @field_validator("basis_rule_ids")
    @classmethod
    def unique_basis_rules(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("basis_rule_ids must not contain duplicates")
        return values


class HumanRouteExpectation(DomainModel):
    approval_required: bool
    approval_id: Identifier | None
    approval_outcome: ApprovalStatus | None
    approval_basis: ApprovalBasisExpectation | None
    admin_review_required: bool

    @model_validator(mode="after")
    def approval_fields_are_all_or_none(self) -> HumanRouteExpectation:
        approval_values_present = (
            self.approval_id is not None,
            self.approval_outcome is not None,
            self.approval_basis is not None,
        )
        if self.approval_required and not all(approval_values_present):
            raise ValueError("approval-required routes need id, outcome, and basis")
        if not self.approval_required and any(approval_values_present):
            raise ValueError("non-approval routes cannot carry approval metadata")
        if (
            self.approval_outcome is ApprovalStatus.REJECTED
            and not self.admin_review_required
        ):
            raise ValueError("a rejected approval must replan to administrative review")
        return self


class ClarificationExpectation(DomainModel):
    required: bool
    impact: ClarificationImpact | None
    resume_target: ClarificationResumeTarget | None

    @model_validator(mode="after")
    def impact_controls_resume(self) -> ClarificationExpectation:
        if not self.required:
            if self.impact is not None or self.resume_target is not None:
                raise ValueError("optional clarification cannot define an impact or resume")
            return self
        if self.impact is None or self.resume_target is None:
            raise ValueError("required clarification needs an impact and resume target")
        expected = (
            ClarificationResumeTarget.PLANNER
            if self.impact is ClarificationImpact.MATERIAL
            else ClarificationResumeTarget.VERIFIER_PRE_ACTION
        )
        if self.resume_target is not expected:
            raise ValueError(f"{self.impact.value} clarification must resume at {expected.value}")
        return self


class VerifierExpectations(DomainModel):
    pre_action: list[VerifierDecisionCode] = Field(min_length=1)
    post_action: list[VerifierDecisionCode] = Field(default_factory=list)

    @field_validator("pre_action")
    @classmethod
    def only_pre_action_codes(
        cls, values: list[VerifierDecisionCode]
    ) -> list[VerifierDecisionCode]:
        allowed = {
            VerifierDecisionCode.VALID,
            VerifierDecisionCode.REPLAN,
            VerifierDecisionCode.CLARIFY,
            VerifierDecisionCode.ESCALATE,
        }
        if any(value not in allowed for value in values):
            raise ValueError("pre_action contains a post-action verifier decision")
        return values

    @field_validator("post_action")
    @classmethod
    def only_post_action_codes(
        cls, values: list[VerifierDecisionCode]
    ) -> list[VerifierDecisionCode]:
        allowed = {
            VerifierDecisionCode.DONE,
            VerifierDecisionCode.CONTINUE,
            VerifierDecisionCode.FAILURE,
            VerifierDecisionCode.CONTINUE_FAILURE,
        }
        if any(value not in allowed for value in values):
            raise ValueError("post_action contains a pre-action verifier decision")
        return values


class CheckpointExpectation(DomainModel):
    pause_required: bool
    persistence_required: bool
    resume_trigger: CheckpointResumeTrigger | None
    resume_target: CheckpointResumeTarget | None

    @model_validator(mode="after")
    def pause_metadata_is_complete(self) -> CheckpointExpectation:
        if self.pause_required:
            if not self.persistence_required:
                raise ValueError("a pause checkpoint must persist graph state")
            if self.resume_trigger is None or self.resume_target is None:
                raise ValueError("a pause checkpoint needs a trigger and resume target")
        elif (
            self.persistence_required
            or self.resume_trigger is not None
            or self.resume_target is not None
        ):
            raise ValueError("checkpoint metadata is invalid when no pause is required")
        return self


class LoopExpectation(DomainModel):
    expected_replans: int = Field(ge=0)
    expected_tool_retries: int = Field(ge=0)
    max_replans: Literal[4]
    max_tool_retries: Literal[2]
    max_total_steps: Literal[20]

    @model_validator(mode="after")
    def expectations_fit_budgets(self) -> LoopExpectation:
        if self.expected_replans > self.max_replans:
            raise ValueError("expected replans exceed max_replans")
        if self.expected_tool_retries > self.max_tool_retries:
            raise ValueError("expected tool retries exceed max_tool_retries")
        return self


class EvaluatorExecutionContract(DomainModel):
    """One hidden oracle record, never an input to an agent-facing node."""

    scenario_id: Identifier
    case_id: Identifier
    evaluator_only: Literal[True]
    expected_outcome: ExpectedOutcome
    goal: GoalExpectation
    human_routes: HumanRouteExpectation
    clarification: ClarificationExpectation
    verifier_expectations: VerifierExpectations
    required_transitions: list[TransitionText] = Field(min_length=1)
    forbidden_transitions: list[TransitionText] = Field(min_length=1)
    checkpoint: CheckpointExpectation
    memory_update_permitted: bool
    loop_expectations: LoopExpectation

    @field_validator("required_transitions", "forbidden_transitions")
    @classmethod
    def transitions_are_unique_and_sorted(
        cls, values: list[str], info: object
    ) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError(f"{getattr(info, 'field_name', 'transitions')} has duplicates")
        if values != sorted(values):
            raise ValueError(f"{getattr(info, 'field_name', 'transitions')} must be sorted")
        return values

    @model_validator(mode="after")
    def validate_routes_and_terminal_expectations(self) -> EvaluatorExecutionContract:
        required = set(self.required_transitions)
        forbidden = set(self.forbidden_transitions)
        if required & forbidden:
            raise ValueError("required and forbidden transitions must be disjoint")

        baseline = {
            "INTAKE:CONTEXT_READY->MEMORY_RETRIEVER",
            "MEMORY_RETRIEVER:READY->PLANNER",
            "RESOLUTION_BUILDER:CANDIDATES_BUILT->VERIFIER_PRE_ACTION",
        }
        if not baseline <= required:
            raise ValueError("required transitions omit the intake/planning baseline")

        approval = self.human_routes.approval_outcome
        if self.human_routes.approval_required:
            self._require_route(
                required, "ACTION_GATE:APPROVAL_REQUIRED->HUMAN_APPROVAL"
            )
            if approval is ApprovalStatus.APPROVED:
                self._require_route(required, "HUMAN_APPROVAL:APPROVED->TRANSACTION")
            elif approval is ApprovalStatus.REJECTED:
                self._require_route(required, "HUMAN_APPROVAL:REJECTED->PLANNER")
            elif approval is ApprovalStatus.PENDING:
                self._require_route(
                    required, "HUMAN_APPROVAL:PENDING->PAUSE_CHECKPOINT"
                )
        else:
            self._require_route(
                forbidden, "ACTION_GATE:APPROVAL_REQUIRED->HUMAN_APPROVAL"
            )

        if self.clarification.required:
            if VerifierDecisionCode.CLARIFY not in self.verifier_expectations.pre_action:
                raise ValueError("required clarification needs a CLARIFY expectation")
            impact = self.clarification.impact
            route = (
                "CLARIFICATION:MATERIAL_CHANGE->PLANNER"
                if impact is ClarificationImpact.MATERIAL
                else "CLARIFICATION:SMALL_CHANGE->VERIFIER_PRE_ACTION"
            )
            self._require_route(required, route)
            self._require_route(
                required, "VERIFIER_PRE_ACTION:CLARIFY->CLARIFICATION"
            )
        elif VerifierDecisionCode.CLARIFY in self.verifier_expectations.pre_action:
            raise ValueError("CLARIFY expectation requires clarification metadata")

        pending = approval is ApprovalStatus.PENDING
        if self.checkpoint.pause_required != pending:
            raise ValueError("only pending approval may require a pause checkpoint")
        if pending:
            self._require_route(
                required, "PAUSE_CHECKPOINT:APPROVAL_OBSERVED->HUMAN_APPROVAL"
            )

        if self.human_routes.admin_review_required:
            self._require_route(
                required, "PLANNER:NO_SAFE_ROUTE->HUMAN_ADMIN_REVIEW"
            )
            self._require_route(
                required, "HUMAN_ADMIN_REVIEW:HANDOFF_PREPARED->FINAL_RESPONSE"
            )

        if self.memory_update_permitted:
            if self.expected_outcome is not ExpectedOutcome.RESOLVED:
                raise ValueError("memory update is permitted only for RESOLVED outcomes")
            if self.verifier_expectations.post_action[-1:] != [
                VerifierDecisionCode.DONE
            ]:
                raise ValueError("memory update requires terminal DONE verification")
            self._require_route(
                required, "VERIFIER_POST_ACTION:DONE->MEMORY_UPDATER"
            )
        elif "VERIFIER_POST_ACTION:DONE->MEMORY_UPDATER" in required:
            raise ValueError("memory update route conflicts with its permission flag")

        expected_satisfied = self.goal.expected_satisfied
        if self.expected_outcome is ExpectedOutcome.RESOLVED:
            if not expected_satisfied or not self.memory_update_permitted:
                raise ValueError("RESOLVED requires a satisfied goal and memory update")
        elif expected_satisfied or self.memory_update_permitted:
            raise ValueError("non-resolved outcomes cannot claim completion or memory update")

        if self.expected_outcome is ExpectedOutcome.PENDING_APPROVAL and not pending:
            raise ValueError("PENDING_APPROVAL requires a pending approval route")
        if pending and self.expected_outcome is not ExpectedOutcome.PENDING_APPROVAL:
            raise ValueError("pending approval must use PENDING_APPROVAL outcome")
        if (
            self.expected_outcome is ExpectedOutcome.CLARIFICATION_REQUIRED
        ) != self.clarification.required:
            raise ValueError("CLARIFICATION_REQUIRED must match clarification metadata")
        if (
            self.expected_outcome is ExpectedOutcome.ESCALATED
        ) != self.human_routes.admin_review_required:
            raise ValueError("ESCALATED must match administrative review metadata")

        if self.loop_expectations.expected_tool_retries > 0:
            self._require_route(
                required, "VERIFIER_POST_ACTION:CONTINUE_FAILURE->PLANNER"
            )
        if self.loop_expectations.expected_replans > 0 and not any(
            transition.endswith("->PLANNER") for transition in required
        ):
            raise ValueError("expected replans require a transition back to PLANNER")
        return self

    @staticmethod
    def _require_route(routes: set[str], route: str) -> None:
        if route not in routes:
            raise ValueError(f"missing required route contract: {route}")

    def parsed_required_transitions(self) -> list[tuple[str, str, str]]:
        """Return ``(source, outcome, destination)`` tuples for trace matching."""

        return [_parse_transition(value) for value in self.required_transitions]


class SourceArtifactHashes(DomainModel):
    approvals_json: Sha256Digest = Field(alias="approvals.json")
    scenarios_json: Sha256Digest = Field(alias="scenarios.json")
    transaction_results_json: Sha256Digest = Field(alias="transaction_results.json")

    def by_filename(self) -> dict[str, str]:
        return self.model_dump(mode="python", by_alias=True)


class ExecutionContractPackage(DomainModel):
    """Validated evaluator-only package for all frozen Stage 3 scenarios."""

    schema_version: Literal["1.0"]
    generator_version: Literal["stage4.0.0"]
    evaluator_only: Literal[True]
    contract_count: int = Field(ge=1)
    contracts: list[EvaluatorExecutionContract] = Field(min_length=1)
    source_artifacts_sha256: SourceArtifactHashes

    @model_validator(mode="after")
    def validate_package_index(self) -> ExecutionContractPackage:
        if self.contract_count != len(self.contracts):
            raise ValueError("contract_count must equal the number of contracts")
        scenario_ids = [contract.scenario_id for contract in self.contracts]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("scenario_id must be unique within the package")
        if scenario_ids != sorted(scenario_ids):
            raise ValueError("contracts must be sorted by scenario_id")
        if any(not contract.evaluator_only for contract in self.contracts):
            raise ValueError("every contract must be evaluator-only")
        return self

    @property
    def by_scenario_id(self) -> dict[str, EvaluatorExecutionContract]:
        return {contract.scenario_id: contract for contract in self.contracts}

    def contract_for(self, scenario_id: str) -> EvaluatorExecutionContract:
        try:
            return self.by_scenario_id[scenario_id]
        except KeyError as exc:
            raise KeyError(f"no execution contract for scenario {scenario_id!r}") from exc

    def verify_source_artifacts(self, data_root: str | Path) -> None:
        """Verify the three frozen source files against their recorded SHA-256."""

        root = Path(data_root)
        expected_hashes = self.source_artifacts_sha256.by_filename()
        for filename, relative_path in _SOURCE_ARTIFACT_PATHS.items():
            source_path = root / relative_path
            if not source_path.is_file():
                raise ValueError(f"source artifact is missing: {source_path}")
            actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
            expected = expected_hashes[filename]
            if actual != expected:
                raise ValueError(
                    f"source artifact hash mismatch for {filename}: "
                    f"expected {expected}, got {actual}"
                )


def load_execution_contract_package(
    path: str | Path,
    *,
    verify_source_artifacts: bool = True,
    data_root: str | Path | None = None,
) -> ExecutionContractPackage:
    """Load the hidden oracle and, by default, verify its frozen source files.

    ``data_root`` defaults to the parent of the package's ``tests`` directory,
    matching the checked-in ``data/tests/execution_contracts.json`` layout.
    Tests loading a standalone mutated fixture may disable source verification.
    """

    contract_path = Path(path)
    package = ExecutionContractPackage.model_validate_json(
        contract_path.read_text(encoding="utf-8")
    )
    if verify_source_artifacts:
        resolved_data_root = (
            Path(data_root) if data_root is not None else contract_path.parent.parent
        )
        package.verify_source_artifacts(resolved_data_root)
    return package


def load_execution_contracts(
    path: str | Path,
    *,
    verify_source_artifacts: bool = True,
    data_root: str | Path | None = None,
) -> ExecutionContractPackage:
    """Concise alias for :func:`load_execution_contract_package`."""

    return load_execution_contract_package(
        path,
        verify_source_artifacts=verify_source_artifacts,
        data_root=data_root,
    )


def _parse_transition(value: str) -> tuple[str, str, str]:
    match = _TRANSITION_PATTERN.fullmatch(value)
    if match is None:  # The Pydantic field constraint should catch this first.
        raise ValueError(f"invalid transition: {value!r}")
    return (
        match.group("source"),
        match.group("outcome"),
        match.group("destination"),
    )


__all__ = [
    "CheckpointExpectation",
    "ClarificationExpectation",
    "EvaluatorExecutionContract",
    "ExecutionContractPackage",
    "GoalExpectation",
    "HumanRouteExpectation",
    "LoopExpectation",
    "SourceArtifactHashes",
    "VerifierExpectations",
    "load_execution_contract_package",
    "load_execution_contracts",
]
