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
