"""Evaluator-only read projections over the accepted Stage 7 artifacts."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from graduation_exception_agent.api.models import (
    EvaluationCampaignArtifact,
    EvaluationCampaignsResponse,
    EvaluationFilterOptions,
    EvaluationRunsResponse,
    EvaluationScenarioRecord,
    EvaluationScenariosResponse,
)
from graduation_exception_agent.config import AppSettings
from graduation_exception_agent.evaluation.models import (
    CampaignMetricsSummary,
    EvaluationRunResult,
)

EvaluationLane = Literal["fixture", "live"]


@dataclass(frozen=True, slots=True)
class _Artifacts:
    lane: EvaluationLane
    metrics: CampaignMetricsSummary
    runs: tuple[EvaluationRunResult, ...]
    scenarios: tuple[EvaluationScenarioRecord, ...]
    failures: tuple[EvaluationRunResult, ...]
    updated_at: datetime


class EvaluationService:
    """Load immutable reports without making them visible to the agent runtime."""

    def __init__(self, settings: AppSettings) -> None:
        root = Path(settings.evaluation_dir)
        self._artifacts: dict[EvaluationLane, _Artifacts] = {
            "fixture": _load_artifacts("fixture", root),
            "live": _load_artifacts("live", root / "live"),
        }

    def campaigns(self) -> EvaluationCampaignsResponse:
        return EvaluationCampaignsResponse(
            campaigns=[
                EvaluationCampaignArtifact(
                    lane=lane,
                    updated_at=artifacts.updated_at,
                    metrics=artifacts.metrics,
                )
                for lane, artifacts in self._artifacts.items()
            ]
        )

    def runs(
        self,
        lane: EvaluationLane,
        *,
        page: int,
        page_size: int,
        search: str = "",
        family: str = "",
        memory: str = "",
        status: str = "",
        outcome: str = "",
        sort: str = "scenario_id",
        direction: str = "asc",
        failures_only: bool = False,
    ) -> EvaluationRunsResponse:
        artifacts = self._artifacts[lane]
        source = artifacts.failures if failures_only else artifacts.runs
        all_records = list(source)
        filters = EvaluationFilterOptions(
            families=sorted({str(item.family) for item in source}),
            memory_conditions=sorted(
                {str(item.memory_condition) for item in source}
            ),
            statuses=["passed", "failed"],
            outcomes=sorted({str(item.expected_outcome) for item in source}),
        )
        needle = search.strip().casefold()
        if needle:
            all_records = [
                item
                for item in all_records
                if needle in _run_search_text(item).casefold()
            ]
        if family:
            all_records = [item for item in all_records if str(item.family) == family]
        if memory:
            all_records = [
                item for item in all_records if str(item.memory_condition) == memory
            ]
        if status:
            expected = status == "passed"
            all_records = [item for item in all_records if item.passed is expected]
        if outcome:
            all_records = [
                item for item in all_records if str(item.expected_outcome) == outcome
            ]
        allowed_sort = {
            "scenario_id",
            "run_id",
            "family",
            "memory_condition",
            "expected_outcome",
            "actual_outcome",
            "passed",
            "graph_steps",
            "observed_tool_calls",
            "latency_ms",
            "total_tokens",
        }
        sort_key = sort if sort in allowed_sort else "scenario_id"
        all_records.sort(
            key=lambda item: _sortable(getattr(item, sort_key)),
            reverse=direction == "desc",
        )
        total = len(all_records)
        start = (page - 1) * page_size
        return EvaluationRunsResponse(
            lane=lane,
            page=page,
            page_size=page_size,
            total=total,
            records=all_records[start : start + page_size],
            filters=filters,
        )

    def scenarios(
        self,
        lane: EvaluationLane,
        *,
        page: int,
        page_size: int,
        search: str = "",
        family: str = "",
        outcome: str = "",
        sort: str = "scenario_id",
        direction: str = "asc",
    ) -> EvaluationScenariosResponse:
        source = self._artifacts[lane].scenarios
        all_records = list(source)
        filters = EvaluationFilterOptions(
            families=sorted({item.family for item in source}),
            memory_conditions=["empty", "relevant", "misleading"],
            statuses=["3/3", "inconsistent"],
            outcomes=sorted({item.expected_outcome for item in source}),
        )
        needle = search.strip().casefold()
        if needle:
            all_records = [
                item
                for item in all_records
                if needle
                in " ".join(
                    [
                        item.scenario_id,
                        item.family,
                        item.expected_outcome,
                        *item.violation_codes,
                    ]
                ).casefold()
            ]
        if family:
            all_records = [item for item in all_records if item.family == family]
        if outcome:
            all_records = [
                item for item in all_records if item.expected_outcome == outcome
            ]
        allowed_sort = {
            "scenario_id",
            "family",
            "expected_outcome",
            "passed_runs",
            "average_tool_calls",
            "average_graph_steps",
            "average_latency_ms",
            "total_tokens",
        }
        sort_key = sort if sort in allowed_sort else "scenario_id"
        all_records.sort(
            key=lambda item: _sortable(getattr(item, sort_key)),
            reverse=direction == "desc",
        )
        total = len(all_records)
        start = (page - 1) * page_size
        return EvaluationScenariosResponse(
            lane=lane,
            page=page,
            page_size=page_size,
            total=total,
            records=all_records[start : start + page_size],
            filters=filters,
        )


def _load_artifacts(lane: EvaluationLane, root: Path) -> _Artifacts:
    metrics_path = root / "metrics_summary.json"
    runs_path = root / "run_results.jsonl"
    scenarios_path = root / "scenario_summary.csv"
    failures_path = root / "failures.jsonl"
    metrics = CampaignMetricsSummary.model_validate_json(
        metrics_path.read_text(encoding="utf-8")
    )
    runs = _load_runs(runs_path)
    failures = _load_runs(failures_path)
    scenarios = _load_scenarios(scenarios_path)
    return _Artifacts(
        lane=lane,
        metrics=metrics,
        runs=runs,
        scenarios=scenarios,
        failures=failures,
        updated_at=datetime.fromtimestamp(
            metrics_path.stat().st_mtime, tz=timezone.utc
        ),
    )


def _load_runs(path: Path) -> tuple[EvaluationRunResult, ...]:
    return tuple(
        EvaluationRunResult.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _load_scenarios(path: Path) -> tuple[EvaluationScenarioRecord, ...]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = tuple(csv.DictReader(handle))
    return tuple(
        EvaluationScenarioRecord(
            scenario_id=row["scenario_id"],
            family=row["family"],
            expected_outcome=row["expected_outcome"],
            passed_runs=int(row["passed_runs"]),
            consistency=row["consistency"],
            empty_passed=_csv_bool(row["empty_passed"]),
            relevant_passed=_csv_bool(row["relevant_passed"]),
            misleading_passed=_csv_bool(row["misleading_passed"]),
            average_tool_calls=float(row["average_tool_calls"]),
            average_graph_steps=float(row["average_graph_steps"]),
            average_latency_ms=float(row["average_latency_ms"]),
            total_tokens=int(row["total_tokens"]),
            violation_codes=[
                item.strip()
                for item in row["violation_codes"].split(";")
                if item.strip()
            ],
        )
        for row in rows
    )


def _csv_bool(value: str) -> bool:
    return value.strip().casefold() == "true"


def _run_search_text(item: EvaluationRunResult) -> str:
    return " ".join(
        [
            item.run_id,
            item.scenario_id,
            str(item.family),
            str(item.memory_condition),
            str(item.expected_outcome),
            str(item.actual_outcome),
            *item.trace,
            *(violation.code for violation in item.violations),
        ]
    )


def _sortable(value: object) -> str | int | float:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    return str(value).casefold()


__all__ = ["EvaluationService"]
