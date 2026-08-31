"""Typed loaders that resolve every real-data source reference."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from graduation_exception_agent.data.json_loader import load_model, load_model_list
from graduation_exception_agent.data.real.markdown import (
    parse_academic_calendar,
    parse_policy_document,
)
from graduation_exception_agent.errors import DataIntegrityError
from graduation_exception_agent.models import (
    AcademicCalendarDocument,
    Course,
    CourseOfferingCollection,
    CoverageContract,
    Curriculum,
    PolicyDocument,
    PolicyDocumentType,
    Programme,
    SourceProvenance,
)


POLICY_FILES: tuple[tuple[str, PolicyDocumentType], ...] = (
    ("registration.md", PolicyDocumentType.REGISTRATION),
    ("exceptions.md", PolicyDocumentType.EXCEPTIONS),
    ("approval_structure.md", PolicyDocumentType.APPROVAL_STRUCTURE),
)


def load_source_manifest(path: str | Path) -> tuple[SourceProvenance, ...]:
    records = tuple(load_model_list(path, SourceProvenance))
    source_ids = [record.source_id for record in records]
    duplicates = sorted(
        {source_id for source_id in source_ids if source_ids.count(source_id) > 1}
    )
    if duplicates:
        _raise_integrity(
            path,
            [
                {
                    "code": "DUPLICATE_SOURCE_ID",
                    "record_id": source_id,
                    "field": "source_id",
                    "referenced_id": source_id,
                }
                for source_id in duplicates
            ],
        )
    return records


def load_programmes(
    path: str | Path, *, sources: Iterable[SourceProvenance]
) -> tuple[Programme, ...]:
    records = tuple(load_model_list(path, Programme))
    _validate_source_ids(
        path,
        ((record.programme_id, record.source_ids) for record in records),
        sources,
    )
    return records


def load_curricula(
    path: str | Path, *, sources: Iterable[SourceProvenance]
) -> tuple[Curriculum, ...]:
    records = tuple(load_model_list(path, Curriculum))
    _validate_source_ids(
        path,
        ((record.curriculum_id, record.source_ids) for record in records),
        sources,
    )
    return records


def load_courses(
    path: str | Path, *, sources: Iterable[SourceProvenance]
) -> tuple[Course, ...]:
    records = tuple(load_model_list(path, Course))
    _validate_source_ids(
        path,
        ((f"course.{record.code}", record.source_ids) for record in records),
        sources,
    )
    return records


def load_course_offerings(
    path: str | Path, *, sources: Iterable[SourceProvenance]
) -> CourseOfferingCollection:
    collection = load_model(path, CourseOfferingCollection)
    references = [("dataset.course_offerings", collection.source_ids)]
    references.extend(
        (offering.offering_id, offering.source_ids)
        for offering in collection.offerings
    )
    _validate_source_ids(path, references, sources)
    return collection


def load_coverage_contract(
    path: str | Path, *, sources: Iterable[SourceProvenance]
) -> CoverageContract:
    contract = load_model(path, CoverageContract)
    references: list[tuple[str, Iterable[str]]] = []
    for target in contract.targets:
        references.append((target.target_id, target.discovery_source_ids))
        references.extend(
            (gap.gap_id, gap.source_ids) for gap in target.gaps
        )
    _validate_source_ids(path, references, sources)
    return contract


def load_academic_calendar(
    path: str | Path, *, sources: Iterable[SourceProvenance]
) -> AcademicCalendarDocument:
    document = parse_academic_calendar(path)
    references = [(document.document_id, document.source_ids)]
    references.extend((event.event_id, event.source_ids) for event in document.events)
    _validate_source_ids(path, references, sources)
    return document


def load_policy_document(
    path: str | Path,
    *,
    sources: Iterable[SourceProvenance],
    expected_type: PolicyDocumentType | None = None,
) -> PolicyDocument:
    document = parse_policy_document(path, expected_type=expected_type)
    references = [(document.document_id, document.source_ids)]
    references.extend(
        (section.section_id, section.source_ids) for section in document.sections
    )
    _validate_source_ids(path, references, sources)
    return document


def load_policy_corpus(
    directory: str | Path, *, sources: Iterable[SourceProvenance]
) -> tuple[PolicyDocument, ...]:
    policy_root = Path(directory)
    source_records = tuple(sources)
    return tuple(
        load_policy_document(
            policy_root / filename,
            sources=source_records,
            expected_type=document_type,
        )
        for filename, document_type in POLICY_FILES
    )


def _validate_source_ids(
    path: str | Path,
    references: Iterable[tuple[str, Iterable[str]]],
    sources: Iterable[SourceProvenance],
) -> None:
    known_source_ids = {source.source_id for source in sources}
    issues = [
        {
            "code": "UNKNOWN_SOURCE_ID",
            "record_id": record_id,
            "field": "source_ids",
            "referenced_id": source_id,
        }
        for record_id, source_ids in references
        for source_id in source_ids
        if source_id not in known_source_ids
    ]
    if issues:
        _raise_integrity(path, issues)


def _raise_integrity(path: str | Path, issues: list[dict[str, str]]) -> None:
    raise DataIntegrityError(path, issues)


__all__ = [
    "POLICY_FILES",
    "load_academic_calendar",
    "load_course_offerings",
    "load_coverage_contract",
    "load_courses",
    "load_curricula",
    "load_policy_corpus",
    "load_policy_document",
    "load_programmes",
    "load_source_manifest",
]
