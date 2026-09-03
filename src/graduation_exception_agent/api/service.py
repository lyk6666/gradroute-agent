"""Thread-safe run service that projects LangGraph state into UI-safe events."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import Condition, RLock, Thread
from time import sleep
from typing import Any
from uuid import uuid4

from graduation_exception_agent.api.models import (
    ApprovalResumeRequest,
    ClarificationResumeRequest,
    DetailItem,
    EvidenceSummary,
    FinalResponseSummary,
    ManualRunRequest,
    MemorySummary,
    NodeExecutionDetail,
    NodeNarrativeSummary,
    NodeStatus,
    PauseSummary,
    PlanStepSummary,
    ReasoningSummary,
    RunEvent,
    RunMode,
    RunSnapshot,
    RunStatus,
    ScenarioSummary,
    StartRunRequest,
    ThreadEventSummary,
    ThreadMemorySummary,
    TimelineItem,
    ToolSummary,
    WorkingStateSummary,
)
from graduation_exception_agent.api.narration import (
    RuntimeNarrator,
    runtime_narrator_from_settings,
)
from graduation_exception_agent.config import AppSettings
from graduation_exception_agent.data.simulated import (
    load_current_registrations,
    load_exception_cases,
    load_scenarios,
    load_students,
)
from graduation_exception_agent.memory import InMemoryExperienceMemory
from graduation_exception_agent.models.orchestration import (
    ApprovalResumePayload,
    ClarificationResumePayload,
)
from graduation_exception_agent.models.runtime import ClarificationImpact
from graduation_exception_agent.models.workflow import ApprovalStatus, ExceptionCaseType
from graduation_exception_agent.orchestration import Stage5ControlPlane
from graduation_exception_agent.reasoning import decision_provider_from_settings
from graduation_exception_agent.runtime import (
    HumanInteractionHandle,
    ScenarioRuntimeFactory,
)


NODE_IDS = (
    "student_case",
    "intake_context",
    "memory_retriever",
    "planner",
    "supervisor_router",
    "degree_audit_agent",
    "policy_agent",
    "course_agent",
    "resolution_builder",
    "clarification",
    "pre_action_verifier",
    "action_gate",
    "human_approval",
    "pause_checkpoint",
    "human_admin_review",
    "transaction",
    "observation",
    "post_action_verifier",
    "final_response",
    "memory_updater",
)

NODE_LABELS = {
    "student_case": "Student / Case",
    "intake_context": "Intake validated",
    "memory_retriever": "Memory retrieved",
    "planner": "Plan created",
    "supervisor_router": "Specialist route selected",
    "degree_audit_agent": "Degree audit evidence",
    "policy_agent": "Policy evidence",
    "course_agent": "Course feasibility",
    "resolution_builder": "Candidate assembled",
    "clarification": "Clarification",
    "pre_action_verifier": "Pre-action verification",
    "action_gate": "Action gate",
    "human_approval": "Human approval",
    "pause_checkpoint": "Approval checkpoint",
    "human_admin_review": "Administrative handoff",
    "transaction": "Transaction",
    "observation": "Outcome observed",
    "post_action_verifier": "Post-action verification",
    "final_response": "Final response",
    "memory_updater": "Memory update",
}

FAMILY_COPY = {
    "S1": (
        "Same-course registration recovery",
        "Recover a valid registration path for the same required course.",
    ),
    "S2": (
        "Prerequisite evidence route",
        "Use bounded evidence and approval without inventing a general waiver.",
    ),
    "S3": (
        "Versioned multi-source reasoning",
        "Apply the correct cohort and curriculum version after clarification.",
    ),
    "S4": (
        "Constraint-heavy index planning",
        "Resolve timetable, workload, availability and approval constraints together.",
    ),
    "S5": (
        "Integrated programme reasoning",
        "Use compatible programme-path evidence without mixing curricula.",
    ),
    "S6": (
        "No valid declared path",
        "Clarify or escalate safely rather than fabricate a resolution.",
    ),
    "S7": (
        "Dynamic registration recovery",
        "Observe a failed transaction, replan and verify the recovered result.",
    ),
}

TOOL_NAMES = {
    "student_record": ("Student Record", "Academic"),
    "current_registration": ("Current Registration", "Academic"),
    "degree_audit": ("Degree Audit", "Academic"),
    "curriculum_lookup": ("Curriculum Lookup", "Academic"),
    "case_context": ("Exception Eligibility", "Policy"),
    "exception_eligibility": ("Exception Eligibility", "Policy"),
    "policy_search": ("Policy Search", "Policy"),
    "approval_requirement": ("Approval Requirement", "Policy"),
    "approval_requirement.current": ("Approval Requirement", "Policy"),
    "approval_requirement.observed": ("Approval Status", "Action"),
    "required_documents": ("Required Documents", "Policy"),
    "course_search": ("Course Search", "Course"),
    "course_details": ("Course Details", "Course"),
    "prerequisite_check": ("Prerequisite Check", "Course"),
    "exclusion_check": ("Exclusion Check", "Course"),
    "timetable_check": ("Timetable Check", "Course"),
    "workload_check": ("Workload Check", "Course"),
    "availability": ("Availability", "Course"),
    "approval_request": ("Request Approval", "Action"),
    "transaction": ("Submit Transaction", "Action"),
    "transaction_status": ("Transaction Status", "Action"),
}

TRACE_EDGE_IDS = {
    ("INTAKE", "MEMORY_RETRIEVER"): "e-intake-memory",
    ("MEMORY_RETRIEVER", "PLANNER"): "e-memory-planner",
    ("PLANNER", "SUPERVISOR_ROUTER"): "e-planner-router",
    ("PLANNER", "HUMAN_ADMIN_REVIEW"): "e-planner-admin",
    ("SUPERVISOR_ROUTER", "DEGREE_AUDIT_AGENT"): "e-router-audit",
    ("SUPERVISOR_ROUTER", "POLICY_AGENT"): "e-router-policy",
    ("SUPERVISOR_ROUTER", "COURSE_AGENT"): "e-router-course",
    ("DEGREE_AUDIT_AGENT", "POLICY_AGENT"): "e-router-policy",
    ("DEGREE_AUDIT_AGENT", "COURSE_AGENT"): "e-router-course",
    ("DEGREE_AUDIT_AGENT", "RESOLUTION_BUILDER"): "e-audit-builder",
    ("POLICY_AGENT", "COURSE_AGENT"): "e-router-course",
    ("POLICY_AGENT", "RESOLUTION_BUILDER"): "e-policy-builder",
    ("COURSE_AGENT", "RESOLUTION_BUILDER"): "e-course-builder",
    ("RESOLUTION_BUILDER", "VERIFIER_PRE_ACTION"): "e-builder-pre",
    ("VERIFIER_PRE_ACTION", "ACTION_GATE"): "e-pre-action",
    ("VERIFIER_PRE_ACTION", "PLANNER"): "e-pre-planner",
    ("VERIFIER_PRE_ACTION", "CLARIFICATION"): "e-pre-clarify",
    ("VERIFIER_PRE_ACTION", "HUMAN_ADMIN_REVIEW"): "e-pre-admin",
    ("CLARIFICATION", "VERIFIER_PRE_ACTION"): "e-clarify-pre",
    ("CLARIFICATION", "PLANNER"): "e-clarify-planner",
    ("ACTION_GATE", "TRANSACTION"): "e-gate-transaction",
    ("ACTION_GATE", "HUMAN_APPROVAL"): "e-gate-approval",
    ("ACTION_GATE", "HUMAN_ADMIN_REVIEW"): "e-gate-admin",
    ("HUMAN_APPROVAL", "TRANSACTION"): "e-approval-transaction",
    ("HUMAN_APPROVAL", "PLANNER"): "e-approval-planner",
    ("HUMAN_APPROVAL", "PAUSE_CHECKPOINT"): "e-approval-pause",
    ("PAUSE_CHECKPOINT", "HUMAN_APPROVAL"): "e-pause-approval",
    ("TRANSACTION", "OBSERVATION"): "e-transaction-observation",
    ("TRANSACTION", "HUMAN_ADMIN_REVIEW"): "e-transaction-admin",
    ("OBSERVATION", "VERIFIER_POST_ACTION"): "e-observation-post",
    ("VERIFIER_POST_ACTION", "PLANNER"): "e-post-planner",
    ("VERIFIER_POST_ACTION", "FINAL_RESPONSE"): "e-post-final",
    ("VERIFIER_POST_ACTION", "MEMORY_UPDATER"): "e-post-memory",
    ("HUMAN_ADMIN_REVIEW", "FINAL_RESPONSE"): "e-admin-final",
}


class RunRecord:
    """Mutable state for one isolated case execution."""

    def __init__(
        self,
        *,
        run_id: str,
        scenario_id: str,
        thread_id: str,
        mode: RunMode,
        plane: Stage5ControlPlane,
        human: HumanInteractionHandle,
        intake: Any,
        profile_summary: ScenarioSummary,
    ) -> None:
        self.run_id = run_id
        self.scenario_id = scenario_id
        self.thread_id = thread_id
        self.mode = mode
        self.plane = plane
        self.human = human
        self.intake = intake
        self.profile_summary = profile_summary
        self.lock = RLock()
        self.condition = Condition(self.lock)
        self.status = RunStatus.QUEUED
        self.current_node: str | None = None
        self.node_statuses = {node_id: NodeStatus.IDLE for node_id in NODE_IDS}
        self.node_statuses["student_case"] = NodeStatus.COMPLETED
        self.timeline: list[TimelineItem] = []
        self.node_details: dict[str, NodeExecutionDetail] = {}
        self.node_attempts: dict[str, int] = {}
        self.working_narrative: str | None = None
        self.thread_narrative: str | None = None
        self.memory_narratives: dict[str, str] = {}
        self.final_narrative: str | None = None
        self.working_known: list[str] = []
        self.working_next: str | None = None
        self.working_attention: str | None = None
        self.thread_highlights: list[str] = []
        self.values: dict[str, Any] = {}
        self.pause: PauseSummary | None = None
        self.resume_token: dict[str, Any] | None = None
        self.error: str | None = None
        self.events: list[RunEvent] = []
        self.latest_event_sequence = 0
        self.step_permits = 1 if mode is RunMode.STEP else 0
        self.awaiting_step = False
        self.worker_active = False


class RunService:
    """Application service for scenario catalogue, execution and SSE replay."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        node_delay_seconds: float = 0.075,
        narrator: RuntimeNarrator | None = None,
    ) -> None:
        if node_delay_seconds < 0:
            raise ValueError("node_delay_seconds must be nonnegative")
        self._settings = settings
        self._node_delay_seconds = node_delay_seconds
        self._data_root = Path(settings.data_dir)
        self._factory = ScenarioRuntimeFactory.from_data_directory(self._data_root)
        self._memory = InMemoryExperienceMemory()
        self._narrator = narrator
        if self._narrator is None:
            try:
                self._narrator = runtime_narrator_from_settings(settings)
            except Exception:
                # Natural-language narration is optional presentation assistance;
                # a credential or provider problem must not prevent safe execution.
                self._narrator = None
        self._records_lock = RLock()
        self._records: dict[str, RunRecord] = {}
        self._scenario_summaries, self._cases = self._load_catalogue()

    def _load_catalogue(self) -> tuple[dict[str, ScenarioSummary], dict[str, Any]]:
        scenarios = load_scenarios(self._data_root / "tests" / "scenarios.json")
        students = {
            item.student_id: item
            for item in load_students(self._data_root / "simulated" / "students.json")
        }
        cases = {
            item.case_id: item
            for item in load_exception_cases(
                self._data_root / "simulated" / "exception_cases.json"
            )
        }
        registrations = {
            item.registration_id: item
            for item in load_current_registrations(
                self._data_root / "simulated" / "current_registrations.json"
            )
        }
        summaries: dict[str, ScenarioSummary] = {}
        for scenario in scenarios:
            split = scenario.split.value
            if split not in {"demo", "evaluation"}:
                continue
            student = students[scenario.student_id]
            case = cases[scenario.case_id]
            registration = registrations[scenario.registration_id]
            family = scenario.family.value
            title, challenge = FAMILY_COPY[family]
            summaries[scenario.scenario_id] = ScenarioSummary(
                scenario_id=scenario.scenario_id,
                family=family,
                split=split,
                title=title,
                challenge=challenge,
                case_type=case.problem_type.value,
                student_id=student.student_id,
                programme=student.programme,
                cohort=student.admission_cohort,
                study_year=student.study_year,
                request_text=case.reason,
                earned_aus=str(student.earned_aus),
                completed_courses=[
                    item.course_code for item in student.completed_courses
                ],
                registered_courses=[
                    item.course_code for item in registration.registered_courses
                ],
                supporting_documents=[
                    item.document_type
                    for item in case.supporting_documents
                    if item.provided
                ],
                expected_response=(
                    scenario.ground_truth.expected_response
                    if split == "demo"
                    else None
                ),
            )
        return summaries, cases

    def scenarios(self) -> list[ScenarioSummary]:
        return [self._scenario_summaries[key] for key in sorted(self._scenario_summaries)]

    def start(self, request: StartRunRequest) -> RunSnapshot:
        summary = self._scenario_summaries.get(request.scenario_id)
        if summary is None:
            raise KeyError(f"unknown runnable scenario {request.scenario_id!r}")
        return self._start_profile(
            summary=summary,
            mode=request.mode,
            display_scenario_id=summary.scenario_id,
        )

    def start_manual(self, request: ManualRunRequest) -> RunSnapshot:
        """Start a new request over a validated synthetic academic profile."""

        summary = self._scenario_summaries.get(request.profile_scenario_id)
        if summary is None:
            raise KeyError(
                f"unknown manual profile scenario {request.profile_scenario_id!r}"
            )
        supplied = (
            request.student_id,
            request.programme,
            request.cohort,
            request.study_year,
            request.problem_type,
        )
        expected = (
            summary.student_id,
            summary.programme,
            summary.cohort,
            summary.study_year,
            summary.case_type,
        )
        if supplied != expected:
            raise ValueError(
                "manual case fields do not match the selected validated synthetic profile"
            )
        request_text = request.request_text.strip()
        if request.notes and request.notes.strip():
            request_text = f"{request_text}\n\nAdditional context: {request.notes.strip()}"
        return self._start_profile(
            summary=summary,
            mode=request.mode,
            display_scenario_id=f"MANUAL-{uuid4().hex[:8].upper()}",
            request_text=request_text,
        )

    def _start_profile(
        self,
        *,
        summary: ScenarioSummary,
        mode: RunMode,
        display_scenario_id: str,
        request_text: str | None = None,
    ) -> RunSnapshot:
        runtime = self._factory.build(
            summary.scenario_id, interactive_approval=True
        )
        plane = Stage5ControlPlane.build(
            tools=runtime.tools,
            decisions=decision_provider_from_settings(self._settings),
            memory=self._memory,
        )
        case = self._cases[runtime.tools.context.case_id]
        run_id = f"run-{uuid4().hex}"
        thread_id = f"thread.{case.case_id}.{run_id[4:16]}"
        intake = plane.create_intake(
            request_text=request_text or case.reason,
            problem_type=ExceptionCaseType(case.problem_type),
            received_at=case.scenario_time,
            thread_id=thread_id,
            submission_ready=case.submission_ready,
            unresolved_questions=list(case.unresolved_questions),
        )
        record = RunRecord(
            run_id=run_id,
            scenario_id=display_scenario_id,
            thread_id=thread_id,
            mode=mode,
            plane=plane,
            human=runtime.human,
            intake=intake,
            profile_summary=summary,
        )
        record.node_details["student_case"] = NodeExecutionDetail(
            node_id="student_case",
            attempt=1,
            status=NodeStatus.COMPLETED,
            input_items=[
                DetailItem(label="Source", value=("Manual case" if request_text else "Scenario catalogue")),
            ],
            output_items=[
                DetailItem(label="Student", value=summary.student_id),
                DetailItem(label="Programme", value=summary.programme),
                DetailItem(label="Cohort", value=summary.cohort),
                DetailItem(label="Request", value=request_text or summary.request_text),
            ],
            state_changes=[DetailItem(label="Case source", value=display_scenario_id)],
            evidence_ids=[],
            tool_names=[],
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        with self._records_lock:
            self._records[run_id] = record
        self._publish(record, "run.queued", "Run accepted by the isolated runtime.")
        self._start_worker(record, resume_payload=None)
        return self.snapshot(run_id)

    def snapshot(self, run_id: str) -> RunSnapshot:
        record = self._get(run_id)
        with record.lock:
            return self._snapshot(record)

    def advance(self, run_id: str) -> RunSnapshot:
        record = self._get(run_id)
        with record.condition:
            if record.mode is not RunMode.STEP:
                raise ValueError("advance is available only for step-by-step runs")
            if record.status is not RunStatus.RUNNING or not record.awaiting_step:
                raise ValueError("this run is not waiting between executable steps")
            record.awaiting_step = False
            record.step_permits += 1
            record.condition.notify_all()
        self._publish(record, "run.advanced", "The next graph step was released.")
        return self.snapshot(run_id)

    def resume(
        self,
        run_id: str,
        request: ClarificationResumeRequest | ApprovalResumeRequest,
    ) -> RunSnapshot:
        record = self._get(run_id)
        with record.lock:
            pause = record.pause
            if record.status is not RunStatus.WAITING or pause is None:
                raise ValueError("run does not have an active human checkpoint")
            token = deepcopy(record.resume_token or {})
            if request.kind != pause.kind:
                raise ValueError("resume kind does not match the active checkpoint")
            if request.kind == "clarification":
                assert isinstance(request, ClarificationResumeRequest)
                payload: Any = ClarificationResumePayload(
                    clarification_id=str(token["clarification_id"]),
                    answers=request.answers,
                    impact=ClarificationImpact(str(token["impact"])),
                    responded_at=datetime.now(UTC),
                )
            else:
                assert isinstance(request, ApprovalResumeRequest)
                observed_at = getattr(record.intake, "received_at", datetime.now(UTC))
                observed_version = record.human.record_approval(
                    approval_id=str(token["approval_id"]),
                    status=ApprovalStatus(request.status),
                    decision_reason=request.decision_reason,
                    observed_at=observed_at,
                )
                payload = ApprovalResumePayload(
                    approval_id=str(token["approval_id"]),
                    expected_version=int(token["approval_version"]),
                    observed_version=observed_version,
                    status=ApprovalStatus(request.status),
                    decision_reason=request.decision_reason,
                    observed_at=observed_at,
                )
            record.pause = None
            record.resume_token = None
            record.status = RunStatus.RUNNING
            record.node_statuses[record.current_node or "pause_checkpoint"] = (
                NodeStatus.COMPLETED
            )
            if record.mode is RunMode.STEP:
                record.step_permits = 1
                record.awaiting_step = False
        self._publish(record, "run.resumed", "Human checkpoint response validated.")
        self._start_worker(record, resume_payload=payload)
        return self.snapshot(run_id)

    def wait_for_events(
        self, run_id: str, *, after: int, timeout: float = 15.0
    ) -> tuple[list[RunEvent], bool]:
        record = self._get(run_id)
        with record.condition:
            events = [event for event in record.events if event.sequence > after]
            terminal = record.status in {RunStatus.COMPLETED, RunStatus.FAILED}
            if not events and not terminal:
                record.condition.wait(timeout)
                events = [event for event in record.events if event.sequence > after]
                terminal = record.status in {RunStatus.COMPLETED, RunStatus.FAILED}
            return events, terminal

    def _get(self, run_id: str) -> RunRecord:
        with self._records_lock:
            record = self._records.get(run_id)
        if record is None:
            raise KeyError(f"unknown run {run_id!r}")
        return record

    def _start_worker(self, record: RunRecord, *, resume_payload: Any | None) -> None:
        with record.lock:
            if record.worker_active:
                raise ValueError("run already has an active worker")
            record.worker_active = True
            record.status = RunStatus.RUNNING
        worker = Thread(
            target=self._execute,
            args=(record, resume_payload),
            daemon=True,
            name=f"ui-run-{record.run_id[-8:]}",
        )
        worker.start()

    def _execute(self, record: RunRecord, resume_payload: Any | None) -> None:
        try:
            self._publish(record, "run.started", "Control-plane execution started.")
            if resume_payload is None:
                self._apply_narration(record, "student_case")
            stream: Iterator[dict[str, Any]] = (
                record.plane.start_stream(record.intake)
                if resume_payload is None
                else record.plane.resume_stream(
                    thread_id=record.thread_id, payload=resume_payload
                )
            )
            iterator = iter(stream)
            while True:
                self._await_step(record)
                try:
                    chunk = next(iterator)
                except StopIteration:
                    break
                if "__interrupt__" in chunk:
                    self._handle_interrupt(record)
                    return
                backend_node = next(iter(chunk))
                node_output = _mapping(chunk.get(backend_node))
                snapshot = record.plane.state(record.thread_id)
                values = dict(snapshot.values)
                node_id = self._ui_node(backend_node, values)
                self._node_update(record, node_id, values, node_output)
            with record.lock:
                record.current_node = None
                record.status = RunStatus.COMPLETED
                record.pause = None
                record.resume_token = None
            self._publish(record, "run.completed", "Run reached a terminal response.")
        except Exception as exc:  # The facade must normalize worker failures.
            with record.lock:
                record.status = RunStatus.FAILED
                record.error = str(exc)
                if record.current_node:
                    record.node_statuses[record.current_node] = NodeStatus.FAILED
            self._publish(record, "run.failed", f"Run failed safely: {exc}")
        finally:
            with record.condition:
                record.worker_active = False
                record.condition.notify_all()

    def _await_step(self, record: RunRecord) -> None:
        if record.mode is not RunMode.STEP:
            return
        should_publish = False
        with record.condition:
            if record.step_permits <= 0 and record.status is RunStatus.RUNNING:
                record.awaiting_step = True
                should_publish = True
        if should_publish:
            self._publish(
                record,
                "run.step_waiting",
                "Step-by-step execution is waiting for the next release.",
            )
        with record.condition:
            while record.step_permits <= 0 and record.status is RunStatus.RUNNING:
                record.condition.wait()
            if record.status is RunStatus.RUNNING:
                record.awaiting_step = False
                record.step_permits -= 1

    def _node_update(
        self,
        record: RunRecord,
        node_id: str,
        values: dict[str, Any],
        node_output: dict[str, Any],
    ) -> None:
        started_at = datetime.now(UTC)
        with record.lock:
            previous_values = deepcopy(record.values)
            if record.current_node and record.current_node != node_id:
                if record.node_statuses[record.current_node] is NodeStatus.RUNNING:
                    record.node_statuses[record.current_node] = NodeStatus.COMPLETED
            record.current_node = node_id
            record.node_statuses[node_id] = NodeStatus.RUNNING
            record.values = values
            attempt = record.node_attempts.get(node_id, 0) + 1
            record.node_attempts[node_id] = attempt
            record.node_details[node_id] = _node_execution_detail(
                node_id=node_id,
                attempt=attempt,
                status=NodeStatus.RUNNING,
                previous_values=previous_values,
                values=values,
                node_output=node_output,
                started_at=started_at,
            )
        self._publish(record, "node.started", f"{NODE_LABELS[node_id]} started.", node_id)
        if self._node_delay_seconds:
            sleep(self._node_delay_seconds)
        occurred_at = datetime.now(UTC)
        with record.lock:
            record.node_statuses[node_id] = NodeStatus.COMPLETED
            detail = record.node_details[node_id]
            record.node_details[node_id] = detail.model_copy(
                update={"status": NodeStatus.COMPLETED, "completed_at": occurred_at}
            )
            record.timeline.append(
                TimelineItem(
                    sequence=len(record.timeline) + 1,
                    node_id=node_id,
                    label=NODE_LABELS[node_id],
                    status=NodeStatus.COMPLETED,
                    occurred_at=occurred_at,
                )
            )
        self._apply_narration(
            record,
            node_id,
            presentation_values=_overlay_presentation_values(values, node_output),
        )
        self._publish(
            record, "node.completed", f"{NODE_LABELS[node_id]} completed.", node_id
        )

    def _handle_interrupt(self, record: RunRecord) -> None:
        snapshot = record.plane.state(record.thread_id)
        values = dict(snapshot.values)
        interrupt_value = snapshot.interrupts[0].value
        if not isinstance(interrupt_value, Mapping):
            raise ValueError("runtime emitted a malformed human checkpoint")
        kind = str(interrupt_value.get("kind", ""))
        if kind == "CLARIFICATION":
            node_id = "clarification"
            missing_fields = [str(item) for item in interrupt_value["missing_fields"]]
            impact = str(interrupt_value["impact"])
            pause = PauseSummary(
                kind="clarification",
                title="Clarification required",
                message=str(interrupt_value["question"]),
                fields=missing_fields,
                impact=impact,
                why_needed=_clarification_reason(
                    missing_fields, values, record.profile_summary
                ),
                decision_depends_on=(
                    "Because this changes the case basis, the answer will be validated and the plan rebuilt before any action is proposed."
                    if impact == "MATERIAL"
                    else "The answer completes a missing part of the current evidence, so the same proposal will return to the pre-action check."
                ),
                evidence_summary=_human_decision_evidence(values, limit=3),
            )
            token = {
                "clarification_id": interrupt_value["clarification_id"],
                "impact": interrupt_value["impact"],
            }
        elif kind == "APPROVAL":
            node_id = "pause_checkpoint"
            requirement = _mapping(values.get("approval_requirement"))
            candidate = _mapping(values.get("action_candidate"))
            approver_role = str(interrupt_value["approver_role"])
            requested_action = _humanize_action(
                str(interrupt_value.get("requested_action") or candidate.get("action") or "")
            )
            approval_basis = _approval_basis_label(requirement)
            pause = PauseSummary(
                kind="approval",
                title="Human approval required",
                message=f"Decide whether {requested_action} may proceed.",
                fields=[],
                why_needed=_approval_reason(
                    values,
                    record.profile_summary,
                    requested_action=requested_action,
                    approver_role=approver_role,
                    approval_basis=approval_basis,
                ),
                decision_depends_on=(
                    f"Approval authorises only the prepared {requested_action}; it does not prove success. "
                    "If rejected, rejection returns the evidence and reason to planning, while pending preserves the checkpoint without submitting anything."
                ),
                requested_action=requested_action,
                approver_role=approver_role,
                approval_basis=approval_basis,
                evidence_summary=_human_decision_evidence(values, limit=5),
            )
            token = {
                "approval_id": interrupt_value["approval_id"],
                "approval_version": interrupt_value["approval_version"],
            }
        else:
            raise ValueError(f"unsupported interrupt kind {kind!r}")
        with record.lock:
            record.values = values
            record.current_node = node_id
            record.node_statuses[node_id] = NodeStatus.WAITING
            record.pause = pause
            record.resume_token = token
            record.status = RunStatus.WAITING
            attempt = record.node_attempts.get(node_id, 0) + 1
            record.node_attempts[node_id] = attempt
            pause_fields = [
                DetailItem(label="Checkpoint", value=pause.title),
                DetailItem(label="Message", value=pause.message),
            ]
            if pause.fields:
                pause_fields.append(
                    DetailItem(label="Required fields", value=", ".join(pause.fields))
                )
            record.node_details[node_id] = NodeExecutionDetail(
                node_id=node_id,
                attempt=attempt,
                status=NodeStatus.WAITING,
                input_items=_input_items_for_node(node_id, values),
                output_items=pause_fields,
                state_changes=[
                    DetailItem(label="Run status", value="Waiting for human input")
                ],
                tool_names=_tool_names_for_node(node_id, {}, values),
                evidence_ids=_evidence_ids(values),
                reasoning=_reasoning_for_node(node_id, values),
                started_at=datetime.now(UTC),
            )
            record.timeline.append(
                TimelineItem(
                    sequence=len(record.timeline) + 1,
                    node_id=node_id,
                    label=NODE_LABELS[node_id],
                    status=NodeStatus.WAITING,
                    occurred_at=datetime.now(UTC),
                )
            )
        self._apply_narration(record, node_id)
        self._publish(record, "run.waiting", pause.message, node_id)

    def _apply_narration(
        self,
        record: RunRecord,
        node_id: str,
        *,
        presentation_values: dict[str, Any] | None = None,
    ) -> None:
        """Narrate the latest UI-safe record without changing execution decisions."""

        narrator = self._narrator
        with record.lock:
            detail = record.node_details.get(node_id)
            if detail is None:
                return
            narration_values = presentation_values or record.values
            fallback = _fallback_node_narrative(
                record, node_id, detail, values=narration_values
            )
            detail = detail.model_copy(update={"narrative": fallback})
            record.node_details[node_id] = detail
            record.working_narrative = fallback.summary
            record.working_next = fallback.next_step
            fallback_terminal = _mapping(narration_values.get("final_outcome"))
            if node_id == "memory_updater" and fallback_terminal:
                final_summary = _final_response_summary(
                    narration_values,
                    fallback_terminal,
                    narrative=record.final_narrative,
                )
                record.working_narrative = (
                    final_summary.narrative or final_summary.resolution_summary
                )
                record.working_next = (
                    final_summary.next_steps[0]
                    if final_summary.next_steps
                    else fallback.next_step
                )
            record.working_known = _human_decision_evidence(narration_values, limit=3)
            record.thread_highlights = _case_event_summaries(narration_values)[-4:]
            if record.pause is not None and node_id in {
                "clarification",
                "human_approval",
                "pause_checkpoint",
            }:
                record.pause = record.pause.model_copy(
                    update={"narrative": fallback.summary}
                )
            payload = self._narration_payload(
                record, node_id, detail, values=narration_values
            )
        if narrator is None:
            return
        result = None
        for _ in range(3):
            try:
                candidate_result = narrator.narrate(payload)
            except Exception:
                continue
            if _narration_fits_node(
                node_id, candidate_result.node_output, narration_values
            ):
                result = candidate_result
                break
        if result is None:
            return
        generated_at = datetime.now(UTC)
        with record.lock:
            latest = record.node_details.get(node_id)
            if latest is None or latest.attempt != detail.attempt:
                return
            record.node_details[node_id] = latest.model_copy(
                update={
                    "narrative": NodeNarrativeSummary(
                        summary=result.node_output,
                        next_step=result.action or None,
                        input=result.node_input,
                        output=result.node_output,
                        state=result.state_change,
                        action=result.action,
                        model_id=narrator.model_id,
                        generated_at=generated_at,
                    )
                }
            )
            terminal = _mapping(narration_values.get("final_outcome"))
            terminal_response = (
                _final_response_summary(
                    narration_values,
                    terminal,
                    narrative=result.final_response or record.final_narrative,
                )
                if node_id == "memory_updater" and terminal
                else None
            )
            record.working_narrative = (
                terminal_response.narrative
                or terminal_response.resolution_summary
                if terminal_response
                else result.working_state
            )
            record.thread_narrative = result.thread_memory
            record.working_known = list(result.working_known)
            record.working_next = result.working_next or None
            record.working_attention = result.working_attention or None
            record.thread_highlights = list(result.thread_highlights)
            record.memory_narratives.update(
                {item.memory_id: item.explanation for item in result.memories}
            )
            if record.pause is not None and node_id in {
                "clarification",
                "human_approval",
                "pause_checkpoint",
            }:
                record.pause = record.pause.model_copy(
                    update={"narrative": result.action or result.node_output}
                )
            if result.final_response:
                record.final_narrative = result.final_response

    def _narration_payload(
        self,
        record: RunRecord,
        node_id: str,
        detail: NodeExecutionDetail,
        *,
        values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        narration_values = values or record.values
        snapshot = self._snapshot(record)
        final_response = (
            snapshot.final_response.model_dump(
                mode="json", exclude={"narrative", "limitations"}
            )
            if snapshot.final_response
            else None
        )
        return {
            "node": {
                "name": NODE_LABELS[node_id],
                "attempt": detail.attempt,
                "status": detail.status.value,
            },
            "case_profile": _narration_case_profile(record, snapshot),
            "communication_brief": _node_communication_goal(node_id),
            "case_evidence": _presentation_case_evidence(narration_values),
            "grounded_draft": {
                "node_summary": detail.narrative.summary if detail.narrative else None,
                "next_action": detail.narrative.action if detail.narrative else None,
            },
            "case_events": _case_event_summaries(narration_values),
            "observed_input": _narration_items(
                detail.input_items, exclude_context=True
            ),
            "observed_output": _narration_items(detail.output_items),
            "persisted_changes": _narration_items(detail.state_changes),
            "evidence_references": list(detail.evidence_ids),
            "working_state": _presentation_working_state(snapshot),
            "thread_memory": _presentation_thread_memory(snapshot),
            "long_term_memory": [
                item.model_dump(
                    mode="json", exclude={"narrative", "verified_at"}
                )
                for item in snapshot.long_term_memory[:5]
            ],
            "final_response": final_response,
        }

    @staticmethod
    def _ui_node(backend_node: str, values: dict[str, Any]) -> str:
        if backend_node != "verifier":
            return backend_node
        phase = str(values.get("verification_phase", ""))
        if phase == "POST_ACTION":
            return "post_action_verifier"
        history = values.get("verification_history", [])
        if history and isinstance(history[-1], dict):
            if history[-1].get("phase") == "POST_ACTION":
                return "post_action_verifier"
        return "pre_action_verifier"

    def _publish(
        self,
        record: RunRecord,
        event_type: str,
        message: str,
        node_id: str | None = None,
    ) -> None:
        with record.condition:
            record.latest_event_sequence += 1
            event = RunEvent(
                sequence=record.latest_event_sequence,
                event_type=event_type,
                occurred_at=datetime.now(UTC),
                run_id=record.run_id,
                node_id=node_id,
                message=message,
                snapshot=self._snapshot(record),
            )
            record.events.append(event)
            record.condition.notify_all()

    def _snapshot(self, record: RunRecord) -> RunSnapshot:
        values = record.values
        counters = _mapping(values.get("loop_counters"))
        caps = _mapping(values.get("loop_caps"))
        plan = _mapping(values.get("plan"))
        candidate = _mapping(values.get("action_candidate"))
        final = _mapping(values.get("final_outcome"))
        current_label = (
            NODE_LABELS.get(record.current_node, record.current_node)
            if record.current_node
            else "Not started"
        )
        plan_steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
        plan_text = (
            f"v{plan.get('version', 1)} · {len(plan_steps)} specialist step(s)"
            if plan
            else "No plan yet"
        )
        candidate_text = str(
            candidate.get("rationale")
            or "A grounded candidate will appear after specialist evidence is assembled."
        )
        trace = values.get("trace") if isinstance(values.get("trace"), list) else []
        response = None
        if final:
            response = _final_response_summary(
                values, final, narrative=record.final_narrative
            )
        reasoning = _reasoning_summaries(values)
        action_parameters = _parameter_items(candidate.get("parameters"))
        pending = values.get("pending_specialists", [])
        intake = _mapping(values.get("intake_context"))
        outstanding = [str(item).replace("_", " ").title() for item in pending]
        outstanding.extend(str(item) for item in intake.get("unresolved_questions", []))
        errors = [
            str(_mapping(item).get("message") or _mapping(item).get("code"))
            for item in values.get("errors", [])
            if isinstance(item, Mapping)
        ]
        evidence_summaries = _evidence_summaries(values)
        event_summaries = _case_event_summaries(values)
        default_working_narrative = (
            response.resolution_summary
            if response
            else f"The case is waiting for human input: {record.pause.message} No action will be taken until it is supplied."
            if record.pause
            else str(candidate.get("rationale"))
            if candidate.get("rationale")
            else (
                f"The case is currently at {current_label.lower()}, using current academic, policy, and course facts."
                if record.current_node
                else "The case is ready to begin from the student's request."
            )
        )
        default_known = [item.summary for item in evidence_summaries[-3:]]
        default_next = (
            record.pause.message
            if record.pause
            else f"Continue to {str(values.get('route', 'the next grounded check')).replace('_', ' ')}."
        )
        default_attention = (
            record.pause.message
            if record.pause
            else (errors[-1] if errors else None)
        )
        default_thread_narrative = (
            "The case history retains the latest verified findings and decisions so a resumed run does not lose context."
            if event_summaries
            else "The case has started, but no material finding has been recorded yet."
        )
        return RunSnapshot(
            run_id=record.run_id,
            scenario_id=record.scenario_id,
            thread_id=record.thread_id,
            mode=record.mode,
            status=record.status,
            can_advance=(
                record.mode is RunMode.STEP
                and record.status is RunStatus.RUNNING
                and record.awaiting_step
            ),
            current_node=record.current_node,
            node_statuses=dict(record.node_statuses),
            node_details={
                key: value.model_copy(deep=True)
                for key, value in record.node_details.items()
            },
            traversed_edges=_traversed_edges(values, record.timeline),
            timeline=list(record.timeline),
            working_state=WorkingStateSummary(
                current_step=str(current_label),
                plan=plan_text,
                route=str(values.get("route", "Awaiting intake")),
                replans=int(counters.get("replans", 0)),
                max_replans=int(caps.get("max_replans", 4)),
                tool_retries=int(counters.get("tool_retries", 0)),
                max_tool_retries=int(caps.get("max_tool_retries", 2)),
                total_steps=int(counters.get("total_steps", 0)),
                max_total_steps=int(caps.get("max_total_steps", 20)),
                status=str(values.get("run_status", record.status.value)).replace("_", " ").title(),
                candidate_resolution=candidate_text,
                plan_version=(int(plan["version"]) if plan.get("version") is not None else None),
                plan_rationale=(str(plan["rationale"]) if plan.get("rationale") else None),
                plan_steps=_plan_step_summaries(plan, values),
                evidence=evidence_summaries,
                action=(str(candidate["action"]) if candidate.get("action") else None),
                action_parameters=action_parameters,
                outstanding_items=list(dict.fromkeys(outstanding)),
                errors=list(dict.fromkeys(errors)),
                reasoning=reasoning,
                narrative=record.working_narrative or default_working_narrative,
                narrative_known=list(record.working_known) or default_known,
                narrative_next=record.working_next or str(default_next),
                narrative_attention=record.working_attention or default_attention,
            ),
            tools=_tool_summaries(values),
            long_term_memory=_memory_summaries(values, record.memory_narratives),
            thread_memory=ThreadMemorySummary(
                trace_events=len(trace),
                clarifications=int("clarification_response" in values),
                checkpoints=len(record.timeline),
                pause_state=record.pause.title if record.pause else "None",
                latest_checkpoint=(
                    record.timeline[-1].label if record.timeline else "Run queued"
                ),
                events=[
                    ThreadEventSummary(
                        sequence=item.sequence,
                        label=item.label,
                        status=item.status.value,
                        occurred_at=item.occurred_at,
                    )
                    for item in record.timeline[-12:]
                ],
                clarification_details=_clarification_details(values),
                approval_details=_approval_details(values),
                narrative=record.thread_narrative or default_thread_narrative,
                narrative_highlights=list(record.thread_highlights) or event_summaries[-4:],
            ),
            pause=record.pause,
            final_response=response,
            error=record.error,
            latest_event_sequence=record.latest_event_sequence,
        )


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="python")
        return dict(dumped) if isinstance(dumped, Mapping) else {}
    return {}


def _overlay_presentation_values(
    values: dict[str, Any], node_output: dict[str, Any]
) -> dict[str, Any]:
    """Expose the latest node delta to narration without changing runtime state."""

    combined = deepcopy(values)
    for key, value in node_output.items():
        if key == "tool_results":
            merged = _mapping(combined.get(key))
            merged.update(_mapping(value))
            combined[key] = merged
        elif key == "specialist_evidence":
            existing = list(combined.get(key, []))
            incoming = value if isinstance(value, list) else [value]
            by_id = {
                str(_mapping(item).get("evidence_id")): item
                for item in [*existing, *incoming]
                if _mapping(item).get("evidence_id")
            }
            combined[key] = list(by_id.values()) or [*existing, *incoming]
        else:
            combined[key] = value
    return combined


def _narration_fits_node(
    node_id: str, text: str, values: dict[str, Any]
) -> bool:
    """Reject fluent but generic or cross-node copy before it reaches the UI."""

    normalized = " ".join(text.split()).lower()
    if len(normalized.split()) < 12:
        return False
    if any(
        phrase in normalized
        for phrase in (
            "node_output",
            "one smooth 60",
            "communication brief",
            "grounded draft",
            "response field",
        )
    ):
        return False
    evidence = _presentation_case_evidence(values)
    course = _mapping(evidence.get("course"))
    scenario = _mapping(values.get("scenario_context"))
    target = str(
        course.get("code")
        or _mapping(scenario.get("initial_state")).get("target_course")
        or ""
    ).lower()
    if target and node_id not in {"memory_updater"} and target not in normalized:
        return False
    role_terms: dict[str, tuple[str, ...]] = {
        "planner": ("plan", "check"),
        "supervisor_router": ("next", "route", "check", "specialist"),
        "degree_audit_agent": ("au", "audit", "graduation", "requirement"),
        "policy_agent": ("policy", "route", "approval", "eligible", "document"),
        "course_agent": ("prerequisite", "class", "timetable", "workload", "availability"),
        "resolution_builder": ("register", "registration", "waiver", "exception", "candidate", "proposed"),
        "pre_action_verifier": ("verify", "verified", "check", "safe", "valid"),
        "clarification": ("missing", "clarif", "provide", "confirm", "answer"),
        "action_gate": ("approval", "automatically", "authority", "proceed", "gate"),
        "pause_checkpoint": ("approval", "decide", "permission", "authorise", "authorize"),
        "human_admin_review": ("review", "staff", "handoff", "cannot", "insufficient"),
        "transaction": ("submitted", "attempt", "transaction", "register", "waiver", "exception"),
        "observation": ("result", "observed", "failed", "success", "pending"),
        "post_action_verifier": ("final", "goal", "verified", "complete", "condition"),
        "final_response": ("verified", "completed", "review", "stopped", "next"),
        "memory_retriever": ("past", "memory", "lesson", "experience", "current evidence"),
        "memory_updater": ("lesson", "memory", "future", "deidentified", "advisory"),
    }
    expected = role_terms.get(node_id)
    if expected and not any(term in normalized for term in expected):
        return False
    if node_id == "course_agent":
        classes = [_mapping(item) for item in course.get("classes", [])]
        chosen = _preferred_feasible_class(course)
        if classes and chosen and str(chosen.get("class_index")) not in normalized:
            return False
    if node_id == "degree_audit_agent" and evidence.get("academic"):
        academic = _mapping(evidence.get("academic"))
        earned = str(academic.get("earned_aus") or "")
        if earned and earned.lower() not in normalized:
            return False
    if node_id == "policy_agent":
        policy = _mapping(evidence.get("policy_and_documents"))
        references = [_mapping(item) for item in policy.get("policy_references", [])]
        if references:
            principal = references[0]
            reference_terms = [
                str(principal.get("reference", "")).lower(),
                " ".join(str(principal.get("name", "")).lower().split()[:3]),
            ]
            if not any(term and term in normalized for term in reference_terms):
                return False
    if node_id == "planner" and int(_mapping(values.get("loop_counters")).get("replans", 0)):
        if not any(term in normalized for term in ("replan", "changed", "failed", "refresh", "again")):
            return False
    return True


def _narration_items(
    items: list[DetailItem], *, exclude_context: bool = False
) -> list[dict[str, str]]:
    """Remove implementation-only records from the model's prose input."""

    excluded = {"Trace", "Intake Error"}
    return [
        item.model_dump()
        for item in items
        if item.label not in excluded
        and item.value != "No populated fields"
        and not (exclude_context and item.label.endswith("Context"))
    ]


def _narration_case_profile(
    record: RunRecord, snapshot: RunSnapshot
) -> dict[str, Any]:
    """Provide concise student-facing context instead of internal context IDs."""

    profile = record.profile_summary
    intake = _mapping(record.values.get("intake_context"))
    scenario = _mapping(record.values.get("scenario_context"))
    initial = _mapping(scenario.get("initial_state"))
    return {
        "student_id": profile.student_id,
        "programme": profile.programme,
        "cohort": profile.cohort,
        "study_year": profile.study_year,
        "earned_aus": profile.earned_aus,
        "completed_courses": list(profile.completed_courses),
        "registered_courses": list(profile.registered_courses),
        "supporting_documents": list(profile.supporting_documents),
        "case_type": profile.case_type,
        "request": str(
            intake.get("request_text")
            or getattr(record.intake, "request_text", profile.request_text)
        ),
        "target_course": initial.get("target_course"),
        "current_step": snapshot.working_state.current_step,
    }


def _node_communication_goal(node_id: str) -> dict[str, Any]:
    """Return a node-specific writing brief rather than a shared prose template."""

    briefs: dict[str, tuple[str, tuple[str, ...]]] = {
        "student_case": (
            "Introduce this student's situation as a coherent case.",
            ("Who is the student?", "What do they need?", "Why is the request time-sensitive?"),
        ),
        "intake_context": (
            "Explain what was accepted into the case and whether any essential fact is still missing.",
            ("What is the concrete request?", "Which course and registration context apply?", "Can grounded checks begin?"),
        ),
        "memory_retriever": (
            "Explain whether past experience suggests a useful approach without treating it as a current rule.",
            ("What similar pattern was found?", "Why might it help?", "Which current facts still require checking?"),
        ),
        "planner": (
            "Describe the ordered case plan in natural language and explain why each check matters.",
            ("What will be checked?", "In what order and why?", "If this is a replan, what new event changed the plan?"),
        ),
        "supervisor_router": (
            "Explain which specialist perspective comes next and which unanswered case question it will resolve.",
            ("Which check is next?", "Why is it needed now?", "What evidence is already complete?"),
        ),
        "degree_audit_agent": (
            "Explain the student's academic position and the target course's graduation significance.",
            ("How many AUs are earned and required?", "What requirement remains outstanding?", "Which curriculum/cohort basis applies?"),
        ),
        "policy_agent": (
            "Explain the represented exception route, eligibility, documents, approval role, and policy provenance.",
            ("Which public or simulated rule applies?", "Why is the case eligible or ineligible?", "Are required documents present?", "Who must approve what?"),
        ),
        "course_agent": (
            "Explain whether the actual course can be taken under the represented current conditions.",
            ("What prerequisite and exclusions apply?", "Is it offered with a feasible class and vacancy?", "Do timetable and workload pass?"),
        ),
        "resolution_builder": (
            "Explain the exact candidate action and how the academic, policy, and course findings support it.",
            ("What would be submitted?", "For which course or class?", "What approval or condition remains?"),
        ),
        "pre_action_verifier": (
            "Explain why the candidate is safe to proceed, must be clarified, must be replanned, or must stop.",
            ("Which checks passed?", "What remains uncertain?", "Which route follows and why?"),
        ),
        "clarification": (
            "Explain the exact missing fact, why current evidence cannot answer it, and how the answer changes the route.",
            ("What must the person provide?", "Which decision depends on it?", "Will planning restart or verification resume?"),
        ),
        "action_gate": (
            "Explain the authority boundary for the already-verified candidate.",
            ("Can it proceed automatically?", "If approval is needed, which rule and role require it?", "What action is strictly in scope?"),
        ),
        "human_approval": (
            "Give the approving person a decision-ready case brief grounded in the actual evidence.",
            ("What exact action is requested?", "Which academic, prerequisite, availability, policy, and document facts support it?", "What do approve, reject, and pending do?"),
        ),
        "pause_checkpoint": (
            "Explain why the case is paused and preserve a decision-ready summary for the approving role.",
            ("Who is deciding what?", "Which policy and evidence support the request?", "What happens for each response?"),
        ),
        "human_admin_review": (
            "Prepare a staff-facing handoff explaining why no safe automated route remains.",
            ("What was checked?", "What rule, evidence, or authority is missing?", "Which CCDS role should take over and what should they review?"),
        ),
        "transaction": (
            "Explain the precise action attempted and the authoritative observed response.",
            ("What was submitted for which course/class?", "Was approval satisfied?", "Did it succeed, fail, or remain pending?"),
        ),
        "observation": (
            "Explain what the transaction result means for the student's case.",
            ("What changed?", "Is the result retryable?", "Must availability be refreshed, the plan changed, or the goal verified?"),
        ),
        "post_action_verifier": (
            "Explain whether the student's requested outcome is actually true after the observed action.",
            ("Which goal conditions passed?", "What evidence proves completion?", "If incomplete, why must the case recover or stop?"),
        ),
        "final_response": (
            "Give the student the verified outcome, its concrete reasons, limitations, and immediate next steps.",
            ("What happened?", "Why is it valid or why did it stop?", "What should the student do next?"),
        ),
        "memory_updater": (
            "Explain the deidentified lesson retained after verified completion and its narrow future use.",
            ("What strategy worked?", "Under which conditions?", "Why can it not replace current evidence?"),
        ),
    }
    objective, questions = briefs.get(
        node_id,
        ("Explain the material case fact produced by this step.", ("What changed and why does it matter?",)),
    )
    return {
        "objective": objective,
        "questions_to_answer": list(questions),
        "primary_copy": "one smooth 60–110 word paragraph when enough evidence exists",
    }


def _tool_result_data(values: dict[str, Any], key: str) -> dict[str, Any]:
    result = _mapping(_mapping(values.get("tool_results")).get(key))
    return _mapping(result.get("data"))


def _tool_result_data_with_prefix(
    values: dict[str, Any], prefix: str
) -> list[dict[str, Any]]:
    results = _mapping(values.get("tool_results"))
    return [
        _mapping(_mapping(raw).get("data"))
        for key, raw in results.items()
        if str(key).startswith(prefix) and _mapping(_mapping(raw).get("data"))
    ]


def _friendly_document(value: str) -> str:
    return value.rsplit(".", 1)[-1].replace("_", " ").strip().lower()


def _policy_reference(rule_id: str) -> dict[str, str]:
    labels = {
        "policy.exception.exchange.pending_transfer": "CCDS pending exchange-credit prerequisite-waiver route",
        "policy.exception.icc.registration": "ICC study-plan deviation route",
        "policy.exception.icc.cc0006_clash": "narrow CC0006 quiz and BDE clash route",
        "policy.exception.restricted_repeat": "restricted-repeat eligibility boundary",
        "policy.prototype.scenario_bounded_audit": "scenario-bounded degree-audit assumption",
        "policy.prototype.registration_operations": "simulated registration-operation rule",
        "policy.prototype.counterfactual_template_reuse": "simulated offering-state reuse rule",
    }
    provenance = (
        "simulated prototype"
        if ".prototype." in rule_id
        else "unverified or unavailable public route"
        if rule_id.startswith("unknown.")
        else "collected public source"
    )
    return {
        "reference": rule_id,
        "name": labels.get(rule_id, rule_id.replace("policy.", "").replace(".", " ")),
        "provenance": provenance,
    }


def _presentation_case_evidence(values: dict[str, Any]) -> dict[str, Any]:
    """Project observed case facts for narration without evaluator-only state."""

    student = _tool_result_data(values, "student_record")
    registration = _tool_result_data(values, "current_registration")
    audit = _tool_result_data(values, "degree_audit")
    curriculum = _tool_result_data(values, "curriculum")
    eligibility = _tool_result_data(values, "exception_eligibility") or _tool_result_data(values, "case_context")
    requirement = _mapping(values.get("approval_requirement")) or _tool_result_data(values, "approval_requirement")
    documents = _tool_result_data(values, "required_documents")
    course = _tool_result_data(values, "course_details")
    prerequisite = _tool_result_data(values, "prerequisite")
    exclusion = _tool_result_data(values, "exclusion")
    workload = _tool_result_data(values, "workload")
    availability = _tool_result_data_with_prefix(values, "availability.")
    timetable = _tool_result_data_with_prefix(values, "timetable.")
    policy_ids = list(dict.fromkeys(
        rule_id
        for item in _evidence_summaries(values)
        for rule_id in item.rule_ids
        if rule_id.startswith("policy.")
    ))
    policy_ids.sort(key=lambda item: (".prototype." in item, item))
    registered_courses = [
        str(_mapping(item).get("course_code"))
        for item in registration.get("registered_courses", [])
        if _mapping(item).get("course_code")
    ]
    offered_classes = [
        {
            "class_index": str(item.get("offering_state_id", "")).rsplit(".", 1)[-1],
            "available": item.get("available"),
            "status": item.get("runtime_status"),
            "vacancies": item.get("vacancies"),
            "waitlist": item.get("waitlist_count"),
            "unavailable_reason": item.get("unavailable_reason"),
        }
        for item in availability[:6]
    ]
    return {
        "student": {
            "programme": student.get("programme"),
            "cohort": student.get("admission_cohort"),
            "study_year": student.get("study_year"),
            "earned_aus": student.get("earned_aus"),
            "academic_standing": student.get("academic_standing"),
            "registered_courses": registered_courses,
        },
        "academic": {
            "audit_outcome": audit.get("audit_outcome"),
            "earned_aus": audit.get("total_earned_aus"),
            "required_aus": audit.get("total_required_aus") or curriculum.get("graduation_aus"),
            "curriculum": curriculum.get("name"),
            "outstanding_requirements": [
                {
                    "name": str(_mapping(item).get("requirement_id", "")).rsplit(".", 1)[-1].replace("_", " "),
                    "earned_aus": _mapping(item).get("earned_aus"),
                    "required_aus": _mapping(item).get("required_aus"),
                    "courses": _mapping(item).get("outstanding_courses", []),
                    "explanation": _mapping(item).get("explanation"),
                }
                for item in audit.get("requirement_results", [])
                if _mapping(item).get("status") != "SATISFIED"
            ][:4],
        },
        "policy_and_documents": {
            "eligibility": eligibility.get("eligibility"),
            "eligibility_reason": eligibility.get("reason"),
            "approval_required": requirement.get("required", eligibility.get("approval_required")),
            "approver": requirement.get("approver_role"),
            "requested_action": requirement.get("requested_action"),
            "approval_basis": requirement.get("basis"),
            "policy_references": [_policy_reference(item) for item in policy_ids],
            "documents": [
                {
                    "name": str(_mapping(item).get("document_type", "")).replace("_", " ").lower(),
                    "provided": _mapping(item).get("provided"),
                    "verified": _mapping(item).get("verified"),
                }
                for item in documents.get("documents", [])
            ],
            "missing_documents": [
                _friendly_document(str(item))
                for item in documents.get("missing_document_ids", eligibility.get("missing_document_ids", []))
            ],
        },
        "course": {
            "code": course.get("code") or prerequisite.get("course_code"),
            "title": course.get("title"),
            "aus": course.get("aus"),
            "catalogue_prerequisite": _mapping(course.get("prerequisites")).get("raw_text"),
            "prerequisite_result": prerequisite.get("result"),
            "prerequisite_reason": prerequisite.get("reason"),
            "exclusions": course.get("exclusions", []),
            "exclusion_result": exclusion.get("result"),
            "conflicting_courses": exclusion.get("conflicting_course_codes", []),
            "workload_result": workload.get("result"),
            "current_workload_aus": workload.get("current_workload_aus"),
            "resulting_workload_aus": workload.get("resulting_workload_aus"),
            "workload_limit_aus": workload.get("workload_limit_aus"),
            "classes": offered_classes,
            "timetable_results": [
                {
                    "class_index": str(item.get("offering_state_id", "")).rsplit(".", 1)[-1],
                    "result": item.get("result"),
                    "conflicts": item.get("conflicts", []),
                }
                for item in timetable[:6]
            ],
        },
        "plan_and_action": {
            "plan_version": _mapping(values.get("plan")).get("version"),
            "plan_reason": _mapping(values.get("plan")).get("rationale"),
            "plan_steps": [
                str(_mapping(item).get("purpose"))
                for item in _mapping(values.get("plan")).get("steps", [])
                if _mapping(item).get("purpose")
            ],
            "replans": _mapping(values.get("loop_counters")).get("replans", 0),
            "recent_verification": [
                {
                    "phase": _mapping(item).get("phase"),
                    "decision": _mapping(item).get("decision"),
                    "reason": _mapping(item).get("reason"),
                }
                for item in values.get("verification_history", [])[-3:]
                if isinstance(item, Mapping)
            ],
            "candidate_action": _humanize_action(str(_mapping(values.get("action_candidate")).get("action") or "")),
            "candidate_reason": _mapping(values.get("action_candidate")).get("rationale"),
            "observation": _mapping(values.get("observation")).get("message"),
        },
    }


def _preferred_feasible_class(course: dict[str, Any]) -> dict[str, Any] | None:
    classes = [_mapping(item) for item in course.get("classes", [])]
    timetable_by_class = {
        str(_mapping(item).get("class_index")): str(_mapping(item).get("result", ""))
        for item in course.get("timetable_results", [])
    }
    return next(
        (
            item
            for item in classes
            if item.get("available")
            and timetable_by_class.get(str(item.get("class_index"))) == "PASS"
        ),
        next((item for item in classes if item.get("available")), classes[0] if classes else None),
    )


def _evidence_rich_fallback(
    record: RunRecord,
    node_id: str,
    *,
    default: str,
    values: dict[str, Any] | None = None,
) -> str:
    """Create useful primary copy even when the optional narrator is unavailable."""

    values = values or record.values
    profile = record.profile_summary
    evidence = _presentation_case_evidence(values)
    academic = _mapping(evidence.get("academic"))
    policy = _mapping(evidence.get("policy_and_documents"))
    course = _mapping(evidence.get("course"))
    action = _mapping(evidence.get("plan_and_action"))
    target = str(course.get("code") or _mapping(_mapping(values.get("scenario_context")).get("initial_state")).get("target_course") or "the requested course")
    plan = _mapping(values.get("plan"))
    decision = _mapping(values.get("verifier_decision"))
    final = _mapping(values.get("final_outcome"))
    handoff = _mapping(values.get("admin_handoff"))
    memories = _memory_summaries(values)
    academic_sentence = (
        f"The represented degree audit records {academic['earned_aus']} of {academic['required_aus']} AUs and lists {target} as outstanding."
        if academic.get("earned_aus") and academic.get("required_aus")
        else ""
    )
    prerequisite_sentence = (
        f"For {target}, the catalogue prerequisite is {course.get('catalogue_prerequisite') or 'not fully represented'}, and the current check returned {str(course.get('prerequisite_result')).lower()}."
        if course.get("prerequisite_result")
        else ""
    )
    classes = [_mapping(item) for item in course.get("classes", [])]
    feasible = [item for item in classes if item.get("available")]
    class_sentence = ""
    if classes:
        selected = _preferred_feasible_class(course) or (feasible[0] if feasible else classes[0])
        selected_timetable = next(
            (
                str(_mapping(item).get("result")).lower()
                for item in course.get("timetable_results", [])
                if _mapping(item).get("class_index") == selected.get("class_index")
                and _mapping(item).get("result")
            ),
            "not confirmed",
        )
        selected_vacancy = (
            f" with {selected.get('vacancies')} simulated vacancies"
            if selected.get("vacancies") is not None
            else ""
        )
        class_sentence = (
            f"Class {selected.get('class_index')} is {'available' if selected.get('available') else 'unavailable'}"
            f"{selected_vacancy}; "
            f"the timetable check is {selected_timetable} and the workload check is "
            f"{str(course.get('workload_result', 'not confirmed')).lower()}."
        )
    references = [_mapping(item) for item in policy.get("policy_references", [])]
    policy_sentence = ""
    if references:
        principal = references[0]
        policy_sentence = (
            f"The relevant basis is {principal.get('name')} ({principal.get('reference')}), recorded as a {principal.get('provenance')} route."
        )
    documents = [_mapping(item) for item in policy.get("documents", [])]
    provided = [str(item.get("name")) for item in documents if item.get("provided")]
    document_sentence = (
        f"The case records {', '.join(provided)} as provided."
        if provided
        else ""
    )
    candidate = _mapping(values.get("action_candidate"))
    requirement = _mapping(values.get("approval_requirement"))
    raw_requested_action = str(
        candidate.get("action") or requirement.get("requested_action") or ""
    )
    lowered_action = raw_requested_action.lower()
    requested_action = (
        _humanize_action(raw_requested_action)
        if candidate.get("action")
        else "prerequisite waiver request"
        if "waiver" in lowered_action
        else "course registration"
        if "register" in lowered_action or "registration" in lowered_action
        else "exception request"
        if raw_requested_action
        else "proposed action"
    )
    approval_sentence = ""
    if requirement.get("required"):
        approval_sentence = (
            f"{requirement.get('approver_role', 'The designated approving role')} must authorise the {requested_action}; eligibility alone is not approval."
        )
    plan_steps = [
        str(_mapping(item).get("purpose"))
        for item in plan.get("steps", [])
        if _mapping(item).get("purpose")
    ]
    replan_count = int(_mapping(values.get("loop_counters")).get("replans", 0))
    recent_reason = next(
        (
            str(_mapping(item).get("reason"))
            for item in reversed(values.get("verification_history", []))
            if _mapping(item).get("reason")
        ),
        "",
    )
    explanations = {
        "student_case": (
            f"This is a Year {profile.study_year} {profile.programme} student from {profile.cohort} with {profile.earned_aus} earned AUs. "
            f"The request concerns {target} after the normal registration route, so the case must establish the correct academic, course, policy, document, and approval path before any action."
        ),
        "intake_context": (
            f"The case accepts a Year {profile.study_year} {profile.programme} request concerning {target}. "
            f"The student has {profile.earned_aus} earned AUs and is currently registered for {', '.join(profile.registered_courses) if profile.registered_courses else 'no represented courses'}. "
            "The request and available supporting information are now ready for current academic, policy, and course checks; no expected scenario answer was added to the case."
        ),
        "memory_retriever": (
            f"{len(memories)} comparable verified past lesson{' was' if len(memories) == 1 else 's were'} found for the {target} case. "
            "These lessons can suggest an order of checks or a recovery pattern, but they do not establish this student's prerequisite, class vacancy, policy eligibility, or approval. Those facts must still come from the current case evidence."
            if memories
            else f"No comparable past lesson was needed for the {target} request. The case will proceed from the student's current degree audit, course conditions, represented policy route, documents, and approval state rather than borrowing a previous outcome."
        ),
        "planner": (
            f"Plan version {plan.get('version', 1)} will "
            + "; then ".join(step.rstrip(".").lower() for step in plan_steps)
            + ". "
            + (
                f"This is replan {replan_count}: {recent_reason} The revised sequence checks the changed fact before another action is considered."
                if replan_count
                else str(plan.get("rationale") or f"Each check is needed before a safe action for {target} can be selected.")
            )
        ),
        "supervisor_router": (
            f"The plan has routed the {target} case to {_human_label(str(values.get('route', 'the next specialist'))).lower()}. "
            f"This check comes next because {str(plan.get('rationale') or 'the unresolved evidence must be completed in the planned order').rstrip('.')}. "
            f"Already recorded findings remain available and will be combined only after every required specialist question is answered."
        ),
        "degree_audit_agent": " ".join(filter(None, [academic_sentence, f"The applicable curriculum is {academic.get('curriculum') or profile.cohort}. This establishes the academic need for the request, but it does not by itself establish policy eligibility, course feasibility, or approval."])),
        "policy_agent": " ".join(filter(None, [
            f"The {target} case is {str(policy.get('eligibility', 'not yet classified')).replace('_', ' ').lower()}: {str(policy.get('eligibility_reason') or 'the represented route must still be checked').rstrip('.')}.",
            policy_sentence,
            document_sentence,
            approval_sentence,
        ])),
        "course_agent": " ".join(filter(None, [
            f"{target} is {course.get('title', 'the requested course')} ({course.get('aus', 'unknown')} AU).",
            prerequisite_sentence,
            f"The exclusion check is {str(course.get('exclusion_result', 'not confirmed')).lower()}.",
            class_sentence,
            "These are represented timetable and course facts; live vacancy is simulated for the prototype.",
        ])),
        "resolution_builder": " ".join(filter(None, [
            str(candidate.get("rationale") or default),
            academic_sentence,
            prerequisite_sentence,
            class_sentence,
            approval_sentence,
        ])),
        "pre_action_verifier": " ".join(filter(None, [
            str(decision.get("reason") or default),
            f"The candidate is the {requested_action} for {target}.",
            policy_sentence,
            approval_sentence,
            "Only the recorded route may continue; an unverified or stale condition sends the case back for clarification, replanning, or staff review.",
        ])),
        "clarification": " ".join(filter(None, [
            record.pause.why_needed if record.pause else default,
            record.pause.decision_depends_on if record.pause else "",
        ])),
        "action_gate": " ".join(filter(None, [
            f"The verified candidate is the {requested_action} for {target}.",
            policy_sentence,
            approval_sentence or "No separate approval is recorded as necessary, so only the verified action may proceed automatically.",
            "The gate does not decide academic facts or grant approval; it enforces the authority already established by the evidence.",
        ])),
        "human_approval": record.pause.why_needed if record.pause else " ".join(filter(None, [academic_sentence, prerequisite_sentence, class_sentence, policy_sentence, document_sentence, approval_sentence])),
        "pause_checkpoint": record.pause.why_needed if record.pause else " ".join(filter(None, [academic_sentence, prerequisite_sentence, class_sentence, policy_sentence, document_sentence, approval_sentence])),
        "human_admin_review": " ".join(filter(None, [
            str(handoff.get("reason") or default),
            academic_sentence,
            prerequisite_sentence,
            policy_sentence,
            f"Staff should review {str(handoff.get('recommended_next_step') or 'the evidence package and decide the next authorised step').rstrip('.')}.",
        ])),
        "transaction": " ".join(filter(None, [
            f"The runtime attempted the verified {requested_action} for {target}.",
            approval_sentence,
            str(_mapping(values.get("observation")).get("message") or "Its receipt has been recorded, but the student's goal still requires a separate outcome check."),
        ])),
        "observation": " ".join(filter(None, [
            str(_mapping(values.get("observation")).get("message") or default),
            f"This observed result—not the proposed plan—now determines whether the {target} case can be verified, retried with refreshed availability, replanned, or handed to staff.",
        ])),
        "post_action_verifier": " ".join(filter(None, [
            str(decision.get("reason") or recent_reason or default),
            f"The final check compares the observed {requested_action} result with every required goal condition for {target}; completion is reported only if all required conditions are satisfied.",
        ])),
        "final_response": (
            f"The {target} case reached {str(final.get('status', 'its final state')).replace('_', ' ').lower()}. "
            f"{str(final.get('message') or default)} The response explains the supporting academic, policy, approval, transaction, and final-check evidence, plus the student's next step."
        ),
        "memory_updater": (
            f"After the {target} outcome was verified, the system retained a deidentified lesson about the successful checks and recovery path. "
            "It contains no student identity and remains advisory: a future case must independently confirm its curriculum, prerequisite, offering, policy, documents, approval, and transaction outcome."
        ),
    }
    return _bounded(explanations.get(node_id, default), 1_200)


def _case_event_summaries(values: dict[str, Any]) -> list[str]:
    events: list[str] = []
    plan = _mapping(values.get("plan"))
    if plan.get("rationale"):
        events.append(str(plan["rationale"]))
    events.extend(item.summary for item in _evidence_summaries(values))
    approval = _mapping(values.get("approval_response"))
    if approval.get("status"):
        events.append(
            f"The approving role returned {str(approval['status']).lower().replace('_', ' ')}."
        )
    observation = _mapping(values.get("observation"))
    if observation.get("message"):
        events.append(str(observation["message"]))
    decision = _mapping(values.get("verifier_decision"))
    if decision.get("reason"):
        events.append(str(decision["reason"]))
    return list(dict.fromkeys(events))[-6:]


def _presentation_working_state(snapshot: RunSnapshot) -> dict[str, Any]:
    working = snapshot.working_state
    return {
        "current_step": working.current_step,
        "status": working.status,
        "plan_reason": working.plan_rationale,
        "checks": [
            {"purpose": item.purpose, "status": item.status}
            for item in working.plan_steps
        ],
        "findings": [item.summary for item in working.evidence],
        "proposed_resolution": working.candidate_resolution,
        "action": _humanize_action(working.action),
        "needs_attention": [*working.outstanding_items, *working.errors],
    }


def _presentation_thread_memory(snapshot: RunSnapshot) -> dict[str, Any]:
    thread = snapshot.thread_memory
    return {
        "case_history": list(thread.narrative_highlights),
        "checkpoints": thread.checkpoints,
        "waiting_for": thread.pause_state if thread.pause_state != "None" else None,
        "clarification": [item.model_dump() for item in thread.clarification_details],
        "approval": [item.model_dump() for item in thread.approval_details],
    }


def _fallback_node_narrative(
    record: RunRecord,
    node_id: str,
    detail: NodeExecutionDetail,
    *,
    values: dict[str, Any] | None = None,
) -> NodeNarrativeSummary:
    """Always provide concise case-specific prose, even when the LLM is offline."""

    values = values or record.values
    profile = record.profile_summary
    scenario = _mapping(values.get("scenario_context"))
    target = str(_mapping(scenario.get("initial_state")).get("target_course") or "the requested course")
    plan = _mapping(values.get("plan"))
    candidate = _mapping(values.get("action_candidate"))
    evidence = {item.specialist: item.summary for item in _evidence_summaries(values)}
    route = _human_label(str(values.get("route", "the next check")))
    decision = _mapping(values.get("verifier_decision"))
    observation = _mapping(values.get("observation"))
    approval = _mapping(values.get("approval_response"))
    final = _mapping(values.get("final_outcome"))
    intake = _mapping(values.get("intake_context"))
    missing_facts = ", ".join(
        str(item).replace("_", " ")
        for item in intake.get("unresolved_questions", [])
    ) or "the requested supporting fact"
    handoff = _mapping(values.get("admin_handoff"))
    memories = _memory_summaries(values)

    student_context = (
        f"A Year {profile.study_year} {profile.programme} student from {profile.cohort} "
        f"is asking for help with {target}."
    )
    input_text = {
        "intake_context": student_context,
        "memory_retriever": f"The case supplied the student's {target} request so comparable past resolution patterns could be considered.",
        "planner": f"The planner received the {target} request and the current student, registration, and case facts.",
        "supervisor_router": f"The router received the case plan for {target} and the checks that remain unfinished.",
        "degree_audit_agent": f"The academic check used this student's cohort, programme, completed work, and the outstanding {target} requirement.",
        "policy_agent": f"The policy check used the {target} case type, attached documents, and declared exception route.",
        "course_agent": f"The course check used the student's current timetable and the latest represented classes for {target}.",
        "resolution_builder": f"The builder received the completed academic, policy, and course findings for {target}.",
        "pre_action_verifier": f"The verifier received the proposed {target} action and its supporting findings.",
        "clarification": f"The verifier identified that {missing_facts} is still needed before the {target} case can continue.",
        "action_gate": f"The gate received the verified {target} proposal and its approval requirement.",
        "human_approval": f"The approving role received the evidence-backed request concerning {target}.",
        "pause_checkpoint": f"The {target} case reached an approval checkpoint and retained its evidence while waiting.",
        "human_admin_review": f"The system received the unresolved {target} case and its collected evidence for a staff handoff.",
        "transaction": f"The transaction step received the verified action selected for {target}.",
        "observation": f"The observer received the actual result of the {target} action.",
        "post_action_verifier": f"The verifier compared the observed {target} result with the student's requested outcome.",
        "final_response": f"The response step received the verified outcome for the student's {target} request.",
        "memory_updater": f"The memory step received a completed, verified {target} outcome for deidentification.",
    }.get(node_id, student_context)

    finding = {
        "intake_context": f"The request was accepted as a {profile.case_type.lower().replace('_', ' ')} case and is ready for grounded checks.",
        "memory_retriever": (
            f"{len(memories)} relevant past pattern{' was' if len(memories) == 1 else 's were'} found as advice only."
            if memories
            else "No comparable past pattern was needed; the case will rely on current evidence."
        ),
        "planner": str(plan.get("rationale") or f"A case-specific plan was prepared for {target}."),
        "supervisor_router": f"The next required check is {route.lower()}.",
        "degree_audit_agent": evidence.get("DEGREE_AUDIT", f"The academic record for {target} was checked."),
        "policy_agent": evidence.get("POLICY", f"The exception route for {target} was checked."),
        "course_agent": evidence.get("COURSE", f"The current class options for {target} were checked."),
        "resolution_builder": str(candidate.get("rationale") or f"No safe candidate action for {target} has been assembled yet."),
        "pre_action_verifier": str(decision.get("reason") or "The proposed action was checked against its evidence and safety conditions."),
        "clarification": str(record.pause.message if record.pause else f"The case needs {missing_facts} before another decision can be made."),
        "action_gate": f"The verified route continues to {route.lower()}.",
        "human_approval": (
            f"The recorded approval status is {str(approval['status']).lower()}."
            if approval.get("status")
            else "The required approval has not yet become observable."
        ),
        "pause_checkpoint": str(record.pause.message if record.pause else "The case is waiting for the required approval to become observable."),
        "human_admin_review": str(handoff.get("reason") or f"No safe autonomous action remains for {target}; the evidence package is ready for staff review."),
        "transaction": str(observation.get("message") or "The selected action was submitted and its result was recorded."),
        "observation": str(observation.get("message") or "The transaction result is now available for verification."),
        "post_action_verifier": str(decision.get("reason") or "The observed result was checked against the student's goal."),
        "final_response": (
            f"The {_humanize_action(str(candidate.get('action') or 'resolution'))} is verified for {target}, and the student-facing next steps are ready."
            if str(final.get("status")) == "DONE"
            else str(final.get("message") or f"The final state of the {target} request was recorded.")
        ),
        "memory_updater": "A deidentified resolution pattern was retained only after the outcome was verified.",
    }.get(node_id, _summarize_value([*detail.output_items, *detail.state_changes]))
    finding = _evidence_rich_fallback(
        record, node_id, default=finding, values=values
    )

    waiting = record.pause is not None
    state_text = (
        f"The case is paused for {record.pause.title.lower()}."
        if waiting
        else {
            "intake_context": "The student's request is now a validated case that can be checked without exposing evaluator information.",
            "memory_retriever": "Any matching past experience is attached as advice only; it cannot replace a current check.",
            "planner": f"A {len(plan.get('steps', []))}-check plan is ready for {target}.",
            "supervisor_router": f"The case is routed to {route.lower()} next.",
            "degree_audit_agent": "The academic finding is retained for the resolution decision.",
            "policy_agent": "The policy, document, and approval finding is retained for the resolution decision.",
            "course_agent": "The latest course and class-feasibility finding is retained for the resolution decision.",
            "resolution_builder": "A concrete candidate is ready for the pre-action safety check.",
            "pre_action_verifier": f"The recorded verifier decision now controls whether the case may continue to {route.lower()}.",
            "clarification": f"The case cannot continue until {missing_facts} is supplied and validated.",
            "action_gate": f"The case may continue only through {route.lower()}.",
            "human_approval": "The approval response is now part of the observable case state.",
            "pause_checkpoint": "The plan and evidence are retained so the case can resume safely after the approval check.",
            "human_admin_review": "The automated route has stopped and a bounded evidence package is ready for staff review.",
            "transaction": "The attempted action and its receipt are recorded, but completion still requires an outcome check.",
            "observation": "The actual transaction result is now available to the final verifier.",
            "post_action_verifier": "The student's goal has been checked against the observed result.",
            "final_response": "The verified outcome is ready to present to the student.",
            "memory_updater": "Only a deidentified, verified lesson was added to advisory memory.",
        }.get(node_id, f"This step is complete and the case is ready for {route.lower()}.")
    )
    action_text = str(record.pause.message) if waiting else {
        "intake_context": "No additional input is needed; the academic and policy checks can begin.",
        "memory_retriever": "No decision is requested from the student; retrieved experience remains advisory.",
        "planner": "No human decision is requested while the planned evidence checks are still running.",
        "supervisor_router": f"The system can send the case to {route.lower()} without human input.",
        "degree_audit_agent": "No human input is needed unless this academic check identifies an unresolved curriculum fact.",
        "policy_agent": "No decision is needed here; any actual approval request is handled separately by the approving role.",
        "course_agent": "No human input is needed while the system compares the represented class options.",
        "resolution_builder": f"The proposed {_humanize_action(str(candidate.get('action') or ''))} must pass verification before it can proceed.",
        "pre_action_verifier": f"The case may continue with the verified {_humanize_action(str(candidate.get('action') or ''))} only along the recorded route.",
        "clarification": f"Provide {missing_facts}; no registration or exception will be submitted before it is validated.",
        "action_gate": f"Follow the recorded {route.lower()} route; the agent cannot bypass approval or review.",
        "pause_checkpoint": "Re-check the named approving role's decision; the agent cannot supply that decision itself.",
        "human_admin_review": "A CCDS staff member should review the prepared evidence and decide the next authorised step.",
        "transaction": "No manual input is requested during the transaction; its observed result determines the next step.",
        "observation": "No manual input is needed; the observed result now returns to verification.",
        "post_action_verifier": "No further action is needed if every goal condition passed; otherwise the case must replan or escalate.",
        "final_response": "The student can now follow the case-specific next steps in the final response.",
        "memory_updater": "No user action is needed; the stored pattern contains no student identity or current rule claim.",
    }.get(node_id, "No separate human action is needed at this step.")
    return NodeNarrativeSummary(
        summary=_bounded(finding, 700),
        next_step=_bounded(action_text, 500),
        input=_bounded(input_text, 500),
        output=_bounded(finding, 700),
        state=_bounded(state_text, 400),
        action=_bounded(action_text, 500),
        model_id="deterministic-presentation",
        generated_at=datetime.now(UTC),
    )


NODE_INPUT_KEYS: dict[str, tuple[str, ...]] = {
    "intake_context": ("start_request", "scenario_context"),
    "memory_retriever": ("intake_context",),
    "planner": ("intake_context", "advisory_memories", "verification_history", "errors"),
    "supervisor_router": ("plan", "pending_specialists", "specialist_evidence"),
    "degree_audit_agent": ("intake_context", "plan", "scenario_context"),
    "policy_agent": ("intake_context", "plan", "scenario_context"),
    "course_agent": ("intake_context", "plan", "scenario_context"),
    "resolution_builder": ("plan", "specialist_evidence", "tool_results"),
    "clarification": ("verifier_decision", "clarification_pause"),
    "pre_action_verifier": ("action_candidate", "specialist_evidence", "approval_requirement"),
    "action_gate": ("action_candidate", "verifier_decision", "approval_requirement"),
    "human_approval": ("action_candidate", "approval_requirement", "approval_response"),
    "pause_checkpoint": ("approval_pause", "approval_requirement"),
    "human_admin_review": ("verifier_decision", "errors", "specialist_evidence"),
    "transaction": ("action_candidate", "approval_response", "action_receipts"),
    "observation": ("action_receipts", "tool_results"),
    "post_action_verifier": ("observation", "action_receipts", "action_candidate"),
    "final_response": ("goal_evaluation", "action_candidate", "observation", "admin_handoff"),
    "memory_updater": ("final_outcome", "goal_evaluation", "action_receipts"),
}


_CONTROL_OUTPUT_KEYS = {
    "loop_counters",
    "pending_specialists",
    "route",
    "run_status",
    "trace",
    "verification_phase",
}


def _human_label(value: str) -> str:
    return value.replace("_", " ").replace(".", " ").strip().title()


def _bounded(value: str, limit: int = 420) -> str:
    clean = " ".join(value.split())
    return clean if len(clean) <= limit else f"{clean[: limit - 1].rstrip()}…"


def _summarize_value(value: Any) -> str:
    if value is None:
        return "Not provided"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (str, int, float)):
        return _bounded(str(value))
    if isinstance(value, list):
        if not value:
            return "None"
        parts: list[str] = []
        for item in value[:5]:
            if isinstance(item, Mapping):
                item_map = _mapping(item)
                primary = next(
                    (
                        item_map.get(key)
                        for key in (
                            "purpose",
                            "summary",
                            "message",
                            "reason",
                            "decision",
                            "action",
                            "specialist",
                            "label",
                            "code",
                            "status",
                            "evidence_id",
                            "receipt_id",
                        )
                        if item_map.get(key) not in (None, "")
                    ),
                    None,
                )
                parts.append(_bounded(str(primary or _compact_mapping(item_map)), 130))
            else:
                parts.append(_bounded(str(item), 130))
        suffix = f" (+{len(value) - 5} more)" if len(value) > 5 else ""
        return "; ".join(parts) + suffix
    if isinstance(value, Mapping):
        return _bounded(_compact_mapping(_mapping(value)))
    return _bounded(str(value))


