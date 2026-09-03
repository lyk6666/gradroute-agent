"""Build fresh, isolated Stage 4 runtimes from the frozen Stage 3 package."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from graduation_exception_agent.data.real.repository import RealDataRepository
from graduation_exception_agent.data.simulated.repository import (
    SimulatedDataRepository,
    Stage3DataBundle,
)
from graduation_exception_agent.models.runtime import (
    GoalEvaluation,
    GoalKind,
    GoalPredicate,
)
from graduation_exception_agent.models.academic import OfferingState, Registration
from graduation_exception_agent.models.tooling import ActionReceipt
from graduation_exception_agent.models.workflow import (
    ApprovalStatus,
    EventType,
    ExceptionCase,
    ObservationCode,
    ScenarioContext,
    StateMutation,
    TransactionAction,
    TransactionCode,
    TransactionResult,
    TransactionScript,
)
from graduation_exception_agent.runtime.controller import ScenarioController
from graduation_exception_agent.runtime.execution import ActionEngine
from graduation_exception_agent.runtime.session import (
    ApprovalRequirement,
    RuntimeSession,
)
from graduation_exception_agent.tools.academic import AcademicStudentTools
from graduation_exception_agent.tools.actions import ActionTransactionTools
from graduation_exception_agent.tools.course import CourseSchedulingTools
from graduation_exception_agent.tools.policy import PolicyExceptionTools


@dataclass(frozen=True, slots=True)
class Stage4Tools:
    """Agent-facing Stage 4 API; contains no evaluator controller or oracle."""

    session_id: str
    runtime_instance_id: str
    context: ScenarioContext
    academic: AcademicStudentTools
    policy: PolicyExceptionTools
    course: CourseSchedulingTools
    actions: ActionTransactionTools
    __session: RuntimeSession

    def evaluate_goal(
        self,
        *,
        goal_kind: GoalKind,
        predicates: list[GoalPredicate],
        evaluation_id: str,
    ) -> GoalEvaluation:
        """Evaluate current-state predicates without consulting ground truth."""

        return self.__session.evaluate_goal(
            goal_kind=goal_kind,
            predicates=predicates,
            evaluation_id=evaluation_id,
        )

    def _claim_stage5_control_plane(self, owner: object, thread_id: str) -> None:
        """Lease this mutable runtime to exactly one Stage 5 facade/thread."""

        self.__session.claim_stage5_control_plane(owner, thread_id)

    def _assert_stage5_control_plane(self, owner: object, thread_id: str) -> None:
        """Fail closed if a facade no longer owns this mutable runtime."""

        self.__session.assert_stage5_control_plane(owner, thread_id)


class EvaluatorHandle:
    """Test-only diagnostics kept separate from the agent-facing tool set."""

    def __init__(
        self, *, session: RuntimeSession, controller: ScenarioController
    ) -> None:
        self.__session = session
        self.__controller = controller

    @property
    def consumed_steps(self) -> int:
        return self.__controller.consumed_steps

    @property
    def complete(self) -> bool:
        return self.__controller.complete

    @property
    def session_revision(self) -> int:
        return self.__session.revision

    def receipts(self) -> tuple[ActionReceipt, ...]:
        return self.__session.receipts()

    def offering_state(self, state_id: str) -> OfferingState:
        return self.__session.get_offering_state(state_id)

    def registration(self) -> Registration:
        return self.__session.get_registration(self.__session.context.registration_id)

    def case(self) -> ExceptionCase:
        return self.__session.get_case(self.__session.case_id)


class HumanInteractionHandle:
    """Host-only input boundary for a simulated human decision."""

    def __init__(self, *, session: RuntimeSession) -> None:
        self.__session = session

    def record_approval(
        self,
        *,
        approval_id: str,
        status: ApprovalStatus,
        decision_reason: str | None,
        observed_at: datetime,
    ) -> int:
        return self.__session.record_human_approval(
            approval_id=approval_id,
            status=status,
            decision_reason=decision_reason,
            observed_at=observed_at,
        )


@dataclass(frozen=True, slots=True)
class ScenarioRuntime:
    """Construction result; pass only ``tools`` into agent/control-plane code."""

    tools: Stage4Tools
    evaluator: EvaluatorHandle
    human: HumanInteractionHandle


class ScenarioRuntimeFactory:
    """Create a clean runtime per scenario without mutating either repository."""

    def __init__(
        self,
        *,
        real_repository: RealDataRepository,
        simulated_repository: SimulatedDataRepository,
    ) -> None:
        self._real = real_repository
        self._simulated = simulated_repository
        # This copy is intentionally held only by the evaluator-side factory.
        self.__bundle: Stage3DataBundle = simulated_repository.bundle
        self.__scenarios = {
            item.scenario_id: item for item in self.__bundle.scenarios
        }
        self.__scripts = {
            item.script_id: item for item in self.__bundle.transaction_scripts
        }
        self.__approvals = {
            item.case_id: item for item in self.__bundle.approvals
        }

    @classmethod
    def from_data_directory(cls, data_directory: str | Path) -> ScenarioRuntimeFactory:
        """Load validated ``real/``, ``simulated/``, and ``tests/`` siblings."""

        root = Path(data_directory)
        real = RealDataRepository.from_directory(root / "real")
        simulated = SimulatedDataRepository.from_directory(
            root / "simulated",
            real_repository=real,
            scenarios_path=root / "tests" / "scenarios.json",
            real_directory=root / "real",
        )
        return cls(real_repository=real, simulated_repository=simulated)

    def build(
        self, scenario_id: str, *, interactive_approval: bool = False
    ) -> ScenarioRuntime:
        scenario = self.__scenarios[scenario_id]
        context = self._simulated.to_agent_context(scenario_id)
        student = self._simulated.get_student(scenario.student_id)
        audit = self._simulated.get_audit(scenario.audit_id)
        registration = self._simulated.get_registration(scenario.registration_id)
        case = self._simulated.get_case(scenario.case_id)
        states = tuple(
            self._simulated.get_offering_state(state_id)
            for state_id in scenario.offering_state_ids
        )
        approval = self.__approvals.get(scenario.case_id)
        requirement = (
            None
            if approval is None
            else ApprovalRequirement(
                approval_id=approval.approval_id,
                case_id=approval.case_id,
                approver_role=approval.approver_role,
                requested_action=approval.requested_action,
                basis=approval.basis,
                basis_rule_ids=tuple(approval.basis_rule_ids),
                required_document_ids=tuple(approval.required_document_ids),
                version=approval.version,
            )
        )
        observable_approval = (
            approval
            if approval is not None
            and approval.observable
            and not interactive_approval
            else None
        )
        session = RuntimeSession(
            session_id=f"session.{case.case_id}",
            context=context,
            student=student,
            audit=audit,
            registration=registration,
            case=case,
            offering_states=states,
            approval_requirement=requirement,
            observable_approval=observable_approval,
        )
        script = self.__scripts[scenario.transaction_script_id]
        if interactive_approval:
            script = _with_interactive_approval_checkpoint(script)
        controller = ScenarioController(
            script=script,
            approval_seed=approval,
        )
        engine = ActionEngine(
            session=session,
            controller=controller,
            real_repository=self._real,
        )
        tools = Stage4Tools(
            session_id=session.session_id,
            runtime_instance_id=uuid4().hex,
            context=context.model_copy(deep=True),
            academic=AcademicStudentTools(
                session=session,
                real_repository=self._real,
            ),
            policy=PolicyExceptionTools(
                session=session,
                real_repository=self._real,
                prototype_policies=self.__bundle.prototype_policies,
            ),
            course=CourseSchedulingTools(
                session=session,
                real_repository=self._real,
            ),
            actions=ActionTransactionTools(engine=engine),
            _Stage4Tools__session=session,
        )
        return ScenarioRuntime(
            tools=tools,
            evaluator=EvaluatorHandle(session=session, controller=controller),
            human=HumanInteractionHandle(session=session),
        )


def _with_interactive_approval_checkpoint(
    script: TransactionScript,
) -> TransactionScript:
    """Turn a scripted approval result into a user-controlled pending gate.

    Only the isolated UI runtime receives this copy. The frozen Stage 3 script
    and the evaluator campaign continue to use their original decisions.
    """

    steps = list(script.steps)
    approval_index = next(
        (
            index
            for index, step in enumerate(steps)
            if step.action is TransactionAction.REQUEST_APPROVAL
        ),
        None,
    )
    if approval_index is None:
        return script
    approval_step = steps[approval_index]
    approval_id = str(approval_step.action_parameters["approval_id"])
    mutation = next(
        item
        for item in approval_step.mutations
        if item.target_id == approval_id
    )
    mutation_payload = mutation.model_dump(mode="python")
    mutation_payload["changes"] = {
        **mutation.changes,
        "observable": True,
        "status": ApprovalStatus.PENDING.value,
        "decision_reason": None,
        "decided_at": None,
    }
    pending_mutation = StateMutation.model_validate(mutation_payload)
    event_payload = (
        approval_step.event.model_dump(mode="python")
        if approval_step.event
        else None
    )
    if event_payload is not None:
        event_payload["event_type"] = EventType.APPROVAL_PENDING
    step_payload = approval_step.model_dump(mode="python")
    step_payload.update(
        {
            "result_code": TransactionCode.APPROVAL_PENDING,
            "observation": ObservationCode.APPROVAL_PENDING,
            "retryable": True,
            "error_code": "APPROVAL_PENDING",
            "message": "The verified request is waiting for a simulated human decision.",
            "event": event_payload,
            "mutations": [pending_mutation],
        }
    )
    steps[approval_index] = TransactionResult.model_validate(step_payload)

    pending_version = int(pending_mutation.resulting_version or 1)
    decided_version = pending_version + 1
    for index in range(approval_index + 1, len(steps)):
        later_payload = steps[index].model_dump(mode="python")
        versions = dict(later_payload.get("precondition_state_versions", {}))
        if versions.get(approval_id) == pending_version:
            versions[approval_id] = decided_version
            later_payload["precondition_state_versions"] = versions
        steps[index] = TransactionResult.model_validate(later_payload)
    payload = script.model_dump(mode="python")
    payload["steps"] = steps
    return TransactionScript.model_validate(payload)


__all__ = [
    "EvaluatorHandle",
    "ScenarioRuntime",
    "ScenarioRuntimeFactory",
    "Stage4Tools",
]
