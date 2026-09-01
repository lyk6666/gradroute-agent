"""Versioned, evaluator-safe schemas exposed to the Stage 8 frontend."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunMode(StrEnum):
    NORMAL = "normal"
    STEP = "step"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


class NodeStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    WAITING = "waiting"
    FAILED = "failed"
    SKIPPED = "skipped"


class ScenarioSummary(ApiModel):
    scenario_id: str
    family: str
    split: Literal["demo", "evaluation"]
    title: str
    challenge: str
    case_type: str
    student_id: str
    programme: str
    cohort: str
    study_year: int
    request_text: str


class TimelineItem(ApiModel):
    sequence: int
    node_id: str
    label: str
    status: NodeStatus
    occurred_at: datetime


class ToolSummary(ApiModel):
    key: str
    name: str
    group: str
    status: str
    summary: str
    provenance_count: int = 0


class MemorySummary(ApiModel):
    label: str
    summary: str
    relevance: float | None = None
    advisory_only: bool = True


class PauseSummary(ApiModel):
    kind: Literal["clarification", "approval"]
    title: str
    message: str
    fields: list[str] = Field(default_factory=list)
    impact: str | None = None


class FinalResponseSummary(ApiModel):
    status: str
    message: str
    evidence_ids: list[str] = Field(default_factory=list)
    academic_verified: bool
    policy_verified: bool
    approval_state: str
    completed_at: datetime | None = None


class WorkingStateSummary(ApiModel):
    current_step: str
    plan: str
    route: str
    replans: int
    max_replans: int
    tool_retries: int
    max_tool_retries: int
    total_steps: int
    max_total_steps: int
    status: str
    candidate_resolution: str


class ThreadMemorySummary(ApiModel):
    trace_events: int
    clarifications: int
    checkpoints: int
    pause_state: str
    latest_checkpoint: str


class RunSnapshot(ApiModel):
    api_version: Literal["1.0"] = "1.0"
    run_id: str
    scenario_id: str
    thread_id: str
    mode: RunMode
    status: RunStatus
    can_advance: bool = False
    current_node: str | None = None
    node_statuses: dict[str, NodeStatus]
    traversed_edges: list[str] = Field(default_factory=list)
    timeline: list[TimelineItem] = Field(default_factory=list)
    working_state: WorkingStateSummary
    tools: list[ToolSummary] = Field(default_factory=list)
    long_term_memory: list[MemorySummary] = Field(default_factory=list)
    thread_memory: ThreadMemorySummary
    pause: PauseSummary | None = None
    final_response: FinalResponseSummary | None = None
    error: str | None = None
    latest_event_sequence: int = 0


class StartRunRequest(ApiModel):
    scenario_id: str
    mode: RunMode = RunMode.NORMAL


class StartRunResponse(ApiModel):
    run_id: str
    events_url: str
    snapshot: RunSnapshot


class ClarificationResumeRequest(ApiModel):
    kind: Literal["clarification"]
    answers: dict[str, Any] = Field(min_length=1)


class ApprovalResumeRequest(ApiModel):
    kind: Literal["approval"]
    status: Literal["PENDING", "APPROVED", "REJECTED"] = "PENDING"
    decision_reason: str | None = None


class RunEvent(ApiModel):
    sequence: int
    event_type: str
    occurred_at: datetime
    run_id: str
    node_id: str | None = None
    message: str
    snapshot: RunSnapshot


__all__ = [
    "ApprovalResumeRequest",
    "ClarificationResumeRequest",
    "FinalResponseSummary",
    "MemorySummary",
    "NodeStatus",
    "PauseSummary",
    "RunEvent",
    "RunMode",
    "RunSnapshot",
    "RunStatus",
    "ScenarioSummary",
    "StartRunRequest",
    "StartRunResponse",
    "ThreadMemorySummary",
    "TimelineItem",
    "ToolSummary",
    "WorkingStateSummary",
]