def _compact_mapping(value: dict[str, Any]) -> str:
    priority = (
        "status",
        "decision",
        "action",
        "code",
        "version",
        "specialist",
        "reason",
        "message",
        "rationale",
        "summary",
    )
    keys = [key for key in priority if value.get(key) not in (None, "")]
    if not keys:
        keys = [key for key, item in value.items() if item not in (None, "", [], {})][:4]
    parts = [f"{_human_label(key)}: {_summarize_value(value[key])}" for key in keys[:4]]
    return " · ".join(parts) or "No populated fields"


def _items_for_keys(values: dict[str, Any], keys: tuple[str, ...]) -> list[DetailItem]:
    return [
        DetailItem(label=_human_label(key), value=_summarize_value(values[key]))
        for key in keys
        if key in values and values[key] not in (None, "", [], {})
    ]


def _input_items_for_node(
    node_id: str, values: dict[str, Any], fallback: dict[str, Any] | None = None
) -> list[DetailItem]:
    keys = NODE_INPUT_KEYS.get(node_id, ("intake_context",))
    items = _items_for_keys(values, keys)
    if not items and fallback is not None:
        items = _items_for_keys(fallback, keys)
    return items or [DetailItem(label="Runtime input", value="No additional input fields")]


def _output_items(
    node_output: dict[str, Any], previous_values: dict[str, Any], values: dict[str, Any]
) -> list[DetailItem]:
    items: list[DetailItem] = []
    for key, value in node_output.items():
        if key in _CONTROL_OUTPUT_KEYS or value in (None, "", [], {}):
            continue
        if key == "tool_results":
            names = _changed_tool_names(previous_values, values)
            items.append(
                DetailItem(
                    label="Tool results",
                    value=", ".join(names) if names else "Tool result state updated",
                )
            )
        else:
            items.append(DetailItem(label=_human_label(key), value=_summarize_value(value)))
    if not items:
        route = node_output.get("route") or values.get("route")
        items.append(
            DetailItem(
                label="Routing result",
                value=_human_label(str(route)) if route else "Control state updated",
            )
        )
    return items


