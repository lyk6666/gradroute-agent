"""UI-4 read-only catalogue, projection and leakage tests."""

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
        frontend_origin="http://localhost:3000",
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_catalogue_is_comprehensive_and_marks_restricted_assets(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/data/catalog")

    assert response.status_code == 200
    payload = response.json()
    datasets = {item["dataset_id"]: item for item in payload["datasets"]}
    assert payload["stats"]["accessible_records"] == 6246
    assert datasets["programmes"]["record_count"] == 22
    assert datasets["courses"]["record_count"] == 219
    assert datasets["indexes"]["record_count"] == 2108
    assert datasets["students"]["record_count"] == 240
    assert datasets["scenarios"]["record_count"] == 140
    assert datasets["transaction_scripts"]["accessible"] is False
    assert datasets["evaluation_contracts"]["provenance"] == "restricted"


def test_table_supports_search_sort_filter_and_pagination(client: TestClient) -> None:
    response = client.get(
        "/api/v1/data/courses",
        params={
            "search": "SC2000",
            "programme": "CSC",
            "sort": "code",
            "direction": "asc",
            "page_size": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["page_size"] == 5
    assert 0 < len(payload["records"]) <= 5
    assert payload["records"] == sorted(
        payload["records"], key=lambda item: item["cells"]["code"]
    )
    assert all(
        "CSC" in item["cells"]["programmes"] for item in payload["records"]
    )


def test_markdown_documents_are_available_as_processed_records(
    client: TestClient,
) -> None:
    calendar = client.get(
        "/api/v1/data/calendar_events", params={"search": "Add/Drop"}
    ).json()
    policies = client.get(
        "/api/v1/data/policy_sections",
        params={"search": "prerequisite-waiver"},
    ).json()

    assert calendar["total"] > 0
    assert policies["total"] > 0
    assert calendar["records"][0]["sections"][0]["title"] == "Processed summary"


def test_scenario_and_student_projections_do_not_leak_evaluator_fields(
    client: TestClient,
) -> None:
    scenarios = client.get(
        "/api/v1/data/scenarios", params={"page_size": 100}
    ).json()
    students = client.get(
        "/api/v1/data/students", params={"page_size": 100}
    ).json()

    serialized = f"{scenarios['records']!r}{students['records']!r}"
    for forbidden in (
        "ground_truth",
        "valid_initial_paths",
        "expected_outcome",
        "injected_event",
        "transaction_script",
        "terminal_profile",
    ):
        assert forbidden not in serialized


def test_restricted_and_unknown_datasets_are_rejected(client: TestClient) -> None:
    restricted = client.get("/api/v1/data/transaction_scripts")
    missing = client.get("/api/v1/data/not-a-dataset")

    assert restricted.status_code == 403
    assert missing.status_code == 404
