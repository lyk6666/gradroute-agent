"""FastAPI application exposing the safe Stage 8 integration boundary."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from graduation_exception_agent.api.models import (
    ApprovalResumeRequest,
    ClarificationResumeRequest,
    RunSnapshot,
    ScenarioSummary,
    StartRunRequest,
    StartRunResponse,
)
from graduation_exception_agent.api.service import RunService
from graduation_exception_agent.config import AppSettings, get_settings


def create_app(
    settings: AppSettings | None = None, service: RunService | None = None
) -> FastAPI:
    selected_settings = settings or get_settings()
    run_service = service or RunService(selected_settings)
    app = FastAPI(
        title="Graduation Exception Agent API",
        version="1.0.0",
        description=(
            "Agent-observable facade for the NTU CCDS-grounded research prototype."
        ),
    )
    app.state.run_service = run_service
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

    @app.get("/api/v1/scenarios", response_model=list[ScenarioSummary])
    def scenarios(
        split: Annotated[Literal["demo", "evaluation"] | None, Query()] = None,
    ) -> list[ScenarioSummary]:
        items = run_service.scenarios()
        return [item for item in items if split is None or item.split == split]

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