def _state_change_items(node_output: dict[str, Any]) -> list[DetailItem]:
    items: list[DetailItem] = []
    for key, value in node_output.items():
        if key == "trace":
            latest = value[-1] if isinstance(value, list) and value else None
            items.append(
                DetailItem(label="Trace", value=_summarize_value(latest or "Updated"))
            )
        elif key == "tool_results":
            count = len(value) if isinstance(value, Mapping) else 0
            items.append(DetailItem(label="Tool result store", value=f"{count} result(s) available"))
        else:
            items.append(DetailItem(label=_human_label(key), value=_summarize_value(value)))
    return items or [DetailItem(label="State", value="No persisted field change")]


def _changed_tool_names(
    previous_values: dict[str, Any], values: dict[str, Any]
) -> list[str]:
    before = _mapping(previous_values.get("tool_results"))
    after = _mapping(values.get("tool_results"))
    names: list[str] = []
    for key, result in after.items():
        if key not in before or before.get(key) != result:
            names.append(TOOL_NAMES.get(str(key), (_human_label(str(key)), "Runtime"))[0])
    return list(dict.fromkeys(names))


def _tool_names_for_node(
    node_id: str, previous_values: dict[str, Any], values: dict[str, Any]
) -> list[str]:
    changed = _changed_tool_names(previous_values, values)
    if changed:
        return changed
    related: dict[str, tuple[str, ...]] = {
        "degree_audit_agent": ("student_record", "degree_audit", "curriculum_lookup"),
        "policy_agent": ("policy_search", "exception_eligibility", "approval_requirement", "required_documents"),
        "course_agent": ("course_search", "course_details", "prerequisite_check", "exclusion_check", "timetable_check", "workload_check", "availability"),
        "human_approval": ("approval_request", "approval_requirement.observed"),
        "transaction": ("transaction",),
        "observation": ("transaction_status", "transaction"),
    }
    available = _mapping(values.get("tool_results"))
    return [
        TOOL_NAMES.get(key, (_human_label(key), "Runtime"))[0]
        for key in related.get(node_id, ())
        if key in available
    ]


