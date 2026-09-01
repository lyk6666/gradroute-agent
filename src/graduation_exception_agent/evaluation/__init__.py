"""Evaluator-only contracts and trace checking support.

This package must not be imported by agent-facing tools, runtime facades, or
graph nodes because its records contain hidden expected resolutions.
"""

from graduation_exception_agent.evaluation.execution_contracts import (
    EvaluatorExecutionContract,
    ExecutionContractPackage,
    load_execution_contract_package,
    load_execution_contracts,
)
from graduation_exception_agent.evaluation.campaign import Stage7EvaluationCampaign
from graduation_exception_agent.evaluation.models import (
    CAMPAIGN_ID,
    RUNNER_VERSION,
    CampaignMetricsSummary,
    CampaignPricing,
    CohortMetrics,
    EvaluationMode,
    EvaluationRunResult,
    EvaluationViolation,
    MIN_LIVE_SCHEMA_PASS_RATE,
    MemoryCondition,
)

__all__ = [
    "EvaluatorExecutionContract",
    "ExecutionContractPackage",
    "load_execution_contract_package",
    "load_execution_contracts",
    "CAMPAIGN_ID",
    "RUNNER_VERSION",
    "CampaignMetricsSummary",
    "CampaignPricing",
    "CohortMetrics",
    "EvaluationMode",
    "EvaluationRunResult",
    "EvaluationViolation",
    "MemoryCondition",
    "MIN_LIVE_SCHEMA_PASS_RATE",
    "Stage7EvaluationCampaign",
]
