"""Immutable, validated repository for Stage 3 simulation and evaluation data."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from graduation_exception_agent.data.real.repository import (
    ConsistencyIssue,
    ConsistencySeverity,
    RealDataRepository,
)
from graduation_exception_agent.data.simulated.loaders import (
    SIMULATED_FILE_NAMES,
    load_approvals,
    load_audit_assumptions,
    load_current_registrations,
    load_degree_audits,
    load_exception_cases,
    load_generation_manifest,
    load_offering_states,
    load_scenarios,
    load_simulation_scopes,
    load_students,
    load_transaction_scripts,
)
from graduation_exception_agent.data.simulated.validator import validate_stage3_data
from graduation_exception_agent.errors import DataIntegrityError
from graduation_exception_agent.models.academic import (
    DegreeAudit,
    ObservableStudent,
    OfferingState,
    Registration,
    Student,
)
from graduation_exception_agent.models.simulation import (
    AuditAssumption,
    GenerationManifest,
    PrototypePolicy,
    SimulationScope,
)
from graduation_exception_agent.models.workflow import (
    Approval,
    ExceptionCase,
    Scenario,
    ScenarioContext,
    TransactionScript,
)


@dataclass(frozen=True, slots=True)
class Stage3DataBundle:
    """All structurally parsed Stage 3 records, including evaluator-only data."""

    manifest: GenerationManifest
    simulation_scopes: tuple[SimulationScope, ...]
    audit_assumptions: tuple[AuditAssumption, ...]
    offering_states: tuple[OfferingState, ...]
    students: tuple[Student, ...]
    degree_audits: tuple[DegreeAudit, ...]
    current_registrations: tuple[Registration, ...]
    exception_cases: tuple[ExceptionCase, ...]
    approvals: tuple[Approval, ...]
    transaction_scripts: tuple[TransactionScript, ...]
    scenarios: tuple[Scenario, ...]

    @property
    def prototype_policies(self) -> tuple[PrototypePolicy, ...]:
        """Inline policies frozen by the generation manifest."""

        return tuple(self.manifest.prototype_policies)


class SimulatedDataRepository:
    """Validated Stage 3 world with defensive, leakage-aware read methods.

    `bundle` is explicitly evaluator-only because it includes transaction scripts
    and scenario ground truth. Agent code should use `to_agent_context` and the
    entity getters instead.
    """

    def __init__(
        self,
        real_repository: RealDataRepository,
        bundle: Stage3DataBundle,
        *,
        source_path: str | Path = "<in-memory-simulated-data>",
        real_directory: str | Path | None = None,
        enforce_expected_counts: bool = True,
        fail_on_errors: bool = True,
    ) -> None:
        issues = validate_stage3_data(
            real_repository,
            bundle,
            real_directory=real_directory,
            enforce_expected_counts=enforce_expected_counts,
        )
        errors = [
            issue for issue in issues if issue.severity is ConsistencySeverity.ERROR
        ]
        if fail_on_errors and errors:
            raise DataIntegrityError(
                source_path,
                [issue.model_dump(mode="json") for issue in errors],
            )

        self._real_repository = real_repository
        self._bundle = deepcopy(bundle)
        self._consistency_issues = deepcopy(issues)
        self._students = _index(self._bundle.students, "student_id")
        self._audits = _index(self._bundle.degree_audits, "audit_id")
        self._audits_by_student = _index(self._bundle.degree_audits, "student_id")
        self._registrations = _index(
            self._bundle.current_registrations, "registration_id"
        )
        self._registrations_by_student = _index(
            self._bundle.current_registrations, "student_id"
        )
        self._cases = _index(self._bundle.exception_cases, "case_id")
        self._states = _index(self._bundle.offering_states, "state_id")
        self._approvals_by_case = _index(self._bundle.approvals, "case_id")
        self._scenarios = _index(self._bundle.scenarios, "scenario_id")

    @classmethod
    def from_directory(
        cls,
        directory: str | Path,
        *,
        real_repository: RealDataRepository,
        scenarios_path: str | Path | None = None,
        real_directory: str | Path | None = None,
        enforce_expected_counts: bool = True,
        fail_on_errors: bool = True,
    ) -> SimulatedDataRepository:
        """Load all Stage 3 files and apply cross-file validation.

        `directory` is `data/simulated`. When omitted, the scenario path is
        resolved as the sibling `data/tests/scenarios.json`, and the hash source
        directory as sibling `data/real`.
        """

        root = Path(directory)
        scenario_source = (
            Path(scenarios_path)
            if scenarios_path is not None
            else root.parent / "tests" / "scenarios.json"
        )
        real_source = (
            Path(real_directory)
            if real_directory is not None
            else root.parent / "real"
        )
        file = lambda key: root / SIMULATED_FILE_NAMES[key]
        bundle = Stage3DataBundle(
            manifest=load_generation_manifest(file("manifest")),
            simulation_scopes=load_simulation_scopes(file("scopes")),
            audit_assumptions=load_audit_assumptions(file("assumptions")),
            offering_states=load_offering_states(file("offering_states")),
            students=load_students(file("students")),
            degree_audits=load_degree_audits(file("audits")),
            current_registrations=load_current_registrations(file("registrations")),
            exception_cases=load_exception_cases(file("cases")),
            approvals=load_approvals(file("approvals")),
            transaction_scripts=load_transaction_scripts(
                file("transaction_scripts")
            ),
            scenarios=load_scenarios(scenario_source),
        )
        return cls(
            real_repository,
            bundle,
            source_path=root,
            real_directory=real_source,
            enforce_expected_counts=enforce_expected_counts,
            fail_on_errors=fail_on_errors,
        )

    @property
    def bundle(self) -> Stage3DataBundle:
        """Return an evaluator-only defensive copy of the complete bundle."""

        return deepcopy(self._bundle)

    @property
    def consistency_issues(self) -> tuple[ConsistencyIssue, ...]:
        return deepcopy(self._consistency_issues)

    def get_student(self, student_id: str) -> ObservableStudent:
        """Return student facts without the evaluator-only terminal profile."""

        return ObservableStudent.from_student(
            deepcopy(self._students[student_id.upper()])
        )

    def get_audit(self, audit_id: str) -> DegreeAudit:
        return deepcopy(self._audits[audit_id])

    def audit_for_student(self, student_id: str) -> DegreeAudit:
        return deepcopy(self._audits_by_student[student_id.upper()])

    def get_registration(self, registration_id: str) -> Registration:
        return deepcopy(self._registrations[registration_id])

    def registration_for_student(self, student_id: str) -> Registration:
        return deepcopy(self._registrations_by_student[student_id.upper()])

    def get_case(self, case_id: str) -> ExceptionCase:
        return deepcopy(self._cases[case_id])

    def get_offering_state(self, state_id: str) -> OfferingState:
        return deepcopy(self._states[state_id])

    def observable_approval_for_case(self, case_id: str) -> Approval | None:
        approval = self._approvals_by_case.get(case_id)
        if approval is None or not approval.observable:
            return None
        return deepcopy(approval)

    def to_agent_context(self, scenario_id: str) -> ScenarioContext:
        """Return only the model-defined observable scenario context."""

        scenario = self._scenarios[scenario_id]
        context = scenario.to_agent_context()
        # ScenarioContext validates recursive leakage on construction; copy once
        # more so callers cannot mutate repository-owned nested state.
        return context.model_copy(deep=True)


def _index(records: tuple[object, ...], field_name: str) -> Mapping[str, object]:
    return MappingProxyType(
        {str(getattr(record, field_name)): record for record in records}
    )


__all__ = ["SimulatedDataRepository", "Stage3DataBundle"]