def _reasoning_summaries(values: dict[str, Any]) -> list[ReasoningSummary]:
    summaries: list[ReasoningSummary] = []
    for item in values.get("reasoning_audit", []):
        event = _mapping(item)
        usage = _mapping(event.get("usage"))
        if not event.get("task"):
            continue
        summaries.append(
            ReasoningSummary(
                task=str(event["task"]),
                status=str(event.get("status", "UNKNOWN")),
                model_id=(str(event["model_id"]) if event.get("model_id") else None),
                applied=bool(event.get("applied")),
                safety_rule=str(event.get("safety_rule", "Deterministic safety rules remain authoritative.")),
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
            )
        )
    return summaries


def _reasoning_for_node(node_id: str, values: dict[str, Any]) -> ReasoningSummary | None:
    task = {
        "planner": "select_specialists",
        "pre_action_verifier": "assess_pre_action",
    }.get(node_id)
    if task is None:
        return None
    return next(
        (item for item in reversed(_reasoning_summaries(values)) if item.task == task),
        None,
    )


def _evidence_ids(value: Any) -> list[str]:
    found: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if key in {"evidence_id", "source_id"} and isinstance(nested, str):
                    found.append(nested)
                elif key in {"evidence_ids", "source_ids", "rule_ids"} and isinstance(nested, list):
                    found.extend(str(entry) for entry in nested if isinstance(entry, str))
                else:
                    visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return list(dict.fromkeys(found))[:30]


