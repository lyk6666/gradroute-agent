"""LangGraph node implementations over the Stage 4 tool boundary."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any

from langgraph.types import interrupt

from graduation_exception_agent.memory import (
    ExperienceMemoryQuery,
    ExperienceMemoryRecord,
    ExperienceMemoryStore,
    MemoryWriteResult,
)
from graduation_exception_agent.models.orchestration import (
    ActionCandidate,
    AdminHandoff,
    ApprovalPause,
    ApprovalResumePayload,
    ClarificationPause,
    ClarificationResumePayload,
    FinalOutcome,
    FinalOutcomeStatus,
    IntakeContext,
    LoopCaps,
    LoopCounters,
    PlanStep,
    ResolutionPlan,
    SpecialistEvidence,
    SpecialistKind,
    SpecialistSelection,
    TraceEvent,
    TransitionEndpoint,
    WorkflowNode,
    WorkflowState,
)
from graduation_exception_agent.models.runtime import (
    ClarificationImpact,
    ClarificationResume,
    GoalKind,
    GoalOperator,
    GoalPredicate,
    VerifierDecision,
    VerifierDecisionCode,
    VerifierPhase,
)
from graduation_exception_agent.models.tooling import (
    ActionReceipt,
    ToolCallContext,
    ToolObservation,
    ToolResponse,
    ToolStatus,
    VersionExpectation,
)
from graduation_exception_agent.models.workflow import (
    ApprovalStatus,
    ExceptionCaseType,
    ObservationCode,
    StateTargetType,
    TransactionAction,
)
from graduation_exception_agent.orchestration.decisions import DecisionProvider
from graduation_exception_agent.runtime.factory import Stage4Tools
from graduation_exception_agent.tools import (
    ApprovalRequest,
    AvailabilityCheckRequest,
    CasePolicyRequest,
    CourseDetailsRequest,
    CurrentRegistrationRequest,
    CurriculumRequest,
    DegreeAuditRequest,
    ExceptionSubmissionRequest,
    RegistrationSubmissionRequest,
    SemesterOfferingsRequest,
    StudentCourseCheckRequest,
    StudentRecordRequest,
    TimetableCheckRequest,
    WaiverSubmissionRequest,
    WorkloadCheckRequest,
)


_SPECIALIST_NODE = {
    SpecialistKind.DEGREE_AUDIT: WorkflowNode.DEGREE_AUDIT_AGENT,
    SpecialistKind.POLICY: WorkflowNode.POLICY_AGENT,
    SpecialistKind.COURSE: WorkflowNode.COURSE_AGENT,
}
_SPECIALIST_ENDPOINT = {
    SpecialistKind.DEGREE_AUDIT: TransitionEndpoint.DEGREE_AUDIT_AGENT,
    SpecialistKind.POLICY: TransitionEndpoint.POLICY_AGENT,
    SpecialistKind.COURSE: TransitionEndpoint.COURSE_AGENT,
}


class Stage5Nodes:
    """Bound node set; only agent-safe Stage 4 tools enter this closure."""

    def __init__(
        self,
        *,
        tools: Stage4Tools,
        decisions: DecisionProvider,
        memory: ExperienceMemoryStore,
    ) -> None:
        self._tools = tools
        self._decisions = decisions
        self._memory = memory

    def intake_context(self, state: WorkflowState) -> dict[str, Any]:
        intake = IntakeContext.model_validate(state["intake_context"])
        context = self._tools.context
        if (
            intake.case_id != context.case_id
            or intake.session_id != self._tools.session_id
            or intake.anonymous_student_id != context.student_id
        ):
            raise ValueError("intake identifiers do not match the Stage 4 session")

        student = self._tools.academic.get_student_record(
            StudentRecordRequest(
                context=self._read_context(state, "intake.student"),
                student_id=context.student_id,
            )
        )
        registration = self._tools.academic.get_current_registration(
            CurrentRegistrationRequest(
                context=self._read_context(state, "intake.registration"),
                registration_id=context.registration_id,
            )
        )
        case_context = self._tools.policy.check_exception_eligibility(
            CasePolicyRequest(
                context=self._read_context(state, "intake.case"),
                case_id=context.case_id,
            )
        )
        failed = [
            (label, response)
            for label, response in (
                ("student intake", student),
                ("registration intake", registration),
                ("case intake", case_context),
            )
            if response.status is ToolStatus.FAILURE
        ]
        intake_error: dict[str, Any] = {}
        errors: list[dict[str, Any]] = []
        if failed:
            labels = ", ".join(label for label, _ in failed)
            intake_error = {
                "code": "INTAKE_TOOL_FAILURE",
                "message": f"Required intake reads failed: {labels}.",
            }
            errors = [
                {
                    "error_id": f"error.{state['case_id']}.intake.{_safe_suffix(label)}",
                    "code": "INTAKE_TOOL_FAILURE",
                    "message": _tool_error_message(response, label),
                }
                for label, response in failed
            ]
        else:
            student_data = _data(student)
            case_data = _data(case_context)
            if (
                student_data.get("programme") != intake.programme_code
                or student_data.get("admission_cohort") != intake.admission_cohort
            ):
                raise ValueError(
                    "intake programme/cohort does not match the student record"
                )
            if case_data.get("problem_type") != intake.problem_type.value:
                raise ValueError(
                    "intake problem_type does not match the observable exception case"
                )
            if intake.problem_type is ExceptionCaseType.COURSE_UNAVAILABLE:
                observed_questions = case_data.get("unresolved_questions")
                if (
                    intake.submission_ready != case_data.get("submission_ready")
                    or not isinstance(observed_questions, list)
                    or intake.unresolved_questions != observed_questions
                ):
                    raise ValueError(
                        "intake readiness does not match the observable exception case"
                    )

        update: dict[str, Any] = {
            "tool_results": self._merged_results(
                state,
                {
                    "student_record": _dump(student),
                    "current_registration": _dump(registration),
                    "case_context": _dump(case_context),
                },
            ),
            "intake_error": intake_error,
            "trace": [
                self._trace(
                    state,
                    TransitionEndpoint.INTAKE,
                    "CONTEXT_READY",
                    TransitionEndpoint.MEMORY_RETRIEVER,
                )
            ],
            "run_status": "RUNNING",
        }
        if errors:
            update["errors"] = errors
        return update

    def memory_retriever(self, state: WorkflowState) -> dict[str, Any]:
        intake = IntakeContext.model_validate(state["intake_context"])
        goal_kind = intake.goal_predicates[0].goal_kind
        memory_error: Exception | None = None
        try:
            query = ExperienceMemoryQuery(
                case_type=intake.problem_type.value,
                goal_kind=goal_kind,
                limit=5,
            )
            raw_records = self._memory.retrieve(query)
            if not isinstance(raw_records, list):
                raise TypeError("memory retrieval must return a list")
            if len(raw_records) > query.limit:
                raise ValueError("memory retrieval exceeded the requested bound")
            records = [
                ExperienceMemoryRecord.model_validate(
                    item.model_dump(mode="python")
                    if isinstance(item, ExperienceMemoryRecord)
                    else item
                )
                for item in raw_records
            ]
        except Exception as exc:  # an advisory backend must never block the case
            records = []
            memory_error = exc
        update: dict[str, Any] = {
            "advisory_memories": [item.model_dump(mode="json") for item in records],
            "trace": [
                self._trace(
                    state,
                    TransitionEndpoint.MEMORY_RETRIEVER,
                    "READY",
                    TransitionEndpoint.PLANNER,
                    note=(
                        "Advisory memory was unavailable; planning continues from "
                        "current Stage 4 tools only."
                        if memory_error is not None
                        else "Advisory experience retrieved; all academic and policy "
                        "claims remain subject to current Stage 4 tool checks."
                    ),
                )
            ],
        }
        if memory_error is not None:
            update["errors"] = [
                {
                    "error_id": f"error.{state['case_id']}.memory.retrieve",
                    "code": "MEMORY_RETRIEVAL_FAILED",
                    "message": (
                        "Advisory memory retrieval failed; planning continued "
                        "from current Stage 4 evidence."
                    ),
                }
            ]
        return update

    def planner(self, state: WorkflowState) -> dict[str, Any]:
        previous = state.get("plan")
        observation = state.get("observation", {})
        is_replan = bool(previous)
        tool_retry = is_replan and bool(observation.get("retryable"))
        advanced, exceeded = self._advance(
            state, replan=is_replan, tool_retry=tool_retry
        )
        if exceeded is not None:
            return self._limit_update(
                state,
                counters=advanced,
                source=TransitionEndpoint.PLANNER,
                reason=exceeded,
            )

        if state.get("intake_error"):
            return {
                "loop_counters": advanced.model_dump(mode="json"),
                "route": WorkflowNode.HUMAN_ADMIN_REVIEW.value,
                "trace": [
                    self._trace(
                        state,
                        TransitionEndpoint.PLANNER,
                        "NO_SAFE_ROUTE",
                        TransitionEndpoint.HUMAN_ADMIN_REVIEW,
                        note=str(state["intake_error"].get("message")),
                    )
                ],
            }

        approval = state.get("approval_response", {})
        unsafe_failure = bool(observation) and not bool(observation.get("retryable"))
        if approval.get("status") == ApprovalStatus.REJECTED.value or unsafe_failure:
            return {
                "loop_counters": advanced.model_dump(mode="json"),
                "route": WorkflowNode.HUMAN_ADMIN_REVIEW.value,
                "trace": [
                    self._trace(
                        state,
                        TransitionEndpoint.PLANNER,
                        "NO_SAFE_ROUTE",
                        TransitionEndpoint.HUMAN_ADMIN_REVIEW,
                    )
                ],
            }

        version = 1
        if previous:
            version = int(previous["version"]) + 1
        intake = IntakeContext.model_validate(state["intake_context"])
        target_course = str(self._tools.context.initial_state["target_course"])
        specialists = self._decisions.select_specialists(state)
        steps = [
            PlanStep(
                step_id=f"step.{state['case_id']}.{version}.{index}",
                ordinal=index,
                purpose=_plan_step_purpose(
                    specialist, intake.problem_type, target_course
                ),
                specialist=specialist,
                depends_on=(
                    []
                    if index == 1
                    else [f"step.{state['case_id']}.{version}.{index - 1}"]
                ),
            )
            for index, specialist in enumerate(specialists, start=1)
        ]
        plan = ResolutionPlan(
            plan_id=f"plan.{state['case_id']}.{version}",
            version=version,
            goal_predicates=[
                GoalPredicate.model_validate(item)
                for item in IntakeContext.model_validate(
                    state["intake_context"]
                ).goal_predicates
            ],
            steps=steps,
            rationale=_plan_rationale(
                intake.problem_type,
                target_course,
                is_replan=is_replan,
                observation=observation,
            ),
            created_at=self._time(state),
        )
        selection = SpecialistSelection(
            selection_id=f"selection.{state['case_id']}.{version}",
            plan_id=plan.plan_id,
            required_specialists=list(specialists),
            rationale=(
                f"These checks are the ones needed to answer the student's "
                f"{target_course} request safely."
            ),
        )
        plan_dump = plan.model_dump(mode="json")
        return {
            "loop_counters": advanced.model_dump(mode="json"),
            "reasoning_audit": self._reasoning_audit(state),
            "plan": plan_dump,
            "plan_history": [*state.get("plan_history", []), plan_dump],
            "specialist_selection": selection.model_dump(mode="json"),
            "pending_specialists": [item.value for item in specialists],
            "route": WorkflowNode.SUPERVISOR_ROUTER.value,
            "trace": [
                self._trace(
                    state,
                    TransitionEndpoint.PLANNER,
                    "PLAN_READY",
                    TransitionEndpoint.SUPERVISOR_ROUTER,
                )
            ],
        }

    def supervisor_router(self, state: WorkflowState) -> dict[str, Any]:
        route = self._next_specialist(state)
        destination = self._endpoint_for_route(route)
        return {
            "route": route,
            "trace": [
                self._trace(
                    state,
                    TransitionEndpoint.SUPERVISOR_ROUTER,
                    "SPECIALIST_SELECTED",
                    destination,
                )
            ],
        }

    def degree_audit_agent(self, state: WorkflowState) -> dict[str, Any]:
        context = self._tools.context
        audit = self._tools.academic.run_degree_audit(
            DegreeAuditRequest(
                context=self._read_context(state, "degree.audit"),
                audit_id=context.audit_id,
            )
        )
        curriculum = self._tools.academic.get_curriculum(
            CurriculumRequest(
                context=self._read_context(state, "degree.curriculum"),
                curriculum_id=context.curriculum_id,
            )
        )
        return self._specialist_update(
            state,
            specialist=SpecialistKind.DEGREE_AUDIT,
            results={
                "degree_audit": audit,
                "curriculum": curriculum,
            },
        )

    def policy_agent(self, state: WorkflowState) -> dict[str, Any]:
        case_id = self._tools.context.case_id
        eligibility = self._tools.policy.check_exception_eligibility(
            CasePolicyRequest(
                context=self._read_context(state, "policy.eligibility"),
                case_id=case_id,
            )
        )
        requirement = self._tools.policy.get_approval_requirement(
            CasePolicyRequest(
                context=self._read_context(state, "policy.approval"),
                case_id=case_id,
            )
        )
        documents = self._tools.policy.get_required_documents(
            CasePolicyRequest(
                context=self._read_context(state, "policy.documents"),
                case_id=case_id,
            )
        )
        update = self._specialist_update(
            state,
            specialist=SpecialistKind.POLICY,
            results={
                "exception_eligibility": eligibility,
                "approval_requirement": requirement,
                "required_documents": documents,
            },
        )
        update["approval_requirement"] = (
            _data(requirement)
            if requirement.status is not ToolStatus.FAILURE
            else {}
        )
        return update

    def course_agent(self, state: WorkflowState) -> dict[str, Any]:
        context = self._tools.context
        initial = context.initial_state
        course_code = str(initial["target_course"])
        results: dict[str, ToolResponse] = {}
        results["course_details"] = self._tools.course.get_course_details(
            CourseDetailsRequest(
                context=self._read_context(state, "course.details"),
                course_code=course_code,
            )
        )
        results["prerequisite"] = self._tools.course.check_prerequisite(
            StudentCourseCheckRequest(
                context=self._read_context(state, "course.prerequisite"),
                course_code=course_code,
                student_id=context.student_id,
            )
        )
        results["exclusion"] = self._tools.course.check_exclusion(
            StudentCourseCheckRequest(
                context=self._read_context(state, "course.exclusion"),
                course_code=course_code,
                student_id=context.student_id,
            )
        )
        results["semester_offerings"] = self._tools.course.get_semester_offerings(
            SemesterOfferingsRequest(
                context=self._read_context(state, "course.offerings"),
                course_code=course_code,
            )
        )
        results["workload"] = self._tools.course.check_workload(
            WorkloadCheckRequest(
                context=self._read_context(state, "course.workload"),
                course_code=course_code,
                registration_id=context.registration_id,
            )
        )
        for state_id in context.offering_state_ids:
            suffix = _safe_suffix(state_id)
            results[f"timetable.{state_id}"] = self._tools.course.check_timetable(
                TimetableCheckRequest(
                    context=self._read_context(state, f"course.timetable.{suffix}"),
                    offering_state_id=state_id,
                    registration_id=context.registration_id,
                )
            )
            results[f"availability.{state_id}"] = (
                self._tools.course.check_availability(
                    AvailabilityCheckRequest(
                        context=self._read_context(
                            state, f"course.availability.{suffix}"
                        ),
                        offering_state_id=state_id,
                    )
                )
            )
        return self._specialist_update(
            state,
            specialist=SpecialistKind.COURSE,
            results=results,
        )

    def _specialist_update(
        self,
        state: WorkflowState,
        *,
        specialist: SpecialistKind,
        results: dict[str, ToolResponse],
    ) -> dict[str, Any]:
        plan = ResolutionPlan.model_validate(state["plan"])
        evidence = self._evidence(plan, specialist, list(results.values()))
        pending = list(state.get("pending_specialists", []))
        if specialist.value in pending:
            pending.remove(specialist.value)
        route = self._next_specialist({**state, "pending_specialists": pending})
        return {
            "tool_results": self._merged_results(
                state, {key: _dump(value) for key, value in results.items()}
            ),
            "specialist_evidence": [evidence.model_dump(mode="json")],
            "pending_specialists": pending,
            "route": route,
            "trace": [
                self._trace(
                    state,
                    _SPECIALIST_ENDPOINT[specialist],
                    "EVIDENCE_READY",
                    self._endpoint_for_route(route),
                )
            ],
        }

    def _evidence(
        self,
        plan: ResolutionPlan,
        specialist: SpecialistKind,
        responses: list[ToolResponse],
    ) -> SpecialistEvidence:
        source_ids: set[str] = set()
        rule_ids: set[str] = set()
        request_ids: set[str] = set()
        versions: dict[str, int] = {}
        completeness_known = True
        for response in responses:
            request_ids.add(response.request_id)
            versions.update(response.entity_versions)
            if response.status is ToolStatus.FAILURE:
                completeness_known = False
            for provenance in response.provenance:
                source_ids.update(provenance.source_ids)
                rule_ids.update(provenance.rule_ids)
                completeness_known = completeness_known and provenance.completeness.value not in {
                    "UNKNOWN",
                    "UNAVAILABLE",
                }
        return SpecialistEvidence(
            evidence_id=f"evidence.{plan.plan_id}.{specialist.value.lower()}",
            specialist=specialist,
            summary=_evidence_summary(
                specialist,
                responses,
                str(self._tools.context.initial_state["target_course"]),
            ),
            source_ids=sorted(source_ids),
            rule_ids=sorted(rule_ids),
            tool_request_ids=sorted(request_ids),
            entity_versions=versions,
            completeness_known=completeness_known,
        )

    def _next_specialist(self, state: WorkflowState) -> str:
        pending = state.get("pending_specialists", [])
        if not pending:
            return WorkflowNode.RESOLUTION_BUILDER.value
        return _SPECIALIST_NODE[SpecialistKind(pending[0])].value

    @staticmethod
    def _endpoint_for_route(route: str) -> TransitionEndpoint:
        mapping = {
            WorkflowNode.DEGREE_AUDIT_AGENT.value: TransitionEndpoint.DEGREE_AUDIT_AGENT,
            WorkflowNode.POLICY_AGENT.value: TransitionEndpoint.POLICY_AGENT,
            WorkflowNode.COURSE_AGENT.value: TransitionEndpoint.COURSE_AGENT,
            WorkflowNode.RESOLUTION_BUILDER.value: TransitionEndpoint.RESOLUTION_BUILDER,
        }
        return mapping[route]

    def resolution_builder(self, state: WorkflowState) -> dict[str, Any]:
        """Build a candidate or send a typed failure through the verifier.

        The frozen topology joins specialists at the verifier.  A missing safe
        index, approval reference, or other candidate prerequisite therefore
        becomes an explicit verifier escalation instead of an uncaught graph
        exception or a speculative write.
        """

        try:
            return self._build_resolution(state)
        except (IndexError, KeyError, ValueError) as exc:
            message = str(exc) or "No grounded candidate action is available."
            return {
                "action_candidate": {},
                "resolution_error": {
                    "code": "NO_SAFE_CANDIDATE",
                    "message": message,
                },
                "verification_phase": VerifierPhase.PRE_ACTION.value,
                "route": WorkflowNode.VERIFIER.value,
                "errors": [
                    {
                        "error_id": f"error.{state['case_id']}.resolution",
                        "code": "NO_SAFE_CANDIDATE",
                        "message": message,
                    }
                ],
                "trace": [
                    self._trace(
                        state,
                        TransitionEndpoint.RESOLUTION_BUILDER,
                        "NO_SAFE_CANDIDATE",
                        TransitionEndpoint.VERIFIER_PRE_ACTION,
                    )
                ],
            }

    def _build_resolution(self, state: WorkflowState) -> dict[str, Any]:
        plan = ResolutionPlan.model_validate(state["plan"])
        intake = IntakeContext.model_validate(state["intake_context"])
        initial = self._tools.context.initial_state
        course_code = str(initial["target_course"])
        requirement = state.get("approval_requirement", {})
        approval_required = bool(requirement.get("required"))
        approval_id = (
            str(requirement["approval_id"]) if approval_required else None
        )
        action: TransactionAction
        parameters: dict[str, Any]
        expected_versions: list[VersionExpectation] = []

        if intake.problem_type in {
            ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
            ExceptionCaseType.TIMETABLE_CONFLICT,
            ExceptionCaseType.WORKLOAD_OVERLOAD,
        }:
            state_id = self._select_registration_state(state)
            action = TransactionAction.SUBMIT_REGISTRATION
            parameters = {"offering_state_id": state_id}
            if state.get("observation", {}).get("retryable"):
                parameters["retry"] = True
            if approval_required:
                parameters.update(
                    {"approval_id": approval_id, "course_code": course_code}
                )
            expected_versions.append(
                self._offering_version(state, state_id)
            )
        elif intake.problem_type is ExceptionCaseType.PREREQUISITE_WAIVER:
            if approval_id is None:
                raise ValueError("a prerequisite-waiver candidate requires approval")
            action = TransactionAction.SUBMIT_WAIVER
            parameters = {
                "approval_id": approval_id,
                "course_code": course_code,
            }
        elif intake.problem_type is ExceptionCaseType.CROSS_PROGRAMME:
            if approval_id is None:
                raise ValueError("a cross-programme candidate requires approval")
            audit_data = _result_data(state, "degree_audit")
            student_data = _result_data(state, "student_record")
            graduation_path_id = (
                audit_data.get("graduation_path_id")
                or student_data.get("graduation_path_id")
            )
            if not graduation_path_id:
                raise ValueError("cross-programme candidate lacks a graduation path")
            action = TransactionAction.SUBMIT_EXCEPTION
            parameters = {
                "approval_id": approval_id,
                "course_code": course_code,
                "curriculum_id": self._tools.context.curriculum_id,
                "graduation_path_id": graduation_path_id,
            }
        elif intake.problem_type is ExceptionCaseType.COURSE_UNAVAILABLE:
            action = TransactionAction.SUBMIT_EXCEPTION
            parameters = {}
            if intake.submission_ready:
                state_id = self._tools.context.offering_state_ids[0]
                parameters["offering_state_id"] = state_id
                expected_versions.append(self._offering_version(state, state_id))
        else:
            # The Stage 3 graduation-clearance simulation intentionally accepts
            # an empty submission payload.  Academic facts stay in evidence and
            # are not smuggled into a mismatched write contract.
            action = TransactionAction.SUBMIT_EXCEPTION
            parameters = {}

        if approval_required and approval_id is not None:
            expected_versions.append(
                VersionExpectation(
                    target_type=StateTargetType.APPROVAL,
                    target_id=approval_id,
                    expected_version=int(requirement["version"]),
                )
            )
        predicates = self._goal_predicates(
            state,
            action=action,
            course_code=course_code,
        )
        evidence_ids = [
            str(item["evidence_id"])
            for item in state.get("specialist_evidence", [])
            if str(item["evidence_id"]).startswith(f"evidence.{plan.plan_id}.")
        ]
        candidate = ActionCandidate(
            candidate_id=f"candidate.{state['case_id']}.{plan.version}",
            plan_id=plan.plan_id,
            action=action,
            parameters=parameters,
            expected_versions=expected_versions,
            goal_predicates=predicates,
            evidence_ids=evidence_ids,
            requires_approval=approval_required,
            approval_id=approval_id,
            idempotency_key=f"idempotency.{state['case_id']}.action.{plan.version}",
            rationale=_candidate_rationale(
                action,
                course_code,
                parameters,
                approval_required=approval_required,
                retrying=bool(state.get("observation", {}).get("retryable")),
            ),
        )
        return {
            "action_candidate": candidate.model_dump(mode="json"),
            "resolution_error": {},
            "verification_phase": VerifierPhase.PRE_ACTION.value,
            "route": WorkflowNode.VERIFIER.value,
            "trace": [
                self._trace(
                    state,
                    TransitionEndpoint.RESOLUTION_BUILDER,
                    "CANDIDATES_BUILT",
                    TransitionEndpoint.VERIFIER_PRE_ACTION,
                )
            ],
        }

    def verifier(self, state: WorkflowState) -> dict[str, Any]:
        phase = VerifierPhase(state["verification_phase"])
        advanced, exceeded = self._advance(state)
        source = (
            TransitionEndpoint.VERIFIER_PRE_ACTION
            if phase is VerifierPhase.PRE_ACTION
            else TransitionEndpoint.VERIFIER_POST_ACTION
        )
        if exceeded is not None:
            return self._limit_update(
                state,
                counters=advanced,
                source=source,
                reason=exceeded,
                phase=phase,
            )
        if phase is VerifierPhase.PRE_ACTION:
            assessment = self._decisions.assess_pre_action(state)
            candidate = (
                ActionCandidate.model_validate(state["action_candidate"])
                if state.get("action_candidate")
                else None
            )
            decision = VerifierDecision(
                decision_id=(
                    f"decision.{state['case_id']}.pre."
                    f"{len(state.get('verification_history', [])) + 1}"
                ),
                phase=phase,
                decision=assessment.decision,
                reason=assessment.reason,
                candidate_path_id=(
                    None if candidate is None else candidate.candidate_id
                ),
                violation_codes=list(assessment.violation_codes),
                checked_predicate_ids=[
                    item.predicate_id
                    for item in ([] if candidate is None else candidate.goal_predicates)
                ],
                entity_versions={
                    item.target_id: item.expected_version
                    for item in ([] if candidate is None else candidate.expected_versions)
                },
                decided_at=self._time(state),
            )
            destination = {
                VerifierDecisionCode.VALID: TransitionEndpoint.ACTION_GATE,
                VerifierDecisionCode.REPLAN: TransitionEndpoint.PLANNER,
                VerifierDecisionCode.CLARIFY: TransitionEndpoint.CLARIFICATION,
                VerifierDecisionCode.ESCALATE: TransitionEndpoint.HUMAN_ADMIN_REVIEW,
            }[assessment.decision]
            route = {
                VerifierDecisionCode.VALID: WorkflowNode.ACTION_GATE.value,
                VerifierDecisionCode.REPLAN: WorkflowNode.PLANNER.value,
                VerifierDecisionCode.CLARIFY: WorkflowNode.CLARIFICATION.value,
                VerifierDecisionCode.ESCALATE: WorkflowNode.HUMAN_ADMIN_REVIEW.value,
            }[assessment.decision]
            update: dict[str, Any] = {
                "loop_counters": advanced.model_dump(mode="json"),
                "reasoning_audit": self._reasoning_audit(state),
                "verifier_decision": decision.model_dump(mode="json"),
                "verification_history": [
                    *state.get("verification_history", []),
                    decision.model_dump(mode="json"),
                ],
                "route": route,
                "trace": [
                    self._trace(
                        state,
                        source,
                        assessment.decision.value,
                        destination,
                        phase=phase,
                    )
                ],
            }
            if assessment.decision is VerifierDecisionCode.CLARIFY:
                missing = list(assessment.missing_fields)
                resume = (
                    ClarificationResume.PLANNER
                    if assessment.clarification_impact
                    is ClarificationImpact.MATERIAL_CHANGE
                    else ClarificationResume.PRE_ACTION_VERIFIER
                )
                pause = ClarificationPause(
                    clarification_id=(
                        f"clarification.{state['case_id']}."
                        f"{state.get('plan', {}).get('plan_id', 'unplanned')}"
                    ),
                    case_id=state["case_id"],
                    question=(
                        "Please provide the missing facts required to continue this "
                        "graduation or registration exception safely."
                    ),
                    missing_fields=list(missing),
                    impact=assessment.clarification_impact,
                    resume_target=resume,
                    requested_at=self._time(state),
                )
                update["clarification_pause"] = pause.model_dump(mode="json")
                update["run_status"] = "WAITING_FOR_CLARIFICATION"
            return update

        candidate = ActionCandidate.model_validate(state["action_candidate"])
        bound_predicates = self._bound_goal_predicates(state, candidate)
        evaluation = self._tools.evaluate_goal(
            goal_kind=bound_predicates[0].goal_kind,
            predicates=bound_predicates,
            evaluation_id=(
                f"evaluation.{state['case_id']}."
                f"{len(state.get('action_receipts', []))}"
            ),
        )
        code = (
            VerifierDecisionCode.DONE
            if evaluation.complete
            else VerifierDecisionCode.CONTINUE_FAILURE
        )
        violations = [] if evaluation.complete else ["GOAL_POSTCONDITION_UNSATISFIED"]
        decision = VerifierDecision(
            decision_id=(
                f"decision.{state['case_id']}.post."
                f"{len(state.get('verification_history', [])) + 1}"
            ),
            phase=phase,
            decision=code,
            reason=(
                "Every required goal predicate is satisfied in current runtime state."
                if evaluation.complete
                else "The observable action result did not satisfy the goal predicates."
            ),
            candidate_path_id=candidate.candidate_id,
            violation_codes=violations,
            checked_predicate_ids=[item.predicate_id for item in candidate.goal_predicates],
            entity_versions={
                str(key): int(value)
                for key, value in state.get("observation", {})
                .get("state_versions", {})
                .items()
            },
            decided_at=self._time(state),
        )
        base = {
            "loop_counters": advanced.model_dump(mode="json"),
            "goal_evaluation": evaluation.model_dump(mode="json"),
            "verifier_decision": decision.model_dump(mode="json"),
            "verification_history": [
                *state.get("verification_history", []),
                decision.model_dump(mode="json"),
            ],
        }
        if evaluation.complete:
            base.update(
                {
                    "route": "done",
                    "run_status": "COMPLETED",
                    "trace": [
                        self._trace(
                            state,
                            source,
                            "DONE",
                            TransitionEndpoint.FINAL_RESPONSE,
                            phase=phase,
                        ),
                        self._trace(
                            state,
                            source,
                            "DONE",
                            TransitionEndpoint.MEMORY_UPDATER,
                            phase=phase,
                            sequence_offset=1,
                        ),
                    ],
                }
            )
        else:
            base.update(
                {
                    "route": WorkflowNode.PLANNER.value,
                    "trace": [
                        self._trace(
                            state,
                            source,
                            "CONTINUE_FAILURE",
                            TransitionEndpoint.PLANNER,
                            phase=phase,
                        )
                    ],
                }
            )
        return base

    def clarification(self, state: WorkflowState) -> dict[str, Any]:
        pause = ClarificationPause.model_validate(state["clarification_pause"])
        raw = interrupt(
            {
                "kind": "CLARIFICATION",
                **pause.model_dump(mode="json"),
            }
        )
        response = ClarificationResumePayload.model_validate(raw)
        if response.clarification_id != pause.clarification_id:
            raise ValueError("clarification response does not match the checkpoint")
        if response.impact is not pause.impact:
            raise ValueError("clarification impact does not match the verified route")
        missing_answers = [
            field
            for field in pause.missing_fields
            if field not in response.answers
            or not _valid_clarification_answer(field, response.answers[field])
        ]
        if missing_answers:
            raise ValueError(
                "clarification response is missing meaningful answers for: "
                + ", ".join(missing_answers)
            )
        advanced, exceeded = self._advance(state, replan=False)
        if exceeded is not None:
            return self._limit_update(
                state,
                counters=advanced,
                source=TransitionEndpoint.CLARIFICATION,
                reason=exceeded,
            )
        small = pause.impact is ClarificationImpact.SMALL_CHANGE
        route = WorkflowNode.VERIFIER.value if small else WorkflowNode.PLANNER.value
        destination = (
            TransitionEndpoint.VERIFIER_PRE_ACTION
            if small
            else TransitionEndpoint.PLANNER
        )
        intake = IntakeContext.model_validate(state["intake_context"])
        intake_update = intake.model_copy(
            update={
                "submission_ready": True if small else intake.submission_ready,
                "unresolved_questions": [],
            }
        )
        return {
            "loop_counters": advanced.model_dump(mode="json"),
            "intake_context": intake_update.model_dump(mode="json"),
            "clarification_response": response.model_dump(mode="json"),
            "route": route,
            "run_status": "RUNNING",
            "trace": [
                self._trace(
                    state,
                    TransitionEndpoint.CLARIFICATION,
                    "SMALL_CHANGE" if small else "MATERIAL_CHANGE",
                    destination,
                )
            ],
        }

    def action_gate(self, state: WorkflowState) -> dict[str, Any]:
        advanced, exceeded = self._advance(state)
        if exceeded is not None:
            return self._limit_update(
                state,
                counters=advanced,
                source=TransitionEndpoint.ACTION_GATE,
                reason=exceeded,
            )
        decision = VerifierDecision.model_validate(state["verifier_decision"])
        if (
            decision.phase is not VerifierPhase.PRE_ACTION
            or decision.decision is not VerifierDecisionCode.VALID
        ):
            raise ValueError("the action gate requires a PRE_ACTION VALID decision")
        candidate = ActionCandidate.model_validate(state["action_candidate"])
        requirement = state.get("approval_requirement", {})
        expected_versions = {
            item.target_id: item.expected_version
            for item in candidate.expected_versions
        }
        gate_mismatch = (
            decision.candidate_path_id != candidate.candidate_id
            or decision.entity_versions != expected_versions
            or bool(requirement.get("required")) != candidate.requires_approval
            or (
                candidate.requires_approval
                and requirement.get("approval_id") != candidate.approval_id
            )
        )
        if gate_mismatch:
            return {
                "loop_counters": advanced.model_dump(mode="json"),
                "route": WorkflowNode.HUMAN_ADMIN_REVIEW.value,
                "trace": [
                    self._trace(
                        state,
                        TransitionEndpoint.ACTION_GATE,
                        "VERIFICATION_MISMATCH",
                        TransitionEndpoint.HUMAN_ADMIN_REVIEW,
                    )
                ],
            }
        approval = candidate.requires_approval
        return {
            "loop_counters": advanced.model_dump(mode="json"),
            "route": (
                WorkflowNode.HUMAN_APPROVAL.value
                if approval
                else WorkflowNode.TRANSACTION.value
            ),
            "trace": [
                self._trace(
                    state,
                    TransitionEndpoint.ACTION_GATE,
                    "APPROVAL_REQUIRED" if approval else "NO_APPROVAL",
                    (
                        TransitionEndpoint.HUMAN_APPROVAL
                        if approval
                        else TransitionEndpoint.TRANSACTION
                    ),
                )
            ],
        }

    def human_approval(self, state: WorkflowState) -> dict[str, Any]:
        advanced, exceeded = self._advance(state)
        if exceeded is not None:
            return self._limit_update(
                state,
                counters=advanced,
                source=TransitionEndpoint.HUMAN_APPROVAL,
                reason=exceeded,
            )
        candidate = ActionCandidate.model_validate(state["action_candidate"])
        if not candidate.requires_approval or candidate.approval_id is None:
            raise ValueError("human_approval requires an approval-bound candidate")

        requirement_response = self._tools.policy.get_approval_requirement(
            CasePolicyRequest(
                context=self._read_context(state, "approval.requirement.current"),
                case_id=state["case_id"],
            )
        )
        if requirement_response.status is ToolStatus.FAILURE:
            return self._tool_failure_update(
                state,
                response=requirement_response,
                source=TransitionEndpoint.HUMAN_APPROVAL,
                label="approval requirement",
                counters=advanced,
                result_updates={
                    "approval_requirement.current": _dump(requirement_response)
                },
            )
        requirement = _data(requirement_response)
        existing = next(
            (
                item
                for item in state.get("action_receipts", [])
                if item.get("action") == TransactionAction.REQUEST_APPROVAL.value
                and item.get("case_id") == state["case_id"]
            ),
            None,
        )
        new_receipts: list[dict[str, Any]] = []
        result_updates: dict[str, dict[str, Any]] = {
            "approval_requirement.current": _dump(requirement_response)
        }
        if existing is None:
            original_version = int(requirement["version"])
            write_context = ToolCallContext(
                session_id=self._tools.session_id,
                request_id=f"request.{state['case_id']}.approval",
                case_id=state["case_id"],
                requested_at=self._time(state),
                idempotency_key=f"idempotency.{state['case_id']}.approval",
                expected_versions=[
                    VersionExpectation(
                        target_type=StateTargetType.APPROVAL,
                        target_id=candidate.approval_id,
                        expected_version=original_version,
                    )
                ],
            )
            approval_response = self._tools.actions.request_approval(
                ApprovalRequest(
                    context=write_context,
                    approval_id=candidate.approval_id,
                )
            )
            result_updates["approval_request"] = _dump(approval_response)
            if isinstance(approval_response.data, dict) and approval_response.data.get(
                "receipt_id"
            ):
                new_receipts.append(dict(approval_response.data))
            if approval_response.status is ToolStatus.FAILURE and not new_receipts:
                return self._tool_failure_update(
                    state,
                    response=approval_response,
                    source=TransitionEndpoint.HUMAN_APPROVAL,
                    label="approval request",
                    counters=advanced,
                    result_updates=result_updates,
                    receipts=new_receipts,
                )
            requirement_response = self._tools.policy.get_approval_requirement(
                CasePolicyRequest(
                    context=self._read_context(state, "approval.requirement.observed"),
                    case_id=state["case_id"],
                )
            )
            if requirement_response.status is ToolStatus.FAILURE:
                result_updates["approval_requirement.observed"] = _dump(
                    requirement_response
                )
                return self._tool_failure_update(
                    state,
                    response=requirement_response,
                    source=TransitionEndpoint.HUMAN_APPROVAL,
                    label="observed approval",
                    counters=advanced,
                    result_updates=result_updates,
                    receipts=new_receipts,
                )
            requirement = _data(requirement_response)
            result_updates["approval_requirement.observed"] = _dump(
                requirement_response
            )

        visible = requirement.get("observable_status")
        status = ApprovalStatus(visible or ApprovalStatus.PENDING.value)
        update: dict[str, Any] = {
            "loop_counters": advanced.model_dump(mode="json"),
            "approval_requirement": requirement,
            "approval_response": {
                "approval_id": candidate.approval_id,
                "status": status.value,
                "version": int(requirement["version"]),
                "decision_reason": requirement.get("decision_reason"),
            },
            "tool_results": self._merged_results(state, result_updates),
        }
        if new_receipts:
            update["action_receipts"] = new_receipts

        if status is ApprovalStatus.APPROVED:
            candidate = self._with_current_approval_version(
                candidate, int(requirement["version"])
            )
            update.update(
                {
                    "action_candidate": candidate.model_dump(mode="json"),
                    "route": WorkflowNode.TRANSACTION.value,
                    "run_status": "RUNNING",
                    "trace": [
                        self._trace(
                            state,
                            TransitionEndpoint.HUMAN_APPROVAL,
                            "APPROVED",
                            TransitionEndpoint.TRANSACTION,
                        )
                    ],
                }
            )
            return update
        if status is ApprovalStatus.REJECTED:
            update.update(
                {
                    "route": WorkflowNode.PLANNER.value,
                    "trace": [
                        self._trace(
                            state,
                            TransitionEndpoint.HUMAN_APPROVAL,
                            "REJECTED",
                            TransitionEndpoint.PLANNER,
                        )
                    ],
                }
            )
            return update

        pause = ApprovalPause(
            approval_id=candidate.approval_id,
            case_id=state["case_id"],
            approval_version=int(requirement["version"]),
            approver_role=str(requirement["approver_role"]),
            requested_action=candidate.action,
            requested_at=self._time(state),
        )
        update.update(
            {
                "approval_pause": pause.model_dump(mode="json"),
                "route": WorkflowNode.PAUSE_CHECKPOINT.value,
                "run_status": "WAITING_FOR_APPROVAL",
                "trace": [
                    self._trace(
                        state,
                        TransitionEndpoint.HUMAN_APPROVAL,
                        "PENDING",
                        TransitionEndpoint.PAUSE_CHECKPOINT,
                    )
                ],
            }
        )
        return update

    def _reasoning_audit(self, state: WorkflowState) -> list[dict[str, Any]]:
        """Copy only the bounded typed audit surface exposed by Stage 6."""

        raw = getattr(self._decisions, "audit_log", None)
        if raw is None:
            return list(state.get("reasoning_audit", []))
        items = raw if isinstance(raw, tuple) else tuple(raw)
        normalized: list[dict[str, Any]] = []
        for item in items:
            payload = (
                item.model_dump(mode="json")
                if hasattr(item, "model_dump")
                else item
            )
            if not isinstance(payload, dict):
                raise ValueError("reasoning audit items must be typed objects")
            normalized.append(
                {
                    "sequence": int(payload["sequence"]),
                    "task": str(payload["task"]),
                    "status": str(payload["status"]),
                    "model_id": (
                        str(payload["model_id"])
                        if payload.get("model_id") is not None
                        else None
                    ),
                    "applied": bool(payload["applied"]),
                    "safety_rule": str(payload["safety_rule"]),
                    "usage": (
                        dict(payload["usage"])
                        if isinstance(payload.get("usage"), dict)
                        else None
                    ),
                }
            )
        return normalized

    def pause_checkpoint(self, state: WorkflowState) -> dict[str, Any]:
        pause = ApprovalPause.model_validate(state["approval_pause"])
        raw = interrupt({"kind": "APPROVAL", **pause.model_dump(mode="json")})
        response = ApprovalResumePayload.model_validate(raw)
        if response.approval_id != pause.approval_id:
            raise ValueError("approval resume does not match the checkpoint")
        if response.expected_version != pause.approval_version:
            raise ValueError("approval resume expected_version does not match checkpoint")
        return {
            "approval_response": response.model_dump(mode="json"),
            "route": WorkflowNode.HUMAN_APPROVAL.value,
            "run_status": "RUNNING",
            "trace": [
                self._trace(
                    state,
                    TransitionEndpoint.PAUSE_CHECKPOINT,
                    "APPROVAL_OBSERVED",
                    TransitionEndpoint.HUMAN_APPROVAL,
                )
            ],
        }

    def transaction(self, state: WorkflowState) -> dict[str, Any]:
        advanced, exceeded = self._advance(state)
        if exceeded is not None:
            return self._limit_update(
                state,
                counters=advanced,
                source=TransitionEndpoint.TRANSACTION,
                reason=exceeded,
            )
        candidate = ActionCandidate.model_validate(state["action_candidate"])
        context = ToolCallContext(
            session_id=self._tools.session_id,
            request_id=f"request.{candidate.candidate_id}",
            case_id=state["case_id"],
            requested_at=self._time(state),
            idempotency_key=candidate.idempotency_key,
            expected_versions=candidate.expected_versions,
        )
        parameters = dict(candidate.parameters)
        try:
            if candidate.action is TransactionAction.SUBMIT_REGISTRATION:
                response = self._tools.actions.submit_registration(
                    RegistrationSubmissionRequest(context=context, **parameters)
                )
            elif candidate.action is TransactionAction.SUBMIT_WAIVER:
                response = self._tools.actions.submit_waiver(
                    WaiverSubmissionRequest(context=context, **parameters)
                )
            elif candidate.action is TransactionAction.SUBMIT_EXCEPTION:
                response = self._tools.actions.submit_exception(
                    ExceptionSubmissionRequest(context=context, **parameters)
                )
            else:
                raise ValueError("REQUEST_APPROVAL is owned by human_approval")
        except Exception:
            message = (
                "The transaction tool raised an unexpected error; no further "
                "action was attempted."
            )
            return {
                "loop_counters": advanced.model_dump(mode="json"),
                "route": WorkflowNode.HUMAN_ADMIN_REVIEW.value,
                "errors": [
                    {
                        "error_id": f"error.{state['case_id']}.transaction",
                        "code": "TRANSACTION_TOOL_FAILURE",
                        "message": message,
                    }
                ],
                "trace": [
                    self._trace(
                        state,
                        TransitionEndpoint.TRANSACTION,
                        "TOOL_FAILURE",
                        TransitionEndpoint.HUMAN_ADMIN_REVIEW,
                    )
                ],
            }
        receipt = dict(response.data) if isinstance(response.data, dict) else None
        attempted = list(state.get("attempted_offering_state_ids", []))
        state_id = parameters.get("offering_state_id")
        if isinstance(state_id, str) and state_id not in attempted:
            attempted.append(state_id)
        update: dict[str, Any] = {
            "loop_counters": advanced.model_dump(mode="json"),
            "tool_results": self._merged_results(
                state, {"transaction": _dump(response)}
            ),
            "attempted_offering_state_ids": attempted,
            "route": WorkflowNode.OBSERVATION.value,
            "trace": [
                self._trace(
                    state,
                    TransitionEndpoint.TRANSACTION,
                    "RESULT",
                    TransitionEndpoint.OBSERVATION,
                )
            ],
        }
        if receipt is not None and receipt.get("receipt_id"):
            update["action_receipts"] = [receipt]
        return update

    def observation(self, state: WorkflowState) -> dict[str, Any]:
        response = ToolResponse.model_validate(state["tool_results"]["transaction"])
        if isinstance(response.data, dict) and isinstance(
            response.data.get("observation"), dict
        ):
            observation = ToolObservation.model_validate(response.data["observation"])
        else:
            observation = self._observation_from_error(state, response)
        return {
            "observation": observation.model_dump(mode="json"),
            "verification_phase": VerifierPhase.POST_ACTION.value,
            "route": WorkflowNode.VERIFIER.value,
            "trace": [
                self._trace(
                    state,
                    TransitionEndpoint.OBSERVATION,
                    "NORMALIZED",
                    TransitionEndpoint.VERIFIER_POST_ACTION,
                )
            ],
        }

    def human_admin_review(self, state: WorkflowState) -> dict[str, Any]:
        advanced, _ = self._advance(state)
        evidence_ids = [
            str(item["evidence_id"])
            for item in state.get("specialist_evidence", [])
        ]
        if not evidence_ids:
            evidence_ids = [f"evidence.{state['case_id']}.intake"]
        reason = str(
            state.get("limit_reason")
            or (
                "No safe autonomous route remains after the observed approval or "
                "transaction outcome."
            )
        )
        handoff = AdminHandoff(
            handoff_id=f"handoff.{state['case_id']}",
            case_id=state["case_id"],
            required_role="CCDS undergraduate administration",
            reason=reason,
            attempted_plan_ids=[
                str(item["plan_id"]) for item in state.get("plan_history", [])
            ],
            evidence_ids=list(dict.fromkeys(evidence_ids)),
            recommended_next_step=(
                "Review the attached grounded evidence and decide the documented "
                "exception or escalation route."
            ),
            created_at=self._time(state),
        )
        return {
            "loop_counters": advanced.model_dump(mode="json"),
            "admin_handoff": handoff.model_dump(mode="json"),
            "route": WorkflowNode.FINAL_RESPONSE.value,
            "run_status": "ESCALATED",
            "trace": [
                self._trace(
                    state,
                    TransitionEndpoint.HUMAN_ADMIN_REVIEW,
                    "HANDOFF_PREPARED",
                    TransitionEndpoint.FINAL_RESPONSE,
                )
            ],
        }

    def memory_updater(self, state: WorkflowState) -> dict[str, Any]:
        evaluation = state.get("goal_evaluation")
        decision = VerifierDecision.model_validate(state["verifier_decision"])
        if (
            not evaluation
            or not bool(evaluation.get("complete"))
            or decision.phase is not VerifierPhase.POST_ACTION
            or decision.decision is not VerifierDecisionCode.DONE
        ):
            raise ValueError("memory_updater is permitted only after verified DONE")
        candidate = ActionCandidate.model_validate(state["action_candidate"])
        intake = IntakeContext.model_validate(state["intake_context"])
        receipt_ids = [
            str(item["receipt_id"])
            for item in state.get("action_receipts", [])
            if item.get("action") != TransactionAction.REQUEST_APPROVAL.value
        ]
        digest = sha256("|".join(receipt_ids).encode("utf-8")).hexdigest()[:16]
        try:
            record = ExperienceMemoryRecord(
                memory_id=f"memory.pattern.{candidate.action.value.lower()}.{digest}",
                case_type=intake.problem_type.value,
                # Retrieval occurs before a concrete action is selected, so
                # long-term matching uses the observable intake goal.  The
                # chosen action remains a tag, never an authoritative fact.
                goal_kind=intake.goal_predicates[0].goal_kind,
                successful_strategy=_memory_strategy(
                    intake.problem_type,
                    candidate.action,
                    recovered=bool(
                        LoopCounters.model_validate(state["loop_counters"]).tool_retries
                    ),
                ),
                recovery_steps=(
                    ["Refresh volatile feasibility and use a verified alternative."]
                    if LoopCounters.model_validate(
                        state["loop_counters"]
                    ).tool_retries
                    else []
                ),
                failed_strategy_patterns=_failed_memory_patterns(
                    intake.problem_type,
                    recovered=bool(
                        LoopCounters.model_validate(state["loop_counters"]).tool_retries
                    ),
                ),
                applicability=_memory_applicability(intake.problem_type),
                tags=[intake.problem_type.value, candidate.action.value],
                verification_receipt_ids=receipt_ids,
                verified_at=self._time(state),
            )
            raw_result = self._memory.write(record)
            result = MemoryWriteResult.model_validate(
                raw_result.model_dump(mode="python")
                if isinstance(raw_result, MemoryWriteResult)
                else raw_result
            )
        except Exception:  # advisory persistence cannot undo verified DONE
            # Long-term experience is advisory.  A denied write is observable,
            # but it cannot roll back or hide an already verified resolution.
            return {
                "memory_write_completed": False,
                "memory_write_result": {
                    "status": "FAILED",
                    "stored": False,
                    "reason": (
                        "Advisory memory persistence failed after verified completion."
                    ),
                },
                "errors": [
                    {
                        "error_id": f"error.{state['case_id']}.memory.write",
                        "code": "MEMORY_WRITE_FAILED",
                        "message": (
                            "Advisory memory persistence failed after verified "
                            "completion."
                        ),
                    }
                ],
            }
        return {
            "memory_write_completed": result.stored,
            "memory_write_result": result.model_dump(mode="json"),
        }

    def final_response(self, state: WorkflowState) -> dict[str, Any]:
        evidence_ids = list(
            dict.fromkeys(
                str(item["evidence_id"])
                for item in state.get("specialist_evidence", [])
            )
        )
        if state.get("admin_handoff"):
            handoff = AdminHandoff.model_validate(state["admin_handoff"])
            outcome = FinalOutcome(
                outcome_id=f"outcome.{state['case_id']}.handoff",
                case_id=state["case_id"],
                status=FinalOutcomeStatus.ADMIN_HANDOFF,
                message=(
                    "The case is prepared for CCDS administrative review because no "
                    "safe autonomous route remains."
                ),
                evidence_ids=evidence_ids,
                admin_handoff_id=handoff.handoff_id,
                memory_write_permitted=False,
                completed_at=self._time(state),
            )
        else:
            from graduation_exception_agent.models.runtime import GoalEvaluation

            evaluation = GoalEvaluation.model_validate(state["goal_evaluation"])
            outcome = FinalOutcome(
                outcome_id=f"outcome.{state['case_id']}.done",
                case_id=state["case_id"],
                status=FinalOutcomeStatus.DONE,
                message=(
                    "The requested resolution is complete and every required runtime "
                    "postcondition has been verified."
                ),
                goal_evaluation=evaluation,
                evidence_ids=evidence_ids,
                memory_write_permitted=True,
                completed_at=self._time(state),
            )
        return {"final_outcome": outcome.model_dump(mode="json")}

    def _select_registration_state(self, state: WorkflowState) -> str:
        initial = self._tools.context.initial_state
        preferred = initial.get("preferred_offering_state_id")
        alternative = initial.get("alternative_offering_state_id")
        ordered = [
            str(value) for value in (preferred, alternative) if isinstance(value, str)
        ]
        attempted = set(state.get("attempted_offering_state_ids", []))
        if state.get("observation", {}).get("retryable"):
            ordered = [value for value in ordered if value not in attempted]
        results = state.get("tool_results", {})
        prerequisite = _result_data(state, "prerequisite").get("result")
        exclusion = _result_data(state, "exclusion").get("result")
        workload = _result_data(state, "workload").get("result")
        for state_id in ordered:
            availability = _result_data(state, f"availability.{state_id}")
            timetable = _result_data(state, f"timetable.{state_id}")
            if (
                availability.get("available") is True
                and timetable.get("result") == "PASS"
                and prerequisite == "PASS"
                and exclusion == "PASS"
                and workload == "PASS"
            ):
                return state_id
        # Keep the error explicit; probing the write tool to discover a hidden
        # script is forbidden.
        raise ValueError(
            "no registration index passes all current feasibility checks"
        )

    def _offering_version(
        self, state: WorkflowState, state_id: str
    ) -> VersionExpectation:
        response = ToolResponse.model_validate(
            state["tool_results"][f"availability.{state_id}"]
        )
        version = response.entity_versions.get(state_id)
        if version is None:
            raise ValueError("availability result omitted its entity version")
        return VersionExpectation(
            target_type=StateTargetType.OFFERING_STATE,
            target_id=state_id,
            expected_version=version,
        )

    def _goal_predicates(
        self,
        state: WorkflowState,
        *,
        action: TransactionAction,
        course_code: str,
    ) -> list[GoalPredicate]:
        if action is TransactionAction.SUBMIT_REGISTRATION:
            return [
                GoalPredicate(
                    predicate_id=f"predicate.{state['case_id']}.course_registered",
                    goal_kind=GoalKind.COURSE_REGISTERED,
                    target_type=StateTargetType.REGISTRATION,
                    target_ids=[self._tools.context.registration_id],
                    field_path="registered_courses.course_code",
                    operator=GoalOperator.CONTAINS,
                    expected_value=course_code,
                    description="The target course appears in the current registration.",
                )
            ]
        kind = (
            GoalKind.WAIVER_SUBMITTED
            if action is TransactionAction.SUBMIT_WAIVER
            else GoalKind.EXCEPTION_SUBMITTED
        )
        return [
            GoalPredicate(
                predicate_id=f"predicate.{state['case_id']}.{kind.value.lower()}",
                goal_kind=kind,
                field_path="action",
                operator=GoalOperator.EQUALS,
                expected_value=action.value,
                description="A committed final receipt records the intended action.",
            ),
            GoalPredicate(
                predicate_id=f"predicate.{state['case_id']}.goal_effect",
                goal_kind=kind,
                field_path="goal_effect",
                operator=GoalOperator.EQUALS,
                expected_value=True,
                description=(
                    "A final, non-intermediate receipt proves the intended goal effect."
                ),
            ),
        ]

    @staticmethod
    def _bound_goal_predicates(
        state: WorkflowState, candidate: ActionCandidate
    ) -> list[GoalPredicate]:
        """Bind receipt predicates to this candidate's one final write.

        Without an explicit transaction target, separate predicates could be
        satisfied by different receipts in a reused runtime session.  The
        registration goal is already bound to the current registration; final
        exception/waiver effects are instead bound to the receipt carrying the
        candidate's idempotency key and action.
        """

        if candidate.action is TransactionAction.SUBMIT_REGISTRATION:
            return list(candidate.goal_predicates)
        matching: list[ActionReceipt] = []
        for raw in state.get("action_receipts", []):
            try:
                receipt = ActionReceipt.model_validate(raw)
            except ValueError:
                continue
            if (
                receipt.idempotency_key == candidate.idempotency_key
                and receipt.action is candidate.action
                and not receipt.intermediate
            ):
                matching.append(receipt)
        matching.sort(key=lambda item: (item.session_revision, item.receipt_id))
        target_id = (
            matching[-1].receipt_id
            if matching
            else f"receipt.missing.{candidate.candidate_id}"
        )
        return [
            predicate.model_copy(
                update={
                    "target_type": StateTargetType.TRANSACTION,
                    "target_ids": [target_id],
                }
            )
            for predicate in candidate.goal_predicates
        ]

    @staticmethod
    def _with_current_approval_version(
        candidate: ActionCandidate, version: int
    ) -> ActionCandidate:
        expectations = [
            item
            for item in candidate.expected_versions
            if item.target_type is not StateTargetType.APPROVAL
        ]
        assert candidate.approval_id is not None
        expectations.append(
            VersionExpectation(
                target_type=StateTargetType.APPROVAL,
                target_id=candidate.approval_id,
                expected_version=version,
            )
        )
        return candidate.model_copy(update={"expected_versions": expectations})

    def _observation_from_error(
        self, state: WorkflowState, response: ToolResponse
    ) -> ToolObservation:
        if response.error is None:
            raise ValueError("transaction response has neither receipt nor error")
        codes = {
            "MODULE_FULL": ObservationCode.MODULE_FULL,
            "CLASS_UNAVAILABLE": ObservationCode.CLASS_UNAVAILABLE,
            "PREREQUISITE_FAILURE": ObservationCode.PREREQUISITE_FAILURE,
            "APPROVAL_REJECTED": ObservationCode.APPROVAL_REJECTED,
            "APPROVAL_PENDING": ObservationCode.APPROVAL_PENDING,
            "STALE_STATE": ObservationCode.STALE_STATE,
            "REQUIRED_INFORMATION_MISSING": ObservationCode.REQUIRED_INFORMATION_MISSING,
        }
        code = codes.get(response.error.code.value, ObservationCode.TEMPORARY_FAILURE)
        return ToolObservation(
            observation_id=f"observation.{state['case_id']}.preflight",
            code=code,
            message=response.error.message,
            retryable=response.error.retryable,
            occurred_at=self._time(state),
            state_versions=response.entity_versions,
        )

    def _advance(
        self,
        state: WorkflowState,
        *,
        replan: bool = False,
        tool_retry: bool = False,
    ) -> tuple[LoopCounters, str | None]:
        current = LoopCounters.model_validate(state["loop_counters"])
        proposed = current.advanced(replan=replan, tool_retry=tool_retry)
        exceeded = proposed.exceeded_cap(LoopCaps.model_validate(state["loop_caps"]))
        return (current, exceeded) if exceeded is not None else (proposed, None)

    def _limit_update(
        self,
        state: WorkflowState,
        *,
        counters: LoopCounters,
        source: TransitionEndpoint,
        reason: str,
        phase: VerifierPhase | None = None,
    ) -> dict[str, Any]:
        return {
            "loop_counters": counters.model_dump(mode="json"),
            "limit_reason": f"Workflow stopped safely at {reason}.",
            "route": WorkflowNode.HUMAN_ADMIN_REVIEW.value,
            "trace": [
                self._trace(
                    state,
                    source,
                    reason,
                    TransitionEndpoint.HUMAN_ADMIN_REVIEW,
                    phase=phase,
                )
            ],
        }

    def _tool_failure_update(
        self,
        state: WorkflowState,
        *,
        response: ToolResponse,
        source: TransitionEndpoint,
        label: str,
        counters: LoopCounters,
        result_updates: dict[str, dict[str, Any]] | None = None,
        receipts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        update: dict[str, Any] = {
            "loop_counters": counters.model_dump(mode="json"),
            "route": WorkflowNode.HUMAN_ADMIN_REVIEW.value,
            "errors": [
                {
                    "error_id": (
                        f"error.{state['case_id']}."
                        f"{source.value.lower()}.{_safe_suffix(label)}"
                    ),
                    "code": "TOOL_FAILURE",
                    "message": _tool_error_message(response, label),
                }
            ],
            "trace": [
                self._trace(
                    state,
                    source,
                    "TOOL_FAILURE",
                    TransitionEndpoint.HUMAN_ADMIN_REVIEW,
                )
            ],
        }
        if result_updates:
            update["tool_results"] = self._merged_results(state, result_updates)
        if receipts:
            update["action_receipts"] = receipts
        return update

    def _trace(
        self,
        state: WorkflowState,
        source: TransitionEndpoint,
        outcome: str,
        destination: TransitionEndpoint,
        *,
        phase: VerifierPhase | None = None,
        note: str | None = None,
        sequence_offset: int = 0,
    ) -> dict[str, Any]:
        return TraceEvent(
            sequence=len(state.get("trace", [])) + 1 + sequence_offset,
            source=source,
            outcome=outcome,
            destination=destination,
            verifier_phase=phase,
            note=note,
        ).model_dump(mode="json")

    def _time(self, state: WorkflowState) -> datetime:
        base = IntakeContext.model_validate(state["intake_context"]).received_at
        offset = (
            len(state.get("trace", []))
            + len(state.get("tool_results", {}))
            + 1
        )
        return base + timedelta(microseconds=offset)

    def _read_context(self, state: WorkflowState, slug: str) -> ToolCallContext:
        plan_version = int(state.get("plan", {}).get("version", 0))
        return ToolCallContext(
            session_id=self._tools.session_id,
            request_id=(
                f"request.{state['case_id']}.{slug}."
                f"{plan_version}.{len(state.get('trace', []))}"
            ),
            case_id=state["case_id"],
            requested_at=self._time(state),
        )

    @staticmethod
    def _merged_results(
        state: WorkflowState, updates: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        return {**state.get("tool_results", {}), **updates}


def _dump(response: ToolResponse) -> dict[str, Any]:
    return response.model_dump(mode="json")


def _data(response: ToolResponse) -> dict[str, Any]:
    if not isinstance(response.data, dict):
        raise ValueError("tool response data is not an object")
    return dict(response.data)


def _plan_step_purpose(
    specialist: SpecialistKind,
    problem_type: ExceptionCaseType,
    course_code: str,
) -> str:
    if specialist is SpecialistKind.DEGREE_AUDIT:
        return f"Confirm how {course_code} affects this student's applicable graduation requirements."
    if specialist is SpecialistKind.POLICY:
        if problem_type is ExceptionCaseType.PREREQUISITE_WAIVER:
            return f"Check the evidence and approval route for a {course_code} prerequisite waiver."
        return f"Confirm the documented exception route, required documents, and approval for {course_code}."
    if problem_type is ExceptionCaseType.TIMETABLE_CONFLICT:
        return f"Find a {course_code} class that avoids the student's timetable conflict and still has capacity."
    return f"Check the current prerequisite, timetable, workload, and availability facts for {course_code}."


def _plan_rationale(
    problem_type: ExceptionCaseType,
    course_code: str,
    *,
    is_replan: bool,
    observation: dict[str, Any],
) -> str:
    if is_replan:
        result = str(observation.get("code") or observation.get("observation") or "the previous attempt").lower().replace("_", " ")
        return f"The {course_code} route is being reconsidered because {result}; current evidence must be refreshed before another action."
    return {
        ExceptionCaseType.REGISTRATION_AFTER_DEADLINE: f"The student still needs {course_code}, so the plan checks the same course's academic fit and current class feasibility before registration.",
        ExceptionCaseType.PREREQUISITE_WAIVER: f"The {course_code} request depends on both academic evidence and a documented approval path, so neither can be assumed.",
        ExceptionCaseType.GRADUATION_REQUIREMENT: f"The applicable cohort curriculum must be established before deciding how {course_code} affects graduation clearance.",
        ExceptionCaseType.TIMETABLE_CONFLICT: f"The plan must identify a conflict-free {course_code} class and confirm the required approval before registration.",
        ExceptionCaseType.CROSS_PROGRAMME: f"The {course_code} decision must remain within the student's declared integrated-programme path and its approval boundary.",
        ExceptionCaseType.COURSE_UNAVAILABLE: f"Because no verified public route is evident for {course_code}, the plan first checks what can be supported and escalates rather than guessing.",
    }.get(problem_type, f"The plan checks only the current evidence needed to answer the student's {course_code} request safely.")


def _display_state_reference(value: Any) -> str:
    text = str(value)
    return text.rsplit(".", 1)[-1]


def _evidence_summary(
    specialist: SpecialistKind,
    responses: list[ToolResponse],
    course_code: str,
) -> str:
    data = [_data(response) for response in responses if response.status is not ToolStatus.FAILURE and isinstance(response.data, dict)]
    if specialist is SpecialistKind.DEGREE_AUDIT:
        audit = next((item for item in data if "audit_outcome" in item), {})
        outcome = str(audit.get("audit_outcome", "not yet determined")).lower().replace("_", " ")
        earned = audit.get("total_earned_aus")
        required = audit.get("total_required_aus")
        total = f"{earned} of {required} AUs" if earned is not None and required is not None else "the recorded AU total"
        outstanding = {
            str(code)
            for result in audit.get("requirement_results", [])
            if isinstance(result, dict)
            for code in result.get("outstanding_courses", [])
        }
        course_fact = f"; {course_code} is recorded as outstanding" if course_code in outstanding else ""
        return f"The degree audit is {outcome} based on {total}{course_fact}."
    if specialist is SpecialistKind.POLICY:
        eligibility = next((item for item in data if "eligibility" in item), {})
        requirement = next((item for item in data if "required" in item), {})
        documents = next((item for item in data if "documents" in item), {})
        eligibility_text = str(eligibility.get("eligibility", "not determined")).lower().replace("_", " ")
        approval = "human approval is required" if requirement.get("required") else "no separate approval is required"
        missing = len(documents.get("missing_document_ids", []))
        document_fact = "all declared documents are present" if missing == 0 else f"{missing} required document(s) are missing"
        return f"The {course_code} case is {eligibility_text}; {approval}, and {document_fact}."

    prerequisite = next((item for item in data if "missing_all_of" in item), {})
    exclusion = next((item for item in data if "conflicting_course_codes" in item), {})
    workload = next((item for item in data if "resulting_workload_aus" in item), {})
    timetables = [item for item in data if "conflicts" in item and "offering_state_id" in item]
    availability = [item for item in data if "vacancies" in item and "offering_state_id" in item]
    prerequisite_text = str(prerequisite.get("result", "unknown")).lower()
    exclusion_text = str(exclusion.get("result", "unknown")).lower()
    workload_text = str(workload.get("result", "unknown")).lower()
    feasible = []
    for item in availability:
        state_id = item.get("offering_state_id")
        timetable = next((row for row in timetables if row.get("offering_state_id") == state_id), {})
        if item.get("available") and timetable.get("result") == "PASS":
            feasible.append(_display_state_reference(state_id))
    class_fact = f"feasible class(es): {', '.join(feasible)}" if feasible else "no conflict-free available class was confirmed"
    return f"For {course_code}, prerequisite is {prerequisite_text}, exclusion is {exclusion_text}, workload is {workload_text}, and {class_fact}."


def _candidate_rationale(
    action: TransactionAction,
    course_code: str,
    parameters: dict[str, Any],
    *,
    approval_required: bool,
    retrying: bool,
) -> str:
    approval = " after the required approval is observed" if approval_required else " without a separate approval"
    if action is TransactionAction.SUBMIT_REGISTRATION:
        class_index = _display_state_reference(parameters.get("offering_state_id", "selected class"))
        refresh = " after refreshing the failed attempt" if retrying else ""
        return f"Register {course_code} in verified class {class_index}{refresh}{approval}, then check the resulting registration."
    if action is TransactionAction.SUBMIT_WAIVER:
        return f"Submit the {course_code} prerequisite waiver only with the attached evidence and observed approval, then verify the waiver result."
    if "graduation_path_id" in parameters:
        return f"Submit the {course_code} exception within the student's declared integrated-programme path after approval, without mixing curricula."
    if parameters:
        return f"Submit the bounded {course_code} exception using the currently verified case facts{approval}, then verify the outcome."
    return f"No autonomous registration is assumed for {course_code}; submit only the limited exception supported by the current evidence and verify the outcome."


def _memory_strategy(
    problem_type: ExceptionCaseType,
    action: TransactionAction,
    *,
    recovered: bool,
) -> str:
    if recovered:
        return "A registration recovered after the failed attempt was treated as new evidence, class feasibility was refreshed at action time, and a newly verified class was used."
    return {
        ExceptionCaseType.REGISTRATION_AFTER_DEADLINE: "A late registration succeeded after the same course's prerequisite, timetable, workload, and class feasibility were checked together at action time.",
        ExceptionCaseType.PREREQUISITE_WAIVER: "A prerequisite waiver succeeded only after the pending-transfer evidence and required human approval were both confirmed.",
        ExceptionCaseType.GRADUATION_REQUIREMENT: "A graduation exception was resolved by applying the student's cohort-specific curriculum and retaining the source limitations.",
        ExceptionCaseType.TIMETABLE_CONFLICT: "A timetable-conflict case succeeded after a conflict-free class was identified and the required approval was confirmed.",
        ExceptionCaseType.CROSS_PROGRAMME: "An integrated-programme exception succeeded after one applicable curriculum path was selected and approved without merging programmes.",
    }.get(problem_type, f"A verified {action.value.lower().replace('_', ' ')} completed only after the current evidence and post-action result were checked.")


def _failed_memory_patterns(
    problem_type: ExceptionCaseType,
    *,
    recovered: bool,
) -> list[str]:
    if recovered:
        return ["Do not reuse an availability result after a registration attempt fails."]
    if problem_type in {ExceptionCaseType.PREREQUISITE_WAIVER, ExceptionCaseType.TIMETABLE_CONFLICT, ExceptionCaseType.CROSS_PROGRAMME}:
        return ["Do not treat an approval request as if the exception action has already completed."]
    return []


def _memory_applicability(problem_type: ExceptionCaseType) -> str:
    return {
        ExceptionCaseType.REGISTRATION_AFTER_DEADLINE: "Use only for another late-registration case where the same academic and live scheduling checks can be repeated.",
        ExceptionCaseType.PREREQUISITE_WAIVER: "Use only when comparable prerequisite evidence exists and the applicable waiver approval route is confirmed again.",
        ExceptionCaseType.GRADUATION_REQUIREMENT: "Use only after matching the student's cohort and curriculum version and checking current source limitations.",
        ExceptionCaseType.TIMETABLE_CONFLICT: "Use only when a current conflict-free class and the applicable approval route can both be verified.",
        ExceptionCaseType.CROSS_PROGRAMME: "Use only for the same kind of programme configuration after confirming one applicable graduation path.",
    }.get(problem_type, "Use only when the current case has comparable verified conditions; past experience is advisory.")


def _result_data(state: WorkflowState, key: str) -> dict[str, Any]:
    raw = state.get("tool_results", {}).get(key)
    if not isinstance(raw, dict):
        return {}
    data = raw.get("data")
    return dict(data) if isinstance(data, dict) else {}


def _safe_suffix(value: str) -> str:
    return value.replace(":", ".").replace(" ", "_")


def _meaningful_answer(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value) and any(_meaningful_answer(item) for item in value.values())
    if isinstance(value, list):
        return bool(value) and any(_meaningful_answer(item) for item in value)
    if isinstance(value, bool):
        return value
    return isinstance(value, (int, float))


def _valid_clarification_answer(field: str, value: Any) -> bool:
    if field == "submission_declaration":
        return value is True
    return _meaningful_answer(value)


def _tool_error_message(response: ToolResponse, label: str) -> str:
    if response.error is None:
        return f"{label} failed without a normalized tool error."
    return f"{label} failed: {response.error.message}"


__all__ = ["Stage5Nodes"]
