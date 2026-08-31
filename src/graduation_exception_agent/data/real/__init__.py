"""Grounded NTU/CCDS data ingestion and repository API."""

from graduation_exception_agent.data.real.loaders import (
    load_academic_calendar,
    load_course_offerings,
    load_courses,
    load_curricula,
    load_policy_corpus,
    load_policy_document,
    load_programmes,
    load_source_manifest,
)
from graduation_exception_agent.data.real.repository import (
    ConsistencyIssue,
    RealDataBundle,
    RealDataRepository,
    validate_real_data,
)

__all__ = [
    "ConsistencyIssue",
    "RealDataBundle",
    "RealDataRepository",
    "load_academic_calendar",
    "load_course_offerings",
    "load_courses",
    "load_curricula",
    "load_policy_corpus",
    "load_policy_document",
    "load_programmes",
    "load_source_manifest",
    "validate_real_data",
]