def _node_execution_detail(
    *,
    node_id: str,
    attempt: int,
    status: NodeStatus,
    previous_values: dict[str, Any],
    values: dict[str, Any],
    node_output: dict[str, Any],
    started_at: datetime,
) -> NodeExecutionDetail:
    return NodeExecutionDetail(
        node_id=node_id,
        attempt=attempt,
        status=status,
        input_items=_input_items_for_node(node_id, previous_values, values),
        output_items=_output_items(node_output, previous_values, values),
        state_changes=_state_change_items(node_output),
        tool_names=_tool_names_for_node(node_id, previous_values, values),
        evidence_ids=_evidence_ids(node_output),
        reasoning=_reasoning_for_node(node_id, values),
        started_at=started_at,
    )


def _parameter_items(value: Any) -> list[DetailItem]:
    parameters = _mapping(value)
    return [
        DetailItem(label=_human_label(str(key)), value=_summarize_value(item))
        for key, item in parameters.items()
    ]


def _public_parameter_items(
    value: Any,
    *,
    target_course: str | None = None,
    programme_path_label: str | None = None,
) -> list[DetailItem]:
    """Keep useful course/class facts while hiding runtime coordination IDs."""

    parameters = _mapping(value)
    items: list[DetailItem] = []
    course = parameters.get("course_code") or target_course
    if course:
        items.append(DetailItem(label="Course", value=str(course)))
    if parameters.get("offering_state_id"):
        items.append(
            DetailItem(
                label="Class index",
                value=str(parameters["offering_state_id"]).rsplit(".", 1)[-1],
            )
        )
    if parameters.get("graduation_path_id"):
        items.append(
            DetailItem(
                label="Programme path",
                value=(
                    programme_path_label
                    or str(parameters["graduation_path_id"])
                    .replace("graduation_path.", "")
                    .replace("graduation.", "")
                    .replace("path.", "")
                    .replace(".", " ")
                ),
            )
        )
    if parameters.get("retry"):
        items.append(DetailItem(label="Recovery attempt", value="Yes; live state was refreshed"))
    return items


