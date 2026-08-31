from __future__ import annotations

import pytest
from pydantic import ValidationError

from graduation_exception_agent.models import (
    CalendarEvent,
    Course,
    CourseOfferingCollection,
    Curriculum,
    PolicyDocument,
    PolicySection,
)


def test_simulated_policy_requires_exact_visible_banner() -> None:
    with pytest.raises(ValidationError, match="SIMULATED POLICY FOR PROTOTYPE"):
        PolicySection(
            section_id="simulated.rule",
            title="Prototype rule",
            origin="SIMULATED_POLICY",
            source_ids=[],
            applicability="EXPLICIT",
            applicable_academic_years=["AY2026-27"],
            applicable_admission_cohorts=[],
            applicability_note="Prototype scope.",
            body_markdown="A convenient invented process.",
            start_line=4,
            end_line=5,
        )


def test_simulated_policy_with_banner_remains_typed_as_simulated() -> None:
    section = PolicySection(
        section_id="simulated.rule",
        title="Prototype rule",
        origin="SIMULATED_POLICY",
        source_ids=[],
        applicability="EXPLICIT",
        applicable_academic_years=["AY2026-27"],
        applicable_admission_cohorts=[],
        applicability_note="Prototype scope.",
        body_markdown=(
            "SIMULATED POLICY FOR PROTOTYPE\n\nA deterministic test-only rule."
        ),
        start_line=4,
        end_line=6,
    )

    assert section.origin.value == "SIMULATED_POLICY"


def test_policy_section_requires_typed_applicability_scope() -> None:
    with pytest.raises(ValidationError, match="requires a year or cohort"):
        PolicySection(
            section_id="policy.test",
            title="Test rule",
            origin="VERIFIED_REAL",
            source_ids=["source.policy"],
            applicability="EXPLICIT",
            applicable_academic_years=[],
            applicable_admission_cohorts=[],
            applicability_note="Missing scope should fail.",
            body_markdown="A sourced statement.",
            start_line=1,
            end_line=1,
        )


def test_policy_document_rejects_section_source_not_declared_by_document() -> None:
    with pytest.raises(ValidationError, match="declared by the policy document"):
        PolicyDocument(
            document_id="policy.test",
            document_type="REGISTRATION",
            title="Test",
            status="AVAILABLE",
            source_ids=["source.document"],
            sections=[
                {
                    "section_id": "policy.test.section",
                    "title": "Section",
                    "origin": "VERIFIED_REAL",
                    "source_ids": ["source.other"],
                    "applicability": "EXPLICIT",
                    "applicable_academic_years": ["AY2026-27"],
                    "applicable_admission_cohorts": [],
                    "applicability_note": "Scoped test.",
                    "body_markdown": "Statement.",
                    "start_line": 1,
                    "end_line": 1,
                }
            ],
            raw_markdown="x",
            content_sha256="0" * 64,
        )


def test_unknown_calendar_event_cannot_gain_invented_dates() -> None:
    with pytest.raises(ValidationError, match="unknown calendar dates must remain null"):
        CalendarEvent(
            event_id="calendar.unknown",
            event_type="COURSE_REGISTRATION",
            name="Unknown personalised time",
            semester=None,
            start_date="2026-06-01",
            end_date=None,
            date_precision="UNKNOWN",
            description="Not publicly available.",
            origin="UNKNOWN",
            source_ids=[],
        )


def test_placeholder_offerings_are_not_a_verified_empty_collection() -> None:
    collection = CourseOfferingCollection(
        status="PLACEHOLDER",
        source_ids=[],
        offerings=[],
        placeholder_reason="No reproducible public snapshot has been collected.",
    )

    assert collection.status.value == "PLACEHOLDER"
    assert collection.placeholder_reason is not None


def test_placeholder_offerings_cannot_contain_records() -> None:
    with pytest.raises(ValidationError, match="cannot contain offerings"):
        CourseOfferingCollection(
            status="PLACEHOLDER",
            source_ids=[],
            offerings=[
                {
                    "offering_id": "offering.sc1003",
                    "course_code": "SC1003",
                    "academic_year": "AY2026-27",
                    "semester": "SEMESTER_1",
                    "status": "UNKNOWN",
                    "indexes": [],
                    "snapshot_at": None,
                    "source_ids": ["source.offering"],
                }
            ],
            placeholder_reason="No reproducible snapshot.",
        )


def test_known_course_applicability_cannot_be_marked_unknown() -> None:
    with pytest.raises(ValidationError, match="programme applicability"):
        Course(
            code="SC1003",
            title="Introduction to Computing",
            aus=3,
            applicable_programmes=["CSC"],
            programme_categories={"CSC": ["PROGRAMME_CORE"]},
            applicability_completeness="UNKNOWN",
            source_ids=["source.curriculum"],
        )


def test_populated_curriculum_must_declare_coverage() -> None:
    with pytest.raises(ValidationError, match="COMPLETE or PARTIAL"):
        Curriculum(
            curriculum_id="curriculum.csc.test",
            programme="CSC",
            admission_cohort="AY2025-26",
            effective_academic_year="AY2025-26",
            graduation_aus=3,
            requirements=[
                {
                    "requirement_id": "requirement.core",
                    "name": "Core",
                    "category": "PROGRAMME_CORE",
                    "minimum_aus": 3,
                }
            ],
            rules_completeness="UNKNOWN",
            source_ids=["source.curriculum"],
        )


def test_curriculum_requires_one_fixed_total_or_explicit_paths() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        Curriculum(
            curriculum_id="curriculum.csc.test",
            programme="CSC",
            admission_cohort="AY2025-26",
            effective_academic_year="AY2025-26",
            graduation_aus=135,
            graduation_paths=[
                {
                    "path_id": "path.alternative",
                    "name": "Alternative",
                    "graduation_aus": 136,
                }
            ],
            requirements=[
                {
                    "requirement_id": "requirement.core",
                    "name": "Core",
                    "category": "PROGRAMME_CORE",
                    "minimum_aus": 3,
                }
            ],
            rules_completeness="PARTIAL",
            source_ids=["source.curriculum"],
        )
