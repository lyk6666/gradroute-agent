"""Offline Stage 8 delivery smoke gate for API and frontend contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from graduation_exception_agent.api.app import create_app
from graduation_exception_agent.config import AppSettings, ExecutionMode


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    frontend = REPOSITORY_ROOT / "frontend"
    required_routes = (
        frontend / "app" / "page.tsx",
        frontend / "app" / "data" / "page.tsx",
        frontend / "app" / "evaluation" / "page.tsx",
        frontend / "app" / "error.tsx",
        frontend / "app" / "loading.tsx",
        frontend / "app" / "not-found.tsx",
    )
    missing = [str(path.relative_to(REPOSITORY_ROOT)) for path in required_routes if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing Stage 8 frontend contracts: {', '.join(missing)}")

    package = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    required_scripts = {"dev", "build", "start", "lint", "typecheck"}
    missing_scripts = sorted(required_scripts - set(package.get("scripts", {})))
    if missing_scripts:
        raise SystemExit(f"Missing frontend scripts: {', '.join(missing_scripts)}")

    settings = AppSettings(
        _env_file=None,
        execution_mode=ExecutionMode.FIXTURE,
        data_dir=REPOSITORY_ROOT / "data",
        evaluation_dir=REPOSITORY_ROOT / "evaluation",
        frontend_origin="http://localhost:3000",
    )
    with TestClient(create_app(settings)) as client:
        health = _get(client, "/api/v1/health")
        readiness = _get(client, "/api/v1/ready")
        scenarios = _get(client, "/api/v1/scenarios")
        data_catalog = _get(client, "/api/v1/data/catalog")
        campaigns = _get(client, "/api/v1/evaluation/campaigns")

    if health["status"] != "operational" or readiness["status"] != "ready":
        raise SystemExit("Runtime or artifact readiness gate failed")
    if len(scenarios) != 112:
        raise SystemExit("Agent scenario catalogue must expose exactly 112 runnable cases")
    if data_catalog["stats"]["accessible_records"] != 6246:
        raise SystemExit("UI-4 accessible-record count changed unexpectedly")
    if {item["lane"] for item in campaigns["campaigns"]} != {"fixture", "live"}:
        raise SystemExit("UI-5 must expose both accepted evaluation lanes")

    serialized_scenarios = repr(scenarios)
    for forbidden in ("expected_outcome", "result_signature", "ground_truth"):
        if forbidden in serialized_scenarios:
            raise SystemExit(f"Evaluator field leaked into agent catalogue: {forbidden}")

    print("Stage 8 delivery smoke gate passed")
    print("  API: operational and ready")
    print("  Main: 112 evaluator-safe runnable scenarios")
    print("  Data: 6,246 processed records")
    print("  Evaluation: fixture + live accepted campaigns")
    print("  Frontend: Main, Data, Evaluation, loading, error and not-found routes")


def _get(client: TestClient, path: str) -> Any:
    response = client.get(path)
    if response.status_code != 200:
        raise SystemExit(f"Smoke request failed: {path} returned {response.status_code}")
    return response.json()


if __name__ == "__main__":
    main()
