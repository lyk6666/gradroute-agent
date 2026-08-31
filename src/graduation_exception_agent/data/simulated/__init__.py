"""Stage 3 simulated-data loading, validation, and repository API."""

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
from graduation_exception_agent.data.simulated.repository import (
    SimulatedDataRepository,
    Stage3DataBundle,
)
from graduation_exception_agent.data.simulated.validator import (
    EXPECTED_APPROVAL_STATUSES,
    EXPECTED_FAMILY_COUNT,
    EXPECTED_PROFILE_COUNT,
    EXPECTED_RECORD_COUNTS,
    EXPECTED_SPLITS_PER_FAMILY,
    validate_stage3_data,
)

__all__ = [
    "EXPECTED_APPROVAL_STATUSES",
    "EXPECTED_FAMILY_COUNT",
    "EXPECTED_PROFILE_COUNT",
    "EXPECTED_RECORD_COUNTS",
    "EXPECTED_SPLITS_PER_FAMILY",
    "SIMULATED_FILE_NAMES",
    "SimulatedDataRepository",
    "Stage3DataBundle",
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
    "validate_stage3_data",
]