def _plan_step_summaries(
    plan: dict[str, Any], values: dict[str, Any]
) -> list[PlanStepSummary]:
    completed = {
        str(_mapping(item).get("specialist"))
        for item in values.get("specialist_evidence", [])
        if isinstance(item, Mapping)
    }
    pending = {str(item) for item in values.get("pending_specialists", [])}
    summaries: list[PlanStepSummary] = []
    for raw in plan.get("steps", []):
        step = _mapping(raw)
        specialist = str(step["specialist"]) if step.get("specialist") else None
        status = "Completed" if specialist in completed else "Pending" if specialist in pending else "Planned"
        summaries.append(
            PlanStepSummary(
                ordinal=int(step.get("ordinal", len(summaries) + 1)),
                purpose=str(step.get("purpose", "Process the next grounded step.")),
                specialist=specialist,
                status=status,
            )
        )
    return summaries


def _evidence_summaries(values: dict[str, Any]) -> list[EvidenceSummary]:
    summaries: list[EvidenceSummary] = []
    seen: set[str] = set()
    for raw in values.get("specialist_evidence", []):
        item = _mapping(raw)
        evidence_id = str(item.get("evidence_id", ""))
        if not evidence_id or evidence_id in seen:
            continue
        seen.add(evidence_id)
        summaries.append(
            EvidenceSummary(
                specialist=str(item.get("specialist", "GENERAL")),
                summary=str(item.get("summary", "Grounded evidence collected.")),
                completeness_known=bool(item.get("completeness_known")),
                source_ids=[str(entry) for entry in item.get("source_ids", [])],
                rule_ids=[str(entry) for entry in item.get("rule_ids", [])],
            )
        )
    return summaries


