"""Shared helpers for the four deterministic Stage 4 tool domains."""

from __future__ import annotations

from collections.abc import Iterable

from graduation_exception_agent.data.real.repository import RealDataRepository
from graduation_exception_agent.models.academic import DataCompleteness
from graduation_exception_agent.models.common import SourceOrigin
from graduation_exception_agent.models.tooling import (
    ToolCallContext,
    ToolError,
    ToolErrorCode,
    ToolProvenance,
    ToolResponse,
    ToolStatus,
)
from graduation_exception_agent.runtime.session import RuntimeSession


def validate_read_context(
    session: RuntimeSession, context: ToolCallContext
) -> ToolResponse | None:
    if context.session_id != session.session_id or context.case_id != session.case_id:
        return failure(
            context,
            ToolErrorCode.FORBIDDEN,
            "The requested record is outside this isolated case session.",
        )
    return None


def success(
    context: ToolCallContext,
    data: object,
    *,
    provenance: Iterable[ToolProvenance] = (),
    entity_versions: dict[str, int] | None = None,
) -> ToolResponse:
    return ToolResponse(
        request_id=context.request_id,
        status=ToolStatus.SUCCESS,
        data=data,  # type: ignore[arg-type]
        provenance=list(provenance),
        entity_versions={} if entity_versions is None else entity_versions,
    )


def failure(
    context: ToolCallContext,
    code: ToolErrorCode,
    message: str,
    *,
    retryable: bool = False,
    details: dict[str, object] | None = None,
) -> ToolResponse:
    return ToolResponse(
        request_id=context.request_id,
        status=ToolStatus.FAILURE,
        error=ToolError(
            code=code,
            message=message,
            retryable=retryable,
            details={} if details is None else details,  # type: ignore[arg-type]
        ),
    )


def simulated_provenance(
    *,
    record_id: str,
    rule_ids: Iterable[str],
    completeness: DataCompleteness = DataCompleteness.COMPLETE,
    origin: SourceOrigin = SourceOrigin.UNKNOWN,
    note: str | None = None,
) -> ToolProvenance:
    rules = list(dict.fromkeys(str(value) for value in rule_ids))
    if not rules:
        rules = ["runtime.stage4.observable-copy"]
    return ToolProvenance(
        source_ids=[],
        rule_ids=rules,
        derived_from_ids=[record_id],
        origin=origin,
        completeness=completeness,
        note=note or "Observable simulated fact derived from the frozen Stage 3 package.",
    )


def real_provenance(
    real: RealDataRepository,
    source_ids: Iterable[str],
    *,
    completeness: DataCompleteness,
    rule_ids: Iterable[str] = (),
    note: str | None = None,
) -> list[ToolProvenance]:
    rules = list(dict.fromkeys(str(value) for value in rule_ids))
    output: list[ToolProvenance] = []
    for source_id in dict.fromkeys(str(value) for value in source_ids):
        source = real.get_source(source_id)
        output.append(
            ToolProvenance(
                source_ids=[source_id],
                rule_ids=rules,
                origin=source.origin,
                completeness=completeness,
                note=note,
            )
        )
    return output


__all__ = [
    "failure",
    "real_provenance",
    "simulated_provenance",
    "success",
    "validate_read_context",
]
