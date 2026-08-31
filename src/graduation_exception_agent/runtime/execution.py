"""Atomic, idempotent execution of Stage 4 simulated action tools."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from graduation_exception_agent.data.real.repository import RealDataRepository
from graduation_exception_agent.models.academic import (
    EligibilityStatus,
    OfferingState,
    Registration,
    RegistrationItem,
    RegistrationItemStatus,
    RegistrationMeeting,
)
from graduation_exception_agent.models.tooling import (
    ActionPostcondition,
    ActionReceipt,
    ToolCallContext,
    ToolError,
    ToolErrorCode,
    ToolObservation,
    ToolResponse,
    ToolStatus,
)
from graduation_exception_agent.models.workflow import (
    Approval,
    ApprovalStatus,
    CaseState,
    ObservationCode,
    StateMutation,
    StateTargetType,
    TransactionAction,
    TransactionCode,
    TransactionResult,
)
from graduation_exception_agent.runtime.controller import (
    ScenarioController,
    ScriptExhaustedError,
    ScriptMismatchError,
)
from graduation_exception_agent.runtime.session import (
    RuntimeSession,
    _MutableSessionState,
)


_SUCCESS_CODES = {
    TransactionCode.SUCCESS,
    TransactionCode.EXCEPTION_SUBMISSION_SUCCESS,
}

_ERROR_CODE_BY_RESULT = {
    TransactionCode.MODULE_FULL: ToolErrorCode.MODULE_FULL,
    TransactionCode.CLASS_UNAVAILABLE: ToolErrorCode.CLASS_UNAVAILABLE,
    TransactionCode.PREREQUISITE_FAILURE: ToolErrorCode.PREREQUISITE_FAILURE,
    TransactionCode.APPROVAL_REJECTED: ToolErrorCode.APPROVAL_REJECTED,
    TransactionCode.APPROVAL_PENDING: ToolErrorCode.APPROVAL_PENDING,
    TransactionCode.STALE_STATE: ToolErrorCode.STALE_STATE,
    TransactionCode.TEMPORARY_SYSTEM_FAILURE: ToolErrorCode.TEMPORARY_FAILURE,
    TransactionCode.REQUIRED_INFORMATION_MISSING: (
        ToolErrorCode.REQUIRED_INFORMATION_MISSING
    ),
}

_MUTABLE_OFFERING_FIELDS = {
    "capacity",
    "vacancies",
    "waitlist_count",
    "runtime_status",
    "available",
    "unavailable_reason",
}
_MUTABLE_APPROVAL_FIELDS = {
    "status",
    "observable",
    "decision_reason",
    "decided_at",
}


class _ActionRejected(RuntimeError):
    def __init__(self, error: ToolError) -> None:
        self.error = error
        super().__init__(error.message)


class ActionEngine:
    """Execute hidden scripted results against an isolated session copy."""

    def __init__(
        self,
        *,
        session: RuntimeSession,
        controller: ScenarioController,
        real_repository: RealDataRepository,
    ) -> None:
        self._session = session
        self._controller = controller
        self._real = real_repository
        self._offerings = {
            offering.offering_id: offering for offering in real_repository.offerings
        }

    def execute(
        self,
        *,
        context: ToolCallContext,
        action: TransactionAction,
        parameters: dict[str, object],
    ) -> ToolResponse:
        """Run one action attempt and return only normalized observable output."""

        error = self._validate_call(context, action, parameters)
        if error is not None:
            return _failure_response(context.request_id, error)
        assert context.idempotency_key is not None
        fingerprint = _fingerprint(context, action, parameters)

        with self._session._lock:
            previous = self._session._idempotency_record(context.idempotency_key)
            if previous is not None:
                old_fingerprint, old_receipt = previous
                if old_fingerprint != fingerprint:
                    return _failure_response(
                        context.request_id,
                        ToolError(
                            code=ToolErrorCode.IDEMPOTENCY_CONFLICT,
                            message=(
                                "The idempotency key is already bound to a different "
                                "action request."
                            ),
                            retryable=False,
                        ),
                    )
                replayed = old_receipt.model_copy(update={"replayed": True})
                return _response_for_receipt(replayed)

            approval_error = self._validate_approval_gate(action, parameters)
            if approval_error is not None:
                return _failure_response(context.request_id, approval_error)

            try:
                return self._controller.consume(
                    action=action,
                    parameters=parameters,
                    execute=lambda step: self._apply_step(
                        context=context,
                        step=step,
                        fingerprint=fingerprint,
                    ),
                )
            except _ActionRejected as exc:
                return _failure_response(context.request_id, exc.error)
            except (ScriptMismatchError, ScriptExhaustedError):
                return _failure_response(
                    context.request_id,
                    ToolError(
                        code=ToolErrorCode.CONSTRAINT_VIOLATION,
                        message=(
                            "The requested action is not available in the current "
                            "runtime state."
                        ),
                        retryable=False,
                    ),
                )

    def transaction_status(
        self, *, context: ToolCallContext, receipt_id: str
    ) -> ToolResponse:
        error = self._validate_context(context)
        if error is not None:
            return _failure_response(context.request_id, error)
        try:
            receipt = self._session.get_receipt(receipt_id)
        except KeyError:
            return _failure_response(
                context.request_id,
                ToolError(
                    code=ToolErrorCode.NOT_FOUND,
                    message="No transaction receipt with that identifier is visible.",
                    retryable=False,
                ),
            )
        return ToolResponse(
            request_id=context.request_id,
            status=receipt.status,
            data=receipt.model_dump(mode="json"),
            error=receipt.error,
            observations=[receipt.observation],
            entity_versions=dict(receipt.entity_versions),
        )

    def _validate_call(
        self,
        context: ToolCallContext,
        action: TransactionAction,
        parameters: dict[str, object],
    ) -> ToolError | None:
        context_error = self._validate_context(context)
        if context_error is not None:
            return context_error
        if context.idempotency_key is None:
            return ToolError(
                code=ToolErrorCode.INVALID_REQUEST,
                message="Action tools require an idempotency key.",
                retryable=False,
            )
        if not parameters and action in {
            TransactionAction.REQUEST_APPROVAL,
            TransactionAction.SUBMIT_REGISTRATION,
            TransactionAction.SUBMIT_WAIVER,
        }:
            return ToolError(
                code=ToolErrorCode.INVALID_REQUEST,
                message="The requested action is missing its target parameters.",
                retryable=False,
            )
        return None

    def _validate_context(self, context: ToolCallContext) -> ToolError | None:
        if context.session_id != self._session.session_id:
            return ToolError(
                code=ToolErrorCode.FORBIDDEN,
                message="The request does not belong to this isolated session.",
                retryable=False,
            )
        if context.case_id != self._session.case_id:
            return ToolError(
                code=ToolErrorCode.FORBIDDEN,
                message="The requested case is outside this isolated session.",
                retryable=False,
            )
        return None

    def _validate_approval_gate(
        self,
        action: TransactionAction,
        parameters: dict[str, object],
    ) -> ToolError | None:
        requirement = self._session.approval_requirement(self._session.case_id)
        approval_id = parameters.get("approval_id")
        if action is TransactionAction.REQUEST_APPROVAL:
            if requirement is None:
                return ToolError(
                    code=ToolErrorCode.CONSTRAINT_VIOLATION,
                    message="This case has no declared approval route.",
                    retryable=False,
                )
            if approval_id != requirement.approval_id:
                return ToolError(
                    code=ToolErrorCode.NOT_FOUND,
                    message="The approval request does not belong to this case.",
                    retryable=False,
                )
            return None

        if requirement is None:
            return None
        if approval_id != requirement.approval_id:
            return ToolError(
                code=ToolErrorCode.APPROVAL_REQUIRED,
                message="The declared approval must be supplied before this write.",
                retryable=False,
            )
        approval = self._session.observable_approval(self._session.case_id)
        if approval is None:
            return ToolError(
                code=ToolErrorCode.APPROVAL_REQUIRED,
                message="The required approval is not yet observable.",
                retryable=False,
            )
        if approval.status is ApprovalStatus.PENDING:
            return ToolError(
                code=ToolErrorCode.APPROVAL_PENDING,
                message="The required approval is still pending.",
                retryable=False,
            )
        if approval.status is ApprovalStatus.REJECTED:
            return ToolError(
                code=ToolErrorCode.APPROVAL_REJECTED,
                message="The requested approval was rejected; the case must replan.",
                retryable=False,
            )
        return None

    def _apply_step(
        self,
        *,
        context: ToolCallContext,
        step: TransactionResult,
        fingerprint: str,
    ) -> ToolResponse:
        candidate = self._session._copy_mutable_state()
        self._validate_versions(context, step, candidate)

        changed_ids: set[str] = set()
        for mutation in step.mutations:
            self._apply_script_mutation(candidate, mutation)
            changed_ids.add(mutation.target_id)

        attempt = len(self._session._receipts) + 1
        receipt_id = f"receipt.runtime.{self._session.case_id}.{attempt}"
        transaction_id = f"transaction.runtime.{self._session.case_id}.{attempt}"
        postconditions: list[ActionPostcondition] = []
        successful = step.result_code in _SUCCESS_CODES
        goal_effect = successful and step.action is not TransactionAction.REQUEST_APPROVAL

        if step.action is TransactionAction.REQUEST_APPROVAL:
            self._apply_approval_case_state(candidate, step.result_code, changed_ids)
            approval_id = str(step.action_parameters["approval_id"])
            approval = candidate.approvals.get(approval_id)
            if approval is not None:
                postconditions.append(
                    ActionPostcondition(
                        postcondition_id=f"postcondition.runtime.{attempt}.approval",
                        target_type=StateTargetType.APPROVAL,
                        target_id=approval_id,
                        field_path="status",
                        expected_value=approval.status.value,
                        observed_value=approval.status.value,
                        satisfied=True,
                    )
                )
        elif goal_effect:
            if step.action is TransactionAction.SUBMIT_REGISTRATION:
                postconditions.extend(
                    self._commit_registration(
                        candidate,
                        step,
                        attempt=attempt,
                        changed_ids=changed_ids,
                    )
                )
            else:
                postconditions.extend(
                    self._commit_case_action(
                        candidate,
                        step.action,
                        receipt_id=receipt_id,
                        attempt=attempt,
                        changed_ids=changed_ids,
                    )
                )
        else:
            self._apply_failure_case_state(candidate, step.result_code, changed_ids)

        status = _tool_status(step.result_code)
        error = _tool_error(step)
        changed_versions = {
            target_id: candidate.entity_versions[target_id]
            for target_id in sorted(changed_ids)
            if target_id in candidate.entity_versions
        }
        observation = ToolObservation(
            observation_id=f"observation.runtime.{self._session.case_id}.{attempt}",
            code=(
                ObservationCode.APPROVAL_PENDING
                if step.result_code is TransactionCode.APPROVAL_PENDING
                else step.observation
            ),
            message=step.message,
            retryable=step.retryable,
            occurred_at=step.occurred_at,
            state_versions=changed_versions,
        )
        receipt = ActionReceipt(
            receipt_id=receipt_id,
            transaction_id=transaction_id,
            session_id=self._session.session_id,
            request_id=context.request_id,
            idempotency_key=context.idempotency_key,
            case_id=context.case_id,
            action=step.action,
            status=status,
            result_code=step.result_code,
            observation=observation,
            message=step.message,
            error=error,
            mutation_ids=[
                f"mutation.runtime.{attempt}.{index}"
                for index in range(1, len(changed_ids) + 1)
            ],
            entity_versions=changed_versions,
            postconditions=postconditions,
            committed=bool(changed_ids) or goal_effect,
            intermediate=step.action is TransactionAction.REQUEST_APPROVAL,
            retryable=step.retryable,
            goal_effect=goal_effect,
            session_revision=self._session.revision + 1,
            committed_at=step.occurred_at,
        )
        self._session._commit_action(
            state=candidate,
            receipt=receipt,
            fingerprint=fingerprint,
        )
        return _response_for_receipt(receipt)

    def _validate_versions(
        self,
        context: ToolCallContext,
        step: TransactionResult,
        candidate: _MutableSessionState,
    ) -> None:
        supplied = {item.target_id: item for item in context.expected_versions}
        for target_id, required_version in step.precondition_state_versions.items():
            expectation = supplied.get(target_id)
            if expectation is None:
                raise _ActionRejected(
                    ToolError(
                        code=ToolErrorCode.INVALID_REQUEST,
                        message=(
                            "The write is missing a required observed state version."
                        ),
                        retryable=False,
                    )
                )
            actual_type, actual_version = self._current_version(candidate, target_id)
            if expectation.target_type is not actual_type:
                raise _ActionRejected(
                    ToolError(
                        code=ToolErrorCode.INVALID_REQUEST,
                        message="A supplied state version uses the wrong target type.",
                        retryable=False,
                    )
                )
            if (
                expectation.expected_version != required_version
                or actual_version != expectation.expected_version
            ):
                raise _ActionRejected(
                    ToolError(
                        code=ToolErrorCode.STALE_STATE,
                        message="The observed state version is no longer current.",
                        retryable=True,
                    )
                )

        for expectation in context.expected_versions:
            actual_type, actual_version = self._current_version(
                candidate, expectation.target_id
            )
            if (
                expectation.target_type is not actual_type
                or expectation.expected_version != actual_version
            ):
                raise _ActionRejected(
                    ToolError(
                        code=ToolErrorCode.STALE_STATE,
                        message="The observed state version is no longer current.",
                        retryable=True,
                    )
                )

    def _current_version(
        self, candidate: _MutableSessionState, target_id: str
    ) -> tuple[StateTargetType, int]:
        if target_id in candidate.offering_states:
            return StateTargetType.OFFERING_STATE, candidate.offering_states[target_id].version
        if target_id in candidate.approvals:
            return StateTargetType.APPROVAL, candidate.approvals[target_id].version
        if target_id == candidate.registration.registration_id:
            return StateTargetType.REGISTRATION, candidate.entity_versions[target_id]
        if target_id == candidate.case.case_id:
            return StateTargetType.CASE, candidate.entity_versions[target_id]
        try:
            seed = self._controller.approval_seed(target_id)
        except KeyError as exc:
            raise _ActionRejected(
                ToolError(
                    code=ToolErrorCode.NOT_FOUND,
                    message="A version target is not visible in this case session.",
                    retryable=False,
                )
            ) from exc
        return StateTargetType.APPROVAL, seed.version

    def _apply_script_mutation(
        self, candidate: _MutableSessionState, mutation: StateMutation
    ) -> None:
        if mutation.target_type is StateTargetType.OFFERING_STATE:
            target = candidate.offering_states.get(mutation.target_id)
            allowed = _MUTABLE_OFFERING_FIELDS
            model = OfferingState
        elif mutation.target_type is StateTargetType.APPROVAL:
            target = candidate.approvals.get(mutation.target_id)
            if target is None:
                try:
                    target = self._controller.approval_seed(mutation.target_id)
                except KeyError as exc:
                    raise _ActionRejected(
                        ToolError(
                            code=ToolErrorCode.NOT_FOUND,
                            message="The transaction target is unavailable.",
                            retryable=False,
                        )
                    ) from exc
            allowed = _MUTABLE_APPROVAL_FIELDS
            model = Approval
        else:
            raise _ActionRejected(
                ToolError(
                    code=ToolErrorCode.CONSTRAINT_VIOLATION,
                    message="The transaction contains an unsupported mutation target.",
                    retryable=False,
                )
            )
        if set(mutation.changes) - allowed:
            raise _ActionRejected(
                ToolError(
                    code=ToolErrorCode.CONSTRAINT_VIOLATION,
                    message="The transaction attempts to change an immutable field.",
                    retryable=False,
                )
            )
        assert mutation.expected_version is not None
        assert mutation.resulting_version is not None
        if target.version != mutation.expected_version:
            raise _ActionRejected(
                ToolError(
                    code=ToolErrorCode.STALE_STATE,
                    message="The transaction mutation is based on stale state.",
                    retryable=True,
                )
            )
        payload = target.model_dump(mode="python")
        payload.update(mutation.changes)
        payload["version"] = mutation.resulting_version
        updated = model.model_validate(payload)
        if mutation.target_type is StateTargetType.OFFERING_STATE:
            candidate.offering_states[mutation.target_id] = updated
        else:
            candidate.approvals[mutation.target_id] = updated
        candidate.entity_versions[mutation.target_id] = mutation.resulting_version

    def _commit_registration(
        self,
        candidate: _MutableSessionState,
        step: TransactionResult,
        *,
        attempt: int,
        changed_ids: set[str],
    ) -> list[ActionPostcondition]:
        state_id = str(step.action_parameters["offering_state_id"])
        state = candidate.offering_states[state_id]
        if not state.available or state.vacancies <= 0:
            raise _ActionRejected(
                ToolError(
                    code=ToolErrorCode.MODULE_FULL,
                    message="The selected class is no longer available.",
                    retryable=False,
                )
            )
        offering = self._offerings[state.template_offering_id]
        index = next(
            item for item in offering.indexes if item.index_id == state.template_index_id
        )
        course = self._real.get_course(offering.course_code)
        requested_course = step.action_parameters.get("course_code")
        if requested_course is not None and requested_course != course.code:
            raise _ActionRejected(
                ToolError(
                    code=ToolErrorCode.CONSTRAINT_VIOLATION,
                    message="The course does not own the selected class index.",
                    retryable=False,
                )
            )
        registration = candidate.registration
        if any(item.course_code == course.code for item in registration.registered_courses):
            raise _ActionRejected(
                ToolError(
                    code=ToolErrorCode.CONSTRAINT_VIOLATION,
                    message="The course is already registered.",
                    retryable=False,
                )
            )
        workload = Decimal(registration.workload_aus) + Decimal(course.aus)
        if workload > Decimal(registration.workload_limit_aus):
            raise _ActionRejected(
                ToolError(
                    code=ToolErrorCode.CONSTRAINT_VIOLATION,
                    message="The registration would exceed the workload limit.",
                    retryable=False,
                )
            )

        item_id = f"registration-item.runtime.{attempt}.{course.code.lower()}"
        item = RegistrationItem(
            registration_item_id=item_id,
            course_code=course.code,
            template_offering_id=state.template_offering_id,
            template_index_id=state.template_index_id,
            offering_state_id=state.state_id,
            expected_state_version=state.version,
            aus=course.aus,
            status=RegistrationItemStatus.REGISTERED,
            eligibility=EligibilityStatus.ELIGIBLE,
            eligibility_reason=(
                "Eligible for the committed deterministic transaction path."
            ),
        )
        meetings = list(registration.timetable)
        for meeting_number, meeting in enumerate(index.meetings, start=1):
            meetings.append(
                RegistrationMeeting(
                    meeting_id=f"meeting.runtime.{attempt}.{meeting_number}",
                    registration_item_id=item_id,
                    course_code=course.code,
                    template_offering_id=state.template_offering_id,
                    template_index_id=state.template_index_id,
                    meeting=meeting,
                )
            )
        registration_payload = registration.model_dump(mode="python")
        registration_payload.update(
            {
                "registered_courses": [*registration.registered_courses, item],
                "timetable": meetings,
                "workload_aus": workload,
                "missing_required_courses": [
                    code
                    for code in registration.missing_required_courses
                    if code != course.code
                ],
            }
        )
        candidate.registration = Registration.model_validate(registration_payload)
        candidate.entity_versions[registration.registration_id] += 1
        changed_ids.add(registration.registration_id)

        state_payload = state.model_dump(mode="python")
        state_payload.update(
            {
                "vacancies": state.vacancies - 1,
                "available": state.vacancies - 1 > 0,
                "version": state.version + 1,
            }
        )
        updated_state = OfferingState.model_validate(state_payload)
        candidate.offering_states[state_id] = updated_state
        candidate.entity_versions[state_id] = updated_state.version
        changed_ids.add(state_id)
        self._set_case_state(candidate, CaseState.RESOLVED, changed_ids)

        return [
            ActionPostcondition(
                postcondition_id=f"postcondition.runtime.{attempt}.registration",
                target_type=StateTargetType.REGISTRATION,
                target_id=registration.registration_id,
                field_path="registered_courses.course_code",
                expected_value=course.code,
                observed_value=course.code,
                satisfied=True,
            ),
            ActionPostcondition(
                postcondition_id=f"postcondition.runtime.{attempt}.case",
                target_type=StateTargetType.CASE,
                target_id=candidate.case.case_id,
                field_path="state",
                expected_value=CaseState.RESOLVED.value,
                observed_value=candidate.case.state.value,
                satisfied=candidate.case.state is CaseState.RESOLVED,
            ),
        ]

    def _commit_case_action(
        self,
        candidate: _MutableSessionState,
        action: TransactionAction,
        *,
        receipt_id: str,
        attempt: int,
        changed_ids: set[str],
    ) -> list[ActionPostcondition]:
        self._set_case_state(candidate, CaseState.RESOLVED, changed_ids)
        return [
            ActionPostcondition(
                postcondition_id=f"postcondition.runtime.{attempt}.transaction",
                target_type=StateTargetType.TRANSACTION,
                target_id=receipt_id,
                field_path="action",
                expected_value=action.value,
                observed_value=action.value,
                satisfied=True,
            ),
            ActionPostcondition(
                postcondition_id=f"postcondition.runtime.{attempt}.case",
                target_type=StateTargetType.CASE,
                target_id=candidate.case.case_id,
                field_path="state",
                expected_value=CaseState.RESOLVED.value,
                observed_value=candidate.case.state.value,
                satisfied=candidate.case.state is CaseState.RESOLVED,
            ),
        ]

    def _apply_approval_case_state(
        self,
        candidate: _MutableSessionState,
        result: TransactionCode,
        changed_ids: set[str],
    ) -> None:
        if result is TransactionCode.SUCCESS:
            state = CaseState.READY_FOR_ACTION
        elif result is TransactionCode.APPROVAL_PENDING:
            state = CaseState.WAITING_FOR_APPROVAL
        else:
            state = CaseState.INVESTIGATING
        self._set_case_state(candidate, state, changed_ids)

    def _apply_failure_case_state(
        self,
        candidate: _MutableSessionState,
        result: TransactionCode,
        changed_ids: set[str],
    ) -> None:
        if result is TransactionCode.REQUIRED_INFORMATION_MISSING:
            self._set_case_state(candidate, CaseState.WAITING_FOR_STUDENT, changed_ids)

    @staticmethod
    def _set_case_state(
        candidate: _MutableSessionState,
        state: CaseState,
        changed_ids: set[str],
    ) -> None:
        if candidate.case.state is state:
            return
        payload = candidate.case.model_dump(mode="python")
        payload["state"] = state
        candidate.case = type(candidate.case).model_validate(payload)
        candidate.entity_versions[candidate.case.case_id] += 1
        changed_ids.add(candidate.case.case_id)


def _fingerprint(
    context: ToolCallContext,
    action: TransactionAction,
    parameters: dict[str, object],
) -> str:
    payload = {
        "session_id": context.session_id,
        "case_id": context.case_id,
        "action": action.value,
        "parameters": parameters,
        "expected_versions": [
            item.model_dump(mode="json")
            for item in sorted(
                context.expected_versions,
                key=lambda value: (value.target_type.value, value.target_id),
            )
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _tool_status(result: TransactionCode) -> ToolStatus:
    if result in _SUCCESS_CODES:
        return ToolStatus.SUCCESS
    if result is TransactionCode.APPROVAL_PENDING:
        return ToolStatus.PENDING
    return ToolStatus.FAILURE


def _tool_error(step: TransactionResult) -> ToolError | None:
    if step.result_code in _SUCCESS_CODES:
        return None
    return ToolError(
        code=_ERROR_CODE_BY_RESULT[step.result_code],
        message=step.message,
        retryable=step.retryable,
        details={"result_code": step.result_code.value},
    )


def _failure_response(request_id: str, error: ToolError) -> ToolResponse:
    return ToolResponse(
        request_id=request_id,
        status=ToolStatus.FAILURE,
        error=error,
    )


def _response_for_receipt(receipt: ActionReceipt) -> ToolResponse:
    return ToolResponse(
        request_id=receipt.request_id,
        status=receipt.status,
        data=receipt.model_dump(mode="json"),
        error=receipt.error,
        observations=[receipt.observation],
        entity_versions=dict(receipt.entity_versions),
    )


__all__ = ["ActionEngine"]
