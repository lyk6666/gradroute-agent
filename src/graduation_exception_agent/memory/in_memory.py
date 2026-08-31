"""Deterministic Stage 5 memory-port implementations."""

from __future__ import annotations

from collections.abc import Iterable
from threading import RLock

from graduation_exception_agent.memory.ports import (
    ExperienceMemoryQuery,
    ExperienceMemoryRecord,
    MemoryWriteResult,
    MemoryWriteStatus,
)


class NullExperienceMemory:
    """Explicitly disabled memory with predictable read and write behavior."""

    def retrieve(self, query: ExperienceMemoryQuery) -> list[ExperienceMemoryRecord]:
        ExperienceMemoryQuery.model_validate(
            query.model_dump(mode="python")
            if isinstance(query, ExperienceMemoryQuery)
            else query
        )
        return []

    def write(self, record: ExperienceMemoryRecord) -> MemoryWriteResult:
        validated = _revalidate_record(record)
        return MemoryWriteResult(
            memory_id=validated.memory_id,
            status=MemoryWriteStatus.DISABLED,
            stored=False,
            reason="Long-term advisory memory is disabled.",
        )


class InMemoryExperienceMemory:
    """Thread-safe, bounded-query memory for tests and local development."""

    def __init__(self, records: Iterable[ExperienceMemoryRecord] = ()) -> None:
        self._lock = RLock()
        self._records: dict[str, ExperienceMemoryRecord] = {}
        for record in records:
            result = self.write(record)
            if result.status is not MemoryWriteStatus.STORED:
                raise ValueError(f"could not seed memory {record.memory_id}")

    def retrieve(self, query: ExperienceMemoryQuery) -> list[ExperienceMemoryRecord]:
        validated_query = ExperienceMemoryQuery.model_validate(
            query.model_dump(mode="python")
            if isinstance(query, ExperienceMemoryQuery)
            else query
        )
        excluded = set(validated_query.exclude_memory_ids)
        requested_tags = set(validated_query.tags)
        with self._lock:
            matches = [
                record
                for record in self._records.values()
                if record.active
                and record.memory_id not in excluded
                and (
                    validated_query.case_type is None
                    or record.case_type == validated_query.case_type
                )
                and (
                    validated_query.goal_kind is None
                    or record.goal_kind is validated_query.goal_kind
                )
                and (
                    not requested_tags
                    or bool(requested_tags.intersection(record.tags))
                )
            ]
        matches.sort(key=lambda record: (record.verified_at, record.memory_id), reverse=True)
        return [record.model_copy(deep=True) for record in matches[: validated_query.limit]]

    def write(self, record: ExperienceMemoryRecord) -> MemoryWriteResult:
        # Revalidation here is the write gate.  Callers cannot smuggle an
        # unchecked object through a Protocol-typed boundary.
        validated = _revalidate_record(record)
        with self._lock:
            existing = self._records.get(validated.memory_id)
            if existing is not None:
                if existing != validated:
                    raise ValueError(
                        "memory_id already exists with different deidentified content"
                    )
                return MemoryWriteResult(
                    memory_id=validated.memory_id,
                    status=MemoryWriteStatus.ALREADY_STORED,
                    stored=False,
                    reason="Identical verified experience was already stored.",
                )
            self._records[validated.memory_id] = validated.model_copy(deep=True)
        return MemoryWriteResult(
            memory_id=validated.memory_id,
            status=MemoryWriteStatus.STORED,
            stored=True,
            reason="Verified deidentified experience stored as advisory memory.",
        )

    def snapshot(self) -> tuple[ExperienceMemoryRecord, ...]:
        """Return an immutable deep-copy snapshot for deterministic test seeding."""

        with self._lock:
            records = sorted(self._records.values(), key=lambda record: record.memory_id)
            return tuple(record.model_copy(deep=True) for record in records)


def _revalidate_record(record: ExperienceMemoryRecord) -> ExperienceMemoryRecord:
    payload = (
        record.model_dump(mode="python")
        if isinstance(record, ExperienceMemoryRecord)
        else record
    )
    return ExperienceMemoryRecord.model_validate(payload)
