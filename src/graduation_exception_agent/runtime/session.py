"""Isolated, mutable Stage 4 runtime state for one observable case.

The session deliberately contains no scenario ground truth, transaction script,
or future event.  Those evaluator-only inputs live in :mod:`runtime.controller`.
Every public read returns a defensive copy so one scenario cannot mutate the
frozen Stage 3 repository or another scenario session.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock
from typing import Any

from pydantic import TypeAdapter

from graduation_exception_agent.models.academic import (
    DegreeAudit,
    ObservableStudent,
    OfferingState,
    Registration,
)
from graduation_exception_agent.models.common import Identifier
from graduation_exception_agent.models.runtime import (
    GoalEvaluation,
    GoalKind,
    GoalOperator,
    GoalPredicate,
    PredicateEvaluation,
)
from graduation_exception_agent.models.tooling import ActionReceipt
from graduation_exception_agent.models.workflow import (
    Approval,
    ApprovalBasis,
    ApprovalStatus,
    CaseState,
    ExceptionCase,
    ScenarioContext,
    StateTargetType,
)


@dataclass(frozen=True, slots=True)
class ApprovalRequirement:
    """Agent-safe approval request metadata with the hidden outcome removed."""

    approval_id: str
    case_id: str
    approver_role: str
    requested_action: str
    basis: ApprovalBasis
    basis_rule_ids: tuple[str, ...]
    required_document_ids: tuple[str, ...]
    version: int

    def to_dict(self) -> dict[str, object]:
        return {
            "approval_id": self.approval_id,
            "case_id": self.case_id,
            "approver_role": self.approver_role,
            "requested_action": self.requested_action,
            "basis": self.basis.value,
            "basis_rule_ids": list(self.basis_rule_ids),
            "required_document_ids": list(self.required_document_ids),
            "version": self.version,
        }


@dataclass(slots=True)
class _MutableSessionState:
    registration: Registration
    case: ExceptionCase
    offering_states: dict[str, OfferingState]
    approvals: dict[str, Approval]
    entity_versions: dict[str, int]


class RuntimeSession:
    """Thread-safe working copy of the facts visible in one case session."""

    def __init__(
        self,
        *,
        session_id: str,
        context: ScenarioContext,
        student: ObservableStudent,
        audit: DegreeAudit,
        registration: Registration,
        case: ExceptionCase,
        offering_states: tuple[OfferingState, ...],
        approval_requirement: ApprovalRequirement | None = None,
        observable_approval: Approval | None = None,
    ) -> None:
        if context.case_id != case.case_id:
            raise ValueError("context and case identifiers must agree")
        if context.student_id != student.student_id:
            raise ValueError("context and student identifiers must agree")
        if context.audit_id != audit.audit_id:
            raise ValueError("context and audit identifiers must agree")
        if context.registration_id != registration.registration_id:
            raise ValueError("context and registration identifiers must agree")
        expected_state_ids = set(context.offering_state_ids)
        actual_state_ids = {state.state_id for state in offering_states}
        if expected_state_ids != actual_state_ids:
            raise ValueError("session offering states must exactly match the context")
        if observable_approval is not None:
            if not observable_approval.observable:
                raise ValueError("an initial approval must already be observable")
            if observable_approval.case_id != case.case_id:
                raise ValueError("approval and case identifiers must agree")

        self._session_id = TypeAdapter(Identifier).validate_python(session_id)
        self._context = context.model_copy(deep=True)
        self._student = student.model_copy(deep=True)
        self._audit = audit.model_copy(deep=True)
        self._registration = registration.model_copy(deep=True)
        self._case = case.model_copy(deep=True)
        self._offering_states = {
            state.state_id: state.model_copy(deep=True) for state in offering_states
        }
        self._approvals: dict[str, Approval] = {}
        if observable_approval is not None:
            self._approvals[observable_approval.approval_id] = (
                observable_approval.model_copy(deep=True)
            )
        self._approval_requirement = deepcopy(approval_requirement)
        self._entity_versions: dict[str, int] = {
            registration.registration_id: 1,
            case.case_id: 1,
            **{state.state_id: state.version for state in offering_states},
        }
        if observable_approval is not None:
            self._entity_versions[observable_approval.approval_id] = (
                observable_approval.version
            )
        self._receipts: dict[str, ActionReceipt] = {}
        self._idempotency: dict[str, tuple[str, str]] = {}
        self._revision = 0
        self._lock = RLock()
        self._stage5_owner: object | None = None
        self._stage5_thread_id: str | None = None

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def case_id(self) -> str:
        return str(self._case.case_id)

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    @property
    def context(self) -> ScenarioContext:
        return self._context.model_copy(deep=True)

    def claim_stage5_control_plane(self, owner: object, thread_id: str) -> None:
        """Atomically lease the mutable session to one facade and one thread."""

        validated_thread = TypeAdapter(Identifier).validate_python(thread_id)
        with self._lock:
            if self._stage5_owner is None:
                self._stage5_owner = owner
                self._stage5_thread_id = validated_thread
                return
            if self._stage5_owner is owner and self._stage5_thread_id == validated_thread:
                return
            raise ValueError(
                "this mutable Stage 4 session is already leased to another "
                "Stage 5 control plane or thread"
            )

    def assert_stage5_control_plane(self, owner: object, thread_id: str) -> None:
        """Verify a Stage 5 facade still owns this session's exclusive lease."""

        with self._lock:
            if self._stage5_owner is not owner or self._stage5_thread_id != thread_id:
                raise ValueError(
                    "this Stage 5 control plane does not own the mutable Stage 4 "
                    "session"
                )

    def get_student(self, student_id: str) -> ObservableStudent:
        if student_id.upper() != self._student.student_id:
            raise KeyError(student_id)
        return self._student.model_copy(deep=True)

    def get_audit(self, audit_id: str) -> DegreeAudit:
        if audit_id != self._audit.audit_id:
            raise KeyError(audit_id)
        return self._audit.model_copy(deep=True)

    def get_registration(self, registration_id: str) -> Registration:
        with self._lock:
            if registration_id != self._registration.registration_id:
                raise KeyError(registration_id)
            return self._registration.model_copy(deep=True)

    def get_case(self, case_id: str) -> ExceptionCase:
        with self._lock:
            if case_id != self._case.case_id:
                raise KeyError(case_id)
            return self._case.model_copy(deep=True)

    def get_offering_state(self, state_id: str) -> OfferingState:
        with self._lock:
            return self._offering_states[state_id].model_copy(deep=True)

    def offering_states(self) -> tuple[OfferingState, ...]:
        with self._lock:
            return tuple(
                state.model_copy(deep=True)
                for state in sorted(
                    self._offering_states.values(), key=lambda item: item.state_id
                )
            )

    def approval_requirement(self, case_id: str) -> ApprovalRequirement | None:
        if case_id != self._case.case_id:
            raise KeyError(case_id)
        return deepcopy(self._approval_requirement)

    def observable_approval(self, case_id: str) -> Approval | None:
        if case_id != self._case.case_id:
            raise KeyError(case_id)
        with self._lock:
            match = next(
                (
                    approval
                    for approval in self._approvals.values()
                    if approval.case_id == case_id and approval.observable
                ),
                None,
            )
            return None if match is None else match.model_copy(deep=True)

    def record_human_approval(
        self,
        *,
        approval_id: str,
        status: ApprovalStatus,
        decision_reason: str | None,
        observed_at: datetime,
    ) -> int:
        """Record a UI user's simulated external decision at an active checkpoint.

        This host-only mutation is not exposed as an agent tool. It changes only
        the isolated runtime copy and therefore cannot alter the frozen scenario
        corpus or another run.
        """

        with self._lock:
            requirement = self._approval_requirement
            if requirement is None or requirement.approval_id != approval_id:
                raise ValueError("approval does not belong to this runtime case")
            current = self._approvals.get(approval_id)
            if current is None or not current.observable:
                raise ValueError("approval is not observable at this checkpoint")
            if current.status is not ApprovalStatus.PENDING:
                raise ValueError("approval checkpoint already has a final decision")
            if status is ApprovalStatus.PENDING:
                return current.version
            if status is ApprovalStatus.REJECTED and not (decision_reason or "").strip():
                raise ValueError("a rejection requires a concise reason")

            decided_at = observed_at
            if decided_at < current.requested_at:
                decided_at = current.requested_at
            payload = current.model_dump(mode="python")
            payload.update(
                {
                    "status": status,
                    "observable": True,
                    "version": current.version + 1,
                    "decision_reason": (
                        decision_reason.strip()
                        if status is ApprovalStatus.REJECTED and decision_reason
                        else None
                    ),
                    "decided_at": decided_at,
                }
            )
            updated = Approval.model_validate(payload)
            self._approvals[approval_id] = updated
            self._entity_versions[approval_id] = updated.version

            case_payload = self._case.model_dump(mode="python")
            case_payload["state"] = (
                CaseState.READY_FOR_ACTION
                if status is ApprovalStatus.APPROVED
                else CaseState.INVESTIGATING
            )
            self._case = ExceptionCase.model_validate(case_payload)
            self._entity_versions[self._case.case_id] += 1
            self._revision += 1
            return updated.version

    def get_receipt(self, receipt_id: str) -> ActionReceipt:
        with self._lock:
            return self._receipts[receipt_id].model_copy(deep=True)

    def receipt_for_idempotency_key(self, idempotency_key: str) -> ActionReceipt | None:
        with self._lock:
            indexed = self._idempotency.get(idempotency_key)
            if indexed is None:
                return None
            return self._receipts[indexed[1]].model_copy(deep=True)

    def receipts(self) -> tuple[ActionReceipt, ...]:
        with self._lock:
            return tuple(receipt.model_copy(deep=True) for receipt in self._receipts.values())

    def entity_version(self, target_id: str) -> int:
        with self._lock:
            return self._entity_versions[target_id]

    def entity_versions(self) -> dict[str, int]:
        with self._lock:
            return dict(self._entity_versions)

    def evaluate_goal(
        self,
        *,
        goal_kind: GoalKind,
        predicates: list[GoalPredicate],
        evaluation_id: str,
    ) -> GoalEvaluation:
        """Evaluate explicit completion predicates against current state only."""

        if not predicates:
            raise ValueError("goal evaluation requires at least one predicate")
        if any(predicate.goal_kind is not goal_kind for predicate in predicates):
            raise ValueError("every predicate must match goal_kind")
        with self._lock:
            results = [self._evaluate_predicate(predicate) for predicate in predicates]
            evaluated_at = self._case.scenario_time + timedelta(
                seconds=max(1, self._revision)
            )
        return GoalEvaluation(
            evaluation_id=evaluation_id,
            goal_kind=goal_kind,
            complete=all(item.satisfied for item in results if item.required),
            predicate_results=results,
            evaluated_at=evaluated_at,
        )

    # The following methods are intentionally internal.  The action engine uses
    # them only while holding ``_lock``; agent-facing tools expose defensive
    # response models rather than this mutable surface.

    def _copy_mutable_state(self) -> _MutableSessionState:
        return _MutableSessionState(
            registration=self._registration.model_copy(deep=True),
            case=self._case.model_copy(deep=True),
            offering_states={
                key: value.model_copy(deep=True)
                for key, value in self._offering_states.items()
            },
            approvals={
                key: value.model_copy(deep=True)
                for key, value in self._approvals.items()
            },
            entity_versions=dict(self._entity_versions),
        )

    def _commit_action(
        self,
        *,
        state: _MutableSessionState,
        receipt: ActionReceipt,
        fingerprint: str,
    ) -> None:
        if receipt.session_revision != self._revision + 1:
            raise ValueError("receipt session revision is not the next revision")
        self._registration = state.registration
        self._case = state.case
        self._offering_states = state.offering_states
        self._approvals = state.approvals
        self._entity_versions = state.entity_versions
        self._receipts[receipt.receipt_id] = receipt.model_copy(deep=True)
        self._idempotency[receipt.idempotency_key] = (
            fingerprint,
            receipt.receipt_id,
        )
        self._revision = receipt.session_revision

    def _idempotency_record(self, key: str) -> tuple[str, ActionReceipt] | None:
        indexed = self._idempotency.get(key)
        if indexed is None:
            return None
        fingerprint, receipt_id = indexed
        return fingerprint, self._receipts[receipt_id].model_copy(deep=True)

    def _evaluate_predicate(self, predicate: GoalPredicate) -> PredicateEvaluation:
        targets = self._predicate_targets(predicate)
        observed: list[Any] = []
        for target in targets:
            observed.extend(_extract_path(target, predicate.field_path.split(".")))
        observed_value: Any
        if not observed:
            observed_value = None
        elif len(observed) == 1:
            observed_value = _json_value(observed[0])
        else:
            observed_value = [_json_value(value) for value in observed]
        satisfied = _compare_goal_value(
            observed,
            predicate.operator,
            predicate.expected_value,
        )
        return PredicateEvaluation(
            predicate_id=predicate.predicate_id,
            required=predicate.required,
            satisfied=satisfied,
            observed_value=observed_value,
            reason=(
                "The current runtime state satisfies the predicate."
                if satisfied
                else "The current runtime state does not satisfy the predicate."
            ),
            evidence_ids=list(predicate.target_ids),
        )

    def _predicate_targets(self, predicate: GoalPredicate) -> list[Any]:
        if predicate.target_type is None:
            if predicate.goal_kind is GoalKind.COURSE_REGISTERED:
                return [self._registration]
            if predicate.goal_kind in {
                GoalKind.WAIVER_SUBMITTED,
                GoalKind.EXCEPTION_SUBMITTED,
                GoalKind.INFORMATION_REQUESTED,
            }:
                return list(self._receipts.values())
            if predicate.goal_kind is GoalKind.APPROVAL_OBSERVED:
                return list(self._approvals.values())
            return [self._case]

        stores: dict[StateTargetType, dict[str, Any]] = {
            StateTargetType.CASE: {str(self._case.case_id): self._case},
            StateTargetType.REGISTRATION: {
                str(self._registration.registration_id): self._registration
            },
            StateTargetType.OFFERING_STATE: self._offering_states,
            StateTargetType.APPROVAL: self._approvals,
            StateTargetType.TRANSACTION: self._receipts,
        }
        store = stores[predicate.target_type]
        return [store[target_id] for target_id in predicate.target_ids if target_id in store]


