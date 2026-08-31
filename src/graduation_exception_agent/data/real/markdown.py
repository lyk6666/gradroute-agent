"""Strict parsers for provenance-bearing Markdown data documents."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError, field_validator

from graduation_exception_agent.errors import (
    DataDecodeError,
    DataFileNotFoundError,
    DataLoadError,
    DataMarkdownError,
    DataSchemaError,
)
from graduation_exception_agent.models import (
    AcademicCalendarDocument,
    AcademicYear,
    AdmissionCohort,
    CalendarEvent,
    DocumentStatus,
    DomainModel,
    Identifier,
    NonEmptyText,
    PolicyApplicability,
    PolicyDocument,
    PolicyDocumentType,
    PolicySection,
    SourceOrigin,
)


_METADATA_PATTERN = re.compile(
    r"\A<!-- GEA-METADATA\r?\n(?P<payload>.*?)\r?\n-->\r?\n",
    flags=re.DOTALL,
)
_SECTION_PATTERN = re.compile(
    r"^## \[(?P<section_id>[A-Za-z0-9][A-Za-z0-9_.:-]*)\] "
    r"(?P<title>\S.*)$"
)


def _unique(values: list[str], field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


class _PolicySectionMetadata(DomainModel):
    section_id: Identifier
    origin: SourceOrigin
    source_ids: list[Identifier] = Field(default_factory=list)
    applicability: PolicyApplicability
    applicable_academic_years: list[AcademicYear] = Field(default_factory=list)
    applicable_admission_cohorts: list[AdmissionCohort] = Field(default_factory=list)
    applicability_note: NonEmptyText

    @field_validator(
        "source_ids", "applicable_academic_years", "applicable_admission_cohorts"
    )
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        return _unique(value, "source_ids")


class _PolicyMetadata(DomainModel):
    document_id: Identifier
    document_type: PolicyDocumentType
    title: NonEmptyText
    status: DocumentStatus
    source_ids: list[Identifier] = Field(default_factory=list)
    sections: list[_PolicySectionMetadata] = Field(default_factory=list)
    placeholder_reason: NonEmptyText | None = None

    @field_validator("source_ids")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        return _unique(value, "source_ids")

    @field_validator("sections")
    @classmethod
    def unique_sections(
        cls, value: list[_PolicySectionMetadata]
    ) -> list[_PolicySectionMetadata]:
        _unique([section.section_id for section in value], "section_ids")
        return value


class _CalendarMetadata(DomainModel):
    document_id: Identifier
    document_type: str = Field(pattern=r"^ACADEMIC_CALENDAR$")
    title: NonEmptyText
    status: DocumentStatus
    academic_year: AcademicYear
    timezone: str = Field(pattern=r"^Asia/Singapore$")
    source_ids: list[Identifier] = Field(min_length=1)
    events: list[CalendarEvent] = Field(min_length=1)
    placeholder_reason: NonEmptyText | None = None

    @field_validator("source_ids")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        return _unique(value, "source_ids")

    @field_validator("events")
    @classmethod
    def unique_events(cls, value: list[CalendarEvent]) -> list[CalendarEvent]:
        _unique([event.event_id for event in value], "event_ids")
        return value


def _read_markdown(path: str | Path) -> tuple[Path, str]:
    source = Path(path)
    try:
        return source, source.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DataFileNotFoundError(source, "file does not exist") from exc
    except UnicodeDecodeError as exc:
        raise DataDecodeError(source, "file is not valid UTF-8") from exc
    except OSError as exc:
        raise DataLoadError(
            source, f"file could not be read ({exc.__class__.__name__})"
        ) from exc


def _metadata_payload(path: Path, raw_markdown: str) -> dict[str, Any]:
    match = _METADATA_PATTERN.match(raw_markdown)
    if match is None:
        raise DataMarkdownError(
            path,
            "document must begin with exactly one <!-- GEA-METADATA JSON --> block",
        )
    if raw_markdown.count("<!-- GEA-METADATA") != 1:
        raise DataMarkdownError(path, "document must contain exactly one metadata block")
    try:
        payload = json.loads(match.group("payload"))
    except json.JSONDecodeError as exc:
        raise DataDecodeError(
            path,
            f"invalid metadata JSON at line {exc.lineno + 1}, column {exc.colno}",
        ) from exc
    if not isinstance(payload, dict):
        raise DataMarkdownError(path, "metadata JSON must be an object")
    return payload


def _validate_metadata(
    path: Path, payload: dict[str, Any], model_type: type[DomainModel]
) -> DomainModel:
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise DataSchemaError(
            path, exc.errors(include_input=False, include_url=False)
        ) from exc


def parse_policy_document(
    path: str | Path,
    *,
    expected_type: PolicyDocumentType | None = None,
) -> PolicyDocument:
    """Parse policy Markdown without resolving cross-file source references."""

    source, raw_markdown = _read_markdown(path)
    payload = _metadata_payload(source, raw_markdown)
    metadata = _validate_metadata(source, payload, _PolicyMetadata)
    assert isinstance(metadata, _PolicyMetadata)
    if expected_type is not None and metadata.document_type is not expected_type:
        raise DataMarkdownError(
            source,
            f"declared document_type {metadata.document_type} does not match "
            f"expected {expected_type}",
        )

    lines = raw_markdown.splitlines()
    headings: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        if not line.startswith("## "):
            continue
        match = _SECTION_PATTERN.fullmatch(line)
        if match is None:
            raise DataMarkdownError(
                source,
                f"line {index + 1}: level-two headings require [section_id]",
            )
        headings.append(
            (index, match.group("section_id"), match.group("title").strip())
        )

    heading_ids = [section_id for _, section_id, _ in headings]
    _raise_duplicate_section_ids(source, heading_ids)
    metadata_by_id = {
        section.section_id: section for section in metadata.sections
    }
    if set(heading_ids) != set(metadata_by_id):
        missing_headings = sorted(set(metadata_by_id) - set(heading_ids))
        missing_metadata = sorted(set(heading_ids) - set(metadata_by_id))
        raise DataMarkdownError(
            source,
            "section/metadata mismatch "
            f"(missing headings={missing_headings}, "
            f"missing metadata={missing_metadata})",
        )

    sections: list[PolicySection] = []
    for position, (line_index, section_id, title) in enumerate(headings):
        next_index = (
            headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        )
        body = "\n".join(lines[line_index + 1 : next_index]).strip()
        entry = metadata_by_id[section_id]
        try:
            sections.append(
                PolicySection(
                    section_id=section_id,
                    title=title,
                    origin=entry.origin,
                    source_ids=entry.source_ids,
                    applicability=entry.applicability,
                    applicable_academic_years=entry.applicable_academic_years,
                    applicable_admission_cohorts=entry.applicable_admission_cohorts,
                    applicability_note=entry.applicability_note,
                    body_markdown=body,
                    start_line=line_index + 1,
                    end_line=max(line_index + 1, next_index),
                )
            )
        except ValidationError as exc:
            raise DataSchemaError(
                source, exc.errors(include_input=False, include_url=False)
            ) from exc

    digest = hashlib.sha256(raw_markdown.encode("utf-8")).hexdigest()
    try:
        return PolicyDocument(
            document_id=metadata.document_id,
            document_type=metadata.document_type,
            title=metadata.title,
            status=metadata.status,
            source_ids=metadata.source_ids,
            sections=sections,
            raw_markdown=raw_markdown,
            content_sha256=digest,
            placeholder_reason=metadata.placeholder_reason,
        )
    except ValidationError as exc:
        raise DataSchemaError(
            source, exc.errors(include_input=False, include_url=False)
        ) from exc


def _raise_duplicate_section_ids(path: Path, values: list[str]) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise DataMarkdownError(path, f"duplicate section IDs: {duplicates}")


def parse_academic_calendar(path: str | Path) -> AcademicCalendarDocument:
    """Parse calendar Markdown without resolving cross-file source references."""

    source, raw_markdown = _read_markdown(path)
    payload = _metadata_payload(source, raw_markdown)
    metadata = _validate_metadata(source, payload, _CalendarMetadata)
    assert isinstance(metadata, _CalendarMetadata)
    digest = hashlib.sha256(raw_markdown.encode("utf-8")).hexdigest()
    try:
        return AcademicCalendarDocument(
            document_id=metadata.document_id,
            title=metadata.title,
            status=metadata.status,
            academic_year=metadata.academic_year,
            timezone=metadata.timezone,
            source_ids=metadata.source_ids,
            events=metadata.events,
            raw_markdown=raw_markdown,
            content_sha256=digest,
            placeholder_reason=metadata.placeholder_reason,
        )
    except ValidationError as exc:
        raise DataSchemaError(
            source, exc.errors(include_input=False, include_url=False)
        ) from exc