def _clarification_details(values: dict[str, Any]) -> list[DetailItem]:
    pause = _mapping(values.get("clarification_pause"))
    response = _mapping(values.get("clarification_response"))
    details: list[DetailItem] = []
    if pause.get("question"):
        details.append(DetailItem(label="Question", value=str(pause["question"])))
    if pause.get("missing_fields"):
        details.append(DetailItem(label="Required fields", value=_summarize_value(pause["missing_fields"])))
    for key, value in _mapping(response.get("answers")).items():
        details.append(DetailItem(label=_human_label(str(key)), value=_summarize_value(value)))
    return details


def _approval_details(values: dict[str, Any]) -> list[DetailItem]:
    requirement = _mapping(values.get("approval_requirement"))
    response = _mapping(values.get("approval_response"))
    fields = (
        ("approval_id", "Approval ID"),
        ("approver_role", "Approver"),
        ("requested_action", "Requested action"),
        ("basis", "Basis"),
        ("observable_status", "Observed status"),
        ("version", "Version"),
    )
    details = [
        DetailItem(label=label, value=_summarize_value(requirement[key]))
        for key, label in fields
        if requirement.get(key) not in (None, "", [], {})
    ]
    if response.get("status"):
        details.append(DetailItem(label="Latest response", value=str(response["status"])))
    if requirement.get("required_document_ids"):
        details.append(
            DetailItem(label="Required documents", value=_summarize_value(requirement["required_document_ids"]))
        )
    return details


def _tool_summaries(values: dict[str, Any]) -> list[ToolSummary]:
    raw_results = values.get("tool_results")
    if not isinstance(raw_results, Mapping):
        return []
    summaries: list[ToolSummary] = []
    for key, raw in raw_results.items():
        result = _mapping(raw)
        name, group = TOOL_NAMES.get(
            str(key), (str(key).replace("_", " ").title(), "Runtime")
        )
        data = result.get("data")
        count = len(data) if isinstance(data, (dict, list)) else int(data is not None)
        error = _mapping(result.get("error"))
        summary = (
            str(error.get("message"))
            if error
            else f"Returned {count} processed field{'s' if count != 1 else ''}."
        )
        provenance = result.get("provenance")
        summaries.append(
            ToolSummary(
                key=str(key),
                name=name,
                group=group,
                status=str(result.get("status", "UNKNOWN")).replace("_", " ").title(),
                summary=summary,
                provenance_count=len(provenance) if isinstance(provenance, list) else 0,
            )
        )
    return summaries


def _memory_summaries(
    values: dict[str, Any], narratives: Mapping[str, str] | None = None
) -> list[MemorySummary]:
    raw = values.get("advisory_memories")
    if not isinstance(raw, list):
        return []
    summaries: list[MemorySummary] = []
    seen: set[str] = set()
    for item in raw:
        memory = _mapping(item)
        memory_id = str(memory.get("memory_id", ""))
        if not memory_id or memory_id in seen:
            continue
        seen.add(memory_id)
        summaries.append(
            MemorySummary(
                memory_id=memory_id,
                label=str(memory.get("case_type", "Verified resolution pattern")),
                summary=str(
                    memory.get("successful_strategy")
                    or memory.get("applicability")
                    or "Deidentified advisory pattern."
                ),
                relevance=(
                    float(memory["relevance"])
                    if isinstance(memory.get("relevance"), (int, float))
                    else None
                ),
                applicability=str(memory.get("applicability", "Use only when current evidence confirms the same conditions.")),
                recovery_steps=[str(entry) for entry in memory.get("recovery_steps", [])],
                failed_patterns=[str(entry) for entry in memory.get("failed_strategy_patterns", [])],
                tags=[str(entry) for entry in memory.get("tags", [])],
                verified_at=memory.get("verified_at"),
                narrative=(narratives or {}).get(memory_id),
            )
        )
    return summaries


def _humanize_action(value: str | None) -> str:
    if not value:
        return "Resolution"
    return {
        "SUBMIT_REGISTRATION": "course registration",
        "SUBMIT_EXCEPTION": "exception request",
        "SUBMIT_WAIVER": "prerequisite waiver request",
        "REQUEST_APPROVAL": "approval request",
    }.get(value, value.replace("_", " ").lower())


def _approval_basis_label(requirement: dict[str, Any]) -> str:
    basis = str(requirement.get("basis", "declared approval route"))
    rules = [str(item) for item in requirement.get("basis_rule_ids", [])]
    references = [_policy_reference(item) for item in rules]
    if basis == "VERIFIED_PUBLIC_ROUTE" and references:
        item = references[0]
        return f"Collected public route: {item['name']} ({item['reference']})"
    if references:
        names = ", ".join(f"{item['name']} ({item['reference']})" for item in references[:2])
        return f"Simulated prototype basis: {names}"
    if "SIMULATED" in basis or "PROTOTYPE" in basis:
        return f"Simulated prototype basis: {_human_label(basis)}"
    return _human_label(basis)