def _extract_path(value: Any, path: list[str]) -> list[Any]:
    if not path:
        return [value]
    if isinstance(value, (list, tuple)):
        return [
            nested
            for item in value
            for nested in _extract_path(item, path)
        ]
    head, *tail = path
    if isinstance(value, dict):
        if head not in value:
            return []
        return _extract_path(value[head], tail)
    if not hasattr(value, head):
        return []
    return _extract_path(getattr(value, head), tail)


def _json_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _compare_goal_value(
    observed: list[Any], operator: GoalOperator, expected: Any
) -> bool:
    normalized = [_json_value(value) for value in observed]
    if operator is GoalOperator.EXISTS:
        return bool(normalized)
    if operator is GoalOperator.EQUALS:
        return any(value == expected for value in normalized)
    if operator is GoalOperator.NOT_EQUALS:
        return bool(normalized) and all(value != expected for value in normalized)
    if operator is GoalOperator.CONTAINS:
        return any(
            expected in value if isinstance(value, (list, str, dict)) else False
            for value in normalized
        ) or expected in normalized
    if operator is GoalOperator.GREATER_THAN_OR_EQUAL:
        return any(value >= expected for value in normalized)
    if operator is GoalOperator.LESS_THAN_OR_EQUAL:
        return any(value <= expected for value in normalized)
    return False


__all__ = ["ApprovalRequirement", "RuntimeSession"]
