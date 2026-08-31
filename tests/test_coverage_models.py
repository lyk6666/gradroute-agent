from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from graduation_exception_agent.data.real import (
    RealDataBundle,
    load_coverage_contract,
    validate_real_data,
)
from graduation_exception_agent.errors import DataIntegrityError
from graduation_exception_agent.models import (
    AcademicCalendarDocument,
    Course,
    CourseOfferingCollection,
    CoverageContract,
    Programme,
    SourceProvenance,
)


def _source() -> SourceProvenance:
    return SourceProvenance(
        source_id="source.programmes",
        source_type="programme_index",
        source_url="https://www.ntu.edu.sg/example/programmes",
        retrieved_at="2026-08-31T12:00:00+08:00",
        checked_at="2026-08-31T12:00:00+08:00",
        version="test snapshot",
        origin="VERIFIED_REAL",
        access_status="RETRIEVED",
        classification="PUBLIC",
        retrieval_method="DIRECT_DOWNLOAD",
        content_sha256="0" * 64,
        checksum_scope="SOURCE_BYTES",
        dependent_records=["coverage.programmes"],
    )


def _contract_payload() -> dict[str, object]:
    return {
        "contract_id": "coverage.stage2",
        "as_of": "2026-08-31T12:00:00+08:00",
        "scope_description": "Test public-data inventory.",
        "targets": [
            {
                "target_id": "coverage.programmes",
                "dataset": "PROGRAMMES",
                "scope_description": "One test programme.",
                "scope_parameters": {"college": ["CCDS"]},
                "expected_record_count": 1,
                "expected_record_ids": ["programme.cs"],
                "inventory_status": "COMPLETE",
                "content_status": "COMPLETE",
                "required_fields": ["code", "name"],
                "discovery_source_ids": ["source.programmes"],
                "gaps": [],
            }
        ],
    }


def _bundle(
    contract: CoverageContract, *, courses: tuple[Course, ...] = ()
) -> RealDataBundle:
    source = _source()
    return RealDataBundle(
        sources=(source,),
        programmes=(
            Programme(
                programme_id="programme.cs",
                code="CS",
                name="Computer Science",
                source_ids=[source.source_id],
            ),
        ),
        curricula=(),
        courses=courses,
        coverage=contract,
        offering_collection=CourseOfferingCollection(
            status="PLACEHOLDER",
            source_ids=[],
            offerings=[],
            placeholder_reason="No offering fixture.",
        ),
        academic_calendar=AcademicCalendarDocument(
            document_id="calendar.test",
            title="Test calendar",
            status="AVAILABLE",
            academic_year="AY2026-27",
            timezone="Asia/Singapore",
            source_ids=[source.source_id],
            events=[
                {
                    "event_id": "calendar.test.teaching",
                    "event_type": "TEACHING",
                    "name": "Teaching",
                    "semester": "SEMESTER_1",
                    "start_date": "2026-08-01",
                    "end_date": "2026-08-02",
                    "date_precision": "EXACT",
                    "description": "Test event.",
                    "origin": "VERIFIED_REAL",
                    "source_ids": [source.source_id],
                }
            ],
            raw_markdown="# Test",
            content_sha256="0" * 64,
        ),
        policies=(),
    )


def test_coverage_contract_round_trips() -> None:
    contract = CoverageContract.model_validate(_contract_payload())

    assert contract.targets[0].expected_record_count == 1
    assert CoverageContract.model_validate(contract.model_dump(mode="json")) == contract


def test_coverage_count_must_match_explicit_denominator() -> None:
    payload = _contract_payload()
    payload["targets"][0]["expected_record_count"] = 2  # type: ignore[index]

    with pytest.raises(ValidationError, match="expected_record_count"):
        CoverageContract.model_validate(payload)


def test_partial_coverage_requires_dimension_specific_gap() -> None:
    payload = _contract_payload()
    payload["targets"][0]["content_status"] = "PARTIAL"  # type: ignore[index]

    with pytest.raises(ValidationError, match="CONTENT PARTIAL"):
        CoverageContract.model_validate(payload)


def test_coverage_loader_resolves_discovery_and_gap_sources(
    tmp_path: Path,
) -> None:
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(_contract_payload()), encoding="utf-8")

    contract = load_coverage_contract(path, sources=[_source()])

    assert contract.contract_id == "coverage.stage2"


def test_coverage_loader_rejects_unknown_source(tmp_path: Path) -> None:
    payload = _contract_payload()
    payload["targets"][0]["discovery_source_ids"] = [  # type: ignore[index]
        "source.missing"
    ]
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DataIntegrityError, match="UNKNOWN_SOURCE_ID"):
        load_coverage_contract(path, sources=[_source()])


def test_coverage_timestamp_requires_timezone() -> None:
    payload = _contract_payload()
    payload["as_of"] = "2026-08-31T12:00:00"

    with pytest.raises(ValidationError, match="timezone"):
        CoverageContract.model_validate(payload)


def test_repository_validator_detects_complete_inventory_drift() -> None:
    payload = deepcopy(_contract_payload())
    target = payload["targets"][0]  # type: ignore[index]
    target["expected_record_count"] = 2
    target["expected_record_ids"] = ["programme.cs", "programme.ce"]
    contract = CoverageContract.model_validate(payload)

    issues = validate_real_data(_bundle(contract))

    assert any(
        issue.code == "COVERAGE_EXPECTED_RECORD_MISSING"
        and issue.referenced_id == "programme.ce"
        for issue in issues
    )


def test_cross_school_course_relation_is_a_warning_not_an_error() -> None:
    course = Course(
        code="SC1001",
        title="Test course",
        aus=3,
        exclusions=["AB1001"],
        exclusions_raw_text="AB1001",
        exclusions_completeness="COMPLETE",
        source_ids=["source.programmes"],
    )

    issues = validate_real_data(
        _bundle(CoverageContract.model_validate(_contract_payload()), courses=(course,))
    )
    relation_issues = [
        issue for issue in issues if issue.code == "UNKNOWN_COURSE_REFERENCE"
    ]

    assert relation_issues
    assert all(issue.severity.value == "WARNING" for issue in relation_issues)
