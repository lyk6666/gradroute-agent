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
    earned_aus: str
    completed_courses: list[str] = Field(default_factory=list)
    registered_courses: list[str] = Field(default_factory=list)
    supporting_documents: list[str] = Field(default_factory=list)
    # Demo cases may reveal the expected explanation for teaching and judging.
    # Evaluation cases deliberately keep this evaluator-only field hidden.
    expected_response: str | None = None


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


class DetailItem(ApiModel):
    label: str
    value: str


class ReasoningSummary(ApiModel):
    task: str
    status: str
    model_id: str | None = None
    applied: bool
    safety_rule: str
    input_tokens: int = 0
    output_tokens: int = 0


class NodeNarrativeSummary(ApiModel):
    summary: str
    next_step: str | None = None
    input: str
    output: str
    state: str
    action: str
    model_id: str
    generated_at: datetime


class NodeExecutionDetail(ApiModel):
    node_id: str
    attempt: int = Field(ge=1)
    status: NodeStatus
    input_items: list[DetailItem] = Field(default_factory=list)
    output_items: list[DetailItem] = Field(default_factory=list)
    state_changes: list[DetailItem] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    reasoning: ReasoningSummary | None = None
    narrative: NodeNarrativeSummary | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class PlanStepSummary(ApiModel):
    ordinal: int
    purpose: str
    specialist: str | None = None
    status: str


class EvidenceSummary(ApiModel):
    specialist: str
    summary: str
    completeness_known: bool
    source_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)


class ThreadEventSummary(ApiModel):
    sequence: int
    label: str
    status: str
    occurred_at: datetime


class MemorySummary(ApiModel):
    memory_id: str
    label: str
    summary: str
    relevance: float | None = None
    advisory_only: bool = True
    applicability: str
    recovery_steps: list[str] = Field(default_factory=list)
    failed_patterns: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    verified_at: datetime | None = None
    narrative: str | None = None


class PauseSummary(ApiModel):
    kind: Literal["clarification", "approval"]
    title: str
    message: str
    fields: list[str] = Field(default_factory=list)
    impact: str | None = None
    why_needed: str
    decision_depends_on: str
    requested_action: str | None = None
    approver_role: str | None = None
    approval_basis: str | None = None
    evidence_summary: list[str] = Field(default_factory=list)
    narrative: str | None = None


class FinalResponseSummary(ApiModel):
    status: str
    headline: str
    message: str
    request_summary: str
    resolution_summary: str
    reasoning_heading: str
    validity_reasons: list[str] = Field(default_factory=list)
    action: str | None = None
    action_parameters: list[DetailItem] = Field(default_factory=list)
    academic_basis: list[str] = Field(default_factory=list)
    policy_basis: list[str] = Field(default_factory=list)
    approval_summary: str
    transaction_summary: str
    next_steps: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    academic_verified: bool
    policy_verified: bool
    approval_state: str
    completed_at: datetime | None = None
    narrative: str | None = None


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
    plan_version: int | None = None
    plan_rationale: str | None = None
    plan_steps: list[PlanStepSummary] = Field(default_factory=list)
    evidence: list[EvidenceSummary] = Field(default_factory=list)
    action: str | None = None
    action_parameters: list[DetailItem] = Field(default_factory=list)
    outstanding_items: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    reasoning: list[ReasoningSummary] = Field(default_factory=list)
    narrative: str | None = None
    narrative_known: list[str] = Field(default_factory=list)
    narrative_next: str | None = None
    narrative_attention: str | None = None


class ThreadMemorySummary(ApiModel):
    trace_events: int
    clarifications: int
    checkpoints: int
    pause_state: str
    latest_checkpoint: str
    events: list[ThreadEventSummary] = Field(default_factory=list)
    clarification_details: list[DetailItem] = Field(default_factory=list)
    approval_details: list[DetailItem] = Field(default_factory=list)
    narrative: str | None = None
    narrative_highlights: list[str] = Field(default_factory=list)


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
    node_details: dict[str, NodeExecutionDetail] = Field(default_factory=dict)
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


class ManualRunRequest(ApiModel):
    profile_scenario_id: str
    student_id: str
    programme: str
    cohort: str
    study_year: int = Field(ge=1, le=8)
    problem_type: str
    request_text: str = Field(min_length=12, max_length=2_000)
    notes: str | None = Field(default=None, max_length=1_000)
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
    "DetailItem",
    "EvaluationCampaignArtifact",
    "EvaluationCampaignsResponse",
    "EvaluationFilterOptions",
    "EvaluationRunsResponse",
    "EvaluationScenarioRecord",
    "EvaluationScenariosResponse",
    "FinalResponseSummary",
    "ManualRunRequest",
    "MemorySummary",
    "NodeExecutionDetail",
    "NodeNarrativeSummary",
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
