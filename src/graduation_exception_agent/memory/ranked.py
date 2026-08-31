"""Deterministic relevance ranking for deidentified advisory experience."""

from __future__ import annotations

from collections.abc import Iterable

from graduation_exception_agent.memory.in_memory import InMemoryExperienceMemory
from graduation_exception_agent.memory.ports import (
    ExperienceMemoryQuery,
    ExperienceMemoryRecord,
)


class RankedInMemoryExperienceMemory(InMemoryExperienceMemory):
    """Retrieve exact or related patterns with transparent weighted ranking."""

    def __init__(self, records: Iterable[ExperienceMemoryRecord] = ()) -> None:
        super().__init__(records)

    def retrieve(self, query: ExperienceMemoryQuery) -> list[ExperienceMemoryRecord]:
        validated = ExperienceMemoryQuery.model_validate(
            query.model_dump(mode="python")
            if isinstance(query, ExperienceMemoryQuery)
            else query
        )
        excluded = set(validated.exclude_memory_ids)
        requested_tags = set(validated.tags)
        ranked: list[tuple[int, float, str, ExperienceMemoryRecord]] = []
        has_filter = bool(
            validated.case_type or validated.goal_kind or requested_tags
        )
        for record in self.snapshot():
            if not record.active or record.memory_id in excluded:
                continue
            score = 0
            if validated.case_type and record.case_type == validated.case_type:
                score += 8
            if validated.goal_kind and record.goal_kind is validated.goal_kind:
                score += 5
            score += 2 * len(requested_tags.intersection(record.tags))
            if has_filter and score == 0:
                continue
            ranked.append(
                (score, record.verified_at.timestamp(), record.memory_id, record)
            )
        ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return [
            item[3].model_copy(deep=True)
            for item in ranked[: validated.limit]
        ]


__all__ = ["RankedInMemoryExperienceMemory"]
