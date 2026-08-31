"""Strict loaders for the Stage 3 simulated-data package."""

from __future__ import annotations

from pathlib import Path

from graduation_exception_agent.data.json_loader import load_model, load_model_list
from graduation_exception_agent.models.academic import (
    DegreeAudit,
    OfferingState,
    Registration,
    Student,
)
from graduation_exception_agent.models.simulation import (
    AuditAssumption,
    GenerationManifest,
    SimulationScope,
)
from graduation_exception_agent.models.workflow import (
    Approval,
    ExceptionCase,
    Scenario,
    TransactionScript,
)


SIMULATED_FILE_NAMES = {
    "manifest": "generation_manifest.json",
    "scopes": "simulation_scope.json",
    "assumptions": "audit_assumptions.json",
    "offering_states": "offering_states.json",
    "students": "students.json",
    "audits": "degree_audits.json",
    "registrations": "current_registrations.json",
    "cases": "exception_cases.json",
    "approvals": "approvals.json",
    "transaction_scripts": "transaction_results.json",
}


def load_generation_manifest(path: str | Path) -> GenerationManifest:
    """Load the single-object generation manifest."""

    return load_model(path, GenerationManifest)


def load_simulation_scopes(path: str | Path) -> tuple[SimulationScope, ...]:
    return tuple(
        load_model_list(path, SimulationScope, identity_field="simulation_scope_id")
    )


def load_audit_assumptions(path: str | Path) -> tuple[AuditAssumption, ...]:
    return tuple(load_model_list(path, AuditAssumption, identity_field="assumption_id"))


def load_offering_states(path: str | Path) -> tuple[OfferingState, ...]:
    return tuple(load_model_list(path, OfferingState, identity_field="state_id"))


def load_students(path: str | Path) -> tuple[Student, ...]:
    return tuple(load_model_list(path, Student, identity_field="student_id"))


def load_degree_audits(path: str | Path) -> tuple[DegreeAudit, ...]:
    return tuple(load_model_list(path, DegreeAudit, identity_field="audit_id"))


def load_current_registrations(path: str | Path) -> tuple[Registration, ...]:
    return tuple(
        load_model_list(path, Registration, identity_field="registration_id")
    )


def load_exception_cases(path: str | Path) -> tuple[ExceptionCase, ...]:
    return tuple(load_model_list(path, ExceptionCase, identity_field="case_id"))


def load_approvals(path: str | Path) -> tuple[Approval, ...]:
    return tuple(load_model_list(path, Approval, identity_field="approval_id"))


def load_transaction_scripts(path: str | Path) -> tuple[TransactionScript, ...]:
    """Load transaction scripts from the historically named results file."""

    return tuple(load_model_list(path, TransactionScript, identity_field="script_id"))


def load_scenarios(path: str | Path) -> tuple[Scenario, ...]:
    return tuple(load_model_list(path, Scenario, identity_field="scenario_id"))


__all__ = [
    "SIMULATED_FILE_NAMES",
    "load_approvals",
    "load_audit_assumptions",
    "load_current_registrations",
    "load_degree_audits",
    "load_exception_cases",
    "load_generation_manifest",
    "load_offering_states",
    "load_scenarios",
    "load_simulation_scopes",
    "load_students",
    "load_transaction_scripts",
]
