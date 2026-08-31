"""Deterministic simulation metadata and explicit prototype-policy contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, JsonValue, field_validator, model_validator

from graduation_exception_agent.models.academic import AuditBasis, Semester
from graduation_exception_agent.models.common import (
    AcademicYear,
    AdmissionCohort,
    DomainModel,
    GeneratedModel,
    Identifier,
    NonEmptyText,
    ProgrammeCode,
    SourceOrigin,
)


SIMULATED_POLICY_BANNER = "SIMULATED POLICY FOR PROTOTYPE"


def _unique(values: list[str], field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


class AuditAssumptionKind(StrEnum):
    SOURCE_BACKED_DERIVATION = "SOURCE_BACKED_DERIVATION"
    PROTOTYPE_MAPPING = "PROTOTYPE_MAPPING"
    TEMPORAL_TEMPLATE = "TEMPORAL_TEMPLATE"
    OPERATIONAL_STATE = "OPERATIONAL_STATE"


class GenerationManifest(DomainModel):
    """Inputs and counts needed to reproduce one complete generated package."""

    manifest_id: Identifier
    generator_version: NonEmptyText
    global_seed: int = Field(ge=0)
    generated_at: datetime
    coverage_contract_id: Identifier
    real_data_hashes: dict[Identifier, str] = Field(min_length=1)
    source_rule_ids: list[Identifier] = Field(min_length=1)
    simulation_period_ids: list[Identifier] = Field(min_length=1)
    simulation_period_rule: NonEmptyText
    prototype_policies: list[PrototypePolicy] = Field(default_factory=list)
    prototype_policy_versions: dict[Identifier, NonEmptyText] = Field(
        default_factory=dict
    )
    record_counts: dict[Identifier, int] = Field(min_length=1)

    @field_validator("generated_at")
    @classmethod
    def timezone_aware_generation_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("generated_at must include a timezone")
        return value

    @field_validator("real_data_hashes")
    @classmethod
    def valid_sha256_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        for name, digest in value.items():
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise ValueError(f"real_data_hashes[{name}] must be lowercase SHA-256")
        return value

    @field_validator("source_rule_ids", "simulation_period_ids")
    @classmethod
    def unique_manifest_lists(cls, value: list[str], info: object) -> list[str]:
        return _unique(value, getattr(info, "field_name", "values"))

    @field_validator("record_counts")
    @classmethod
    def nonnegative_record_counts(cls, value: dict[str, int]) -> dict[str, int]:
        if any(count < 0 for count in value.values()):
            raise ValueError("record_counts must be nonnegative")
        return value

    @model_validator(mode="after")
    def validate_prototype_policy_inventory(self) -> GenerationManifest:
        _unique(
            [policy.policy_id for policy in self.prototype_policies],
            "prototype_policy_ids",
        )
        versions = {
            policy.policy_id: policy.version for policy in self.prototype_policies
        }
        if versions != self.prototype_policy_versions:
            raise ValueError(
                "prototype_policy_versions must exactly index prototype_policies"
            )
        return self


class SimulationScope(GeneratedModel):
    """One curriculum-specific mapping into a counterfactual future period."""

    simulation_scope_id: Identifier
    curriculum_id: Identifier
    programme: ProgrammeCode
    admission_cohort: AdmissionCohort
    simulation_period_id: Identifier
    simulation_academic_year: AcademicYear
    simulation_semester: Semester
    template_academic_year: AcademicYear
    template_semester: Semester
    terminal_study_year: int = Field(ge=1, le=8)
    student_count: int = Field(gt=0)
    audit_basis: AuditBasis = AuditBasis.SCENARIO_BOUNDED_SIMULATION
    counterfactual_time_basis: NonEmptyText
    permitted_graduation_path_ids: list[Identifier] = Field(default_factory=list)
    permitted_study_plan_path_labels: list[NonEmptyText] = Field(
        default_factory=list
    )
    accepted_gap_ids: list[Identifier] = Field(default_factory=list)
    assumption_ids: list[Identifier] = Field(default_factory=list)

    @field_validator(
        "permitted_graduation_path_ids",
        "permitted_study_plan_path_labels",
        "accepted_gap_ids",
        "assumption_ids",
    )
    @classmethod
    def unique_scope_lists(cls, value: list[str], info: object) -> list[str]:
        return _unique(value, getattr(info, "field_name", "values"))


class AuditAssumption(GeneratedModel):
    """A declared derivation or prototype mapping used by generated audits."""

    assumption_id: Identifier
    simulation_scope_id: Identifier
    kind: AuditAssumptionKind
    description: NonEmptyText
    declared_value: JsonValue
    affected_record_ids: list[Identifier] = Field(min_length=1)
    limitations: list[NonEmptyText] = Field(default_factory=list)
    prototype_policy_id: Identifier | None = None

    @field_validator("affected_record_ids", "limitations")
    @classmethod
    def unique_assumption_lists(cls, value: list[str], info: object) -> list[str]:
        return _unique(value, getattr(info, "field_name", "values"))

    @model_validator(mode="after")
    def validate_prototype_link(self) -> AuditAssumption:
        if (
            self.kind is AuditAssumptionKind.PROTOTYPE_MAPPING
            and self.prototype_policy_id is None
        ):
            raise ValueError("prototype mappings require prototype_policy_id")
        if (
            self.kind is AuditAssumptionKind.SOURCE_BACKED_DERIVATION
            and self.prototype_policy_id is not None
        ):
            raise ValueError(
                "source-backed derivations cannot cite a prototype policy"
            )
        return self


class PrototypePolicy(GeneratedModel):
    """An invented policy that cannot masquerade as verified university policy."""

    policy_id: Identifier
    title: NonEmptyText
    origin: SourceOrigin
    body_markdown: NonEmptyText
    applicable_academic_years: list[AcademicYear] = Field(default_factory=list)
    applicable_admission_cohorts: list[AdmissionCohort] = Field(
        default_factory=list
    )
    applicability_note: NonEmptyText
    version: NonEmptyText

    @field_validator("applicable_academic_years", "applicable_admission_cohorts")
    @classmethod
    def unique_applicability(cls, value: list[str], info: object) -> list[str]:
        return _unique(value, getattr(info, "field_name", "applicability"))

    @model_validator(mode="after")
    def validate_simulated_policy_metadata(self) -> PrototypePolicy:
        if self.origin is not SourceOrigin.SIMULATED_POLICY:
            raise ValueError("prototype policy origin must be SIMULATED_POLICY")
        first_line = next(
            (line.strip() for line in self.body_markdown.splitlines() if line.strip()),
            "",
        )
        if first_line != SIMULATED_POLICY_BANNER:
            raise ValueError(
                f"prototype policy must begin with exact banner {SIMULATED_POLICY_BANNER!r}"
            )
        if not (
            self.applicable_academic_years or self.applicable_admission_cohorts
        ):
            raise ValueError(
                "prototype policy requires academic-year or admission-cohort applicability"
            )
        return self
