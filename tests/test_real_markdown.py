from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from graduation_exception_agent.data.real.markdown import (
    parse_academic_calendar,
    parse_policy_document,
)
from graduation_exception_agent.errors import (
    DataMarkdownError,
    DataSchemaError,
)
from graduation_exception_agent.models import PolicyDocumentType


REAL_ROOT = Path(__file__).parents[1] / "data" / "real"


def test_calendar_parser_preserves_raw_document_and_hash() -> None:
    path = REAL_ROOT / "academic_calendar.md"
    calendar = parse_academic_calendar(path)

    assert calendar.academic_year == "AY2026-27"
    assert calendar.timezone == "Asia/Singapore"
    assert calendar.status.value == "PARTIAL"
    assert calendar.content_sha256 == hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    assert any(event.origin.value == "UNKNOWN" for event in calendar.events)


def test_calendar_covers_the_public_operating_cycle_and_ccds_internships() -> None:
    calendar = parse_academic_calendar(REAL_ROOT / "academic_calendar.md")
    by_id = {event.event_id: event for event in calendar.events}

    required_types = {
        "TEACHING",
        "RECESS",
        "REVISION_EXAMINATION",
        "VACATION",
        "SPECIAL_TERM",
        "INTERNSHIP",
        "COURSE_REGISTRATION",
        "ADD_DROP",
        "SCHEDULE_RELEASE",
        "ALLOCATION_RESULTS",
        "RESULTS",
        "FGO",
        "RESULT_REVIEW",
        "CONVOCATION_CUTOFF",
    }
    assert required_types <= {event.event_type.value for event in calendar.events}
    assert by_id["calendar.s1.revision_examination"].start_date.isoformat() == (
        "2026-11-16"
    )
    assert by_id["calendar.s2.revision_examination"].end_date.isoformat() == (
        "2027-05-07"
    )
    assert by_id["calendar.ccds.pi.s1"].start_date.isoformat() == "2026-07-20"
    assert by_id["calendar.ccds.enhanced_pi.s2"].end_date.isoformat() == (
        "2027-08-06"
    )
    assert by_id["calendar.s1.registration.general"].date_precision.value == (
        "GENERAL"
    )
    assert by_id["calendar.personalised.registration.exact"].origin.value == (
        "UNKNOWN"
    )


@pytest.mark.parametrize(
    ("filename", "expected_type"),
    [
        ("registration.md", PolicyDocumentType.REGISTRATION),
        ("exceptions.md", PolicyDocumentType.EXCEPTIONS),
        ("approval_structure.md", PolicyDocumentType.APPROVAL_STRUCTURE),
    ],
)
def test_policy_parser_preserves_section_provenance_and_lines(
    filename: str, expected_type: PolicyDocumentType
) -> None:
    document = parse_policy_document(
        REAL_ROOT / "public_policies" / filename,
        expected_type=expected_type,
    )

    assert document.document_type is expected_type
    assert document.raw_markdown.startswith("<!-- GEA-METADATA")
    assert all(section.start_line <= section.end_line for section in document.sections)
    assert all(section.body_markdown for section in document.sections)
    verified = document.verified_sections(admission_cohort="AY2026-27")
    assert verified
    assert all(
        section.origin.value == "VERIFIED_REAL"
        for section in verified
    )