def _human_decision_evidence(
    values: dict[str, Any], *, limit: int = 5
) -> list[str]:
    evidence = _presentation_case_evidence(values)
    academic = _mapping(evidence.get("academic"))
    policy = _mapping(evidence.get("policy_and_documents"))
    course = _mapping(evidence.get("course"))
    items: list[str] = []
    if academic.get("earned_aus") and academic.get("required_aus"):
        outstanding = [
            str(code)
            for requirement in academic.get("outstanding_requirements", [])
            for code in _mapping(requirement).get("courses", [])
        ]
        items.append(
            f"Degree audit: {academic['earned_aus']} of {academic['required_aus']} AUs are recorded"
            f"; {', '.join(outstanding) if outstanding else 'a graduation requirement'} remains outstanding."
        )
    if course.get("code") and course.get("prerequisite_result"):
        prerequisite = course.get("catalogue_prerequisite") or "the represented catalogue prerequisite"
        items.append(
            f"Prerequisite: {course['code']} requires {prerequisite}; the current check returned "
            f"{str(course['prerequisite_result']).lower()}."
        )
    classes = [
        _mapping(item) for item in course.get("classes", []) if _mapping(item).get("class_index")
    ]
    if classes:
        described = _preferred_feasible_class(course) or classes[0]
        timetable = next(
            (
                _mapping(item).get("result")
                for item in course.get("timetable_results", [])
                if _mapping(item).get("class_index") == described.get("class_index")
            ),
            None,
        )
        vacancy_text = (
            f" with {described['vacancies']} simulated vacancies"
            if described.get("vacancies") is not None
            else ""
        )
        items.append(
            f"Course feasibility: class {described['class_index']} is "
            f"{'available' if described.get('available') else 'not available'}"
            f"{vacancy_text}"
            f"; timetable is {str(timetable).lower() if timetable else 'not yet confirmed'} and workload is "
            f"{str(course.get('workload_result', 'not yet confirmed')).lower()}."
        )
    references = [_mapping(item) for item in policy.get("policy_references", [])]
    if references:
        names = "; ".join(
            f"{item.get('name')} [{item.get('provenance')}]" for item in references[:2]
        )
        items.append(f"Policy basis: {names}.")
    documents = [_mapping(item) for item in policy.get("documents", [])]
    if documents:
        provided = [str(item.get("name")) for item in documents if item.get("provided")]
        missing = [str(item) for item in policy.get("missing_documents", [])]
        items.append(
            f"Documents: {', '.join(provided) if provided else 'none are recorded as provided'}"
            f"; {', '.join(missing) + ' missing' if missing else 'no required document is recorded as missing'}."
        )
    return items[:limit]


def _approval_reason(
    values: dict[str, Any],
    profile: ScenarioSummary,
    *,
    requested_action: str,
    approver_role: str,
    approval_basis: str,
) -> str:
    evidence = _presentation_case_evidence(values)
    academic = _mapping(evidence.get("academic"))
    course = _mapping(evidence.get("course"))
    policy = _mapping(evidence.get("policy_and_documents"))
    target = str(course.get("code") or "the requested course")
    fragments = [
        f"This Year {profile.study_year} {profile.programme} case concerns {target}."
    ]
    if academic.get("earned_aus") and academic.get("required_aus"):
        fragments.append(
            f"The represented degree audit records {academic['earned_aus']} of "
            f"{academic['required_aus']} AUs and keeps {target} outstanding."
        )
    if course.get("prerequisite_result"):
        prerequisite = course.get("catalogue_prerequisite") or "the represented prerequisite"
        fragments.append(
            f"The prerequisite check against {prerequisite} returned "
            f"{str(course['prerequisite_result']).lower()}."
        )
    feasible = _preferred_feasible_class(course)
    if feasible:
        fragments.append(
            f"Represented class {feasible.get('class_index')} is available"
            f"{f' with {feasible.get('vacancies')} simulated vacancies' if feasible.get('vacancies') is not None else ''}, "
            f"and the workload check is {str(course.get('workload_result', 'not confirmed')).lower()}."
        )
    documents = [_mapping(item) for item in policy.get("documents", [])]
    provided = [str(item.get("name")) for item in documents if item.get("provided")]
    if provided:
        fragments.append(f"The case includes {', '.join(provided)}.")
    fragments.append(
        f"Under {approval_basis}, the prepared {requested_action} requires permission from "
        f"{approver_role}, which must decide whether it "
        "is authorised; eligibility and complete documents do not grant approval by themselves."
    )
    if "Simulated prototype" in approval_basis:
        fragments.append("That approval basis is a hackathon simulation, not a general official NTU rule.")
    return _bounded(" ".join(fragments), 1_400)


def _clarification_reason(
    fields: list[str], values: dict[str, Any], profile: ScenarioSummary
) -> str:
    friendly = ", ".join(field.replace("_", " ") for field in fields)
    evidence = _presentation_case_evidence(values)
    course = _mapping(evidence.get("course"))
    academic = _mapping(evidence.get("academic"))
    target = str(course.get("code") or "the requested course")
    known = (
        f" The represented audit currently records {academic['earned_aus']} of {academic['required_aus']} AUs."
        if academic.get("earned_aus") and academic.get("required_aus")
        else ""
    )
    return _bounded(
        f"For this Year {profile.study_year} {profile.programme} request concerning {target}, "
        f"the system cannot safely determine the correct exception route while {friendly} is missing."
        f"{known} The missing answer can change the applicable curriculum, policy, or action, "
        "so no registration or exception will be submitted before it is confirmed.",
        1_200,
    )


def _final_response_summary(
    values: dict[str, Any],
    final: dict[str, Any],
    *,
    narrative: str | None = None,
) -> FinalResponseSummary:
    intake = _mapping(values.get("intake_context"))
    candidate = _mapping(values.get("action_candidate"))
    goal = _mapping(final.get("goal_evaluation"))
    evaluation = goal or _mapping(values.get("goal_evaluation"))
    action = str(candidate["action"]) if candidate.get("action") else None
    action_label = _humanize_action(action)
    scenario = _mapping(values.get("scenario_context"))
    target_course = _mapping(scenario.get("initial_state")).get("target_course")
    programme_path_label = _tool_result_data(values, "student_record").get(
        "study_plan_path_label"
    )
    parameters = _public_parameter_items(
        candidate.get("parameters"),
        target_course=str(target_course or "") or None,
        programme_path_label=(
            str(programme_path_label) if programme_path_label else None
        ),
    )
    parameter_phrase = ", ".join(
        f"{item.label.lower()} {item.value}"
        for item in parameters
        if item.label != "Recovery attempt"
    )
    evidence = _evidence_summaries(values)
    academic_basis = [item.summary for item in evidence if item.specialist == "DEGREE_AUDIT"]
    course_basis = [item.summary for item in evidence if item.specialist == "COURSE"]
    if course_basis:
        academic_basis.extend(course_basis)
    policy_basis = [item.summary for item in evidence if item.specialist == "POLICY"]
    approval = _approval_state(values)
    requirement = _mapping(values.get("approval_requirement"))
    approver = str(requirement.get("approver_role", "the designated approving role"))
    decision_reason = str(requirement.get("decision_reason") or "").strip()
    approval_summary = (
        f"{approver} returned {approval.replace('_', ' ').lower()}"
        f"{f': {decision_reason.rstrip('.')}' if decision_reason else ''}."
        if requirement.get("required")
        else "No separate approval was required for the verified action."
    )
    receipts = [
        _mapping(item)
        for item in values.get("action_receipts", [])
        if isinstance(item, Mapping)
    ]
    final_receipt = next(
        (item for item in reversed(receipts) if not item.get("intermediate")),
        receipts[-1] if receipts else {},
    )
    observation = _mapping(values.get("observation"))
    if final_receipt:
        result_text = str(
            final_receipt.get("result_code", final_receipt.get("status", "UNKNOWN"))
        ).replace("_", " ").lower()
        transaction_summary = (
            f"{_humanize_action(str(final_receipt.get('action', action or ''))).capitalize()} "
            f"returned {result_text}. The system retained a transaction receipt for the case record."
        )
    elif observation:
        transaction_summary = str(observation.get("message", "The runtime outcome was observed."))
    else:
        transaction_summary = "No transaction was executed; the case ended at a human or safety boundary."
    status = str(final.get("status", "UNKNOWN"))
    complete = bool(evaluation.get("complete"))
    predicate_results = [
        _mapping(item) for item in evaluation.get("predicate_results", []) if isinstance(item, Mapping)
    ]
    satisfied = sum(bool(item.get("satisfied")) for item in predicate_results)
    total = len(predicate_results)
    handoff = _mapping(values.get("admin_handoff"))
    if status == "DONE":
        headline = f"{action_label.capitalize()} verified"
        recovered = int(_mapping(values.get("loop_counters")).get("tool_retries", 0)) > 0
        resolution_summary = (
            f"The {action_label} completed"
            f"{f' for {parameter_phrase}' if parameter_phrase else ''} and the post-action verifier confirmed "
            f"{satisfied} of {total} required condition(s)."
        )
        resolution_summary = resolution_summary.replace(
            "the post-action verifier confirmed", "the final check confirmed"
        )
        if action == "SUBMIT_REGISTRATION":
            next_steps = [
                "Confirm that the course and class index appear in the student registration record.",
                "Keep the transaction receipt; if the class changes again, request a fresh availability check before another attempt.",
            ]
            if recovered:
                resolution_summary += " The first attempt did not complete, so availability was refreshed before the verified alternative was used."
        elif action == "SUBMIT_WAIVER":
            next_steps = [
                "Monitor the prerequisite-waiver record until the curriculum or registration view reflects the approved exception.",
                "Keep the submitted exchange transcript, course mappings, approval, and receipt together.",
            ]
        else:
            next_steps = [
                "Monitor the exception case until the programme record reflects the approved outcome.",
                "Keep the approval, supporting documents, and transaction receipt together.",
            ]
    elif status == "ADMIN_HANDOFF":
        headline = "Administrative review required"
        resolution_summary = str(
            handoff.get("reason")
            or "No safe autonomous resolution remained, so the evidence package was prepared for review."
        )
        next_steps = [
            str(handoff.get("recommended_next_step") or "Contact the identified CCDS administrative role with the prepared evidence."),
        ]
    else:
        headline = status.replace("_", " ").title()
        resolution_summary = str(final.get("message", "The run ended at a safe boundary."))
        next_steps = ["Review the outstanding requirements before attempting another action."]
    if status == "DONE":
        validity_reasons = list(dict.fromkeys([
            *(academic_basis[:2]),
            *(policy_basis[:1]),
            approval_summary,
            (
                f"The final check confirmed all {total} required outcome condition(s)."
                if total
                else "The final check confirmed that the requested outcome is now present in the simulated student record."
            ),
        ]))
        reasoning_heading = "Why this is valid"
    elif status == "ADMIN_HANDOFF":
        validity_reasons = list(dict.fromkeys([
            resolution_summary,
            "The system stopped before an unsupported action because the available evidence or authority was insufficient.",
        ]))
        reasoning_heading = "Why human review is required"
    else:
        validity_reasons = [
            "The case stopped at a safety boundary because the available information did not support a verified action."
        ]
        reasoning_heading = "Why the case stopped here"
    message = (
        f"{resolution_summary} {approval_summary} {transaction_summary}"
        if status == "DONE"
        else resolution_summary
    )
    errors = [
        str(_mapping(item).get("message"))
        for item in values.get("errors", [])
        if isinstance(item, Mapping) and _mapping(item).get("message")
    ]
    limitations = list(dict.fromkeys([
        *errors,
        "Student, offering, approval and transaction records are simulated for this hackathon prototype.",
    ]))
    return FinalResponseSummary(
        status=status,
        headline=headline,
        message=_bounded(message, 1_600),
        request_summary=str(intake.get("request_text", "Request text was not retained.")),
        resolution_summary=resolution_summary,
        reasoning_heading=reasoning_heading,
        validity_reasons=validity_reasons,
        action=action,
        action_parameters=parameters,
        academic_basis=academic_basis,
        policy_basis=policy_basis,
        approval_summary=approval_summary,
        transaction_summary=transaction_summary,
        next_steps=next_steps,
        limitations=limitations,
        evidence_ids=[str(item) for item in final.get("evidence_ids", [])],
        academic_verified=complete,
        policy_verified=bool(policy_basis) or bool(final.get("evidence_ids")),
        approval_state=approval,
        completed_at=final.get("completed_at"),
        narrative=narrative,
    )


def _approval_state(values: dict[str, Any]) -> str:
    response = _mapping(values.get("approval_response"))
    if response.get("status"):
        return str(response["status"])
    candidate = _mapping(values.get("action_candidate"))
    return "REQUIRED" if candidate.get("requires_approval") else "NOT_REQUIRED"


def _traversed_edges(
    values: dict[str, Any], timeline: list[TimelineItem]
) -> list[str]:
    traversed: list[str] = []
    if "intake_context" in values or any(
        item.node_id == "intake_context" for item in timeline
    ):
        traversed.append("e-student-intake")
    trace = values.get("trace")
    if not isinstance(trace, list):
        return traversed
    for item in trace:
        event = _mapping(item)
        edge_id = TRACE_EDGE_IDS.get(
            (str(event.get("source", "")), str(event.get("destination", "")))
        )
        if edge_id and edge_id not in traversed:
            traversed.append(edge_id)
    return traversed


__all__ = ["RunService"]
