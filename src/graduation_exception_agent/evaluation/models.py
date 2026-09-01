"""Typed Stage 7 campaign results and aggregate reporting contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from graduation_exception_agent.models.common import DomainModel, Identifier
from graduation_exception_agent.models.runtime import VerifierDecisionCode
from graduation_exception_agent.models.workflow import (
    ExpectedOutcome,
    ScenarioFamily,
)


CAMPAIGN_ID = "stage7.ntu-ccds.ay2026-27s1.v1"
RUNNER_VERSION = "stage7.0.0"
MIN_LIVE_SCHEMA_PASS_RATE = 0.95


class EvaluationMode(StrEnum):
    FIXTURE = "fixture"
    BEDROCK = "bedrock"


class MemoryCondition(StrEnum):
    EMPTY = "empty"
    RELEVANT = "relevant"
    MISLEADING = "misleading"


MEMORY_CONDITIONS = (
    MemoryCondition.EMPTY,
    MemoryCondition.RELEVANT,
    MemoryCondition.MISLEADING,
)


class EvaluationViolation(DomainModel):
    code: Identifier
    message: str = Field(min_length=1, max_length=1_000)


class CampaignPricing(DomainModel):
    input_usd_per_million_tokens: float = Field(default=0.0, ge=0)
    output_usd_per_million_tokens: float = Field(default=0.0, ge=0)

    @property
    def configured(self) -> bool:
        return bool(
            self.input_usd_per_million_tokens
            or self.output_usd_per_million_tokens
        )


class EvaluationRunResult(DomainModel):
    campaign_id: Literal[CAMPAIGN_ID] = CAMPAIGN_ID
    runner_version: Literal[RUNNER_VERSION] = RUNNER_VERSION
    scenario_id: Identifier
    run_id: Identifier
    repetition: int = Field(ge=1, le=3)
    memory_condition: MemoryCondition
    evaluation_mode: EvaluationMode
    model_id: str | None = Field(default=None, max_length=256)
    family: ScenarioFamily
    expected_outcome: ExpectedOutcome
    actual_outcome: ExpectedOutcome
    task_completed: bool
    resolution_valid: bool
    passed: bool
    violations: list[EvaluationViolation] = Field(default_factory=list)
    required_transitions_missing: list[str] = Field(default_factory=list)
    forbidden_transitions_observed: list[str] = Field(default_factory=list)
    trace: list[str]
    verifier_pre_action: list[VerifierDecisionCode] = Field(default_factory=list)
    verifier_post_action: list[VerifierDecisionCode] = Field(default_factory=list)
    observed_tool_calls: int = Field(ge=0)
    successful_tool_calls: int = Field(ge=0)
    graph_steps: int = Field(ge=0)
    replans: int = Field(ge=0)
    tool_retries: int = Field(ge=0)
    total_steps: int = Field(ge=0)
    memory_hits: int = Field(ge=0)
    memory_candidate_ids: list[Identifier] = Field(default_factory=list)
    memory_write_attempted: bool
    memory_write_completed: bool
    approval_transitions: list[str] = Field(default_factory=list)
    admin_escalation: bool
    clarification_impact: str | None = Field(default=None, max_length=64)
    clarification_resume_target: str | None = Field(default=None, max_length=64)
    checkpoint_paused: bool
    checkpoint_resumed: bool
    reasoning_calls: int = Field(ge=0)
    reasoning_successes: int = Field(ge=0)
    reasoning_fallbacks: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    latency_ms: int = Field(ge=0)
    result_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    error_type: Identifier | None = None

    @field_validator(
        "required_transitions_missing",
        "forbidden_transitions_observed",
        "memory_candidate_ids",
    )
    @classmethod
    def unique_lists(cls, values: list[str], info: object) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError(f"{getattr(info, 'field_name', 'values')} has duplicates")
        return values

    @model_validator(mode="after")
    def validate_totals_and_outcome(self) -> EvaluationRunResult:
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens must equal input_tokens plus output_tokens")
        if self.successful_tool_calls > self.observed_tool_calls:
            raise ValueError("successful_tool_calls cannot exceed observed_tool_calls")
        if self.reasoning_successes + self.reasoning_fallbacks > self.reasoning_calls:
            raise ValueError("reasoning outcome counts cannot exceed reasoning calls")
        if self.resolution_valid != (not self.violations):
            raise ValueError("resolution_valid must be true exactly without violations")
        if self.passed != (self.task_completed and self.resolution_valid):
            raise ValueError("passed must combine task completion and resolution validity")
        return self


class CohortMetrics(DomainModel):
    run_count: int = Field(ge=0)
    passed_runs: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    average_graph_steps: float = Field(ge=0)
    average_tool_calls: float = Field(ge=0)
    average_latency_ms: float = Field(ge=0)


class CampaignMetricsSummary(DomainModel):
    campaign_id: Literal[CAMPAIGN_ID] = CAMPAIGN_ID
    runner_version: Literal[RUNNER_VERSION] = RUNNER_VERSION
    evaluation_mode: EvaluationMode
    model_id: str | None = Field(default=None, max_length=256)
    scenario_count: Literal[105]
    repetitions_per_scenario: Literal[3]
    run_count: Literal[315]
    passed_runs: int = Field(ge=0, le=315)
    failed_runs: int = Field(ge=0, le=315)
    task_completion_rate: float = Field(ge=0, le=1)
    valid_resolution_rate: float = Field(ge=0, le=1)
    constraint_violation_rate: float = Field(ge=0, le=1)
    recovery_success_rate: float = Field(ge=0, le=1)
    correct_escalation_rate: float = Field(ge=0, le=1)
    approval_compliance_rate: float = Field(ge=0, le=1)
    clarification_routing_accuracy: float = Field(ge=0, le=1)
    checkpoint_resume_integrity: float = Field(ge=0, le=1)
    memory_override_violation_rate: float = Field(ge=0, le=1)
    memory_write_gate_violation_rate: float = Field(ge=0, le=1)
    post_action_false_completion_rate: float = Field(ge=0, le=1)
    tool_call_success_rate: float = Field(ge=0, le=1)
    schema_validation_pass_rate: float | None = Field(default=None, ge=0, le=1)
    loop_cap_hit_rate: float = Field(ge=0, le=1)
    scenarios_passing_3_of_3: int = Field(ge=0, le=105)
    scenario_consistency_rate: float = Field(ge=0, le=1)
    average_tool_calls: float = Field(ge=0)
    average_graph_steps: float = Field(ge=0)
    average_latency_ms: float = Field(ge=0)
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    reasoning_calls: int = Field(ge=0)
    reasoning_successes: int = Field(ge=0)
    reasoning_fallbacks: int = Field(ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    acceptance_passed: bool
    acceptance_failures: list[Identifier] = Field(default_factory=list)
    violation_counts: dict[Identifier, int] = Field(default_factory=dict)
    by_family: dict[str, CohortMetrics]
    by_memory_condition: dict[str, CohortMetrics]

    @model_validator(mode="after")
    def validate_campaign_totals(self) -> CampaignMetricsSummary:
        if self.passed_runs + self.failed_runs != self.run_count:
            raise ValueError("passed_runs plus failed_runs must equal run_count")
        if self.total_tokens != self.total_input_tokens + self.total_output_tokens:
            raise ValueError("token totals do not reconcile")
        if self.reasoning_successes + self.reasoning_fallbacks > self.reasoning_calls:
            raise ValueError("reasoning outcome counts cannot exceed reasoning calls")
        if self.acceptance_passed != (not self.acceptance_failures):
            raise ValueError(
                "acceptance_passed must be true exactly without acceptance failures"
            )
        if len(self.acceptance_failures) != len(set(self.acceptance_failures)):
            raise ValueError("acceptance_failures has duplicates")
        return self


__all__ = [
    "CAMPAIGN_ID",
    "MIN_LIVE_SCHEMA_PASS_RATE",
    "RUNNER_VERSION",
    "CampaignMetricsSummary",
    "CampaignPricing",
    "CohortMetrics",
    "EvaluationMode",
    "EvaluationRunResult",
    "EvaluationViolation",
    "MEMORY_CONDITIONS",
    "MemoryCondition",
]
