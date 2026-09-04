"""Compiled Stage 5 LangGraph control plane and checkpointed runner."""

from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import Any, Iterator, Mapping

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from graduation_exception_agent.memory import (
    ExperienceMemoryStore,
    NullExperienceMemory,
)
from graduation_exception_agent.models.orchestration import (
    ApprovalPause,
    ApprovalResumePayload,
    ClarificationPause,
    ClarificationResumePayload,
    IntakeContext,
    LoopCaps,
    LoopCounters,
    WorkflowNode,
    WorkflowState,
)
from graduation_exception_agent.models.runtime import (
    GoalKind,
    GoalOperator,
    GoalPredicate,
)
from graduation_exception_agent.models.tooling import ToolCallContext, ToolStatus
from graduation_exception_agent.models.workflow import (
    CaseState,
    ExceptionCaseType,
    StateTargetType,
)
from graduation_exception_agent.orchestration.decisions import (
    DecisionProvider,
    GroundedDecisionProvider,
)
from graduation_exception_agent.orchestration.nodes import Stage5Nodes
from graduation_exception_agent.runtime.factory import Stage4Tools
from graduation_exception_agent.tools import CasePolicyRequest, StudentRecordRequest


class Stage5ControlPlane:
    """One compiled graph bound to one isolated Stage 4 case session."""

    def __init__(
        self,
        *,
        tools: Stage4Tools,
        graph: Any,
        checkpointer: Any,
        loop_caps: LoopCaps,
    ) -> None:
        self.tools = tools
        self.graph = graph
        self.checkpointer = checkpointer
        self.loop_caps = loop_caps
        self._session_id = tools.session_id
        self._case_id = tools.context.case_id
        self._runtime_instance_id = tools.runtime_instance_id
        self._owner_token = object()
        self._checkpoint_key_prefix = (
            f"stage5|session:{len(self._session_id)}:{self._session_id}"
            f"|case:{len(self._case_id)}:{self._case_id}"
            f"|runtime:{len(self._runtime_instance_id)}:{self._runtime_instance_id}"
        )
        self._owned_thread_id: str | None = None
        self._ownership_lock = Lock()

    @classmethod
    def build(
        cls,
        *,
        tools: Stage4Tools,
        decisions: DecisionProvider | None = None,
        memory: ExperienceMemoryStore | None = None,
        checkpointer: Any | None = None,
        loop_caps: LoopCaps | None = None,
    ) -> Stage5ControlPlane:
        """Compile the frozen topology around agent-safe Stage 4 tools."""

        selected_decisions = decisions or GroundedDecisionProvider()
        selected_memory = memory or NullExperienceMemory()
        selected_checkpointer = checkpointer or InMemorySaver()
        selected_caps = loop_caps or LoopCaps()
        nodes = Stage5Nodes(
            tools=tools,
            decisions=selected_decisions,
            memory=selected_memory,
        )
        builder = StateGraph(WorkflowState)
        builder.add_node(WorkflowNode.INTAKE_CONTEXT.value, nodes.intake_context)
        builder.add_node(
            WorkflowNode.MEMORY_RETRIEVER.value, nodes.memory_retriever
        )
        builder.add_node(WorkflowNode.PLANNER.value, nodes.planner)
        builder.add_node(
            WorkflowNode.SUPERVISOR_ROUTER.value, nodes.supervisor_router
        )
        builder.add_node(
            WorkflowNode.DEGREE_AUDIT_AGENT.value, nodes.degree_audit_agent
        )
        builder.add_node(WorkflowNode.POLICY_AGENT.value, nodes.policy_agent)
        builder.add_node(WorkflowNode.COURSE_AGENT.value, nodes.course_agent)
        builder.add_node(
            WorkflowNode.RESOLUTION_BUILDER.value, nodes.resolution_builder
        )
        # One registered verifier is invoked in both explicit phases.
        builder.add_node(WorkflowNode.VERIFIER.value, nodes.verifier)
        builder.add_node(WorkflowNode.CLARIFICATION.value, nodes.clarification)
        builder.add_node(WorkflowNode.ACTION_GATE.value, nodes.action_gate)
        builder.add_node(WorkflowNode.HUMAN_APPROVAL.value, nodes.human_approval)
        builder.add_node(
            WorkflowNode.PAUSE_CHECKPOINT.value, nodes.pause_checkpoint
        )
        builder.add_node(
            WorkflowNode.HUMAN_ADMIN_REVIEW.value, nodes.human_admin_review
        )
        builder.add_node(WorkflowNode.TRANSACTION.value, nodes.transaction)
        builder.add_node(WorkflowNode.OBSERVATION.value, nodes.observation)
        builder.add_node(WorkflowNode.MEMORY_UPDATER.value, nodes.memory_updater)
        builder.add_node(WorkflowNode.FINAL_RESPONSE.value, nodes.final_response)

        builder.add_edge(START, WorkflowNode.INTAKE_CONTEXT.value)
        builder.add_edge(
            WorkflowNode.INTAKE_CONTEXT.value,
            WorkflowNode.MEMORY_RETRIEVER.value,
        )
        builder.add_edge(
            WorkflowNode.MEMORY_RETRIEVER.value, WorkflowNode.PLANNER.value
        )
        builder.add_conditional_edges(
            WorkflowNode.PLANNER.value,
            _route,
            {
                WorkflowNode.SUPERVISOR_ROUTER.value: WorkflowNode.SUPERVISOR_ROUTER.value,
                WorkflowNode.HUMAN_ADMIN_REVIEW.value: WorkflowNode.HUMAN_ADMIN_REVIEW.value,
            },
        )
        specialist_routes = {
            WorkflowNode.DEGREE_AUDIT_AGENT.value: WorkflowNode.DEGREE_AUDIT_AGENT.value,
            WorkflowNode.POLICY_AGENT.value: WorkflowNode.POLICY_AGENT.value,
            WorkflowNode.COURSE_AGENT.value: WorkflowNode.COURSE_AGENT.value,
            WorkflowNode.RESOLUTION_BUILDER.value: WorkflowNode.RESOLUTION_BUILDER.value,
        }
        builder.add_conditional_edges(
            WorkflowNode.SUPERVISOR_ROUTER.value, _route, specialist_routes
        )
        for specialist in (
            WorkflowNode.DEGREE_AUDIT_AGENT,
            WorkflowNode.POLICY_AGENT,
            WorkflowNode.COURSE_AGENT,
        ):
            builder.add_conditional_edges(
                specialist.value, _route, specialist_routes
            )
        builder.add_edge(
            WorkflowNode.RESOLUTION_BUILDER.value, WorkflowNode.VERIFIER.value
        )
        builder.add_conditional_edges(
            WorkflowNode.VERIFIER.value,
            _verifier_route,
            {
                WorkflowNode.ACTION_GATE.value: WorkflowNode.ACTION_GATE.value,
                WorkflowNode.PLANNER.value: WorkflowNode.PLANNER.value,
                WorkflowNode.CLARIFICATION.value: WorkflowNode.CLARIFICATION.value,
                WorkflowNode.HUMAN_ADMIN_REVIEW.value: WorkflowNode.HUMAN_ADMIN_REVIEW.value,
                WorkflowNode.MEMORY_UPDATER.value: WorkflowNode.MEMORY_UPDATER.value,
                WorkflowNode.FINAL_RESPONSE.value: WorkflowNode.FINAL_RESPONSE.value,
            },
        )
        builder.add_conditional_edges(
            WorkflowNode.CLARIFICATION.value,
            _route,
            {
                WorkflowNode.VERIFIER.value: WorkflowNode.VERIFIER.value,
                WorkflowNode.PLANNER.value: WorkflowNode.PLANNER.value,
                WorkflowNode.HUMAN_ADMIN_REVIEW.value: WorkflowNode.HUMAN_ADMIN_REVIEW.value,
            },
        )
        builder.add_conditional_edges(
            WorkflowNode.ACTION_GATE.value,
            _route,
            {
                WorkflowNode.HUMAN_APPROVAL.value: WorkflowNode.HUMAN_APPROVAL.value,
                WorkflowNode.TRANSACTION.value: WorkflowNode.TRANSACTION.value,
                WorkflowNode.HUMAN_ADMIN_REVIEW.value: WorkflowNode.HUMAN_ADMIN_REVIEW.value,
            },
        )
        builder.add_conditional_edges(
            WorkflowNode.HUMAN_APPROVAL.value,
            _route,
            {
                WorkflowNode.TRANSACTION.value: WorkflowNode.TRANSACTION.value,
                WorkflowNode.PLANNER.value: WorkflowNode.PLANNER.value,
                WorkflowNode.PAUSE_CHECKPOINT.value: WorkflowNode.PAUSE_CHECKPOINT.value,
                WorkflowNode.HUMAN_ADMIN_REVIEW.value: WorkflowNode.HUMAN_ADMIN_REVIEW.value,
            },
        )
        builder.add_edge(
            WorkflowNode.PAUSE_CHECKPOINT.value,
            WorkflowNode.HUMAN_APPROVAL.value,
        )
        builder.add_conditional_edges(
            WorkflowNode.TRANSACTION.value,
            _route,
            {
                WorkflowNode.OBSERVATION.value: WorkflowNode.OBSERVATION.value,
                WorkflowNode.HUMAN_ADMIN_REVIEW.value: WorkflowNode.HUMAN_ADMIN_REVIEW.value,
            },
        )
        builder.add_edge(WorkflowNode.OBSERVATION.value, WorkflowNode.VERIFIER.value)
        builder.add_edge(
            WorkflowNode.HUMAN_ADMIN_REVIEW.value,
            WorkflowNode.FINAL_RESPONSE.value,
        )
        builder.add_edge(WorkflowNode.MEMORY_UPDATER.value, END)
        builder.add_edge(WorkflowNode.FINAL_RESPONSE.value, END)
        compiled = builder.compile(checkpointer=selected_checkpointer)
        return cls(
            tools=tools,
            graph=compiled,
            checkpointer=selected_checkpointer,
            loop_caps=selected_caps,
        )

    def create_intake(
        self,
        *,
        request_text: str,
        problem_type: ExceptionCaseType,
        received_at: datetime,
        thread_id: str | None = None,
        case_state: CaseState = CaseState.OPEN,
        submission_ready: bool | None = None,
        unresolved_questions: list[str] | None = None,
    ) -> IntakeContext:
        """Build typed intake from a current agent-safe student read."""

        context = self.tools.context
        student_response = self.tools.academic.get_student_record(
            StudentRecordRequest(
                context=ToolCallContext(
                    session_id=self.tools.session_id,
                    request_id=f"request.{context.case_id}.intake_builder",
                    case_id=context.case_id,
                    requested_at=received_at,
                ),
                student_id=context.student_id,
            )
        )
        case_response = self.tools.policy.check_exception_eligibility(
            CasePolicyRequest(
                context=ToolCallContext(
                    session_id=self.tools.session_id,
                    request_id=f"request.{context.case_id}.intake_case_builder",
                    case_id=context.case_id,
                    requested_at=received_at,
                ),
                case_id=context.case_id,
            )
        )
        if (
            student_response.status is ToolStatus.FAILURE
            or not isinstance(student_response.data, dict)
        ):
            raise ValueError("cannot build intake without the observable student record")
        if (
            case_response.status is ToolStatus.FAILURE
            or not isinstance(case_response.data, dict)
        ):
            raise ValueError("cannot build intake without the observable exception case")

        case_problem_type = case_response.data.get("problem_type")
        if case_problem_type != problem_type.value:
            raise ValueError(
                "problem_type does not match the observable exception case"
            )

        resolved_submission_ready = submission_ready
        resolved_unresolved_questions = (
            list(unresolved_questions) if unresolved_questions is not None else []
        )
        if problem_type is ExceptionCaseType.COURSE_UNAVAILABLE:
            observed_ready = case_response.data.get("submission_ready")
            observed_questions_raw = case_response.data.get("unresolved_questions")
            if observed_ready is not None and not isinstance(observed_ready, bool):
                raise ValueError("observable submission_ready is malformed")
            if not isinstance(observed_questions_raw, list) or not all(
                isinstance(item, str) for item in observed_questions_raw
            ):
                raise ValueError("observable unresolved_questions are malformed")
            observed_questions = list(observed_questions_raw)
            if submission_ready is not None and submission_ready != observed_ready:
                raise ValueError(
                    "submission_ready does not match the observable exception case"
                )
            if (
                unresolved_questions is not None
                and list(unresolved_questions) != observed_questions
            ):
                raise ValueError(
                    "unresolved_questions do not match the observable exception case"
                )
            resolved_submission_ready = observed_ready
            resolved_unresolved_questions = observed_questions

        predicate = GoalPredicate(
            predicate_id=f"predicate.{context.case_id}.case_resolved",
            goal_kind=GoalKind.CASE_STATE_REACHED,
            target_type=StateTargetType.CASE,
            target_ids=[context.case_id],
            field_path="state",
            operator=GoalOperator.EQUALS,
            expected_value=CaseState.RESOLVED.value,
            description="The exception case reaches the resolved state.",
        )
        return IntakeContext(
            case_id=context.case_id,
            session_id=self.tools.session_id,
            thread_id=thread_id or f"thread.{context.case_id}",
            anonymous_student_id=context.student_id,
            programme_code=str(student_response.data["programme"]),
            admission_cohort=str(student_response.data["admission_cohort"]),
            request_text=request_text,
            problem_type=problem_type,
            submission_ready=resolved_submission_ready,
            unresolved_questions=resolved_unresolved_questions,
            case_state=case_state,
            goal_predicates=[predicate],
            registration_id=context.registration_id,
            audit_id=context.audit_id,
            received_at=received_at,
        )

    def start(self, intake: IntakeContext) -> dict[str, Any]:
        """Start a new checkpointed thread and run until terminal or interrupt."""

        validated, initial = self._prepare_start(intake)
        return self.graph.invoke(initial, config=self._config(validated.thread_id))

    def start_stream(self, intake: IntakeContext) -> Iterator[dict[str, Any]]:
        """Yield node updates for a new checkpointed thread.

        The stream contains only graph updates derived from agent-observable
        state. Evaluator scripts and ground truth remain behind the Stage 4
        action boundary.
        """

        validated, initial = self._prepare_start(intake)
        yield from self.graph.stream(
            initial,
            config=self._config(validated.thread_id),
            stream_mode="updates",
        )

    def _prepare_start(
        self, intake: IntakeContext
    ) -> tuple[IntakeContext, WorkflowState]:
        """Validate ownership and construct the shared start state."""

        validated = IntakeContext.model_validate(intake)
        if validated.session_id != self._session_id:
            raise ValueError("intake belongs to a different Stage 4 session")
        if validated.case_id != self._case_id:
            raise ValueError("intake belongs to a different Stage 4 case")
        if validated.anonymous_student_id != self.tools.context.student_id:
            raise ValueError("intake belongs to a different Stage 4 student")
        self._claim_thread_for_start(validated.thread_id)
        initial: WorkflowState = {
            "schema_version": "5.0",
            "thread_id": validated.thread_id,
            "session_id": validated.session_id,
            "case_id": validated.case_id,
            "start_request": {
                "request_text": validated.request_text,
                "received_at": validated.received_at.isoformat(),
            },
            "intake_context": validated.model_dump(mode="json"),
            "scenario_context": self.tools.context.model_dump(mode="json"),
            "advisory_memories": [],
            "reasoning_audit": [],
            "plan_history": [],
            "specialist_evidence": [],
            "verification_history": [],
            "action_receipts": [],
            "tool_results": {},
            "attempted_offering_state_ids": [],
            "errors": [],
            "trace": [],
            "loop_caps": self.loop_caps.model_dump(mode="json"),
            "loop_counters": LoopCounters().model_dump(mode="json"),
            "run_status": "RUNNING",
        }
        return validated, initial

    def resume(
        self,
        *,
        thread_id: str,
        payload: ApprovalResumePayload
        | ClarificationResumePayload
        | Mapping[str, Any],
    ) -> dict[str, Any]:
        """Resume exactly one persisted interrupt using the same thread id."""

        snapshot = self._require_owned_checkpoint(thread_id)
        value = self._validate_resume(snapshot, payload)
        return self.graph.invoke(
            Command(resume=value), config=self._config(thread_id)
        )

    def resume_stream(
        self,
        *,
        thread_id: str,
        payload: ApprovalResumePayload
        | ClarificationResumePayload
        | Mapping[str, Any],
    ) -> Iterator[dict[str, Any]]:
        """Yield node updates while resuming one persisted interrupt."""

        snapshot = self._require_owned_checkpoint(thread_id)
        value = self._validate_resume(snapshot, payload)
        yield from self.graph.stream(
            Command(resume=value),
            config=self._config(thread_id),
            stream_mode="updates",
        )

    def state(self, thread_id: str) -> Any:
        return self._require_owned_checkpoint(thread_id)

    def history(self, thread_id: str) -> list[Any]:
        self._require_owned_checkpoint(thread_id)
        snapshots = list(self.graph.get_state_history(self._config(thread_id)))
        if not snapshots:
            raise ValueError("no persisted checkpoint exists for this control plane")
        for snapshot in snapshots:
            # The LangGraph input checkpoint precedes channel application and
            # therefore contains only reducer defaults. Its private saver key
            # is already scoped by _config; every applied state must retain the
            # facade ownership fields.
            if snapshot.metadata.get("source") == "input":
                continue
            self._validate_checkpoint_ownership(snapshot, thread_id)
        return snapshots

    def _config(self, thread_id: str) -> dict[str, Any]:
        return {
            "configurable": {
                # This is a private saver key. The stable public thread id is
                # retained in WorkflowState and never used outside its owning
                # session and case namespace.
                "thread_id": (
                    f"{self._checkpoint_key_prefix}"
                    f"|thread:{len(thread_id)}:{thread_id}"
                ),
            },
            "recursion_limit": 100,
        }

    def _claim_thread_for_start(self, thread_id: str) -> None:
        """Permanently bind this mutable-session facade to one new thread."""

        with self._ownership_lock:
            if self._owned_thread_id is not None:
                if self._owned_thread_id == thread_id:
                    raise ValueError(
                        f"Stage 5 thread {thread_id!r} has already been started"
                    )
                raise ValueError(
                    "this Stage 5 control plane already owns external thread "
                    f"{self._owned_thread_id!r}; a mutable Stage 4 session cannot "
                    "serve a second thread"
                )
            existing = self.graph.get_state(self._config(thread_id))
            if existing.values or existing.created_at is not None:
                raise ValueError(
                    f"a persisted checkpoint already exists for Stage 5 thread "
                    f"{thread_id!r} in this session and case"
                )
            self.tools._claim_stage5_control_plane(self._owner_token, thread_id)
            # Claim before invoking. If execution fails, retaining the claim is
            # fail-closed because the mutable session may already have changed.
            self._owned_thread_id = thread_id

    def _require_owned_checkpoint(self, thread_id: str) -> Any:
        """Return a checkpoint only when this facade owns its persisted state."""

        with self._ownership_lock:
            if self._owned_thread_id is None:
                raise ValueError("this Stage 5 control plane has not started a thread")
            if thread_id != self._owned_thread_id:
                raise ValueError(
                    "thread does not belong to this Stage 5 control plane; expected "
                    f"{self._owned_thread_id!r}"
                )
            self.tools._assert_stage5_control_plane(
                self._owner_token, thread_id
            )
        snapshot = self.graph.get_state(self._config(thread_id))
        if not snapshot.values or snapshot.created_at is None:
            raise ValueError("no persisted checkpoint exists for this control plane")
        self._validate_checkpoint_ownership(snapshot, thread_id)
        return snapshot

    def _validate_checkpoint_ownership(self, snapshot: Any, thread_id: str) -> None:
        values = snapshot.values
        expected = {
            "thread_id": thread_id,
            "session_id": self._session_id,
            "case_id": self._case_id,
        }
        for field, expected_value in expected.items():
            if values.get(field) != expected_value:
                raise ValueError(
                    f"persisted checkpoint {field} does not belong to this "
                    "Stage 5 control plane"
                )
        try:
            intake = IntakeContext.model_validate(values.get("intake_context"))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "persisted checkpoint has an invalid intake owner"
            ) from exc
        if (
            intake.thread_id != thread_id
            or intake.session_id != self._session_id
            or intake.case_id != self._case_id
        ):
            raise ValueError(
                "persisted intake does not belong to this Stage 5 control plane"
            )

    def _validate_resume(
        self,
        snapshot: Any,
        payload: ApprovalResumePayload
        | ClarificationResumePayload
        | Mapping[str, Any],
    ) -> dict[str, Any]:
        """Validate the active interrupt and normalize its matching payload."""

        if len(snapshot.interrupts) != 1:
            raise ValueError("resume requires exactly one active persisted interrupt")
        interrupt_value = snapshot.interrupts[0].value
        if not isinstance(interrupt_value, Mapping):
            raise ValueError("persisted interrupt payload is invalid")
        kind = interrupt_value.get("kind")
        raw_payload = (
            payload.model_dump(mode="json")
            if isinstance(payload, (ApprovalResumePayload, ClarificationResumePayload))
            else dict(payload)
        )
        values = snapshot.values

        if kind == "CLARIFICATION":
            if snapshot.next != (WorkflowNode.CLARIFICATION.value,):
                raise ValueError("clarification checkpoint has an invalid resume node")
            if values.get("run_status") != "WAITING_FOR_CLARIFICATION":
                raise ValueError(
                    "clarification checkpoint is not waiting for a response"
                )
            pause = ClarificationPause.model_validate(
                values.get("clarification_pause")
            )
            response = ClarificationResumePayload.model_validate(raw_payload)
            expected_interrupt = {
                "kind": "CLARIFICATION",
                **pause.model_dump(mode="json"),
            }
            if dict(interrupt_value) != expected_interrupt:
                raise ValueError(
                    "clarification interrupt does not match checkpoint state"
                )
            if response.clarification_id != pause.clarification_id:
                raise ValueError("clarification response does not match the checkpoint")
            if response.impact is not pause.impact:
                raise ValueError(
                    "clarification impact does not match the verified route"
                )
            missing_answers = [
                field
                for field in pause.missing_fields
                if field not in response.answers
                or not _valid_resume_answer(field, response.answers[field])
            ]
            if missing_answers:
                raise ValueError(
                    "clarification response is missing meaningful answers for: "
                    + ", ".join(missing_answers)
                )
            return response.model_dump(mode="json")

        if kind == "APPROVAL":
            if snapshot.next != (WorkflowNode.PAUSE_CHECKPOINT.value,):
                raise ValueError("approval checkpoint has an invalid resume node")
            if values.get("run_status") != "WAITING_FOR_APPROVAL":
                raise ValueError("approval checkpoint is not waiting for a response")
            pause = ApprovalPause.model_validate(values.get("approval_pause"))
            response = ApprovalResumePayload.model_validate(raw_payload)
            expected_interrupt = {
                "kind": "APPROVAL",
                **pause.model_dump(mode="json"),
            }
            if dict(interrupt_value) != expected_interrupt:
                raise ValueError("approval interrupt does not match checkpoint state")
            if response.approval_id != pause.approval_id:
                raise ValueError("approval resume does not match the checkpoint")
            if response.expected_version != pause.approval_version:
                raise ValueError(
                    "approval resume expected_version does not match checkpoint"
                )
            return response.model_dump(mode="json")

        raise ValueError(f"unsupported persisted interrupt kind: {kind!r}")


def _route(state: WorkflowState) -> str:
    return state["route"]


def _verifier_route(state: WorkflowState) -> str | list[str]:
    if state["route"] == "done":
        return [
            WorkflowNode.MEMORY_UPDATER.value,
            WorkflowNode.FINAL_RESPONSE.value,
        ]
    return state["route"]


def _meaningful_resume_answer(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value) and any(
            _meaningful_resume_answer(item) for item in value.values()
        )
    if isinstance(value, list):
        return bool(value) and any(_meaningful_resume_answer(item) for item in value)
    if isinstance(value, bool):
        return value
    return isinstance(value, (int, float))


def _valid_resume_answer(field: str, value: Any) -> bool:
    if field == "submission_declaration":
        return value is True
    return _meaningful_resume_answer(value)


__all__ = ["Stage5ControlPlane"]
