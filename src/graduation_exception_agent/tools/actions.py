"""Action & Transaction tool adapters over the atomic runtime engine."""

from __future__ import annotations

from graduation_exception_agent.models.common import (
    CourseCode,
    DomainModel,
    Identifier,
)
from graduation_exception_agent.models.tooling import ToolCallContext, ToolResponse
from graduation_exception_agent.models.workflow import TransactionAction
from graduation_exception_agent.runtime.execution import ActionEngine


class ApprovalRequest(DomainModel):
    context: ToolCallContext
    approval_id: Identifier


class RegistrationSubmissionRequest(DomainModel):
    context: ToolCallContext
    offering_state_id: Identifier
    approval_id: Identifier | None = None
    course_code: CourseCode | None = None
    retry: bool | None = None


class WaiverSubmissionRequest(DomainModel):
    context: ToolCallContext
    approval_id: Identifier
    course_code: CourseCode


class ExceptionSubmissionRequest(DomainModel):
    context: ToolCallContext
    offering_state_id: Identifier | None = None
    approval_id: Identifier | None = None
    course_code: CourseCode | None = None
    curriculum_id: Identifier | None = None
    graduation_path_id: Identifier | None = None


class TransactionStatusRequest(DomainModel):
    context: ToolCallContext
    receipt_id: Identifier


class ActionTransactionTools:
    """Typed write endpoints; no method exposes its hidden script/controller."""

    def __init__(self, *, engine: ActionEngine) -> None:
        self.__engine = engine

    def request_approval(self, request: ApprovalRequest) -> ToolResponse:
        return self.__engine.execute(
            context=request.context,
            action=TransactionAction.REQUEST_APPROVAL,
            parameters={"approval_id": request.approval_id},
        )

    def submit_registration(
        self, request: RegistrationSubmissionRequest
    ) -> ToolResponse:
        parameters: dict[str, object] = {
            "offering_state_id": request.offering_state_id
        }
        if request.approval_id is not None:
            parameters["approval_id"] = request.approval_id
        if request.course_code is not None:
            parameters["course_code"] = request.course_code
        if request.retry is not None:
            parameters["retry"] = request.retry
        return self.__engine.execute(
            context=request.context,
            action=TransactionAction.SUBMIT_REGISTRATION,
            parameters=parameters,
        )

    def submit_waiver(self, request: WaiverSubmissionRequest) -> ToolResponse:
        return self.__engine.execute(
            context=request.context,
            action=TransactionAction.SUBMIT_WAIVER,
            parameters={
                "approval_id": request.approval_id,
                "course_code": request.course_code,
            },
        )

    def submit_exception(self, request: ExceptionSubmissionRequest) -> ToolResponse:
        parameters = {
            key: value
            for key, value in {
                "offering_state_id": request.offering_state_id,
                "approval_id": request.approval_id,
                "course_code": request.course_code,
                "curriculum_id": request.curriculum_id,
                "graduation_path_id": request.graduation_path_id,
            }.items()
            if value is not None
        }
        return self.__engine.execute(
            context=request.context,
            action=TransactionAction.SUBMIT_EXCEPTION,
            parameters=parameters,
        )

    def get_transaction_status(
        self, request: TransactionStatusRequest
    ) -> ToolResponse:
        return self.__engine.transaction_status(
            context=request.context,
            receipt_id=request.receipt_id,
        )


__all__ = [
    "ActionTransactionTools",
    "ApprovalRequest",
    "ExceptionSubmissionRequest",
    "RegistrationSubmissionRequest",
    "TransactionStatusRequest",
    "WaiverSubmissionRequest",
]
