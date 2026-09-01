"""FastAPI application exposing the safe Stage 8 integration boundary."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from graduation_exception_agent.api.models import (
    ApprovalResumeRequest,
    ClarificationResumeRequest,
    DataCatalogResponse,
    DataPageResponse,
    EvaluationCampaignsResponse,
    EvaluationRunsResponse,
    EvaluationScenariosResponse,
    RunSnapshot,
    ScenarioSummary,
    StartRunRequest,
    StartRunResponse,
)
from graduation_exception_agent.api.data_service import DataService
from graduation_exception_agent.api.evaluation_service import EvaluationService
from graduation_exception_agent.api.service import RunService
from graduation_exception_agent.config import AppSettings, get_settings


def create_app(
    settings: AppSettings | None = None,
    service: RunService | None = None,
    data_service: DataService | None = None,
    evaluation_service: EvaluationService | None = None,
) -> FastAPI:
    selected_settings = settings or get_settings()
    run_service = service or RunService(selected_settings)

    @lru_cache(maxsize=1)
    def get_data_service() -> DataService:
        return data_service or DataService(selected_settings)

    @lru_cache(maxsize=1)
    def get_evaluation_service() -> EvaluationService:
        return evaluation_service or EvaluationService(selected_settings)

    app = FastAPI(
        title="Graduation Exception Agent API",
        version="1.0.0",
        description=(
            "Agent-observable facade for the NTU CCDS-grounded research prototype."
        ),
    )
    app.state.run_service = run_service
    app.state.data_service_provider = get_data_service
    app.state.evaluation_service_provider = get_evaluation_service
    origin = str(selected_settings.frontend_origin).rstrip("/")
    allowed_origins = sorted(
        {origin, "http://localhost:3000", "http://127.0.0.1:3000"}
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {
            "status": "operational",
            "api_version": "1.0",
            "execution_mode": selected_settings.execution_mode.value,
        }

    @app.get("/api/v1/ready")
    def readiness() -> dict[str, str]:
        data_root = Path(selected_settings.data_dir)
        evaluation_root = Path(selected_settings.evaluation_dir)
        data_ready = all(
            (data_root / relative).is_file()
            for relative in (
                "real/source_manifest.json",
                "real/courses.json",
                "simulated/students.json",
                "tests/scenarios.json",
            )
        )
        evaluation_ready = all(
            (evaluation_root / relative).is_file()
            for relative in (
                "metrics_summary.json",
                "run_results.jsonl",
                "live/metrics_summary.json",
                "live/run_results.jsonl",
            )
        )
        status = "ready" if data_ready and evaluation_ready else "degraded"
        return {
            "status": status,
            "runtime": "ready",
            "data_package": "available" if data_ready else "missing",
            "evaluation_artifacts": "available" if evaluation_ready else "missing",
        }

    @app.get("/api/v1/scenarios", response_model=list[ScenarioSummary])
    def scenarios(
        split: Annotated[Literal["demo", "evaluation"] | None, Query()] = None,
    ) -> list[ScenarioSummary]:
        items = run_service.scenarios()
        return [item for item in items if split is None or item.split == split]

    @app.get("/api/v1/data/catalog", response_model=DataCatalogResponse)
    def data_catalog() -> DataCatalogResponse:
        return get_data_service().catalog()

    @app.get("/api/v1/data/{dataset_id}", response_model=DataPageResponse)
    def data_page(
        dataset_id: str,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 25,
        search: Annotated[str, Query(max_length=200)] = "",
        programme: Annotated[str, Query(max_length=40)] = "",
        status: Annotated[str, Query(max_length=80)] = "",
        sort: Annotated[str, Query(max_length=80)] = "",
        direction: Annotated[Literal["asc", "desc"], Query()] = "asc",
    ) -> DataPageResponse:
        try:
            return get_data_service().page(
                dataset_id,
                page=page,
                page_size=page_size,
                search=search,
                programme=programme,
                status=status,
                sort=sort,
                direction=direction,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.get(
        "/api/v1/evaluation/campaigns", response_model=EvaluationCampaignsResponse
    )
    def evaluation_campaigns() -> EvaluationCampaignsResponse:
        return get_evaluation_service().campaigns()

    @app.get("/api/v1/evaluation/runs", response_model=EvaluationRunsResponse)
    def evaluation_runs(
        lane: Annotated[Literal["fixture", "live"], Query()] = "live",
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 25,
        search: Annotated[str, Query(max_length=200)] = "",
        family: Annotated[str, Query(max_length=16)] = "",
        memory: Annotated[str, Query(max_length=32)] = "",
        status: Annotated[Literal["", "passed", "failed"], Query()] = "",
        outcome: Annotated[str, Query(max_length=64)] = "",
        sort: Annotated[str, Query(max_length=80)] = "scenario_id",
        direction: Annotated[Literal["asc", "desc"], Query()] = "asc",
    ) -> EvaluationRunsResponse:
        return get_evaluation_service().runs(
            lane,
            page=page,
            page_size=page_size,
            search=search,
            family=family,
            memory=memory,
            status=status,
            outcome=outcome,
            sort=sort,
            direction=direction,
        )

    @app.get(
        "/api/v1/evaluation/scenarios", response_model=EvaluationScenariosResponse
    )
    def evaluation_scenarios(
        lane: Annotated[Literal["fixture", "live"], Query()] = "live",
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 25,
        search: Annotated[str, Query(max_length=200)] = "",
        family: Annotated[str, Query(max_length=16)] = "",
        outcome: Annotated[str, Query(max_length=64)] = "",
        sort: Annotated[str, Query(max_length=80)] = "scenario_id",
        direction: Annotated[Literal["asc", "desc"], Query()] = "asc",
    ) -> EvaluationScenariosResponse:
        return get_evaluation_service().scenarios(
            lane,
            page=page,
            page_size=page_size,
            search=search,
            family=family,
            outcome=outcome,
            sort=sort,
            direction=direction,
        )

    @app.get("/api/v1/evaluation/failures", response_model=EvaluationRunsResponse)
    def evaluation_failures(
        lane: Annotated[Literal["fixture", "live"], Query()] = "live",
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    ) -> EvaluationRunsResponse:
        return get_evaluation_service().runs(
            lane,
            page=page,
            page_size=page_size,
            failures_only=True,
        )

    @app.post("/api/v1/runs", response_model=StartRunResponse, status_code=202)
    def start_run(request: StartRunRequest) -> StartRunResponse:
        try:
            snapshot = run_service.start(request)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return StartRunResponse(
            run_id=snapshot.run_id,
            events_url=f"/api/v1/runs/{snapshot.run_id}/events",
            snapshot=snapshot,
        )

    @app.get("/api/v1/runs/{run_id}", response_model=RunSnapshot)
    def run_snapshot(run_id: str) -> RunSnapshot:
        try:
            return run_service.snapshot(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/runs/{run_id}/advance", response_model=RunSnapshot)
    def advance_run(run_id: str) -> RunSnapshot:
        try:
            return run_service.advance(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/runs/{run_id}/resume", response_model=RunSnapshot)
    def resume_run(
        run_id: str,
        request: ClarificationResumeRequest | ApprovalResumeRequest,
    ) -> RunSnapshot:
        try:
            return run_service.resume(run_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/v1/runs/{run_id}/events")
    async def run_events(
        run_id: str,
        after: Annotated[int, Query(ge=0)] = 0,
    ) -> StreamingResponse:
        try:
            run_service.snapshot(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        async def stream() -> AsyncIterator[str]:
            cursor = after
            while True:
                events, terminal = await run_in_threadpool(
                    run_service.wait_for_events,
                    run_id,
                    after=cursor,
                    timeout=12.0,
                )
                if not events:
                    if terminal:
                        return
                    yield ": heartbeat\n\n"
                    continue
                for event in events:
                    cursor = event.sequence
                    payload = json.dumps(
                        event.model_dump(mode="json"), separators=(",", ":")
                    )
                    yield f"id: {event.sequence}\ndata: {payload}\n\n"
                if terminal:
                    return

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    return app


app = create_app()

__all__ = ["app", "create_app"]
