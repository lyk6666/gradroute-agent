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
    FinalResponseSummary,
    MemorySummary,
    NodeStatus,
    PauseSummary,
    RunEvent,
    RunMode,
    RunSnapshot,
    RunStatus,
    ScenarioSummary,
    StartRunRequest,
    ThreadMemorySummary,
    TimelineItem,
    ToolSummary,
    WorkingStateSummary,
)
from graduation_exception_agent.config import AppSettings
from graduation_exception_agent.data.simulated import (
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
    ) -> None:
        self.run_id = run_id
        self.scenario_id = scenario_id
        self.thread_id = thread_id
        self.mode = mode
        self.plane = plane
        self.intake = intake
        self.lock = RLock()
        self.condition = Condition(self.lock)
        self.status = RunStatus.QUEUED
        self.current_node: str | None = None
        self.node_statuses = {node_id: NodeStatus.IDLE for node_id in NODE_IDS}
        self.node_statuses["student_case"] = NodeStatus.COMPLETED
        self.timeline: list[TimelineItem] = []
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
        self, settings: AppSettings, *, node_delay_seconds: float = 0.075
    ) -> None:
        if node_delay_seconds < 0:
            raise ValueError("node_delay_seconds must be nonnegative")
        self._settings = settings
        self._node_delay_seconds = node_delay_seconds
        self._data_root = Path(settings.data_dir)
        self._factory = ScenarioRuntimeFactory.from_data_directory(self._data_root)
        self._memory = InMemoryExperienceMemory()
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
        summaries: dict[str, ScenarioSummary] = {}
        for scenario in scenarios:
            split = scenario.split.value
            if split not in {"demo", "evaluation"}:
                continue
            student = students[scenario.student_id]
            case = cases[scenario.case_id]
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
            )
        return summaries, cases

    def scenarios(self) -> list[ScenarioSummary]:
        return [self._scenario_summaries[key] for key in sorted(self._scenario_summaries)]

    def start(self, request: StartRunRequest) -> RunSnapshot:
        summary = self._scenario_summaries.get(request.scenario_id)
        if summary is None:
            raise KeyError(f"unknown runnable scenario {request.scenario_id!r}")
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
            request_text=case.reason,
            problem_type=ExceptionCaseType(case.problem_type),
            received_at=case.scenario_time,
            thread_id=thread_id,
            submission_ready=case.submission_ready,
            unresolved_questions=list(case.unresolved_questions),
        )
        record = RunRecord(
            run_id=run_id,
            scenario_id=summary.scenario_id,
            thread_id=thread_id,
            mode=request.mode,
            plane=plane,
            intake=intake,
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
                snapshot = record.plane.state(record.thread_id)
                values = dict(snapshot.values)
                node_id = self._ui_node(backend_node, values)
                self._node_update(record, node_id, values)
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
        self, record: RunRecord, node_id: str, values: dict[str, Any]
    ) -> None:
        with record.lock:
            if record.current_node and record.current_node != node_id:
                if record.node_statuses[record.current_node] is NodeStatus.RUNNING:
                    record.node_statuses[record.current_node] = NodeStatus.COMPLETED
            record.current_node = node_id
            record.node_statuses[node_id] = NodeStatus.RUNNING
            record.values = values
        self._publish(record, "node.started", f"{NODE_LABELS[node_id]} started.", node_id)
        if self._node_delay_seconds:
            sleep(self._node_delay_seconds)
        occurred_at = datetime.now(UTC)
        with record.lock:
            record.node_statuses[node_id] = NodeStatus.COMPLETED
            record.timeline.append(
                TimelineItem(
                    sequence=len(record.timeline) + 1,
                    node_id=node_id,
                    label=NODE_LABELS[node_id],
                    status=NodeStatus.COMPLETED,
                    occurred_at=occurred_at,
                )
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
            record.timeline.append(
                TimelineItem(
                    sequence=len(record.timeline) + 1,
                    node_id=node_id,
                    label=NODE_LABELS[node_id],
                    status=NodeStatus.WAITING,
                    occurred_at=datetime.now(UTC),
                )
            )
        self._publish(record, "run.waiting", pause.message, node_id)

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
            goal = _mapping(final.get("goal_evaluation"))
            response = FinalResponseSummary(
                status=str(final.get("status", "UNKNOWN")),
                message=str(final.get("message", "Run ended without a response message.")),
                evidence_ids=[str(item) for item in final.get("evidence_ids", [])],
                academic_verified=bool(goal.get("complete")),
                policy_verified=bool(final.get("evidence_ids")),
                approval_state=_approval_state(values),
                completed_at=final.get("completed_at"),
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
            ),
            tools=_tool_summaries(values),
            long_term_memory=_memory_summaries(values),
            thread_memory=ThreadMemorySummary(
                trace_events=len(trace),
                clarifications=int("clarification_response" in values),
                checkpoints=len(record.timeline),
                pause_state=record.pause.title if record.pause else "None",
                latest_checkpoint=(
                    record.timeline[-1].label if record.timeline else "Run queued"
                ),
            ),
            pause=record.pause,
            final_response=response,
            error=record.error,
            latest_event_sequence=record.latest_event_sequence,
        )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


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


def _memory_summaries(values: dict[str, Any]) -> list[MemorySummary]:
    raw = values.get("advisory_memories")
    if not isinstance(raw, list):
        return []
    summaries: list[MemorySummary] = []
    for item in raw:
        memory = _mapping(item)
        summaries.append(
            MemorySummary(
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
            )
        )
    return summaries


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