def test_policy_corpus_preserves_public_routes_and_explicit_gaps() -> None:
    documents = {
        filename: parse_policy_document(
            REAL_ROOT / "public_policies" / filename,
            expected_type=expected_type,
        )
        for filename, expected_type in [
            ("registration.md", PolicyDocumentType.REGISTRATION),
            ("exceptions.md", PolicyDocumentType.EXCEPTIONS),
            ("approval_structure.md", PolicyDocumentType.APPROVAL_STRUCTURE),
        ]
    }
    section_ids = {
        section.section_id
        for document in documents.values()
        for section in document.sections
    }

    required_public_routes = {
        "policy.registration.matriculation.ay2026-27",
        "policy.registration.stars_guide.waitlist",
        "policy.exception.course_exemption.olympiad",
        "policy.exception.course_exemption.poly.ay2026",
        "policy.exception.exchange.course_matching",
        "policy.exception.exchange.credit_transfer",
        "policy.exception.exchange.pending_transfer",
        "policy.exception.icc.cc0006_clash",
        "policy.exception.icc.short_loa",
        "policy.exception.restricted_repeat",
        "policy.graduation.public_status",
        "policy.approval.chair_concerned",
        "policy.role.ccds_undergraduate_office",
        "policy.role.ccds_part_time",
        "policy.role.oas_registration",
        "policy.role.it_service_desk",
        "policy.role.one_stop",
        "policy.approval.exchange.associate_dean",
        "policy.approval.exchange.pmc",
    }
    required_unknown_boundaries = {
        "unknown.registration.personalised",
        "unknown.registration.live_allocation",
        "unknown.exception.general_prerequisite_waiver",
        "unknown.exception.after_add_drop",
        "unknown.exception.overload_process",
        "unknown.exception.general_clash_waiver",
        "unknown.exception.restricted_repeat_process",
        "unknown.exception.substitution",
        "unknown.exception.full_loa",
        "unknown.approval.general_exception_chain",
        "unknown.approval.delegation_sla",
    }
    assert required_public_routes <= section_ids
    assert required_unknown_boundaries <= section_ids

    all_sections = {
        section.section_id: section
        for document in documents.values()
        for section in document.sections
    }
    assert all(
        all_sections[section_id].origin.value == "UNKNOWN"
        and not all_sections[section_id].source_ids
        for section_id in required_unknown_boundaries
    )


def test_policy_parser_rejects_unlabelled_simulation(tmp_path: Path) -> None:
    path = tmp_path / "exceptions.md"
    path.write_text(
        """<!-- GEA-METADATA
{
  "document_id": "policy.test",
  "document_type": "EXCEPTIONS",
  "title": "Test",
  "status": "PARTIAL",
  "source_ids": [],
  "sections": [
    {"section_id": "simulated.test", "origin": "SIMULATED_POLICY", "source_ids": [], "applicability": "EXPLICIT", "applicable_academic_years": ["AY2026-27"], "applicable_admission_cohorts": [], "applicability_note": "Prototype scope."}
  ],
  "placeholder_reason": null
}
-->

# Test

## [simulated.test] Invented rule

This has no required banner.
""",
        encoding="utf-8",
    )

    with pytest.raises(DataSchemaError, match="SIMULATED POLICY FOR PROTOTYPE"):
        parse_policy_document(path)


def test_policy_parser_rejects_untracked_heading(tmp_path: Path) -> None:
    path = tmp_path / "registration.md"
    path.write_text(
        """<!-- GEA-METADATA
{
  "document_id": "policy.test",
  "document_type": "REGISTRATION",
  "title": "Test",
  "status": "PARTIAL",
  "source_ids": [],
  "sections": [],
  "placeholder_reason": null
}
-->

# Test

## Untracked rule

Body.
""",
        encoding="utf-8",
    )

    with pytest.raises(DataMarkdownError, match=r"require \[section_id\]"):
        parse_policy_document(path)


def test_policy_parser_rejects_document_type_mismatch() -> None:
    path = REAL_ROOT / "public_policies" / "registration.md"

    with pytest.raises(DataMarkdownError, match="does not match"):
        parse_policy_document(path, expected_type=PolicyDocumentType.EXCEPTIONS)


def test_markdown_parser_rejects_multiple_metadata_blocks(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.md"
    path.write_text(
        "<!-- GEA-METADATA\n{}\n-->\n<!-- GEA-METADATA\n{}\n-->\n",
        encoding="utf-8",
    )

    with pytest.raises(DataMarkdownError, match="exactly one metadata block"):
        parse_policy_document(path)
