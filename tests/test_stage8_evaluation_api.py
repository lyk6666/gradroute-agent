"""UI-5 accepted-campaign projection and evaluator-boundary tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from graduation_exception_agent.api.app import create_app
from graduation_exception_agent.config import AppSettings, ExecutionMode


@pytest.fixture(scope="module")
def client() -> TestClient:
    settings = AppSettings(
        _env_file=None,
        execution_mode=ExecutionMode.FIXTURE,
        data_dir="data",
        evaluation_dir="evaluation",
        frontend_origin="http://localhost:3000",
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_campaign_catalogue_exposes_both_accepted_lanes(client: TestClient) -> None:
    response = client.get("/api/v1/evaluation/campaigns")

    assert response.status_code == 200
    campaigns = {item["lane"]: item["metrics"] for item in response.json()["campaigns"]}
    assert set(campaigns) == {"fixture", "live"}
    assert campaigns["fixture"]["passed_runs"] == 315
    assert campaigns["fixture"]["scenarios_passing_3_of_3"] == 105
    assert campaigns["live"]["reasoning_calls"] == 720
    assert campaigns["live"]["reasoning_successes"] == 720
    assert campaigns["live"]["reasoning_fallbacks"] == 0
    assert campaigns["live"]["acceptance_passed"] is True


def test_run_explorer_filters_and_returns_evaluator_trace(client: TestClient) -> None:
    response = client.get(
        "/api/v1/evaluation/runs",
        params={
            "lane": "live",
            "memory": "misleading",
            "family": "S7",
            "sort": "latency_ms",
            "direction": "desc",
            "page_size": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 15
    assert len(payload["records"]) == 10
    assert all(item["memory_condition"] == "misleading" for item in payload["records"])
    assert all(item["family"] == "S7" for item in payload["records"])
    assert all(item["expected_outcome"] == item["actual_outcome"] for item in payload["records"])
    assert all(item["trace"] for item in payload["records"])
    assert [item["latency_ms"] for item in payload["records"]] == sorted(
        (item["latency_ms"] for item in payload["records"]), reverse=True
    )


def test_scenario_consistency_table_is_complete(client: TestClient) -> None:
    response = client.get(
        "/api/v1/evaluation/scenarios",
        params={"lane": "fixture", "family": "S2", "page_size": 100},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 15
    assert all(item["consistency"] == "3/3" for item in payload["records"])
    assert all(item["empty_passed"] for item in payload["records"])
    assert all(item["relevant_passed"] for item in payload["records"])
    assert all(item["misleading_passed"] for item in payload["records"])


def test_accepted_campaign_failure_artifacts_are_empty(client: TestClient) -> None:
    fixture = client.get("/api/v1/evaluation/failures", params={"lane": "fixture"})
    live = client.get("/api/v1/evaluation/failures", params={"lane": "live"})

    assert fixture.status_code == 200
    assert live.status_code == 200
    assert fixture.json()["total"] == 0
    assert live.json()["total"] == 0


def test_evaluator_fields_do_not_appear_in_agent_scenario_catalogue(
    client: TestClient,
) -> None:
    evaluator = client.get(
        "/api/v1/evaluation/runs", params={"lane": "fixture", "page_size": 1}
    ).json()
    agent_catalogue = client.get("/api/v1/scenarios").json()

    assert "expected_outcome" in evaluator["records"][0]
    serialized_agent_catalogue = repr(agent_catalogue)
    assert "expected_outcome" not in serialized_agent_catalogue
    assert "result_signature" not in serialized_agent_catalogue
    assert "violations" not in serialized_agent_catalogue
