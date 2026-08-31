"""Machine-checkable completeness contract for the grounded real-data bundle."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from graduation_exception_agent.models.common import (
    DomainModel,
    Identifier,
    NonEmptyText,
)


def _unique(values: list[str], field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


class CoverageStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class CoverageDataset(StrEnum):
    PROGRAMMES = "PROGRAMMES"
    CURRICULA = "CURRICULA"
    COURSES = "COURSES"
    COURSE_OFFERINGS = "COURSE_OFFERINGS"
    ACADEMIC_CALENDAR = "ACADEMIC_CALENDAR"
    REGISTRATION_GUIDANCE = "REGISTRATION_GUIDANCE"
    EXCEPTION_POLICIES = "EXCEPTION_POLICIES"
    APPROVAL_STRUCTURE = "APPROVAL_STRUCTURE"


class CoverageDimension(StrEnum):
    INVENTORY = "INVENTORY"
    CONTENT = "CONTENT"


class CoverageGap(DomainModel):
    gap_id: Identifier
    dimension: CoverageDimension
    affected_record_ids: list[Identifier] = Field(default_factory=list)
    affected_fields: list[Identifier] = Field(min_length=1)
    reason: NonEmptyText
    source_ids: list[Identifier] = Field(min_length=1)

    @field_validator(
        "affected_record_ids",
        "affected_fields",
        "source_ids",
    )
    @classmethod
    def unique_values(cls, value: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "values")
        return _unique(value, field_name)


class DatasetCoverage(DomainModel):
    target_id: Identifier
    dataset: CoverageDataset
    scope_description: NonEmptyText
    scope_parameters: dict[Identifier, list[NonEmptyText]] = Field(
        default_factory=dict
    )
    expected_record_count: int = Field(ge=0)
    expected_record_ids: list[Identifier] = Field(default_factory=list)
    inventory_status: CoverageStatus
    content_status: CoverageStatus
    required_fields: list[Identifier] = Field(min_length=1)
    discovery_source_ids: list[Identifier] = Field(min_length=1)
    gaps: list[CoverageGap] = Field(default_factory=list)

    @field_validator(
        "expected_record_ids",
        "required_fields",
        "discovery_source_ids",
    )
    @classmethod
    def unique_values(cls, value: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "values")
        return _unique(value, field_name)

    @field_validator("scope_parameters")
    @classmethod
    def unique_scope_values(
        cls, value: dict[str, list[str]]
    ) -> dict[str, list[str]]:
        for key, values in value.items():
            _unique(values, f"scope_parameters[{key}]")
        return value

    @model_validator(mode="after")
    def validate_claim(self) -> DatasetCoverage:
        if self.expected_record_count != len(self.expected_record_ids):
            raise ValueError(
                "expected_record_count must equal len(expected_record_ids)"
            )
        gap_ids = [gap.gap_id for gap in self.gaps]
        _unique(gap_ids, "gap_ids")
        for dimension, status in (
            (CoverageDimension.INVENTORY, self.inventory_status),
            (CoverageDimension.CONTENT, self.content_status),
        ):
            dimension_gaps = [
                gap for gap in self.gaps if gap.dimension is dimension
            ]
            if status is CoverageStatus.COMPLETE and dimension_gaps:
                raise ValueError(
                    f"{dimension.value} COMPLETE cannot contain matching gaps"
                )
            if status is not CoverageStatus.COMPLETE and not dimension_gaps:
                raise ValueError(
                    f"{dimension.value} {status.value} requires a matching gap"
                )
        return self


class CoverageContract(DomainModel):
    contract_id: Identifier
    as_of: datetime
    scope_description: NonEmptyText
    targets: list[DatasetCoverage] = Field(min_length=1)

    @field_validator("as_of")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        return value

    @model_validator(mode="after")
    def unique_targets(self) -> CoverageContract:
        _unique([target.target_id for target in self.targets], "target_ids")
        _unique(
            [target.dataset.value for target in self.targets],
            "coverage datasets",
        )
        return self


__all__ = [
    "CoverageContract",
    "CoverageDataset",
    "CoverageDimension",
    "CoverageGap",
    "CoverageStatus",
    "DatasetCoverage",
]
