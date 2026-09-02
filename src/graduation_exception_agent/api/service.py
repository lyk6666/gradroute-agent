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
from graduation_exception_agent.runtime import ScenarioRuntimeFactory


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
        intake: Any,
        profile_summary: ScenarioSummary,
    ) -> None:
        self.run_id = run_id
        self.scenario_id = scenario_id
        self.thread_id = thread_id
        self.mode = mode
        self.plane = plane
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
        runtime = self._factory.build(summary.scenario_id)
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
                payload = ApprovalResumePayload(
                    approval_id=str(token["approval_id"]),
                    expected_version=int(token["approval_version"]),
                    observed_version=int(token["approval_version"]),
                    status=ApprovalStatus(request.status),
                    decision_reason=request.decision_reason,
                    observed_at=datetime.now(UTC),
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
        self._apply_narration(record, node_id)
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
            pause = PauseSummary(
                kind="clarification",
                title="Clarification required",
                message=str(interrupt_value["question"]),
                fields=[str(item) for item in interrupt_value["missing_fields"]],
                impact=str(interrupt_value["impact"]),
            )
            token = {
                "clarification_id": interrupt_value["clarification_id"],
                "impact": interrupt_value["impact"],
            }
        elif kind == "APPROVAL":
            node_id = "pause_checkpoint"
            pause = PauseSummary(
                kind="approval",
                title="Approval observation required",
                message=(
                    f"Re-check the authoritative {interrupt_value['approver_role']} "
                    "decision before continuing."
                ),
                fields=[],
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

    def _apply_narration(self, record: RunRecord, node_id: str) -> None:
        """Narrate the latest UI-safe record without changing execution decisions."""

        narrator = self._narrator
        if narrator is None:
            return
        with record.lock:
            detail = record.node_details.get(node_id)
            if detail is None:
                return
            payload = self._narration_payload(record, node_id, detail)
        try:
            result = narrator.narrate(payload)
        except Exception:
            return
        generated_at = datetime.now(UTC)
        with record.lock:
            latest = record.node_details.get(node_id)
            if latest is None or latest.attempt != detail.attempt:
                return
            record.node_details[node_id] = latest.model_copy(
                update={
                    "narrative": NodeNarrativeSummary(
                        input=result.node_input,
                        output=result.node_output,
                        state=result.state_change,
                        action=result.action,
                        model_id=narrator.model_id,
                        generated_at=generated_at,
                    )
                }
            )
            record.working_narrative = result.working_state
            record.thread_narrative = result.thread_memory
            record.working_known = list(result.working_known)
            record.working_next = result.working_next or None
            record.working_attention = result.working_attention or None
            record.thread_highlights = list(result.thread_highlights)
            record.memory_narratives.update(
                {item.memory_id: item.explanation for item in result.memories}
            )
            if result.final_response:
                record.final_narrative = result.final_response

    def _narration_payload(
        self,
        record: RunRecord,
        node_id: str,
        detail: NodeExecutionDetail,
    ) -> dict[str, Any]:
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
            "observed_input": _narration_items(
                detail.input_items, exclude_context=True
            ),
            "observed_output": _narration_items(detail.output_items),
            "persisted_changes": _narration_items(detail.state_changes),
            "tools_used": list(detail.tool_names),
            "evidence_references": list(detail.evidence_ids),
            "working_state": snapshot.working_state.model_dump(
                mode="json", exclude={"narrative", "reasoning"}
            ),
            "thread_memory": snapshot.thread_memory.model_dump(
                mode="json", exclude={"narrative"}
            ),
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
                evidence=_evidence_summaries(values),
                action=(str(candidate["action"]) if candidate.get("action") else None),
                action_parameters=action_parameters,
                outstanding_items=list(dict.fromkeys(outstanding)),
                errors=list(dict.fromkeys(errors)),
                reasoning=reasoning,
                narrative=record.working_narrative,
                narrative_known=list(record.working_known),
                narrative_next=record.working_next,
                narrative_attention=record.working_attention,
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
                narrative=record.thread_narrative,
                narrative_highlights=list(record.thread_highlights),
            ),
            pause=record.pause,
            final_response=response,
            error=record.error,
            latest_event_sequence=record.latest_event_sequence,
        )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


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
        "registered_courses": list(profile.registered_courses),
        "supporting_documents": list(profile.supporting_documents),
        "request": str(
            intake.get("request_text")
            or getattr(record.intake, "request_text", profile.request_text)
        ),
        "target_course": initial.get("target_course"),
        "current_step": snapshot.working_state.current_step,
    }


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
    parameters = _parameter_items(candidate.get("parameters"))
    parameter_phrase = ", ".join(f"{item.label.lower()} {item.value}" for item in parameters)
    evidence = _evidence_summaries(values)
    academic_basis = [item.summary for item in evidence if item.specialist == "DEGREE_AUDIT"]
    course_basis = [item.summary for item in evidence if item.specialist == "COURSE"]
    if course_basis:
        academic_basis.extend(course_basis)
    policy_basis = [item.summary for item in evidence if item.specialist == "POLICY"]
    approval = _approval_state(values)
    requirement = _mapping(values.get("approval_requirement"))
    approver = str(requirement.get("approver_role", "the designated approving role"))
    approval_summary = (
        f"{approver} returned {approval.replace('_', ' ').lower()}."
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
        transaction_summary = (
            f"{_humanize_action(str(final_receipt.get('action', action or ''))).capitalize()} "
            f"returned {str(final_receipt.get('result_code', final_receipt.get('status', 'UNKNOWN'))).replace('_', ' ').lower()}"
            f" with receipt {final_receipt.get('receipt_id', 'not recorded')}."
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
        resolution_summary = (
            f"The runtime completed the {action_label}"
            f"{f' for {parameter_phrase}' if parameter_phrase else ''} and the post-action verifier confirmed "
            f"{satisfied} of {total} required condition(s)."
        )
        next_steps = [
            "Keep the transaction receipt and supporting evidence for reference.",
            "Confirm the resulting registration or case status in the relevant student system.",
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
