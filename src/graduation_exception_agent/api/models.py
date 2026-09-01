"""Versioned, evaluator-safe schemas exposed to the Stage 8 frontend."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from graduation_exception_agent.evaluation.models import (
    CampaignMetricsSummary,
    EvaluationRunResult,
)


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


DataProvenance = Literal["real", "simulated", "derived", "restricted"]
DataDomain = Literal["academic", "operational", "cases", "governance"]


class DataColumn(ApiModel):
    key: str
    label: str
    kind: Literal["text", "number", "status", "date", "list"] = "text"


class DataDatasetSummary(ApiModel):
    dataset_id: str
    domain: DataDomain
    label: str
    description: str
    provenance: DataProvenance
    record_count: int
    accessible: bool = True
    columns: list[DataColumn] = Field(default_factory=list)
    default_sort: str | None = None


class DataDomainSummary(ApiModel):
    domain: DataDomain
    label: str
    description: str
    dataset_ids: list[str]


class DataCatalogStats(ApiModel):
    datasets: int
    accessible_records: int
    real_records: int
    simulated_records: int
    restricted_records: int


class DataCatalogResponse(ApiModel):
    api_version: Literal["1.0"] = "1.0"
    domains: list[DataDomainSummary]
    datasets: list[DataDatasetSummary]
    stats: DataCatalogStats


class DataField(ApiModel):
    label: str
    value: str


class DataSection(ApiModel):
    title: str
    fields: list[DataField]


class DataRelationship(ApiModel):
    label: str
    dataset_id: str
    record_ids: list[str]
    total_count: int


class DataRecord(ApiModel):
    record_id: str
    title: str
    subtitle: str = ""
    provenance: DataProvenance
    status: str | None = None
    cells: dict[str, str]
    sections: list[DataSection] = Field(default_factory=list)
    relationships: list[DataRelationship] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    lineage_ids: list[str] = Field(default_factory=list)
    quality_notes: list[str] = Field(default_factory=list)


class DataFilterOptions(ApiModel):
    programmes: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)


class DataPageResponse(ApiModel):
    api_version: Literal["1.0"] = "1.0"
    dataset: DataDatasetSummary
    page: int
    page_size: int
    total: int
    records: list[DataRecord]
    filters: DataFilterOptions


class EvaluationCampaignArtifact(ApiModel):
    lane: Literal["fixture", "live"]
    updated_at: datetime
    metrics: CampaignMetricsSummary


class EvaluationCampaignsResponse(ApiModel):
    api_version: Literal["1.0"] = "1.0"
    campaigns: list[EvaluationCampaignArtifact]


class EvaluationFilterOptions(ApiModel):
    families: list[str] = Field(default_factory=list)
    memory_conditions: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)


class EvaluationRunsResponse(ApiModel):
    api_version: Literal["1.0"] = "1.0"
    lane: Literal["fixture", "live"]
    page: int
    page_size: int
    total: int
    records: list[EvaluationRunResult]
    filters: EvaluationFilterOptions


class EvaluationScenarioRecord(ApiModel):
    scenario_id: str
    family: str
    expected_outcome: str
    passed_runs: int
    consistency: str
    empty_passed: bool
    relevant_passed: bool
    misleading_passed: bool
    average_tool_calls: float
    average_graph_steps: float
    average_latency_ms: float
    total_tokens: int
    violation_codes: list[str] = Field(default_factory=list)


class EvaluationScenariosResponse(ApiModel):
    api_version: Literal["1.0"] = "1.0"
    lane: Literal["fixture", "live"]
    page: int
    page_size: int
    total: int
    records: list[EvaluationScenarioRecord]
    filters: EvaluationFilterOptions


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
    "DataCatalogResponse",
    "DataCatalogStats",
    "DataColumn",
    "DataDatasetSummary",
    "DataDomainSummary",
    "DataField",
    "DataFilterOptions",
    "DataPageResponse",
    "DataRecord",
    "DataRelationship",
    "DataSection",
    "EvaluationCampaignArtifact",
    "EvaluationCampaignsResponse",
    "EvaluationFilterOptions",
    "EvaluationRunsResponse",
    "EvaluationScenarioRecord",
    "EvaluationScenariosResponse",
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
