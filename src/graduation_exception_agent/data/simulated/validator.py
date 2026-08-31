"""Deterministic cross-file validation for Stage 3 simulated data."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
import hashlib
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Mapping

from pydantic import BaseModel, ValidationError

from graduation_exception_agent.data.real.repository import (
    ConsistencyIssue,
    ConsistencySeverity,
    RealDataRepository,
)
from graduation_exception_agent.models.academic import (
    CreditStatus,
    RuntimeOfferingStatus,
)
from graduation_exception_agent.models.workflow import (
    ApprovalStatus,
    EventType,
    ExpectedOutcome,
    ObservationCode,
    ScenarioFamily,
    ScenarioSplit,
    StateTargetType,
    TransactionAction,
    TransactionCode,
)
from graduation_exception_agent.rules import (
    PrerequisiteResult,
    evaluate_prerequisite,
)

if TYPE_CHECKING:
    from graduation_exception_agent.data.simulated.repository import Stage3DataBundle


EXPECTED_RECORD_COUNTS: Mapping[str, int] = {
    "simulation_scopes": 17,
    "offering_states": 2_108,
    "students": 240,
    "degree_audits": 240,
    "current_registrations": 240,
    "exception_cases": 140,
    "approvals": 60,
    "transaction_scripts": 140,
    "scenarios": 140,
}

EXPECTED_PROFILE_COUNT = 60
EXPECTED_FAMILY_COUNT = 20
EXPECTED_SPLITS_PER_FAMILY: Mapping[str, int] = {
    ScenarioSplit.DEVELOPMENT.value: 4,
    ScenarioSplit.DEMO.value: 1,
    ScenarioSplit.EVALUATION.value: 15,
}
EXPECTED_APPROVAL_STATUSES: Mapping[str, int] = {
    ApprovalStatus.APPROVED.value: 24,
    ApprovalStatus.REJECTED.value: 24,
    ApprovalStatus.PENDING.value: 12,
}

_IDENTITY_FIELDS: Mapping[str, str] = {
    "simulation_scopes": "simulation_scope_id",
    "audit_assumptions": "assumption_id",
    "prototype_policies": "policy_id",
    "offering_states": "state_id",
    "students": "student_id",
    "degree_audits": "audit_id",
    "current_registrations": "registration_id",
    "exception_cases": "case_id",
    "approvals": "approval_id",
    "transaction_scripts": "script_id",
    "scenarios": "scenario_id",
}

_RESULT_OBSERVATIONS: Mapping[str, str] = {
    TransactionCode.SUCCESS.value: ObservationCode.TRANSACTION_SUCCESS.value,
    TransactionCode.EXCEPTION_SUBMISSION_SUCCESS.value: (
        ObservationCode.TRANSACTION_SUCCESS.value
    ),
    TransactionCode.MODULE_FULL.value: ObservationCode.MODULE_FULL.value,
    TransactionCode.CLASS_UNAVAILABLE.value: ObservationCode.CLASS_UNAVAILABLE.value,
    TransactionCode.PREREQUISITE_FAILURE.value: (
        ObservationCode.PREREQUISITE_FAILURE.value
    ),
    TransactionCode.APPROVAL_REJECTED.value: ObservationCode.APPROVAL_REJECTED.value,
    TransactionCode.APPROVAL_PENDING.value: ObservationCode.APPROVAL_PENDING.value,
    TransactionCode.STALE_STATE.value: ObservationCode.STALE_STATE.value,
    TransactionCode.TEMPORARY_SYSTEM_FAILURE.value: (
        ObservationCode.TEMPORARY_FAILURE.value
    ),
    TransactionCode.REQUIRED_INFORMATION_MISSING.value: (
        ObservationCode.REQUIRED_INFORMATION_MISSING.value
    ),
}

_EVENT_RESULTS: Mapping[str, tuple[str, str]] = {
    EventType.VACANCY_BECOMES_ZERO.value: (
        TransactionCode.MODULE_FULL.value,
        ObservationCode.MODULE_FULL.value,
    ),
    EventType.CLASS_BECOMES_UNAVAILABLE.value: (
        TransactionCode.CLASS_UNAVAILABLE.value,
        ObservationCode.CLASS_UNAVAILABLE.value,
    ),
    EventType.APPROVAL_GRANTED.value: (
        TransactionCode.SUCCESS.value,
        ObservationCode.TRANSACTION_SUCCESS.value,
    ),
    EventType.APPROVAL_REJECTED.value: (
        TransactionCode.APPROVAL_REJECTED.value,
        ObservationCode.APPROVAL_REJECTED.value,
    ),
    EventType.APPROVAL_PENDING.value: (
        TransactionCode.APPROVAL_PENDING.value,
        ObservationCode.APPROVAL_PENDING.value,
    ),
    EventType.TEMPORARY_TRANSACTION_FAILURE.value: (
        TransactionCode.TEMPORARY_SYSTEM_FAILURE.value,
        ObservationCode.TEMPORARY_FAILURE.value,
    ),
    EventType.STATE_CHANGED_BEFORE_COMMIT.value: (
        TransactionCode.STALE_STATE.value,
        ObservationCode.STALE_STATE.value,
    ),
    EventType.REQUIRED_INFORMATION_MISSING.value: (
        TransactionCode.REQUIRED_INFORMATION_MISSING.value,
        ObservationCode.REQUIRED_INFORMATION_MISSING.value,
    ),
}

_MUST_RETRY_RESULTS = {
    TransactionCode.STALE_STATE.value,
    TransactionCode.TEMPORARY_SYSTEM_FAILURE.value,
}

_MUTABLE_FIELDS_BY_TARGET_TYPE: Mapping[str, frozenset[str]] = {
    StateTargetType.OFFERING_STATE.value: frozenset(
        {
            "capacity",
            "vacancies",
            "waitlist_count",
            "runtime_status",
            "available",
            "unavailable_reason",
        }
    ),
    StateTargetType.APPROVAL.value: frozenset(
        {
            "status",
            "observable",
            "decision_reason",
            "decided_at",
        }
    ),
}

_TARGET_MODEL_BY_TARGET_TYPE: Mapping[str, str] = {
    StateTargetType.OFFERING_STATE.value: "OfferingState",
    StateTargetType.APPROVAL.value: "Approval",
}

_LEAKAGE_KEYS = {
    "approval_decision",
    "approval_status",
    "decision_reason",
    "event_type",
    "expected_outcome",
    "family",
    "final_state",
    "future_event",
    "ground_truth",
    "injected_event",
    "invalid_paths",
    "post_event_state",
    "scenario_id",
    "script_id",
    "split",
    "terminal_profile",
    "transaction_script",
    "transaction_script_id",
    "valid_final_paths",
    "valid_initial_paths",
}

_REQUIRED_REAL_HASH_PATHS = {
    "academic_calendar.md",
    "course_offerings.json",
    "courses.json",
    "coverage.json",
    "curriculum.json",
    "programmes.json",
    "public_policies/approval_structure.md",
    "public_policies/exceptions.md",
    "public_policies/registration.md",
    "source_manifest.json",
}

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class _Issues:
    def __init__(self) -> None:
        self.items: list[ConsistencyIssue] = []

    def add(
        self,
        code: str,
        dataset: str,
        record_id: str,
        field: str,
        message: str,
        *,
        referenced_id: str | None = None,
        severity: ConsistencySeverity = ConsistencySeverity.ERROR,
    ) -> None:
        safe_reference = (
            referenced_id
            if referenced_id is None or _IDENTIFIER_PATTERN.fullmatch(referenced_id)
            else None
        )
        self.items.append(
            ConsistencyIssue(
                code=code,
                severity=severity,
                dataset=dataset,
                record_id=record_id,
                field=field,
                referenced_id=safe_reference,
                message=message,
            )
        )

    def result(self) -> tuple[ConsistencyIssue, ...]:
        return tuple(
            sorted(
                self.items,
                key=lambda issue: (
                    issue.severity.value,
                    issue.dataset,
                    issue.record_id,
                    issue.field,
                    issue.code,
                    issue.referenced_id or "",
                ),
            )
        )


def validate_stage3_data(
    real_repository: RealDataRepository,
    bundle: Stage3DataBundle,
    *,
    real_directory: str | Path | None = None,
    enforce_expected_counts: bool = True,
) -> tuple[ConsistencyIssue, ...]:
    """Return all Stage 3 integrity issues in deterministic order."""

    issues = _Issues()
    datasets = _bundle_datasets(bundle)
    _check_duplicate_ids(datasets, issues)
    _check_global_ids(datasets, issues)
    _check_manifest(
        real_repository,
        bundle,
        datasets,
        issues,
        real_directory=Path(real_directory) if real_directory else None,
        enforce_expected_counts=enforce_expected_counts,
    )

    real = _RealIndex(real_repository)
    scope_by_id = _by_id(bundle.simulation_scopes, "simulation_scope_id")
    assumption_by_id = _by_id(bundle.audit_assumptions, "assumption_id")
    state_by_id = _by_id(bundle.offering_states, "state_id")
    student_by_id = _by_id(bundle.students, "student_id")
    audit_by_id = _by_id(bundle.degree_audits, "audit_id")
    registration_by_id = _by_id(bundle.current_registrations, "registration_id")
    case_by_id = _by_id(bundle.exception_cases, "case_id")
    approval_by_id = _by_id(bundle.approvals, "approval_id")
    script_by_id = _by_id(bundle.transaction_scripts, "script_id")

    _check_scopes(bundle, real, issues)
    _check_offering_states(bundle, real, scope_by_id, issues)
    _check_students(
        bundle,
        real,
        scope_by_id,
        issues,
        enforce_expected_counts=enforce_expected_counts,
    )
    _check_audits(bundle, real, scope_by_id, student_by_id, issues)
    _check_registrations(
        bundle,
        real,
        scope_by_id,
        state_by_id,
        student_by_id,
        issues,
    )
    _check_cases(
        bundle,
        real,
        student_by_id,
        audit_by_id,
        registration_by_id,
        issues,
    )
    _check_approvals(bundle, case_by_id, issues, enforce_expected_counts)
    _check_scripts(
        bundle,
        real,
        case_by_id,
        approval_by_id,
        state_by_id,
        issues,
    )
    _check_scenarios(
        bundle,
        real,
        student_by_id,
        audit_by_id,
        registration_by_id,
        case_by_id,
        approval_by_id,
        script_by_id,
        state_by_id,
        issues,
        enforce_expected_counts,
    )
    _check_one_per_student(bundle, issues)
    _check_generated_metadata(bundle, issues)
    _check_rule_and_assumption_references(
        bundle,
        real,
        assumption_by_id,
        issues,
    )
    return issues.result()


def _bundle_datasets(bundle: Stage3DataBundle) -> dict[str, tuple[Any, ...]]:
    return {
        "simulation_scopes": tuple(bundle.simulation_scopes),
        "audit_assumptions": tuple(bundle.audit_assumptions),
        "prototype_policies": tuple(bundle.prototype_policies),
        "offering_states": tuple(bundle.offering_states),
        "students": tuple(bundle.students),
        "degree_audits": tuple(bundle.degree_audits),
        "current_registrations": tuple(bundle.current_registrations),
        "exception_cases": tuple(bundle.exception_cases),
        "approvals": tuple(bundle.approvals),
        "transaction_scripts": tuple(bundle.transaction_scripts),
        "scenarios": tuple(bundle.scenarios),
    }


def _value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _by_id(records: Iterable[Any], field: str) -> dict[str, Any]:
    return {str(getattr(record, field)): record for record in records}


def _record_id(record: Any) -> str:
    # Check entity-specific primary keys before foreign keys such as student_id
    # or simulation_scope_id. Most generated records deliberately carry both.
    for field in (
        "scenario_id",
        "script_id",
        "transaction_id",
        "approval_id",
        "case_id",
        "registration_id",
        "audit_id",
        "student_id",
        "state_id",
        "assumption_id",
        "policy_id",
        "simulation_scope_id",
    ):
        value = getattr(record, field, None)
        if value is not None:
            return str(value)
    return record.__class__.__name__.lower()


def _check_duplicate_ids(
    datasets: Mapping[str, tuple[Any, ...]], issues: _Issues
) -> None:
    for dataset, records in datasets.items():
        identity = _IDENTITY_FIELDS[dataset]
        counts = Counter(str(getattr(record, identity)) for record in records)
        for duplicate_id, count in counts.items():
            if count > 1:
                issues.add(
                    "DUPLICATE_ID",
                    dataset,
                    duplicate_id,
                    identity,
                    f"{identity} occurs {count} times",
                )

    transaction_ids = [
        str(step.transaction_id)
        for script in datasets["transaction_scripts"]
        for step in script.steps
    ]
    for duplicate_id, count in Counter(transaction_ids).items():
        if count > 1:
            issues.add(
                "DUPLICATE_ID",
                "transaction_scripts",
                duplicate_id,
                "steps.transaction_id",
                f"transaction_id occurs {count} times across scripts",
            )


def _check_global_ids(
    datasets: Mapping[str, tuple[Any, ...]], issues: _Issues
) -> None:
    owners: dict[str, list[str]] = defaultdict(list)
    for dataset, records in datasets.items():
        identity = _IDENTITY_FIELDS[dataset]
        for record in records:
            owners[str(getattr(record, identity))].append(dataset)
    for identifier, owner_datasets in owners.items():
        if len(set(owner_datasets)) > 1:
            issues.add(
                "AMBIGUOUS_GLOBAL_ID",
                "simulation",
                identifier,
                "record_id",
                "identifier is reused across datasets: "
                + ", ".join(sorted(set(owner_datasets))),
            )


def _check_manifest(
    real_repository: RealDataRepository,
    bundle: Stage3DataBundle,
    datasets: Mapping[str, tuple[Any, ...]],
    issues: _Issues,
    *,
    real_directory: Path | None,
    enforce_expected_counts: bool,
) -> None:
    manifest = bundle.manifest
    manifest_id = str(getattr(manifest, "manifest_id", "generation_manifest"))
    expected = _as_mapping(manifest.record_counts)
    count_aliases = {
        "simulation_scopes": ("simulation_scopes", "scopes", "scope_records"),
        "audit_assumptions": ("audit_assumptions", "assumptions"),
        "prototype_policies": ("prototype_policies",),
        "offering_states": ("offering_states",),
        "students": ("students",),
        "degree_audits": ("degree_audits", "audits"),
        "current_registrations": ("current_registrations", "registrations"),
        "exception_cases": ("exception_cases", "cases"),
        "approvals": ("approvals",),
        "transaction_scripts": ("transaction_scripts",),
        "scenarios": ("scenarios",),
    }
    for dataset, records in datasets.items():
        declared = _first_mapping_value(expected, count_aliases[dataset])
        if declared is None:
            issues.add(
                "MISSING_EXPECTED_COUNT",
                "generation_manifest",
                manifest_id,
                f"record_counts.{dataset}",
                "manifest does not declare this generated dataset count",
            )
        elif int(declared) != len(records):
            issues.add(
                "MANIFEST_COUNT_MISMATCH",
                "generation_manifest",
                manifest_id,
                f"record_counts.{dataset}",
                f"manifest declares {declared}, but {len(records)} records were loaded",
            )
        required = EXPECTED_RECORD_COUNTS.get(dataset)
        if enforce_expected_counts and required is not None and len(records) != required:
            issues.add(
                "STAGE3_COUNT_MISMATCH",
                dataset,
                manifest_id,
                "record_count",
                f"Stage 3 requires exactly {required} records; found {len(records)}",
            )

    _check_frozen_real_snapshot(
        manifest,
        real_repository,
        issues,
        manifest_id=manifest_id,
        real_directory=real_directory,
    )


def _check_frozen_real_snapshot(
    manifest: Any,
    real_repository: RealDataRepository,
    issues: _Issues,
    *,
    manifest_id: str,
    real_directory: Path | None,
) -> None:
    coverage_id = manifest.coverage_contract_id
    actual_coverage_id = real_repository.coverage.contract_id
    if str(coverage_id) != str(actual_coverage_id):
        issues.add(
            "COVERAGE_CONTRACT_MISMATCH",
            "generation_manifest",
            manifest_id,
            "coverage_contract_id",
            "frozen coverage contract does not match the loaded real repository",
            referenced_id=str(coverage_id),
        )
    artifacts = manifest.real_data_hashes
    if not artifacts:
        issues.add(
            "MISSING_FROZEN_ARTIFACTS",
            "generation_manifest",
            manifest_id,
            "real_data_hashes",
            "real-data snapshot must contain frozen artifact hashes",
        )
        return
    if real_directory is None:
        issues.add(
            "REAL_DIRECTORY_REQUIRED",
            "generation_manifest",
            manifest_id,
            "real_data_hashes",
            "real_directory is required to verify frozen SHA-256 values",
        )
        return

    root = real_directory.resolve()
    resolved_paths: set[str] = set()
    for artifact_name, expected_sha in artifacts.items():
        artifact_id = str(artifact_name)
        candidate = _resolve_real_artifact(root, artifact_id)
        if candidate is None:
            issues.add(
                "UNSAFE_FROZEN_ARTIFACT_PATH",
                "generation_manifest",
                manifest_id,
                "real_data_hashes",
                "frozen artifact path escapes the real-data directory",
                referenced_id=artifact_id,
            )
            continue
        try:
            actual_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
        except OSError:
            issues.add(
                "FROZEN_ARTIFACT_UNREADABLE",
                "generation_manifest",
                manifest_id,
                "real_data_hashes",
                f"frozen artifact is missing or unreadable: {candidate.name}",
                referenced_id=artifact_id,
            )
            continue
        try:
            resolved_paths.add(candidate.relative_to(root).as_posix())
        except ValueError:
            # `_resolve_real_artifact` already guards this; keep the validator
            # defensive if a platform changes path-resolution behavior.
            continue
        if actual_sha != str(expected_sha):
            issues.add(
                "FROZEN_ARTIFACT_HASH_MISMATCH",
                "generation_manifest",
                manifest_id,
                "real_data_hashes",
                f"SHA-256 mismatch for {candidate.name}",
                referenced_id=artifact_id,
            )
    for relative in sorted(_REQUIRED_REAL_HASH_PATHS - resolved_paths):
        issues.add(
            "MISSING_FROZEN_REAL_HASH",
            "generation_manifest",
            manifest_id,
            "real_data_hashes",
            f"manifest does not freeze required real artifact {relative}",
            referenced_id=Path(relative).name,
        )


def _resolve_real_artifact(root: Path, relative: str) -> Path | None:
    normalized = Path(relative.replace("\\", "/"))
    parts = normalized.parts
    if len(parts) >= 2 and parts[0].lower() == "data" and parts[1].lower() == "real":
        normalized = Path(*parts[2:])
    candidate = (root / normalized).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate.exists():
        return candidate
    if len(normalized.parts) == 1:
        alternatives = list(root.rglob(normalized.name))
        if len(alternatives) == 1:
            return alternatives[0].resolve()
        suffix = normalized.suffix
        if not suffix:
            alternatives = [
                *root.rglob(f"{normalized.name}.json"),
                *root.rglob(f"{normalized.name}.md"),
            ]
            if len(alternatives) == 1:
                return alternatives[0].resolve()
    return candidate


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    if is_dataclass(value):
        return {field.name: getattr(value, field.name) for field in fields(value)}
    return {}


def _first_mapping_value(
    values: Mapping[str, Any], keys: Iterable[str]
) -> Any | None:
    for key in keys:
        if key in values:
            return values[key]
    return None


class _RealIndex:
    def __init__(self, repository: RealDataRepository) -> None:
        self.sources = {source.source_id: source for source in repository.sources}
        self.programmes = {
            programme.code: programme for programme in repository.programmes
        }
        self.curricula = {
            curriculum.curriculum_id: curriculum
            for curriculum in repository.curricula
        }
        self.courses = {course.code: course for course in repository.courses}
        self.offerings = {
            offering.offering_id: offering for offering in repository.offerings
        }
        self.indexes: dict[tuple[str, str], tuple[Any, Any]] = {}
        for offering in repository.offerings:
            for index in offering.indexes:
                self.indexes[(offering.offering_id, index.index_id)] = (
                    offering,
                    index,
                )
        self.offering_terms = {
            (str(offering.academic_year), str(_value(offering.semester)))
            for offering in repository.offerings
        }
        self.calendar = repository.bundle.academic_calendar
        self.policies = repository.policies
        self.coverage = repository.coverage
        self.rule_ids = self._rule_ids()

    def _rule_ids(self) -> set[str]:
        ids = set(self.sources)
        ids.add(str(self.coverage.contract_id))
        for target in self.coverage.targets:
            ids.add(str(target.target_id))
            ids.update(str(gap.gap_id) for gap in target.gaps)
        for programme in self.programmes.values():
            ids.update((str(programme.programme_id), str(programme.code)))
        for curriculum in self.curricula.values():
            ids.add(str(curriculum.curriculum_id))
            ids.update(str(item.requirement_id) for item in curriculum.requirements)
            ids.update(str(path.path_id) for path in curriculum.graduation_paths)
            ids.update(str(item.plan_item_id) for item in curriculum.study_plan)
        for course in self.courses.values():
            ids.update((str(course.code), f"course.{course.code}"))
        for offering in self.offerings.values():
            ids.add(str(offering.offering_id))
            ids.update(str(index.index_id) for index in offering.indexes)
        ids.add(str(self.calendar.document_id))
        ids.update(str(event.event_id) for event in self.calendar.events)
        for document in self.policies:
            ids.add(str(document.document_id))
            ids.update(str(section.section_id) for section in document.sections)
        return ids


def _check_scopes(
    bundle: Stage3DataBundle, real: _RealIndex, issues: _Issues
) -> None:
    for scope in bundle.simulation_scopes:
        scope_id = str(scope.simulation_scope_id)
        template_term = (
            str(scope.template_academic_year),
            str(_value(scope.template_semester)),
        )
        if template_term not in real.offering_terms:
            issues.add(
                "UNKNOWN_TEMPLATE_TERM",
                "simulation_scopes",
                scope_id,
                "template_academic_year",
                "scope template term is absent from the real offering snapshot",
            )
        curriculum = real.curricula.get(str(scope.curriculum_id))
        if curriculum is None:
            issues.add(
                "UNKNOWN_CURRICULUM",
                "simulation_scopes",
                scope_id,
                "curriculum_id",
                "simulation scope references an unknown real curriculum",
                referenced_id=str(scope.curriculum_id),
            )
            continue
        if str(scope.programme) != str(curriculum.programme):
            issues.add(
                "SCOPE_PROGRAMME_MISMATCH",
                "simulation_scopes",
                scope_id,
                "programme",
                "scope programme does not match its curriculum",
                referenced_id=str(scope.programme),
            )
        if str(scope.admission_cohort) != str(curriculum.admission_cohort):
            issues.add(
                "SCOPE_COHORT_MISMATCH",
                "simulation_scopes",
                scope_id,
                "admission_cohort",
                "scope admission cohort does not match its curriculum",
                referenced_id=str(scope.admission_cohort),
            )
        if curriculum.study_plan:
            expected_year = max(item.study_year for item in curriculum.study_plan)
            if int(scope.terminal_study_year) != expected_year:
                issues.add(
                    "TERMINAL_YEAR_MISMATCH",
                    "simulation_scopes",
                    scope_id,
                    "terminal_study_year",
                    f"terminal year must equal study-plan maximum {expected_year}",
                )
            expected_academic_year = _terminal_academic_year(
                str(scope.admission_cohort), expected_year
            )
            if (
                expected_academic_year is not None
                and str(scope.simulation_academic_year) != expected_academic_year
            ):
                issues.add(
                    "SIMULATION_YEAR_DERIVATION_MISMATCH",
                    "simulation_scopes",
                    scope_id,
                    "simulation_academic_year",
                    "counterfactual year must follow admission cohort plus terminal year",
                )
        else:
            issues.add(
                "SCOPE_WITHOUT_STUDY_PLAN",
                "simulation_scopes",
                scope_id,
                "curriculum_id",
                "positive audit simulation requires a detailed study plan",
                referenced_id=str(scope.curriculum_id),
            )
        known_paths = {str(path.path_id) for path in curriculum.graduation_paths}
        declared_paths = {
            str(value)
            for value in (
                getattr(scope, "graduation_path_ids", None)
                or getattr(scope, "permitted_graduation_path_ids", None)
                or ()
            )
        }
        for path_id in sorted(declared_paths - known_paths):
            issues.add(
                "UNKNOWN_GRADUATION_PATH",
                "simulation_scopes",
                scope_id,
                "graduation_path_ids",
                "scope graduation path is absent from its curriculum",
                referenced_id=path_id,
            )
        known_labels = {
            str(item.path_label)
            for item in curriculum.study_plan
            if item.path_label is not None
        }
        declared_labels = {
            str(value)
            for value in (
                getattr(scope, "study_plan_path_labels", None)
                or getattr(scope, "permitted_study_plan_path_labels", None)
                or ()
            )
        }
        for label in sorted(declared_labels - known_labels):
            issues.add(
                "UNKNOWN_STUDY_PLAN_PATH",
                "simulation_scopes",
                scope_id,
                "study_plan_path_labels",
                "scope study-plan label is absent from its curriculum",
                referenced_id=label,
            )


def _terminal_academic_year(cohort: str, study_year: int) -> str | None:
    normalized = cohort.upper().removeprefix("AY")
    first = normalized.split("-", 1)[0].split("/", 1)[0]
    if len(first) != 4 or not first.isdigit():
        return None
    start = int(first) + study_year - 1
    return f"AY{start}-{str(start + 1)[-2:]}"


def _check_offering_states(
    bundle: Stage3DataBundle,
    real: _RealIndex,
    scope_by_id: Mapping[str, Any],
    issues: _Issues,
) -> None:
    expected_pairs = set(real.indexes)
    states_by_pair: dict[tuple[str, str], list[Any]] = defaultdict(list)
    known_periods = {
        str(scope.simulation_period_id) for scope in scope_by_id.values()
    }
    for state in bundle.offering_states:
        state_id = str(state.state_id)
        pair = (str(state.template_offering_id), str(state.template_index_id))
        states_by_pair[pair].append(state)
        source = real.indexes.get(pair)
        if source is None:
            issues.add(
                "UNKNOWN_TEMPLATE_INDEX",
                "offering_states",
                state_id,
                "template_index_id",
                "offering state does not resolve to a real offering/index pair",
                referenced_id=str(state.template_index_id),
            )
        else:
            offering, _ = source
            if str(state.template_academic_year) != str(offering.academic_year):
                issues.add(
                    "TEMPLATE_YEAR_MISMATCH",
                    "offering_states",
                    state_id,
                    "template_academic_year",
                    "offering state year does not match the real offering",
                )
            if _value(state.template_semester) != _value(offering.semester):
                issues.add(
                    "TEMPLATE_SEMESTER_MISMATCH",
                    "offering_states",
                    state_id,
                    "template_semester",
                    "offering state semester does not match the real offering",
                )
        if str(state.simulation_period_id) not in known_periods:
            issues.add(
                "UNKNOWN_SIMULATION_PERIOD",
                "offering_states",
                state_id,
                "simulation_period_id",
                "offering state period is not declared by any simulation scope",
                referenced_id=str(state.simulation_period_id),
            )

    for pair in sorted(expected_pairs):
        matches = states_by_pair.get(pair, [])
        if not matches:
            issues.add(
                "MISSING_OFFERING_STATE",
                "offering_states",
                str(pair[0]),
                "template_index_id",
                "real offering/index pair has no simulated state",
                referenced_id=str(pair[1]),
            )
        elif len(matches) > 1:
            issues.add(
                "DUPLICATE_OFFERING_STATE",
                "offering_states",
                str(matches[0].state_id),
                "template_index_id",
                "real offering/index pair must have exactly one simulated state",
                referenced_id=str(pair[1]),
            )
    for pair, states in states_by_pair.items():
        if pair not in expected_pairs and len(states) > 1:
            # The unknown-reference error above is sufficient for a single record;
            # retain a separate cardinality error for ambiguous unknown pairs.
            issues.add(
                "DUPLICATE_UNKNOWN_OFFERING_STATE",
                "offering_states",
                str(states[0].state_id),
                "template_index_id",
                "unknown offering/index pair is repeated",
                referenced_id=str(pair[1]),
            )


def _check_students(
    bundle: Stage3DataBundle,
    real: _RealIndex,
    scope_by_id: Mapping[str, Any],
    issues: _Issues,
    *,
    enforce_expected_counts: bool,
) -> None:
    scope_counts: Counter[str] = Counter()
    profile_counts: Counter[str] = Counter()
    for student in bundle.students:
        student_id = str(student.student_id)
        scope_id = str(student.simulation_scope_id)
        scope_counts[scope_id] += 1
        profile_counts[str(_value(student.terminal_profile))] += 1
        scope = scope_by_id.get(scope_id)
        if scope is None:
            issues.add(
                "UNKNOWN_SIMULATION_SCOPE",
                "students",
                student_id,
                "simulation_scope_id",
                "student references an unknown simulation scope",
                referenced_id=scope_id,
            )
        else:
            _check_equal_fields(
                issues,
                "students",
                student_id,
                student,
                scope,
                (
                    "simulation_period_id",
                    "programme",
                    "curriculum_id",
                    "admission_cohort",
                ),
                code="STUDENT_SCOPE_MISMATCH",
            )
            if int(student.study_year) != int(scope.terminal_study_year):
                issues.add(
                    "STUDENT_YEAR_MISMATCH",
                    "students",
                    student_id,
                    "study_year",
                    "student year must equal its scope terminal year",
                )
            _check_selected_paths(student, scope, real, issues, "students", student_id)

        if str(student.programme) not in real.programmes:
            issues.add(
                "UNKNOWN_PROGRAMME",
                "students",
                student_id,
                "programme",
                "student programme is absent from real data",
                referenced_id=str(student.programme),
            )
        if str(student.curriculum_id) not in real.curricula:
            issues.add(
                "UNKNOWN_CURRICULUM",
                "students",
                student_id,
                "curriculum_id",
                "student curriculum is absent from real data",
                referenced_id=str(student.curriculum_id),
            )
        for programme in student.additional_programmes:
            if str(programme) not in real.programmes:
                issues.add(
                    "UNKNOWN_PROGRAMME",
                    "students",
                    student_id,
                    "additional_programmes",
                    "additional programme is absent from real data",
                    referenced_id=str(programme),
                )
        for attempt in student.completed_courses:
            course = real.courses.get(str(attempt.course_code))
            if course is None:
                issues.add(
                    "UNKNOWN_COMPLETED_COURSE",
                    "students",
                    student_id,
                    "completed_courses.course_code",
                    "completed course is absent from the real catalogue subset",
                    referenced_id=str(attempt.course_code),
                )
                continue
            if (
                _value(attempt.credit_status) == CreditStatus.EARNED.value
                and Decimal(attempt.aus_earned) != Decimal(course.aus)
            ):
                issues.add(
                    "COMPLETED_COURSE_AU_MISMATCH",
                    "students",
                    student_id,
                    "completed_courses.aus_earned",
                    "earned attempt AUs must exactly match catalogue AUs, including zero",
                    referenced_id=str(attempt.course_code),
                )
        for exemption in student.exemptions:
            if (
                exemption.course_code is not None
                and str(exemption.course_code) not in real.courses
            ):
                issues.add(
                    "UNKNOWN_EXEMPTED_COURSE",
                    "students",
                    student_id,
                    "exemptions.course_code",
                    "course-targeted exemption is absent from the catalogue subset",
                    referenced_id=str(exemption.course_code),
                )
            if exemption.category is not None:
                curriculum = real.curricula.get(str(student.curriculum_id))
                known_categories = (
                    {
                        str(requirement.category)
                        for requirement in curriculum.requirements
                    }
                    if curriculum is not None
                    else set()
                )
                if str(exemption.category) not in known_categories:
                    issues.add(
                        "UNKNOWN_EXEMPTION_CATEGORY",
                        "students",
                        student_id,
                        "exemptions.category",
                        "category-targeted exemption is absent from the curriculum",
                        referenced_id=str(exemption.category),
                    )

    for scope_id, scope in scope_by_id.items():
        declared = int(getattr(scope, "student_count", 0))
        actual = scope_counts[scope_id]
        if actual != declared:
            issues.add(
                "SCOPE_STUDENT_COUNT_MISMATCH",
                "simulation_scopes",
                scope_id,
                "student_count",
                f"scope declares {declared} students, but {actual} resolve to it",
            )
    if enforce_expected_counts:
        for profile in sorted(profile_counts):
            if profile_counts[profile] != EXPECTED_PROFILE_COUNT:
                issues.add(
                    "PROFILE_COUNT_MISMATCH",
                    "students",
                    "terminal_profiles",
                    "terminal_profile",
                    f"profile {profile} requires {EXPECTED_PROFILE_COUNT} students; "
                    f"found {profile_counts[profile]}",
                    referenced_id=profile,
                )
        if len(profile_counts) != 4:
            issues.add(
                "PROFILE_CARDINALITY_MISMATCH",
                "students",
                "terminal_profiles",
                "terminal_profile",
                f"Stage 3 requires four terminal profiles; found {len(profile_counts)}",
            )


def _check_selected_paths(
    record: Any,
    scope: Any,
    real: _RealIndex,
    issues: _Issues,
    dataset: str,
    record_id: str,
) -> None:
    curriculum = real.curricula.get(str(record.curriculum_id))
    if curriculum is None:
        return
    selected_path = getattr(record, "graduation_path_id", None)
    known_paths = {str(path.path_id) for path in curriculum.graduation_paths}
    if known_paths and selected_path is None:
        issues.add(
            "MISSING_GRADUATION_PATH",
            dataset,
            record_id,
            "graduation_path_id",
            "a curriculum with alternative graduation paths requires one selected path",
        )
    if selected_path is not None and str(selected_path) not in known_paths:
        issues.add(
            "UNKNOWN_GRADUATION_PATH",
            dataset,
            record_id,
            "graduation_path_id",
            "selected graduation path is absent from the curriculum",
            referenced_id=str(selected_path),
        )
    permitted_paths = {
        str(value)
        for value in (
            getattr(scope, "graduation_path_ids", None)
            or getattr(scope, "permitted_graduation_path_ids", None)
            or ()
        )
    }
    if selected_path is not None and permitted_paths and str(selected_path) not in permitted_paths:
        issues.add(
            "PATH_OUTSIDE_SCOPE",
            dataset,
            record_id,
            "graduation_path_id",
            "selected graduation path is not enabled by the simulation scope",
            referenced_id=str(selected_path),
        )
    selected_label = getattr(record, "study_plan_path_label", None)
    known_labels = {
        str(item.path_label)
        for item in curriculum.study_plan
        if item.path_label is not None
    }
    if known_labels and selected_label is None:
        issues.add(
            "MISSING_STUDY_PLAN_PATH",
            dataset,
            record_id,
            "study_plan_path_label",
            "a curriculum with alternative study-plan labels requires one selected label",
        )
    if selected_label is not None and str(selected_label) not in known_labels:
        issues.add(
            "UNKNOWN_STUDY_PLAN_PATH",
            dataset,
            record_id,
            "study_plan_path_label",
            "selected study-plan path label is absent from the curriculum",
            referenced_id=str(selected_label),
        )
    if selected_path is not None and selected_label is not None:
        path_value = str(selected_path).lower()
        attachment = (
            "pi"
            if ".pi" in path_value or "-pi" in path_value
            else "pa"
            if ".pa" in path_value or "-pa" in path_value
            else None
        )
        if attachment is not None and not str(selected_label).lower().startswith(
            attachment
        ):
            issues.add(
                "PATH_LABEL_MISMATCH",
                dataset,
                record_id,
                "study_plan_path_label",
                "study-plan attachment label does not match the selected graduation path",
                referenced_id=str(selected_label),
            )


def _check_equal_fields(
    issues: _Issues,
    dataset: str,
    record_id: str,
    left: Any,
    right: Any,
    field_names: Iterable[str],
    *,
    code: str,
) -> None:
    for field_name in field_names:
        if not hasattr(left, field_name) or not hasattr(right, field_name):
            continue
        if _value(getattr(left, field_name)) != _value(getattr(right, field_name)):
            issues.add(
                code,
                dataset,
                record_id,
                field_name,
                f"{field_name} does not match the referenced record",
            )


def _check_audit_credit_allocation(
    audit: Any,
    student: Any,
    curriculum: Any,
    issues: _Issues,
) -> None:
    """Reconcile every awarded AU with one curriculum requirement.

    The student record is the credit ledger, while ``RequirementProgress`` is
    its category allocation.  Category exemptions route directly through the
    curriculum's unique requirement categories.  Earned courses and
    course-targeted exemptions route through published study-plan and
    requirement course mappings.
    """

    audit_id = str(audit.audit_id)
    requirement_by_category = {
        str(requirement.category): str(requirement.requirement_id)
        for requirement in curriculum.requirements
    }
    course_requirements: dict[str, set[str]] = defaultdict(set)
    for item in curriculum.study_plan:
        if item.course_code is not None and item.requirement_id is not None:
            course_requirements[str(item.course_code)].add(str(item.requirement_id))
    for requirement in curriculum.requirements:
        requirement_id = str(requirement.requirement_id)
        for course_code in (*requirement.required_courses, *requirement.elective_pool):
            course_requirements[str(course_code)].add(requirement_id)

    allocated_aus: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    category_exemption_aus: dict[str, Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    expected_course_requirement: dict[str, str] = {}

    def allocate_course(
        course_code: str,
        aus: Decimal,
        *,
        field: str,
    ) -> None:
        candidates = course_requirements.get(course_code, set())
        if len(candidates) != 1:
            code = (
                "AUDIT_AMBIGUOUS_COURSE_CREDIT_ALLOCATION"
                if candidates
                else "AUDIT_UNALLOCATED_COURSE_CREDIT"
            )
            issues.add(
                code,
                "degree_audits",
                audit_id,
                field,
                "credited course must resolve to exactly one curriculum requirement",
                referenced_id=course_code,
            )
            return
        requirement_id = next(iter(candidates))
        allocated_aus[requirement_id] += aus
        expected_course_requirement[course_code] = requirement_id

    for attempt in student.completed_courses:
        if _value(attempt.credit_status) != CreditStatus.EARNED.value:
            continue
        allocate_course(
            str(attempt.course_code),
            Decimal(attempt.aus_earned),
            field="student.completed_courses",
        )

    for exemption in student.exemptions:
        category_requirement = (
            requirement_by_category.get(str(exemption.category))
            if exemption.category is not None
            else None
        )
        course_code = (
            str(exemption.course_code)
            if exemption.course_code is not None
            else None
        )
        course_candidates = (
            course_requirements.get(course_code, set())
            if course_code is not None
            else set()
        )

        if category_requirement is not None:
            if course_code is not None and (
                len(course_candidates) != 1
                or category_requirement not in course_candidates
            ):
                issues.add(
                    "AUDIT_EXEMPTION_TARGET_CONFLICT",
                    "degree_audits",
                    audit_id,
                    "student.exemptions",
                    "course and category exemption targets must resolve to the same requirement",
                    referenced_id=str(exemption.exemption_id),
                )
                continue
            allocated_aus[category_requirement] += Decimal(exemption.aus_awarded)
            category_exemption_aus[category_requirement] += Decimal(
                exemption.aus_awarded
            )
            if course_code is not None:
                expected_course_requirement[course_code] = category_requirement
            continue

        if course_code is not None:
            allocate_course(
                course_code,
                Decimal(exemption.aus_awarded),
                field="student.exemptions.course_code",
            )
            continue

        # Unknown categories are reported by the student validator as well;
        # retain a credit-specific issue because those AUs cannot be reconciled.
        issues.add(
            "AUDIT_UNALLOCATED_EXEMPTION_CREDIT",
            "degree_audits",
            audit_id,
            "student.exemptions",
            "exemption credit must resolve to one curriculum requirement",
            referenced_id=str(exemption.exemption_id),
        )

    course_locations: dict[str, list[str]] = defaultdict(list)
    result_by_requirement = {
        str(result.requirement_id): result for result in audit.requirement_results
    }
    for result in audit.requirement_results:
        requirement_id = str(result.requirement_id)
        for course_code in result.completed_courses:
            course_locations[str(course_code)].append(requirement_id)

    for course_code, expected_requirement in expected_course_requirement.items():
        locations = course_locations.get(course_code, [])
        if not locations:
            issues.add(
                "AUDIT_CREDITED_COURSE_NOT_ALLOCATED",
                "degree_audits",
                audit_id,
                "requirement_results.completed_courses",
                "every credited course must appear in one requirement result",
                referenced_id=course_code,
            )
        elif len(locations) > 1:
            issues.add(
                "AUDIT_CREDITED_COURSE_MULTIPLE_ALLOCATION",
                "degree_audits",
                audit_id,
                "requirement_results.completed_courses",
                "a credited course must not be allocated to multiple requirements",
                referenced_id=course_code,
            )
        elif locations[0] != expected_requirement:
            issues.add(
                "AUDIT_COURSE_REQUIREMENT_MISMATCH",
                "degree_audits",
                audit_id,
                "requirement_results.completed_courses",
                "credited course is allocated outside its grounded requirement",
                referenced_id=course_code,
            )

    for requirement in curriculum.requirements:
        requirement_id = str(requirement.requirement_id)
        result = result_by_requirement.get(requirement_id)
        if result is None:
            continue
        expected_aus = allocated_aus[requirement_id]
        if Decimal(result.earned_aus) != expected_aus:
            issues.add(
                "AUDIT_REQUIREMENT_CREDIT_MISMATCH",
                "degree_audits",
                audit_id,
                "requirement_results.earned_aus",
                "requirement earned AUs must equal its allocated course and exemption credits",
                referenced_id=requirement_id,
            )
        if category_exemption_aus[requirement_id] > Decimal(result.earned_aus):
            issues.add(
                "AUDIT_CATEGORY_EXEMPTION_OVERALLOCATION",
                "degree_audits",
                audit_id,
                "student.exemptions.category",
                "category exemption AUs cannot exceed that requirement's earned AUs",
                referenced_id=requirement_id,
            )

    allocated_total = sum(allocated_aus.values(), Decimal("0"))
    if allocated_total != Decimal(student.earned_aus):
        issues.add(
            "AUDIT_UNALLOCATED_STUDENT_CREDIT",
            "degree_audits",
            audit_id,
            "student.earned_aus",
            "all awarded student AUs must allocate to curriculum requirements",
        )


def _check_audits(
    bundle: Stage3DataBundle,
    real: _RealIndex,
    scope_by_id: Mapping[str, Any],
    student_by_id: Mapping[str, Any],
    issues: _Issues,
) -> None:
    for audit in bundle.degree_audits:
        audit_id = str(audit.audit_id)
        student = student_by_id.get(str(audit.student_id))
        if student is None:
            issues.add(
                "UNKNOWN_STUDENT",
                "degree_audits",
                audit_id,
                "student_id",
                "audit references an unknown student",
                referenced_id=str(audit.student_id),
            )
            continue
        scope = scope_by_id.get(str(audit.simulation_scope_id))
        if scope is None:
            issues.add(
                "UNKNOWN_SIMULATION_SCOPE",
                "degree_audits",
                audit_id,
                "simulation_scope_id",
                "audit references an unknown simulation scope",
                referenced_id=str(audit.simulation_scope_id),
            )
        _check_equal_fields(
            issues,
            "degree_audits",
            audit_id,
            audit,
            student,
            (
                "simulation_scope_id",
                "simulation_period_id",
                "curriculum_id",
                "graduation_path_id",
                "study_plan_path_label",
            ),
            code="AUDIT_STUDENT_MISMATCH",
        )
        if Decimal(audit.total_earned_aus) != Decimal(student.earned_aus):
            issues.add(
                "AUDIT_EARNED_AU_MISMATCH",
                "degree_audits",
                audit_id,
                "total_earned_aus",
                "audit earned AUs must match the student record",
            )
        requirement_earned_total = sum(
            (Decimal(result.earned_aus) for result in audit.requirement_results),
            Decimal("0"),
        )
        if requirement_earned_total != Decimal(audit.total_earned_aus):
            issues.add(
                "AUDIT_EARNED_LEDGER_MISMATCH",
                "degree_audits",
                audit_id,
                "requirement_results.earned_aus",
                "requirement earned AUs must sum to audit total_earned_aus",
            )
        if (
            audit.total_required_aus is not None
            and all(
                result.required_aus is not None
                for result in audit.requirement_results
            )
        ):
            requirement_required_total = sum(
                (
                    Decimal(result.required_aus)
                    for result in audit.requirement_results
                    if result.required_aus is not None
                ),
                Decimal("0"),
            )
            if requirement_required_total != Decimal(audit.total_required_aus):
                issues.add(
                    "AUDIT_REQUIRED_LEDGER_MISMATCH",
                    "degree_audits",
                    audit_id,
                    "requirement_results.required_aus",
                    "known requirement AUs must sum to audit total_required_aus",
                )
        if scope is not None:
            _check_equal_fields(
                issues,
                "degree_audits",
                audit_id,
                audit,
                scope,
                ("simulation_period_id", "simulation_academic_year"),
                code="AUDIT_SCOPE_MISMATCH",
            )
            if _value(audit.semester) != _value(scope.simulation_semester):
                issues.add(
                    "AUDIT_SCOPE_MISMATCH",
                    "degree_audits",
                    audit_id,
                    "semester",
                    "audit semester does not match scope simulation_semester",
                )
            if _value(audit.audit_basis) != _value(scope.audit_basis):
                issues.add(
                    "AUDIT_SCOPE_MISMATCH",
                    "degree_audits",
                    audit_id,
                    "audit_basis",
                    "audit basis does not match its simulation scope",
                )
            _check_selected_paths(audit, scope, real, issues, "degree_audits", audit_id)

        curriculum = real.curricula.get(str(audit.curriculum_id))
        if curriculum is None:
            issues.add(
                "UNKNOWN_CURRICULUM",
                "degree_audits",
                audit_id,
                "curriculum_id",
                "audit references an unknown real curriculum",
                referenced_id=str(audit.curriculum_id),
            )
            continue
        requirement_ids = {
            str(requirement.requirement_id) for requirement in curriculum.requirements
        }
        audit_requirement_ids = {
            str(result.requirement_id) for result in audit.requirement_results
        }
        if audit_requirement_ids != requirement_ids:
            issues.add(
                "AUDIT_REQUIREMENT_COVERAGE_MISMATCH",
                "degree_audits",
                audit_id,
                "requirement_results",
                "audit must cover every declared curriculum requirement exactly once",
            )
        _check_audit_credit_allocation(
            audit,
            student,
            curriculum,
            issues,
        )
        for result in audit.requirement_results:
            if str(result.requirement_id) not in requirement_ids:
                issues.add(
                    "UNKNOWN_REQUIREMENT",
                    "degree_audits",
                    audit_id,
                    "requirement_results.requirement_id",
                    "audit result references a requirement outside its curriculum",
                    referenced_id=str(result.requirement_id),
                )
            for course_code in (*result.completed_courses, *result.outstanding_courses):
                if str(course_code) not in real.courses:
                    issues.add(
                        "UNKNOWN_AUDIT_COURSE",
                        "degree_audits",
                        audit_id,
                        "requirement_results.courses",
                        "audit course is absent from the real catalogue subset",
                        referenced_id=str(course_code),
                    )
            credited_courses = {
                str(attempt.course_code)
                for attempt in student.completed_courses
                if _value(attempt.credit_status) == CreditStatus.EARNED.value
            } | {
                str(exemption.course_code)
                for exemption in student.exemptions
                if exemption.course_code is not None
            }
            for course_code in result.completed_courses:
                if str(course_code) not in credited_courses:
                    issues.add(
                        "AUDIT_COMPLETION_NOT_IN_STUDENT_RECORD",
                        "degree_audits",
                        audit_id,
                        "requirement_results.completed_courses",
                        "audit marks a course complete without earned or exempted credit",
                        referenced_id=str(course_code),
                    )
            for course_code in result.outstanding_courses:
                if str(course_code) in credited_courses:
                    issues.add(
                        "AUDIT_OUTSTANDING_COURSE_ALREADY_CREDITED",
                        "degree_audits",
                        audit_id,
                        "requirement_results.outstanding_courses",
                        "audit marks an earned or exempted course as outstanding",
                        referenced_id=str(course_code),
                    )
        expected_total: Decimal | None = None
        if audit.graduation_path_id is not None:
            path = next(
                (
                    path
                    for path in curriculum.graduation_paths
                    if str(path.path_id) == str(audit.graduation_path_id)
                ),
                None,
            )
            if path is not None:
                expected_total = Decimal(path.graduation_aus)
        elif not curriculum.graduation_paths and curriculum.graduation_aus is not None:
            expected_total = Decimal(curriculum.graduation_aus)
        if (
            expected_total is not None
            and audit.total_required_aus is not None
            and Decimal(audit.total_required_aus) != expected_total
        ):
            issues.add(
                "AUDIT_REQUIRED_AU_MISMATCH",
                "degree_audits",
                audit_id,
                "total_required_aus",
                "audit required AUs do not match the selected curriculum path",
            )


def _check_registrations(
    bundle: Stage3DataBundle,
    real: _RealIndex,
    scope_by_id: Mapping[str, Any],
    state_by_id: Mapping[str, Any],
    student_by_id: Mapping[str, Any],
    issues: _Issues,
) -> None:
    for registration in bundle.current_registrations:
        registration_id = str(registration.registration_id)
        student = student_by_id.get(str(registration.student_id))
        if student is None:
            issues.add(
                "UNKNOWN_STUDENT",
                "current_registrations",
                registration_id,
                "student_id",
                "registration references an unknown student",
                referenced_id=str(registration.student_id),
            )
        else:
            _check_equal_fields(
                issues,
                "current_registrations",
                registration_id,
                registration,
                student,
                ("simulation_scope_id", "simulation_period_id"),
                code="REGISTRATION_STUDENT_MISMATCH",
            )
        scope = scope_by_id.get(str(registration.simulation_scope_id))
        if scope is None:
            issues.add(
                "UNKNOWN_SIMULATION_SCOPE",
                "current_registrations",
                registration_id,
                "simulation_scope_id",
                "registration references an unknown simulation scope",
                referenced_id=str(registration.simulation_scope_id),
            )
        else:
            _check_equal_fields(
                issues,
                "current_registrations",
                registration_id,
                registration,
                scope,
                (
                    "simulation_period_id",
                    "simulation_academic_year",
                    "template_academic_year",
                    "template_semester",
                ),
                code="REGISTRATION_SCOPE_MISMATCH",
            )
            if _value(registration.semester) != _value(scope.simulation_semester):
                issues.add(
                    "REGISTRATION_SCOPE_MISMATCH",
                    "current_registrations",
                    registration_id,
                    "semester",
                    "registration semester does not match scope simulation_semester",
                )

        item_by_id = {
            str(item.registration_item_id): item
            for item in registration.registered_courses
        }
        for item in registration.registered_courses:
            item_id = str(item.registration_item_id)
            state = state_by_id.get(str(item.offering_state_id))
            if state is None:
                issues.add(
                    "UNKNOWN_OFFERING_STATE",
                    "current_registrations",
                    registration_id,
                    "registered_courses.offering_state_id",
                    "registration item references an unknown offering state",
                    referenced_id=str(item.offering_state_id),
                )
                continue
            _check_equal_fields(
                issues,
                "current_registrations",
                registration_id,
                item,
                state,
                ("template_offering_id", "template_index_id"),
                code="REGISTRATION_STATE_MISMATCH",
            )
            if str(state.simulation_period_id) != str(
                registration.simulation_period_id
            ):
                issues.add(
                    "REGISTRATION_STATE_PERIOD_MISMATCH",
                    "current_registrations",
                    registration_id,
                    "registered_courses.offering_state_id",
                    "offering state and registration use different simulation periods",
                    referenced_id=str(item.offering_state_id),
                )
            if (
                str(state.template_academic_year)
                != str(registration.template_academic_year)
                or _value(state.template_semester)
                != _value(registration.template_semester)
            ):
                issues.add(
                    "REGISTRATION_STATE_TERM_MISMATCH",
                    "current_registrations",
                    registration_id,
                    "registered_courses.offering_state_id",
                    "offering state and registration use different template terms",
                    referenced_id=str(item.offering_state_id),
                )
            if int(item.expected_state_version) != int(state.version):
                issues.add(
                    "OFFERING_STATE_VERSION_MISMATCH",
                    "current_registrations",
                    registration_id,
                    "registered_courses.expected_state_version",
                    "registration item must observe the initial offering-state version",
                    referenced_id=str(item.offering_state_id),
                )
            pair = (str(item.template_offering_id), str(item.template_index_id))
            source = real.indexes.get(pair)
            if source is None:
                issues.add(
                    "UNKNOWN_TEMPLATE_INDEX",
                    "current_registrations",
                    registration_id,
                    "registered_courses.template_index_id",
                    "registration item does not resolve to a real offering/index pair",
                    referenced_id=str(item.template_index_id),
                )
                continue
            offering, _ = source
            if str(item.course_code) != str(offering.course_code):
                issues.add(
                    "REGISTRATION_COURSE_OWNERSHIP_MISMATCH",
                    "current_registrations",
                    registration_id,
                    "registered_courses.course_code",
                    "course code does not own the referenced offering/index",
                    referenced_id=item_id,
                )
            course = real.courses.get(str(item.course_code))
            if course is None:
                issues.add(
                    "UNKNOWN_REGISTERED_COURSE",
                    "current_registrations",
                    registration_id,
                    "registered_courses.course_code",
                    "registered course is absent from the real catalogue subset",
                    referenced_id=str(item.course_code),
                )
            elif Decimal(item.aus) != Decimal(course.aus):
                issues.add(
                    "REGISTRATION_AU_MISMATCH",
                    "current_registrations",
                    registration_id,
                    "registered_courses.aus",
                    "registration item AUs must match catalogue AUs, including zero",
                    referenced_id=str(item.course_code),
                )
            if (
                str(_value(item.status)) == "REGISTERED"
                and str(_value(item.eligibility)) != "ELIGIBLE"
            ):
                issues.add(
                    "REGISTERED_ITEM_NOT_ELIGIBLE",
                    "current_registrations",
                    registration_id,
                    "registered_courses.eligibility",
                    "a REGISTERED item must be marked ELIGIBLE",
                    referenced_id=item_id,
                )

        _check_registration_meetings(
            registration,
            registration_id,
            item_by_id,
            real,
            issues,
        )
        for course_code in registration.missing_required_courses:
            if str(course_code) not in real.courses:
                issues.add(
                    "UNKNOWN_MISSING_COURSE",
                    "current_registrations",
                    registration_id,
                    "missing_required_courses",
                    "missing required course is absent from the real catalogue subset",
                    referenced_id=str(course_code),
                )


def _check_registration_meetings(
    registration: Any,
    registration_id: str,
    item_by_id: Mapping[str, Any],
    real: _RealIndex,
    issues: _Issues,
) -> None:
    actual_by_item: dict[str, Counter[str]] = defaultdict(Counter)
    for attributed in registration.timetable:
        item_id = str(attributed.registration_item_id)
        if item_id not in item_by_id:
            # The model validator normally catches this; retain protection for
            # in-memory bundles assembled with model_construct.
            issues.add(
                "UNKNOWN_REGISTRATION_ITEM",
                "current_registrations",
                registration_id,
                "timetable.registration_item_id",
                "attributed meeting references an unknown registration item",
                referenced_id=item_id,
            )
            continue
        actual_by_item[item_id][_canonical(attributed.meeting)] += 1
    for item_id, item in item_by_id.items():
        pair = (str(item.template_offering_id), str(item.template_index_id))
        source = real.indexes.get(pair)
        if source is None:
            continue
        _, index = source
        expected = Counter(_canonical(meeting) for meeting in index.meetings)
        if actual_by_item[item_id] != expected:
            issues.add(
                "REGISTRATION_TIMETABLE_MISMATCH",
                "current_registrations",
                registration_id,
                "timetable",
                "attributed meetings must exactly match the real template index",
                referenced_id=item_id,
            )


def _canonical(value: Any) -> str:
    if isinstance(value, BaseModel):
        return value.model_dump_json(exclude_none=False)
    return repr(value)


def _check_cases(
    bundle: Stage3DataBundle,
    real: _RealIndex,
    student_by_id: Mapping[str, Any],
    audit_by_id: Mapping[str, Any],
    registration_by_id: Mapping[str, Any],
    issues: _Issues,
) -> None:
    for case in bundle.exception_cases:
        case_id = str(case.case_id)
        student = student_by_id.get(str(case.student_id))
        if student is None:
            issues.add(
                "UNKNOWN_STUDENT",
                "exception_cases",
                case_id,
                "student_id",
                "case references an unknown student",
                referenced_id=str(case.student_id),
            )
        for field_name, records, code in (
            ("audit_id", audit_by_id, "UNKNOWN_AUDIT"),
            ("registration_id", registration_by_id, "UNKNOWN_REGISTRATION"),
        ):
            reference = getattr(case, field_name, None)
            if reference is None:
                continue
            linked = records.get(str(reference))
            if linked is None:
                issues.add(
                    code,
                    "exception_cases",
                    case_id,
                    field_name,
                    f"case {field_name} does not resolve",
                    referenced_id=str(reference),
                )
            elif str(linked.student_id) != str(case.student_id):
                issues.add(
                    "CASE_STUDENT_LINK_MISMATCH",
                    "exception_cases",
                    case_id,
                    field_name,
                    f"case {field_name} belongs to a different student",
                    referenced_id=str(reference),
                )
            elif field_name == "registration_id" and case.scenario_time != linked.scenario_time:
                issues.add(
                    "CASE_TIME_MISMATCH",
                    "exception_cases",
                    case_id,
                    "scenario_time",
                    "case and current registration must share the same scenario time",
                    referenced_id=str(reference),
                )
        if student is not None and hasattr(case, "simulation_scope_id"):
            if str(case.simulation_scope_id) != str(student.simulation_scope_id):
                issues.add(
                    "CASE_SCOPE_MISMATCH",
                    "exception_cases",
                    case_id,
                    "simulation_scope_id",
                    "case scope does not match its student",
                )
        for evidence in case.evidence:
            if evidence.source_id is not None and str(evidence.source_id) not in real.sources:
                issues.add(
                    "UNKNOWN_EVIDENCE_SOURCE",
                    "exception_cases",
                    case_id,
                    "evidence.source_id",
                    "case evidence cites an unknown real source",
                    referenced_id=str(evidence.source_id),
                )


def _check_approvals(
    bundle: Stage3DataBundle,
    case_by_id: Mapping[str, Any],
    issues: _Issues,
    enforce_expected_counts: bool,
) -> None:
    by_case: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    for approval in bundle.approvals:
        approval_id = str(approval.approval_id)
        case_id = str(approval.case_id)
        by_case[case_id] += 1
        status_counts[str(_value(approval.status))] += 1
        case = case_by_id.get(case_id)
        if case is None:
            issues.add(
                "UNKNOWN_CASE",
                "approvals",
                approval_id,
                "case_id",
                "approval references an unknown exception case",
                referenced_id=case_id,
            )
            continue
        if str(approval.simulation_scope_id) != str(case.simulation_scope_id):
            issues.add(
                "APPROVAL_SCOPE_MISMATCH",
                "approvals",
                approval_id,
                "simulation_scope_id",
                "approval scope does not match its case",
            )
        known_documents = {
            str(document.document_id) for document in case.supporting_documents
        }
        documents = {
            str(document.document_id): document
            for document in case.supporting_documents
        }
        for document_id in approval.required_document_ids:
            if str(document_id) not in known_documents:
                issues.add(
                    "UNKNOWN_REQUIRED_DOCUMENT",
                    "approvals",
                    approval_id,
                    "required_document_ids",
                    "approval requires a document not declared by its case",
                    referenced_id=str(document_id),
                )
            elif str(_value(approval.status)) == ApprovalStatus.APPROVED.value:
                document = documents[str(document_id)]
                if not document.provided or document.verified is False:
                    issues.add(
                        "APPROVED_WITHOUT_REQUIRED_DOCUMENT",
                        "approvals",
                        approval_id,
                        "required_document_ids",
                        "approved workflow requires every required document to be provided and not rejected",
                        referenced_id=str(document_id),
                    )
    for case_id, count in by_case.items():
        if count > 1:
            issues.add(
                "MULTIPLE_APPROVALS_PER_CASE",
                "approvals",
                case_id,
                "case_id",
                f"case has {count} approval records; Stage 3 permits at most one",
            )
    if enforce_expected_counts:
        for status, expected in EXPECTED_APPROVAL_STATUSES.items():
            actual = status_counts[status]
            if actual != expected:
                issues.add(
                    "APPROVAL_STATUS_COUNT_MISMATCH",
                    "approvals",
                    "approval_statuses",
                    "status",
                    f"{status} requires {expected} records; found {actual}",
                    referenced_id=status,
                )


def _check_scripts(
    bundle: Stage3DataBundle,
    real: _RealIndex,
    case_by_id: Mapping[str, Any],
    approval_by_id: Mapping[str, Any],
    state_by_id: Mapping[str, Any],
    issues: _Issues,
) -> None:
    script_cases: Counter[str] = Counter()
    for script in bundle.transaction_scripts:
        script_id = str(script.script_id)
        case_id = str(script.case_id)
        script_cases[case_id] += 1
        if case_id not in case_by_id:
            issues.add(
                "UNKNOWN_CASE",
                "transaction_scripts",
                script_id,
                "case_id",
                "transaction script references an unknown exception case",
                referenced_id=case_id,
            )
        elif str(script.simulation_scope_id) != str(
            case_by_id[case_id].simulation_scope_id
        ):
            issues.add(
                "SCRIPT_SCOPE_MISMATCH",
                "transaction_scripts",
                script_id,
                "simulation_scope_id",
                "transaction script scope does not match its case",
            )
        replay_targets = {
            **state_by_id,
            **approval_by_id,
        }
        versions = {
            target_id: int(target.version)
            for target_id, target in replay_targets.items()
            if hasattr(target, "version")
        }
        previous_step: Any | None = None
        approval_event_times: dict[str, Any] = {}
        for position, step in enumerate(script.steps, start=1):
            transaction_id = str(step.transaction_id)
            if str(step.case_id) != case_id:
                issues.add(
                    "TRANSACTION_CASE_MISMATCH",
                    "transaction_scripts",
                    script_id,
                    "steps.case_id",
                    "transaction step case differs from its script case",
                    referenced_id=transaction_id,
                )
            if int(step.attempt_number) != position:
                issues.add(
                    "TRANSACTION_ATTEMPT_SEQUENCE",
                    "transaction_scripts",
                    script_id,
                    "steps.attempt_number",
                    "attempt numbers must be consecutive in persisted order",
                    referenced_id=transaction_id,
                )
            if (
                previous_step is not None
                and step.occurred_at <= previous_step.occurred_at
            ):
                issues.add(
                    "TRANSACTION_STEP_TIME_ORDER",
                    "transaction_scripts",
                    script_id,
                    "steps.occurred_at",
                    "transaction step times must increase strictly in attempt order",
                    referenced_id=transaction_id,
                )
            result = str(_value(step.result_code))
            observation = str(_value(step.observation))
            if (
                position < len(script.steps)
                and result
                not in {
                    TransactionCode.SUCCESS.value,
                    TransactionCode.EXCEPTION_SUBMISSION_SUCCESS.value,
                }
                and not step.retryable
            ):
                issues.add(
                    "NONTERMINAL_FAILURE_NOT_RETRYABLE",
                    "transaction_scripts",
                    script_id,
                    "steps.retryable",
                    "a failed step followed by another attempt must be retryable",
                    referenced_id=transaction_id,
                )
            expected_observation = _RESULT_OBSERVATIONS.get(result)
            if expected_observation is None or observation != expected_observation:
                issues.add(
                    "TRANSACTION_OBSERVATION_MISMATCH",
                    "transaction_scripts",
                    script_id,
                    "steps.observation",
                    "observation does not match the transaction result code",
                    referenced_id=transaction_id,
                )
            if result in _MUST_RETRY_RESULTS and not step.retryable:
                issues.add(
                    "TRANSACTION_RETRY_MISMATCH",
                    "transaction_scripts",
                    script_id,
                    "steps.retryable",
                    "temporary and stale-state failures must be retryable",
                    referenced_id=transaction_id,
                )
            event = step.event
            if event is not None:
                _check_event_result(
                    event,
                    result,
                    observation,
                    issues,
                    "transaction_scripts",
                    script_id,
                    transaction_id,
                )
                _check_script_event_target(
                    event,
                    case_id,
                    case_by_id,
                    approval_by_id,
                    state_by_id,
                    issues,
                    script_id,
                    transaction_id,
                )
                if (
                    str(_value(event.target_type))
                    == StateTargetType.APPROVAL.value
                ):
                    approval_event_times[str(event.target_id)] = event.occurs_at
            approval_id = step.action_parameters.get("approval_id")
            if approval_id is not None:
                approval = approval_by_id.get(str(approval_id))
                if approval is None:
                    issues.add(
                        "UNKNOWN_APPROVAL",
                        "transaction_scripts",
                        script_id,
                        "steps.action_parameters.approval_id",
                        "transaction step references an unknown approval",
                        referenced_id=str(approval_id),
                    )
                elif str(approval.case_id) != case_id:
                    issues.add(
                        "TRANSACTION_APPROVAL_CASE_MISMATCH",
                        "transaction_scripts",
                        script_id,
                        "steps.action_parameters.approval_id",
                        "transaction approval belongs to a different case",
                        referenced_id=str(approval_id),
                    )
            if (
                event is not None
                and str(_value(event.target_type)) == "APPROVAL"
                and str(approval_id) != str(event.target_id)
            ):
                issues.add(
                    "EVENT_APPROVAL_BINDING_MISMATCH",
                    "transaction_scripts",
                    script_id,
                    "steps.action_parameters.approval_id",
                    "approval event target must equal the action approval_id",
                    referenced_id=str(event.event_id),
                )
            if (
                event is not None
                and str(_value(event.target_type)) == StateTargetType.APPROVAL.value
            ):
                targeted_mutations = [
                    mutation
                    for mutation in step.mutations
                    if str(_value(mutation.target_type))
                    == StateTargetType.APPROVAL.value
                    and str(mutation.target_id) == str(event.target_id)
                ]
                if not any(
                    mutation.changes.get("observable") is True
                    for mutation in targeted_mutations
                ):
                    issues.add(
                        "APPROVAL_EVENT_NOT_OBSERVABLE",
                        "transaction_scripts",
                        script_id,
                        "steps.mutations.changes.observable",
                        "an approval event mutation must make the decision observable",
                        referenced_id=transaction_id,
                    )
            if (
                event is not None
                and _event_value(event)
                == EventType.STATE_CHANGED_BEFORE_COMMIT.value
                and not any(
                    str(_value(mutation.target_type))
                    == StateTargetType.OFFERING_STATE.value
                    and str(mutation.target_id) == str(event.target_id)
                    for mutation in step.mutations
                )
            ):
                issues.add(
                    "STALE_STATE_EVENT_WITHOUT_MUTATION",
                    "transaction_scripts",
                    script_id,
                    "steps.mutations",
                    "STATE_CHANGED_BEFORE_COMMIT must advance its offering state version",
                    referenced_id=transaction_id,
                )
            action = str(_value(step.action))
            if (
                approval_id is not None
                and event is None
                and action != TransactionAction.REQUEST_APPROVAL.value
                and result
                in {
                    TransactionCode.SUCCESS.value,
                    TransactionCode.EXCEPTION_SUBMISSION_SUCCESS.value,
                }
                and step.precondition_state_versions.get(str(approval_id)) != 2
            ):
                issues.add(
                    "APPROVAL_FOLLOWUP_PRECONDITION_MISMATCH",
                    "transaction_scripts",
                    script_id,
                    "steps.precondition_state_versions",
                    "a successful approved follow-up must require observable approval version 2",
                    referenced_id=str(approval_id),
                )
            if (
                approval_id is not None
                and approval is not None
                and str(_value(approval.status)) == ApprovalStatus.APPROVED.value
                and event is None
                and action != TransactionAction.REQUEST_APPROVAL.value
            ):
                cutoffs = [
                    value
                    for value in (
                        approval.decided_at,
                        approval_event_times.get(str(approval_id)),
                    )
                    if value is not None
                ]
                if cutoffs and step.occurred_at <= max(cutoffs):
                    issues.add(
                        "APPROVAL_FOLLOWUP_TIME_ORDER",
                        "transaction_scripts",
                        script_id,
                        "steps.occurred_at",
                        "an approved follow-up must occur after its decision event",
                        referenced_id=transaction_id,
                    )
            if action == TransactionAction.SUBMIT_REGISTRATION.value:
                registration_state_id = step.action_parameters.get(
                    "offering_state_id"
                )
                if registration_state_id is None:
                    issues.add(
                        "REGISTRATION_STATE_REQUIRED",
                        "transaction_scripts",
                        script_id,
                        "steps.action_parameters.offering_state_id",
                        "SUBMIT_REGISTRATION requires an offering_state_id",
                        referenced_id=transaction_id,
                    )
                elif str(registration_state_id) not in {
                    str(value) for value in step.precondition_state_versions
                }:
                    issues.add(
                        "REGISTRATION_STATE_PRECONDITION_MISSING",
                        "transaction_scripts",
                        script_id,
                        "steps.precondition_state_versions",
                        "SUBMIT_REGISTRATION must bind its offering state version",
                        referenced_id=str(registration_state_id),
                    )
            _check_action_parameters(
                step,
                real,
                state_by_id,
                issues,
                script_id,
                transaction_id,
            )
            _check_mutations(
                step,
                versions,
                replay_targets,
                issues,
                script_id,
                transaction_id,
            )
            previous_step = step
    for case_id, count in script_cases.items():
        if count > 1:
            issues.add(
                "MULTIPLE_SCRIPTS_PER_CASE",
                "transaction_scripts",
                case_id,
                "case_id",
                f"case has {count} transaction scripts",
            )
    missing = set(case_by_id) - set(script_cases)
    for case_id in sorted(missing):
        issues.add(
            "CASE_WITHOUT_TRANSACTION_SCRIPT",
            "transaction_scripts",
            case_id,
            "case_id",
            "every generated exception case requires one transaction script",
        )


def _check_script_event_target(
    event: Any,
    case_id: str,
    case_by_id: Mapping[str, Any],
    approval_by_id: Mapping[str, Any],
    state_by_id: Mapping[str, Any],
    issues: _Issues,
    script_id: str,
    transaction_id: str,
) -> None:
    """Resolve an event target and bind case-scoped targets to the script."""

    target_id = str(event.target_id)
    target_type = str(_value(event.target_type))
    targets = {
        StateTargetType.CASE.value: case_by_id,
        StateTargetType.APPROVAL.value: approval_by_id,
        StateTargetType.OFFERING_STATE.value: state_by_id,
    }.get(target_type)
    if targets is None:
        return
    target = targets.get(target_id)
    if target is None:
        issues.add(
            "UNKNOWN_EVENT_TARGET",
            "transaction_scripts",
            script_id,
            "steps.event.target_id",
            "transaction event target does not resolve",
            referenced_id=target_id,
        )
        return
    if target_type == StateTargetType.CASE.value and target_id != case_id:
        issues.add(
            "EVENT_CASE_BINDING_MISMATCH",
            "transaction_scripts",
            script_id,
            "steps.event.target_id",
            "CASE event target must equal the transaction script case",
            referenced_id=transaction_id,
        )
    if (
        target_type == StateTargetType.APPROVAL.value
        and str(target.case_id) != case_id
    ):
        issues.add(
            "EVENT_APPROVAL_CASE_MISMATCH",
            "transaction_scripts",
            script_id,
            "steps.event.target_id",
            "approval event target must belong to the transaction script case",
            referenced_id=target_id,
        )


def _check_mutations(
    step: Any,
    versions: dict[str, int],
    replay_targets: dict[str, Any],
    issues: _Issues,
    script_id: str,
    transaction_id: str,
) -> None:
    for target_id, expected in step.precondition_state_versions.items():
        target_id = str(target_id)
        if target_id not in replay_targets:
            issues.add(
                "UNKNOWN_PRECONDITION_TARGET",
                "transaction_scripts",
                script_id,
                "steps.precondition_state_versions",
                "transaction precondition references an unknown versioned state",
                referenced_id=target_id,
            )
            continue
        current = versions.get(target_id)
        if current is not None and int(expected) != current:
            issues.add(
                "STALE_PRECONDITION_VERSION",
                "transaction_scripts",
                script_id,
                "steps.precondition_state_versions",
                f"precondition expects version {expected}, but replay state is {current}",
                referenced_id=target_id,
            )
    for mutation in step.mutations:
        target_id = str(mutation.target_id)
        if target_id not in replay_targets:
            issues.add(
                "UNKNOWN_MUTATION_TARGET",
                "transaction_scripts",
                script_id,
                "steps.mutations.target_id",
                "state mutation references an unknown versioned target",
                referenced_id=target_id,
            )
            continue
        expected = mutation.expected_version
        new = mutation.resulting_version
        if expected is None or new is None:
            # Non-versioned mutations are allowed only for entity types whose
            # persisted contract has no version field.
            if hasattr(replay_targets[target_id], "version"):
                issues.add(
                    "MUTATION_WITHOUT_VERSION",
                    "transaction_scripts",
                    script_id,
                    "steps.mutations.expected_version",
                    "mutation of a versioned target requires both versions",
                    referenced_id=target_id,
                )
            continue
        current = versions.get(target_id)
        if current is not None and int(expected) != current:
            issues.add(
                "STALE_MUTATION_VERSION",
                "transaction_scripts",
                script_id,
                "steps.mutations.expected_version",
                f"mutation expected version {expected}, but replay state is {current}",
                referenced_id=target_id,
            )
        if int(new) != int(expected) + 1:
            issues.add(
                "NON_MONOTONIC_STATE_VERSION",
                "transaction_scripts",
                script_id,
                "steps.mutations.resulting_version",
                "state mutation version must increment exactly once",
                referenced_id=target_id,
            )
        target = replay_targets[target_id]
        target_type = str(_value(mutation.target_type))
        expected_model = _TARGET_MODEL_BY_TARGET_TYPE.get(target_type)
        if expected_model != target.__class__.__name__:
            issues.add(
                "MUTATION_TARGET_TYPE_MISMATCH",
                "transaction_scripts",
                script_id,
                "steps.mutations.target_type",
                "mutation target_type does not match the referenced entity",
                referenced_id=target_id,
            )
        else:
            allowed_fields = _MUTABLE_FIELDS_BY_TARGET_TYPE[target_type]
            rejected_fields = sorted(set(mutation.changes) - allowed_fields)
            if rejected_fields:
                issues.add(
                    "MUTATION_FIELD_NOT_MUTABLE",
                    "transaction_scripts",
                    script_id,
                    "steps.mutations.changes",
                    "mutation attempts to change immutable or unknown fields: "
                    + ", ".join(rejected_fields),
                    referenced_id=target_id,
                )
            else:
                candidate = target.model_dump(mode="python")
                candidate.update(mutation.changes)
                candidate["version"] = int(new)
                try:
                    replay_targets[target_id] = target.__class__.model_validate(
                        candidate
                    )
                except ValidationError as exc:
                    first_error = exc.errors(include_url=False)[0]
                    issues.add(
                        "INVALID_MUTATION_RESULT_STATE",
                        "transaction_scripts",
                        script_id,
                        "steps.mutations.changes",
                        "mutation produces an invalid target state: "
                        + str(first_error["msg"]),
                        referenced_id=target_id,
                    )
        versions[target_id] = int(new)


def _check_action_parameters(
    step: Any,
    real: _RealIndex,
    state_by_id: Mapping[str, Any],
    issues: _Issues,
    script_id: str,
    transaction_id: str,
) -> None:
    parameters = step.action_parameters
    course_code = parameters.get("course_code", parameters.get("target_course"))
    offering_id = parameters.get("template_offering_id")
    index_id = parameters.get("template_index_id")
    state_id = parameters.get("offering_state_id")
    if course_code is not None and str(course_code) not in real.courses:
        issues.add(
            "UNKNOWN_ACTION_COURSE",
            "transaction_scripts",
            script_id,
            "steps.action_parameters.course_code",
            "transaction action references an unknown course",
            referenced_id=str(course_code),
        )
    pair = None
    if (offering_id is None) != (index_id is None):
        issues.add(
            "INCOMPLETE_ACTION_INDEX_REFERENCE",
            "transaction_scripts",
            script_id,
            "steps.action_parameters.template_index_id",
            "template_offering_id and template_index_id must be provided together",
            referenced_id=transaction_id,
        )
    if offering_id is not None and index_id is not None:
        pair = (str(offering_id), str(index_id))
        source = real.indexes.get(pair)
        if source is None:
            issues.add(
                "UNKNOWN_ACTION_INDEX",
                "transaction_scripts",
                script_id,
                "steps.action_parameters.template_index_id",
                "transaction action references an unknown offering/index pair",
                referenced_id=str(index_id),
            )
        elif course_code is not None and str(source[0].course_code) != str(course_code):
            issues.add(
                "ACTION_COURSE_OWNERSHIP_MISMATCH",
                "transaction_scripts",
                script_id,
                "steps.action_parameters.course_code",
                "transaction course does not own its offering/index",
                referenced_id=transaction_id,
            )
    if state_id is not None:
        state = state_by_id.get(str(state_id))
        if state is None:
            issues.add(
                "UNKNOWN_ACTION_OFFERING_STATE",
                "transaction_scripts",
                script_id,
                "steps.action_parameters.offering_state_id",
                "transaction action references an unknown offering state",
                referenced_id=str(state_id),
            )
        elif pair is not None and pair != (
            str(state.template_offering_id),
            str(state.template_index_id),
        ):
            issues.add(
                "ACTION_STATE_INDEX_MISMATCH",
                "transaction_scripts",
                script_id,
                "steps.action_parameters.offering_state_id",
                "transaction state does not belong to its offering/index",
                referenced_id=str(state_id),
            )
        else:
            source = real.indexes.get(
                (
                    str(state.template_offering_id),
                    str(state.template_index_id),
                )
            )
            if (
                source is not None
                and course_code is not None
                and str(source[0].course_code) != str(course_code)
            ):
                issues.add(
                    "ACTION_STATE_COURSE_MISMATCH",
                    "transaction_scripts",
                    script_id,
                    "steps.action_parameters.offering_state_id",
                    "offering state template course does not match the action course",
                    referenced_id=str(state_id),
                )


def _check_event_result(
    event: Any,
    result: str,
    observation: str,
    issues: _Issues,
    dataset: str,
    record_id: str,
    referenced_id: str,
) -> None:
    event_value = _event_value(event)
    expected = _EVENT_RESULTS.get(event_value)
    if expected is None or (result, observation) != expected:
        issues.add(
            "EVENT_RESULT_MISMATCH",
            dataset,
            record_id,
            "event_type",
            "injected event does not match transaction result and observation",
            referenced_id=referenced_id,
        )


def _event_value(event: Any) -> str:
    if hasattr(event, "event_type"):
        event = event.event_type
    return str(_value(event))


def _check_initial_context_contract(
    scenario: Any,
    case: Any | None,
    registration: Any | None,
    state_by_id: Mapping[str, Any],
    issues: _Issues,
) -> None:
    scenario_id = str(scenario.scenario_id)
    linked_state_ids = {str(value) for value in scenario.offering_state_ids}
    observed_versions = scenario.initial_state.get("observed_state_versions")
    if not isinstance(observed_versions, Mapping):
        issues.add(
            "MISSING_OBSERVED_STATE_VERSIONS",
            "scenarios",
            scenario_id,
            "initial_state.observed_state_versions",
            "initial state must map every linked offering state to its baseline version",
        )
    else:
        observed_ids = {str(value) for value in observed_versions}
        if observed_ids != linked_state_ids:
            issues.add(
                "OBSERVED_STATE_VERSION_SET_MISMATCH",
                "scenarios",
                scenario_id,
                "initial_state.observed_state_versions",
                "observed state-version keys must exactly match offering_state_ids",
            )
        for state_id in sorted(observed_ids & linked_state_ids):
            state = state_by_id.get(state_id)
            if state is None:
                continue
            observed = observed_versions[state_id]
            if (
                isinstance(observed, bool)
                or not isinstance(observed, int)
                or observed != int(state.version)
            ):
                issues.add(
                    "OBSERVED_STATE_VERSION_MISMATCH",
                    "scenarios",
                    scenario_id,
                    "initial_state.observed_state_versions",
                    "observed offering-state version differs from the baseline state",
                    referenced_id=state_id,
                )

    request_time = scenario.initial_state.get("request_time")
    parsed_request_time: datetime | None = None
    if isinstance(request_time, datetime):
        parsed_request_time = request_time
    elif isinstance(request_time, str):
        try:
            parsed_request_time = datetime.fromisoformat(request_time)
        except ValueError:
            parsed_request_time = None
    expected_times = [
        linked.scenario_time
        for linked in (case, registration)
        if linked is not None
    ]
    if (
        parsed_request_time is None
        or any(parsed_request_time != expected for expected in expected_times)
    ):
        issues.add(
            "SCENARIO_REQUEST_TIME_MISMATCH",
            "scenarios",
            scenario_id,
            "initial_state.request_time",
            "request_time must equal the linked case and registration scenario_time",
        )


def _check_scenarios(
    bundle: Stage3DataBundle,
    real: _RealIndex,
    student_by_id: Mapping[str, Any],
    audit_by_id: Mapping[str, Any],
    registration_by_id: Mapping[str, Any],
    case_by_id: Mapping[str, Any],
    approval_by_id: Mapping[str, Any],
    script_by_id: Mapping[str, Any],
    state_by_id: Mapping[str, Any],
    issues: _Issues,
    enforce_expected_counts: bool,
) -> None:
    scenario_cases: Counter[str] = Counter()
    scenario_scripts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    family_splits: dict[str, Counter[str]] = defaultdict(Counter)
    human_cases: set[str] = set()
    approval_by_case = {
        str(approval.case_id): approval for approval in approval_by_id.values()
    }
    observable_ids = {
        *student_by_id,
        *audit_by_id,
        *registration_by_id,
        *case_by_id,
        *state_by_id,
    }
    for scenario in bundle.scenarios:
        scenario_id = str(scenario.scenario_id)
        case_id = str(scenario.case_id)
        script_id = str(scenario.transaction_script_id)
        family = str(_value(scenario.family))
        split = str(_value(scenario.split))
        scenario_cases[case_id] += 1
        scenario_scripts[script_id] += 1
        family_counts[family] += 1
        family_splits[family][split] += 1

        student = student_by_id.get(str(scenario.student_id))
        audit = audit_by_id.get(str(scenario.audit_id))
        registration = registration_by_id.get(str(scenario.registration_id))
        case = case_by_id.get(case_id)
        script = script_by_id.get(script_id)
        for field_name, linked, code in (
            ("student_id", student, "UNKNOWN_STUDENT"),
            ("audit_id", audit, "UNKNOWN_AUDIT"),
            ("registration_id", registration, "UNKNOWN_REGISTRATION"),
            ("case_id", case, "UNKNOWN_CASE"),
            ("transaction_script_id", script, "UNKNOWN_TRANSACTION_SCRIPT"),
        ):
            if linked is None:
                issues.add(
                    code,
                    "scenarios",
                    scenario_id,
                    field_name,
                    f"scenario {field_name} does not resolve",
                    referenced_id=str(getattr(scenario, field_name)),
                )
        if student is not None:
            _check_equal_fields(
                issues,
                "scenarios",
                scenario_id,
                scenario,
                student,
                ("simulation_scope_id", "curriculum_id"),
                code="SCENARIO_STUDENT_MISMATCH",
            )
        for field_name, linked in (
            ("audit_id", audit),
            ("registration_id", registration),
            ("case_id", case),
        ):
            if linked is not None and str(linked.student_id) != str(scenario.student_id):
                issues.add(
                    "SCENARIO_STUDENT_LINK_MISMATCH",
                    "scenarios",
                    scenario_id,
                    field_name,
                    f"scenario {field_name} belongs to a different student",
                    referenced_id=str(getattr(scenario, field_name)),
                )
        if script is not None and str(script.case_id) != case_id:
            issues.add(
                "SCENARIO_SCRIPT_CASE_MISMATCH",
                "scenarios",
                scenario_id,
                "transaction_script_id",
                "scenario script belongs to a different case",
                referenced_id=script_id,
            )
        for state_id in scenario.offering_state_ids:
            if str(state_id) not in state_by_id:
                issues.add(
                    "UNKNOWN_OFFERING_STATE",
                    "scenarios",
                    scenario_id,
                    "offering_state_ids",
                    "scenario links an unknown offering state",
                    referenced_id=str(state_id),
                )
        for reference in scenario.initial_state_refs:
            if str(reference) not in observable_ids:
                issues.add(
                    "NON_OBSERVABLE_INITIAL_REFERENCE",
                    "scenarios",
                    scenario_id,
                    "initial_state_refs",
                    "initial reference is missing or evaluator-only",
                    referenced_id=str(reference),
                )
        required_initial_refs = {
            str(scenario.student_id),
            str(scenario.audit_id),
            str(scenario.registration_id),
            str(scenario.case_id),
            *(str(state_id) for state_id in scenario.offering_state_ids),
        }
        missing_initial_refs = required_initial_refs - {
            str(value) for value in scenario.initial_state_refs
        }
        for reference in sorted(missing_initial_refs):
            issues.add(
                "MISSING_INITIAL_REFERENCE",
                "scenarios",
                scenario_id,
                "initial_state_refs",
                "scenario omits an observable entity needed by its context",
                referenced_id=reference,
            )
        extraneous_initial_refs = {
            str(value) for value in scenario.initial_state_refs
        } - required_initial_refs
        for reference in sorted(extraneous_initial_refs):
            issues.add(
                "EXTRANEOUS_INITIAL_REFERENCE",
                "scenarios",
                scenario_id,
                "initial_state_refs",
                "scenario exposes an unrelated observable entity",
                referenced_id=reference,
            )
        _check_initial_context_contract(
            scenario,
            case,
            registration,
            state_by_id,
            issues,
        )

        target_course = _check_scenario_target_course(
            scenario,
            student,
            real,
            state_by_id,
            issues,
        )
        _check_resolution_paths(
            scenario,
            student,
            real,
            approval_by_id,
            state_by_id,
            target_course,
            issues,
        )
        _check_script_scenario_bindings(
            scenario,
            script,
            real,
            state_by_id,
            target_course,
            issues,
        )
        _check_expected_outcome(
            scenario,
            script,
            approval_by_case.get(case_id),
            issues,
        )
        _check_observable_intake_readiness(scenario, case, issues)
        _check_family_semantics(
            scenario,
            student,
            registration,
            script,
            real,
            state_by_id,
            target_course,
            issues,
        )

        if scenario.ground_truth.requires_human:
            human_cases.add(case_id)
            if case_id not in approval_by_case:
                issues.add(
                    "HUMAN_SCENARIO_WITHOUT_APPROVAL",
                    "scenarios",
                    scenario_id,
                    "ground_truth.requires_human",
                    "human-required scenario has no approval workflow record",
                    referenced_id=case_id,
                )
        event = scenario.injected_event
        if event is not None:
            _check_scenario_event(
                scenario,
                script,
                case_by_id,
                approval_by_id,
                state_by_id,
                issues,
            )
        elif script is not None and any(step.event is not None for step in script.steps):
            issues.add(
                "UNDECLARED_SCRIPT_EVENT",
                "scenarios",
                scenario_id,
                "injected_event",
                "transaction script contains an event absent from its scenario",
                referenced_id=script_id,
            )
        _check_agent_context(scenario, issues)

    for case_id, count in scenario_cases.items():
        if count > 1:
            issues.add(
                "MULTIPLE_SCENARIOS_PER_CASE",
                "scenarios",
                case_id,
                "case_id",
                f"case is used by {count} scenarios",
            )
    for script_id, count in scenario_scripts.items():
        if count > 1:
            issues.add(
                "MULTIPLE_SCENARIOS_PER_SCRIPT",
                "scenarios",
                script_id,
                "transaction_script_id",
                f"transaction script is used by {count} scenarios",
            )
    for case_id in sorted(set(case_by_id) - set(scenario_cases)):
        issues.add(
            "CASE_WITHOUT_SCENARIO",
            "scenarios",
            case_id,
            "case_id",
            "every exception case requires one evaluation scenario",
        )

    approval_cases = set(approval_by_case)
    for case_id in sorted(approval_cases - human_cases):
        issues.add(
            "APPROVAL_WITHOUT_HUMAN_GROUND_TRUTH",
            "scenarios",
            case_id,
            "ground_truth.requires_human",
            "approval record exists for a scenario not marked as human-required",
        )
    if enforce_expected_counts:
        for family in (item.value for item in ScenarioFamily):
            actual = family_counts[family]
            if actual != EXPECTED_FAMILY_COUNT:
                issues.add(
                    "SCENARIO_FAMILY_COUNT_MISMATCH",
                    "scenarios",
                    f"family.{family}",
                    "family",
                    f"family {family} requires {EXPECTED_FAMILY_COUNT}; found {actual}",
                    referenced_id=family,
                )
            for split, expected in EXPECTED_SPLITS_PER_FAMILY.items():
                split_actual = family_splits[family][split]
                if split_actual != expected:
                    issues.add(
                        "SCENARIO_SPLIT_COUNT_MISMATCH",
                        "scenarios",
                        f"family.{family}",
                        "split",
                        f"family {family} split {split} requires {expected}; "
                        f"found {split_actual}",
                        referenced_id=split,
                    )


def _state_source(real: _RealIndex, state: Any) -> tuple[Any, Any] | None:
    return real.indexes.get(
        (str(state.template_offering_id), str(state.template_index_id))
    )


def _state_course(real: _RealIndex, state: Any) -> str | None:
    source = _state_source(real, state)
    return None if source is None else str(source[0].course_code)


def _check_scenario_target_course(
    scenario: Any,
    student: Any | None,
    real: _RealIndex,
    state_by_id: Mapping[str, Any],
    issues: _Issues,
) -> str | None:
    scenario_id = str(scenario.scenario_id)
    value = scenario.initial_state.get("target_course")
    if not isinstance(value, str) or not value.strip():
        issues.add(
            "MISSING_SCENARIO_TARGET_COURSE",
            "scenarios",
            scenario_id,
            "initial_state.target_course",
            "scenario must declare one nonempty observable target course",
        )
        return None
    target_course = value.strip().upper()
    if target_course not in real.courses:
        issues.add(
            "UNKNOWN_SCENARIO_TARGET_COURSE",
            "scenarios",
            scenario_id,
            "initial_state.target_course",
            "scenario target course is absent from the real catalogue",
            referenced_id=target_course,
        )
        return target_course
    if student is not None:
        curriculum = real.curricula.get(str(student.curriculum_id))
        if curriculum is not None:
            matching_items = [
                item
                for item in curriculum.study_plan
                if str(item.course_code or "") == target_course
            ]
            if not matching_items:
                issues.add(
                    "TARGET_COURSE_OUTSIDE_STUDY_PLAN",
                    "scenarios",
                    scenario_id,
                    "initial_state.target_course",
                    "target course is absent from the selected curriculum study plan",
                    referenced_id=target_course,
                )
            elif not any(
                item.path_label is None
                or (
                    student.study_plan_path_label is not None
                    and str(item.path_label) == str(student.study_plan_path_label)
                )
                for item in matching_items
            ):
                issues.add(
                    "TARGET_COURSE_PATH_MISMATCH",
                    "scenarios",
                    scenario_id,
                    "initial_state.target_course",
                    "target course is incompatible with the selected study-plan path",
                    referenced_id=target_course,
                )
    for state_id in scenario.offering_state_ids:
        state = state_by_id.get(str(state_id))
        state_course = None if state is None else _state_course(real, state)
        if state_course is not None and state_course != target_course:
            issues.add(
                "SCENARIO_STATE_COURSE_MISMATCH",
                "scenarios",
                scenario_id,
                "offering_state_ids",
                "linked offering state belongs to a different course than the target",
                referenced_id=str(state_id),
            )
    return target_course


def _ground_truth_paths(scenario: Any) -> Iterator[tuple[str, Any]]:
    for field_name in (
        "valid_initial_paths",
        "valid_final_paths",
        "invalid_paths",
    ):
        for path in getattr(scenario.ground_truth, field_name):
            yield field_name, path


def _parameter_state_ids(parameters: Mapping[str, Any]) -> Iterator[tuple[str, str]]:
    for key, value in parameters.items():
        if str(key).endswith("offering_state_id") and value is not None:
            yield str(key), str(value)


def _path_state_ids(paths: Iterable[Any]) -> set[str]:
    return {
        state_id
        for path in paths
        for step in path.steps
        for _, state_id in _parameter_state_ids(step.parameters)
    }


def _check_resolution_paths(
    scenario: Any,
    student: Any | None,
    real: _RealIndex,
    approval_by_id: Mapping[str, Any],
    state_by_id: Mapping[str, Any],
    target_course: str | None,
    issues: _Issues,
) -> None:
    scenario_id = str(scenario.scenario_id)
    linked_states = {str(value) for value in scenario.offering_state_ids}
    curriculum = real.curricula.get(str(scenario.curriculum_id))
    known_paths = (
        {str(path.path_id) for path in curriculum.graduation_paths}
        if curriculum is not None
        else set()
    )
    for group, path in _ground_truth_paths(scenario):
        for step in path.steps:
            parameters = step.parameters
            for key, state_id in _parameter_state_ids(parameters):
                state = state_by_id.get(state_id)
                if state is None:
                    issues.add(
                        "UNKNOWN_PATH_OFFERING_STATE",
                        "scenarios",
                        scenario_id,
                        f"ground_truth.{group}.steps.parameters.{key}",
                        "resolution path offering state does not resolve",
                        referenced_id=state_id,
                    )
                elif state_id not in linked_states:
                    issues.add(
                        "PATH_STATE_OUTSIDE_SCENARIO",
                        "scenarios",
                        scenario_id,
                        f"ground_truth.{group}.steps.parameters.{key}",
                        "resolution path offering state is not linked by the scenario",
                        referenced_id=state_id,
                    )
                elif group in {"valid_initial_paths", "valid_final_paths"} and not (
                    _state_initially_usable(state)
                ):
                    issues.add(
                        "PATH_STATE_NOT_INITIALLY_USABLE",
                        "scenarios",
                        scenario_id,
                        f"ground_truth.{group}.steps.parameters.{key}",
                        "valid resolution path state must initially be open and available",
                        referenced_id=state_id,
                    )
                elif (
                    target_course is not None
                    and _state_course(real, state) != target_course
                ):
                    issues.add(
                        "PATH_STATE_COURSE_MISMATCH",
                        "scenarios",
                        scenario_id,
                        f"ground_truth.{group}.steps.parameters.{key}",
                        "resolution path state does not offer the scenario target course",
                        referenced_id=state_id,
                    )
            approval_id = parameters.get("approval_id")
            if approval_id is not None:
                approval = approval_by_id.get(str(approval_id))
                if approval is None:
                    issues.add(
                        "UNKNOWN_PATH_APPROVAL",
                        "scenarios",
                        scenario_id,
                        f"ground_truth.{group}.steps.parameters.approval_id",
                        "resolution path approval does not resolve",
                        referenced_id=str(approval_id),
                    )
                elif str(approval.case_id) != str(scenario.case_id):
                    issues.add(
                        "PATH_APPROVAL_CASE_MISMATCH",
                        "scenarios",
                        scenario_id,
                        f"ground_truth.{group}.steps.parameters.approval_id",
                        "resolution path approval belongs to a different case",
                        referenced_id=str(approval_id),
                    )
            curriculum_id = parameters.get("curriculum_id")
            if (
                curriculum_id is not None
                and str(curriculum_id) != str(scenario.curriculum_id)
            ):
                issues.add(
                    "PATH_CURRICULUM_MISMATCH",
                    "scenarios",
                    scenario_id,
                    f"ground_truth.{group}.steps.parameters.curriculum_id",
                    "resolution path curriculum must equal the scenario curriculum",
                    referenced_id=str(curriculum_id),
                )
            graduation_path_id = parameters.get("graduation_path_id")
            if graduation_path_id is not None:
                path_id = str(graduation_path_id)
                if path_id not in known_paths:
                    issues.add(
                        "UNKNOWN_PATH_GRADUATION_PATH",
                        "scenarios",
                        scenario_id,
                        f"ground_truth.{group}.steps.parameters.graduation_path_id",
                        "resolution path graduation path is absent from the curriculum",
                        referenced_id=path_id,
                    )
                elif (
                    student is None
                    or student.graduation_path_id is None
                    or path_id != str(student.graduation_path_id)
                ):
                    issues.add(
                        "PATH_GRADUATION_PATH_MISMATCH",
                        "scenarios",
                        scenario_id,
                        f"ground_truth.{group}.steps.parameters.graduation_path_id",
                        "resolution path graduation path is not the student's selected path",
                        referenced_id=path_id,
                    )
            for course_key in ("course_code", "target_course"):
                course_value = parameters.get(course_key)
                if course_value is None:
                    continue
                course_code = str(course_value).upper()
                if course_code not in real.courses:
                    issues.add(
                        "UNKNOWN_PATH_COURSE",
                        "scenarios",
                        scenario_id,
                        f"ground_truth.{group}.steps.parameters.{course_key}",
                        "resolution path course does not resolve",
                        referenced_id=course_code,
                    )
                elif target_course is not None and course_code != target_course:
                    issues.add(
                        "PATH_TARGET_COURSE_MISMATCH",
                        "scenarios",
                        scenario_id,
                        f"ground_truth.{group}.steps.parameters.{course_key}",
                        "resolution path course differs from the scenario target",
                        referenced_id=course_code,
                    )


def _check_script_scenario_bindings(
    scenario: Any,
    script: Any | None,
    real: _RealIndex,
    state_by_id: Mapping[str, Any],
    target_course: str | None,
    issues: _Issues,
) -> None:
    if script is None:
        return
    scenario_id = str(scenario.scenario_id)
    linked_states = {str(value) for value in scenario.offering_state_ids}
    for step in script.steps:
        state_id = step.action_parameters.get("offering_state_id")
        if state_id is not None and str(state_id) not in linked_states:
            issues.add(
                "ACTION_STATE_OUTSIDE_SCENARIO",
                "scenarios",
                scenario_id,
                "transaction_script.steps.action_parameters.offering_state_id",
                "transaction action state is not linked by the scenario",
                referenced_id=str(state_id),
            )
        action_course = step.action_parameters.get(
            "course_code", step.action_parameters.get("target_course")
        )
        if (
            action_course is not None
            and target_course is not None
            and str(action_course).upper() != target_course
        ):
            issues.add(
                "ACTION_TARGET_COURSE_MISMATCH",
                "scenarios",
                scenario_id,
                "transaction_script.steps.action_parameters.course_code",
                "transaction action course differs from the scenario target",
                referenced_id=str(action_course),
            )
        if state_id is not None and action_course is not None:
            state = state_by_id.get(str(state_id))
            if (
                state is not None
                and _state_course(real, state) != str(action_course).upper()
            ):
                issues.add(
                    "ACTION_STATE_COURSE_MISMATCH",
                    "scenarios",
                    scenario_id,
                    "transaction_script.steps.action_parameters.offering_state_id",
                    "transaction state template course differs from its action course",
                    referenced_id=str(state_id),
                )


def _expected_outcome_for_terminal(
    terminal_code: str, approval: Any | None
) -> str:
    if approval is not None:
        status = str(_value(approval.status))
        if status == ApprovalStatus.REJECTED.value:
            return ExpectedOutcome.ESCALATED.value
        if status == ApprovalStatus.PENDING.value:
            return ExpectedOutcome.PENDING_APPROVAL.value
    return {
        TransactionCode.SUCCESS.value: ExpectedOutcome.RESOLVED.value,
        TransactionCode.EXCEPTION_SUBMISSION_SUCCESS.value: (
            ExpectedOutcome.RESOLVED.value
        ),
        TransactionCode.REQUIRED_INFORMATION_MISSING.value: (
            ExpectedOutcome.CLARIFICATION_REQUIRED.value
        ),
        TransactionCode.APPROVAL_PENDING.value: ExpectedOutcome.PENDING_APPROVAL.value,
        TransactionCode.STALE_STATE.value: ExpectedOutcome.FAILED.value,
        TransactionCode.TEMPORARY_SYSTEM_FAILURE.value: ExpectedOutcome.FAILED.value,
    }.get(terminal_code, ExpectedOutcome.ESCALATED.value)


def _check_expected_outcome(
    scenario: Any,
    script: Any | None,
    approval: Any | None,
    issues: _Issues,
) -> None:
    if script is None or not script.steps:
        return
    scenario_id = str(scenario.scenario_id)
    terminal_code = str(_value(script.steps[-1].result_code))
    expected = _expected_outcome_for_terminal(terminal_code, approval)
    actual = str(_value(scenario.ground_truth.expected_outcome))
    if actual != expected:
        issues.add(
            "EXPECTED_OUTCOME_MISMATCH",
            "scenarios",
            scenario_id,
            "ground_truth.expected_outcome",
            f"terminal workflow implies {expected}, not {actual}",
            referenced_id=str(script.steps[-1].transaction_id),
        )
    if approval is None:
        return
    status = str(_value(approval.status))
    permitted_terminal = {
        ApprovalStatus.APPROVED.value: {
            TransactionCode.SUCCESS.value,
            TransactionCode.EXCEPTION_SUBMISSION_SUCCESS.value,
        },
        ApprovalStatus.REJECTED.value: {TransactionCode.APPROVAL_REJECTED.value},
        ApprovalStatus.PENDING.value: {TransactionCode.APPROVAL_PENDING.value},
    }[status]
    if terminal_code not in permitted_terminal:
        issues.add(
            "APPROVAL_TERMINAL_RESULT_MISMATCH",
            "scenarios",
            scenario_id,
            "transaction_script.steps.result_code",
            "terminal transaction result does not agree with approval status",
            referenced_id=str(approval.approval_id),
        )


def _course_has_prerequisite(course: Any) -> bool:
    prerequisite = course.prerequisites
    return bool(
        prerequisite.all_of
        or prerequisite.any_of
        or prerequisite.minimum_study_year is not None
        or (prerequisite.raw_text and prerequisite.raw_text.strip())
    )


def _student_prerequisite_result(course: Any, student: Any) -> PrerequisiteResult:
    prerequisite = course.prerequisites
    completed = {
        str(item.course_code)
        for item in student.completed_courses
        if item.credit_status is CreditStatus.EARNED
    }
    completed.update(
        str(item.course_code)
        for item in student.exemptions
        if item.course_code is not None
    )
    if prerequisite.raw_text and prerequisite.raw_text.strip():
        return evaluate_prerequisite(
            prerequisite.raw_text,
            completed_courses=completed,
            study_year=int(student.study_year),
        )
    results: list[PrerequisiteResult] = []
    if prerequisite.all_of:
        results.append(
            PrerequisiteResult.PASS
            if set(map(str, prerequisite.all_of)).issubset(completed)
            else PrerequisiteResult.FAIL
        )
    if prerequisite.any_of:
        results.append(
            PrerequisiteResult.PASS
            if set(map(str, prerequisite.any_of)) & completed
            else PrerequisiteResult.FAIL
        )
    if prerequisite.minimum_study_year is not None:
        results.append(
            PrerequisiteResult.PASS
            if int(student.study_year) >= int(prerequisite.minimum_study_year)
            else PrerequisiteResult.FAIL
        )
    return (
        PrerequisiteResult.PASS
        if all(result is PrerequisiteResult.PASS for result in results)
        else PrerequisiteResult.FAIL
    )


def _meeting_conflicts(left: Any, right: Any) -> bool:
    if any(
        value is None
        for value in (
            left.day,
            left.start_time,
            left.end_time,
            right.day,
            right.start_time,
            right.end_time,
        )
    ):
        return True
    if left.day != right.day:
        return False
    left_weeks = set(left.teaching_weeks)
    right_weeks = set(right.teaching_weeks)
    if left_weeks and right_weeks and left_weeks.isdisjoint(right_weeks):
        return False
    return left.start_time < right.end_time and right.start_time < left.end_time


def _state_conflicts_registration(
    real: _RealIndex, state: Any, registration: Any
) -> bool:
    source = _state_source(real, state)
    if source is None:
        return True
    return any(
        _meeting_conflicts(candidate, attributed.meeting)
        for candidate in source[1].meetings
        for attributed in registration.timetable
    )


def _state_initially_usable(state: Any) -> bool:
    return (
        str(_value(state.runtime_status)) == RuntimeOfferingStatus.OPEN.value
        and state.available is True
        and int(state.vacancies) > 0
    )


def _check_usable_state(
    scenario_id: str,
    field: str,
    state_id: str,
    state_by_id: Mapping[str, Any],
    issues: _Issues,
) -> Any | None:
    state = state_by_id.get(state_id)
    if state is None:
        issues.add(
            "UNKNOWN_SCENARIO_STATE",
            "scenarios",
            scenario_id,
            field,
            "scenario state does not resolve",
            referenced_id=state_id,
        )
    elif not _state_initially_usable(state):
        issues.add(
            "PATH_STATE_NOT_INITIALLY_USABLE",
            "scenarios",
            scenario_id,
            field,
            "resolution state must initially be open, available, and have a vacancy",
            referenced_id=state_id,
        )
    return state


def _check_registration_feasibility(
    scenario: Any,
    student: Any,
    registration: Any,
    script: Any,
    real: _RealIndex,
    state_by_id: Mapping[str, Any],
    target_course: str,
    issues: _Issues,
) -> None:
    scenario_id = str(scenario.scenario_id)
    course = real.courses[target_course]
    successful = {
        TransactionCode.SUCCESS.value,
        TransactionCode.EXCEPTION_SUBMISSION_SUCCESS.value,
    }
    for step in script.steps:
        if (
            str(_value(step.action)) != TransactionAction.SUBMIT_REGISTRATION.value
            or str(_value(step.result_code)) not in successful
        ):
            continue
        state_id = step.action_parameters.get("offering_state_id")
        if state_id is None:
            continue
        state = _check_usable_state(
            scenario_id,
            "transaction_script.steps.action_parameters.offering_state_id",
            str(state_id),
            state_by_id,
            issues,
        )
        if _student_prerequisite_result(course, student) is not PrerequisiteResult.PASS:
            issues.add(
                "RESOLVED_REGISTRATION_PREREQUISITE_NOT_PASS",
                "scenarios",
                scenario_id,
                "initial_state.target_course",
                "a successful registration requires a deterministic prerequisite PASS",
                referenced_id=target_course,
            )
        if registration.workload_aus + course.aus > registration.workload_limit_aus:
            issues.add(
                "RESOLVED_REGISTRATION_WORKLOAD_EXCEEDED",
                "scenarios",
                scenario_id,
                "registration_id",
                "target course would exceed the student's workload limit",
                referenced_id=str(registration.registration_id),
            )
        if state is not None and _state_conflicts_registration(real, state, registration):
            issues.add(
                "RESOLVED_REGISTRATION_TIMETABLE_CONFLICT",
                "scenarios",
                scenario_id,
                "transaction_script.steps.action_parameters.offering_state_id",
                "successful registration state conflicts with the current timetable",
                referenced_id=str(state_id),
            )


def _check_family_semantics(
    scenario: Any,
    student: Any | None,
    registration: Any | None,
    script: Any | None,
    real: _RealIndex,
    state_by_id: Mapping[str, Any],
    target_course: str | None,
    issues: _Issues,
) -> None:
    scenario_id = str(scenario.scenario_id)
    family = str(_value(scenario.family))
    if target_course is None or target_course not in real.courses:
        return
    course = real.courses[target_course]
    if family == ScenarioFamily.S2_PREREQUISITE_EXCEPTION.value:
        if not _course_has_prerequisite(course):
            issues.add(
                "S2_TARGET_WITHOUT_PREREQUISITE",
                "scenarios",
                scenario_id,
                "initial_state.target_course",
                "S2 prerequisite-exception target must have a nonempty prerequisite",
                referenced_id=target_course,
            )
    if family == ScenarioFamily.S5_CROSS_PROGRAMME.value and (
        student is None or student.graduation_path_id is None
    ):
        issues.add(
            "S5_GRADUATION_PATH_REQUIRED",
            "scenarios",
            scenario_id,
            "student_id",
            "S5 cross-programme scenarios require a selected graduation path",
            referenced_id=str(scenario.student_id),
        )
    if family == ScenarioFamily.S5_CROSS_PROGRAMME.value:
        curriculum = real.curricula.get(str(scenario.curriculum_id))
        if (
            curriculum is not None
            and str(_value(curriculum.configuration_kind)) == "BASE"
            and str(curriculum.programme) in {"AISC", "CE", "CSC", "DSAI"}
        ):
            issues.add(
                "S5_PRIMARY_BASE_CURRICULUM",
                "scenarios",
                scenario_id,
                "curriculum_id",
                "S5 requires an integrated, non-primary, or overlay curriculum",
                referenced_id=str(scenario.curriculum_id),
            )
    if student is not None and registration is not None and script is not None:
        _check_registration_feasibility(
            scenario,
            student,
            registration,
            script,
            real,
            state_by_id,
            target_course,
            issues,
        )

    linked_states = {str(value) for value in scenario.offering_state_ids}
    if family in {
        ScenarioFamily.S1_NORMAL_RECOVERY.value,
        ScenarioFamily.S4_CONSTRAINT_HEAVY.value,
        ScenarioFamily.S7_DYNAMIC_FAILURE.value,
    }:
        preferred_id = scenario.initial_state.get("preferred_offering_state_id")
        alternative_id = scenario.initial_state.get("alternative_offering_state_id")
        if not isinstance(preferred_id, str) or not isinstance(alternative_id, str):
            issues.add(
                "MISSING_FAMILY_STATE_PAIR",
                "scenarios",
                scenario_id,
                "initial_state",
                "S1, S4, and S7 require preferred and alternative offering states",
            )
            return
        if preferred_id == alternative_id:
            issues.add(
                "FAMILY_STATE_PAIR_NOT_DISTINCT",
                "scenarios",
                scenario_id,
                "initial_state",
                "preferred and alternative offering states must differ",
                referenced_id=preferred_id,
            )
        for field, state_id in (
            ("initial_state.preferred_offering_state_id", preferred_id),
            ("initial_state.alternative_offering_state_id", alternative_id),
        ):
            if state_id not in linked_states:
                issues.add(
                    "FAMILY_STATE_OUTSIDE_SCENARIO",
                    "scenarios",
                    scenario_id,
                    field,
                    "family state must be linked by offering_state_ids",
                    referenced_id=state_id,
                )
            _check_usable_state(
                scenario_id, field, state_id, state_by_id, issues
            )
        preferred = state_by_id.get(preferred_id)
        alternative = state_by_id.get(alternative_id)
        if registration is not None and preferred is not None and alternative is not None:
            preferred_conflicts = _state_conflicts_registration(
                real, preferred, registration
            )
            alternative_conflicts = _state_conflicts_registration(
                real, alternative, registration
            )
            if family in {
                ScenarioFamily.S1_NORMAL_RECOVERY.value,
                ScenarioFamily.S4_CONSTRAINT_HEAVY.value,
            }:
                if not preferred_conflicts:
                    issues.add(
                        "PREFERRED_STATE_MUST_CONFLICT",
                        "scenarios",
                        scenario_id,
                        "initial_state.preferred_offering_state_id",
                        "S1/S4 preferred state must conflict with the current timetable",
                        referenced_id=preferred_id,
                    )
                if alternative_conflicts:
                    issues.add(
                        "ALTERNATIVE_STATE_TIMETABLE_CONFLICT",
                        "scenarios",
                        scenario_id,
                        "initial_state.alternative_offering_state_id",
                        "S1/S4 alternative state must be conflict-free",
                        referenced_id=alternative_id,
                    )
            elif preferred_conflicts or alternative_conflicts:
                issues.add(
                    "S7_INITIAL_STATE_NOT_FEASIBLE",
                    "scenarios",
                    scenario_id,
                    "initial_state",
                    "both S7 states must be conflict-free before the event",
                )
        if student is not None and (
            _student_prerequisite_result(course, student)
            is not PrerequisiteResult.PASS
        ):
            issues.add(
                "FAMILY_TARGET_PREREQUISITE_NOT_PASS",
                "scenarios",
                scenario_id,
                "initial_state.target_course",
                "S1/S4/S7 target prerequisite must pass in the student record",
                referenced_id=target_course,
            )
        if registration is not None and (
            registration.workload_aus + course.aus > registration.workload_limit_aus
        ):
            issues.add(
                "FAMILY_TARGET_WORKLOAD_EXCEEDED",
                "scenarios",
                scenario_id,
                "registration_id",
                "S1/S4/S7 target course must fit the workload limit",
                referenced_id=str(registration.registration_id),
            )
        if family == ScenarioFamily.S7_DYNAMIC_FAILURE.value:
            initial_ids = _path_state_ids(
                scenario.ground_truth.valid_initial_paths
            )
            final_ids = _path_state_ids(scenario.ground_truth.valid_final_paths)
            if (
                not initial_ids
                or not final_ids
                or not (final_ids - initial_ids)
            ):
                issues.add(
                    "S7_PATH_STATE_TRANSITION_INVALID",
                    "scenarios",
                    scenario_id,
                    "ground_truth",
                    "S7 requires at least one feasible final state distinct from the initial path",
                )
            if preferred_id not in initial_ids or alternative_id not in final_ids:
                issues.add(
                    "S7_PATH_STATE_PAIR_MISMATCH",
                    "scenarios",
                    scenario_id,
                    "ground_truth",
                    "S7 paths must move from preferred to alternative state",
                )
            event_type = (
                _event_value(scenario.injected_event)
                if scenario.injected_event is not None
                else None
            )
            if (
                event_type
                in {
                    EventType.VACANCY_BECOMES_ZERO.value,
                    EventType.CLASS_BECOMES_UNAVAILABLE.value,
                }
                and preferred_id in final_ids
            ):
                issues.add(
                    "S7_PERSISTENTLY_INVALIDATED_STATE_REUSED",
                    "scenarios",
                    scenario_id,
                    "ground_truth.valid_final_paths",
                    "vacancy and unavailability events forbid the invalidated state as a final path",
                    referenced_id=preferred_id,
                )

    if family == ScenarioFamily.S6_NO_VALID_PATH.value:
        event = scenario.injected_event
        if event is None:
            issues.add(
                "S6_EVENT_REQUIRED",
                "scenarios",
                scenario_id,
                "injected_event",
                "S6 requires a conclusive state or missing-information event",
            )
            return
        event_type = _event_value(event)
        target_type = str(_value(event.target_type))
        expected_target = {
            EventType.REQUIRED_INFORMATION_MISSING.value: (
                StateTargetType.CASE.value,
                str(scenario.case_id),
            ),
            EventType.CLASS_BECOMES_UNAVAILABLE.value: (
                StateTargetType.OFFERING_STATE.value,
                str(event.target_id),
            ),
        }.get(event_type)
        if expected_target is None:
            issues.add(
                "S6_EVENT_TYPE_INVALID",
                "scenarios",
                scenario_id,
                "injected_event.event_type",
                "S6 supports only missing-information or class-unavailable events",
                referenced_id=str(event.event_id),
            )
        else:
            expected_type, expected_id = expected_target
            if target_type != expected_type or str(event.target_id) != expected_id:
                issues.add(
                    "S6_EVENT_TARGET_MISMATCH",
                    "scenarios",
                    scenario_id,
                    "injected_event.target_id",
                    "S6 event target is incoherent with its event type",
                    referenced_id=str(event.target_id),
                )
            if (
                expected_type == StateTargetType.OFFERING_STATE.value
                and str(event.target_id) not in linked_states
            ):
                issues.add(
                    "S6_STATE_OUTSIDE_SCENARIO",
                    "scenarios",
                    scenario_id,
                    "injected_event.target_id",
                    "S6 offering event must target a scenario-linked state",
                    referenced_id=str(event.target_id),
                )


def _check_observable_intake_readiness(
    scenario: Any,
    case: Any | None,
    issues: _Issues,
) -> None:
    """Keep agent-visible intake facts aligned without exposing an oracle."""

    if case is None:
        return
    scenario_id = str(scenario.scenario_id)
    family = str(_value(scenario.family))
    ready = case.submission_ready
    questions = [str(value) for value in case.unresolved_questions]
    if family != ScenarioFamily.S6_NO_VALID_PATH.value:
        if ready is not None or questions:
            issues.add(
                "NON_S6_INTAKE_READINESS_OVERRIDE",
                "exception_cases",
                str(case.case_id),
                "submission_ready",
                "non-S6 cases must retain the neutral intake defaults",
                referenced_id=scenario_id,
            )
        return

    event = scenario.injected_event
    event_type = _event_value(event) if event is not None else None
    if event_type == EventType.REQUIRED_INFORMATION_MISSING.value:
        if ready is not False or questions != ["submission_declaration"]:
            issues.add(
                "S6_MISSING_INTAKE_DECLARATION",
                "exception_cases",
                str(case.case_id),
                "unresolved_questions",
                "missing-information S6 cases must expose the unresolved submission declaration",
                referenced_id=scenario_id,
            )
    elif event_type == EventType.CLASS_BECOMES_UNAVAILABLE.value:
        if ready is not True or questions:
            issues.add(
                "S6_INTAKE_NOT_READY_FOR_NO_PATH",
                "exception_cases",
                str(case.case_id),
                "submission_ready",
                "conclusive no-path S6 cases must expose a complete intake",
                referenced_id=scenario_id,
            )


def _check_scenario_event(
    scenario: Any,
    script: Any | None,
    case_by_id: Mapping[str, Any],
    approval_by_id: Mapping[str, Any],
    state_by_id: Mapping[str, Any],
    issues: _Issues,
) -> None:
    event = scenario.injected_event
    assert event is not None
    scenario_id = str(scenario.scenario_id)
    target_id = str(event.target_id)
    target_type = str(_value(event.target_type))
    if "OFFERING" in target_type:
        target = state_by_id.get(target_id)
    elif "APPROVAL" in target_type:
        target = approval_by_id.get(target_id)
    elif target_type == StateTargetType.CASE.value:
        target = case_by_id.get(target_id)
    else:
        target = None
    if target is None and target_type in {
        StateTargetType.OFFERING_STATE.value,
        StateTargetType.APPROVAL.value,
        StateTargetType.CASE.value,
    }:
        issues.add(
            "UNKNOWN_EVENT_TARGET",
            "scenarios",
            scenario_id,
            "injected_event.target_id",
            "injected event target does not resolve",
            referenced_id=target_id,
        )
    elif event.expected_version is not None and hasattr(target, "version"):
        if int(event.expected_version) != int(target.version):
            issues.add(
                "EVENT_VERSION_MISMATCH",
                "scenarios",
                scenario_id,
                "injected_event.expected_version",
                "event expected version does not match the initial target",
                referenced_id=target_id,
            )
    if target_type == StateTargetType.CASE.value and target is not None:
        if target_id != str(scenario.case_id):
            issues.add(
                "EVENT_CASE_BINDING_MISMATCH",
                "scenarios",
                scenario_id,
                "injected_event.target_id",
                "CASE event target must equal the scenario case",
                referenced_id=target_id,
            )
    if target_type == "APPROVAL" and target is not None:
        expected_status = {
            EventType.APPROVAL_GRANTED.value: ApprovalStatus.APPROVED.value,
            EventType.APPROVAL_REJECTED.value: ApprovalStatus.REJECTED.value,
            EventType.APPROVAL_PENDING.value: ApprovalStatus.PENDING.value,
        }.get(_event_value(event))
        if expected_status is not None and str(_value(target.status)) != expected_status:
            issues.add(
                "APPROVAL_EVENT_STATUS_MISMATCH",
                "scenarios",
                scenario_id,
                "injected_event.event_type",
                "approval record status does not match the injected approval event",
                referenced_id=target_id,
            )
        if str(target.case_id) != str(scenario.case_id):
            issues.add(
                "APPROVAL_EVENT_CASE_MISMATCH",
                "scenarios",
                scenario_id,
                "injected_event.target_id",
                "approval event target belongs to a different case",
                referenced_id=target_id,
            )
    if script is None:
        return
    matching_steps = [
        step
        for step in script.steps
        if step.event is not None and str(step.event.event_id) == str(event.event_id)
    ]
    if len(matching_steps) != 1:
        issues.add(
            "SCENARIO_EVENT_SCRIPT_MISMATCH",
            "scenarios",
            scenario_id,
            "injected_event.event_id",
            "scenario event must occur exactly once in its transaction script",
            referenced_id=str(event.event_id),
        )
        return
    step = matching_steps[0]
    if step.event != event:
        issues.add(
            "SCENARIO_EVENT_PAYLOAD_MISMATCH",
            "scenarios",
            scenario_id,
            "injected_event",
            "scenario event payload differs from the scripted event",
            referenced_id=str(event.event_id),
        )
    _check_event_result(
        event,
        str(_value(step.result_code)),
        str(_value(step.observation)),
        issues,
        "scenarios",
        scenario_id,
        str(step.transaction_id),
    )


def _check_agent_context(scenario: Any, issues: _Issues) -> None:
    scenario_id = str(scenario.scenario_id)
    try:
        context = scenario.to_agent_context()
    except (TypeError, ValueError) as exc:
        issues.add(
            "AGENT_CONTEXT_REJECTED",
            "scenarios",
            scenario_id,
            "initial_state",
            f"scenario cannot produce a safe agent context: {exc}",
        )
        return
    payload = (
        context.model_dump(mode="python")
        if isinstance(context, BaseModel)
        else _as_mapping(context)
    )
    leaked_paths = list(_find_leakage(payload))
    for path in leaked_paths:
        issues.add(
            "AGENT_CONTEXT_LEAKAGE",
            "scenarios",
            scenario_id,
            "initial_state",
            f"agent context exposes evaluator-only key at {path}",
        )


def _find_leakage(value: Any, path: str = "context") -> Iterator[str]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            next_path = f"{path}.{key}"
            if normalized in _LEAKAGE_KEYS:
                yield next_path
            yield from _find_leakage(nested, next_path)
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            yield from _find_leakage(nested, f"{path}.{index}")


def _check_one_per_student(bundle: Stage3DataBundle, issues: _Issues) -> None:
    student_ids = {str(student.student_id) for student in bundle.students}
    for dataset, records, identity in (
        ("degree_audits", bundle.degree_audits, "audit_id"),
        ("current_registrations", bundle.current_registrations, "registration_id"),
    ):
        counts = Counter(str(record.student_id) for record in records)
        for student_id in sorted(student_ids):
            count = counts[student_id]
            if count != 1:
                issues.add(
                    "STUDENT_RECORD_CARDINALITY",
                    dataset,
                    student_id,
                    "student_id",
                    f"student requires exactly one {identity}; found {count}",
                )


def _check_generated_metadata(bundle: Stage3DataBundle, issues: _Issues) -> None:
    manifest = bundle.manifest
    expected_version = str(manifest.generator_version)
    global_seed = int(manifest.global_seed)
    for dataset, records in _bundle_datasets(bundle).items():
        for record in records:
            record_id = _record_id(record)
            if str(record.generator_version) != expected_version:
                issues.add(
                    "GENERATOR_VERSION_MISMATCH",
                    dataset,
                    record_id,
                    "generator_version",
                    "record generator version differs from the manifest",
                )
            _check_generated_seed(
                record,
                dataset,
                record_id,
                global_seed,
                issues,
            )
            if dataset == "transaction_scripts":
                for step in record.steps:
                    if str(step.generator_version) != expected_version:
                        issues.add(
                            "GENERATOR_VERSION_MISMATCH",
                            dataset,
                            record_id,
                            "steps.generator_version",
                            "transaction step generator version differs from manifest",
                            referenced_id=str(step.transaction_id),
                        )
                    _check_generated_seed(
                        step,
                        dataset,
                        str(step.transaction_id),
                        global_seed,
                        issues,
                    )
    periods = {
        str(scope.simulation_period_id) for scope in bundle.simulation_scopes
    }
    declared_periods = {str(value) for value in manifest.simulation_period_ids}
    if periods != declared_periods:
        issues.add(
            "SIMULATION_PERIOD_SET_MISMATCH",
            "generation_manifest",
            str(manifest.manifest_id),
            "simulation_period_ids",
            "manifest simulation periods must exactly match scope periods",
        )


def _check_generated_seed(
    record: Any,
    dataset: str,
    record_id: str,
    global_seed: int,
    issues: _Issues,
) -> None:
    payload = f"{global_seed}|{record.__class__.__name__}|{record_id}"
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    expected = int.from_bytes(digest[:8], "big") % 2_000_000_000
    if int(record.seed) != expected:
        issues.add(
            "GENERATED_SEED_MISMATCH",
            dataset,
            record_id,
            "seed",
            "generated seed does not match the manifest seed and stable entity identity",
        )


def _check_rule_and_assumption_references(
    bundle: Stage3DataBundle,
    real: _RealIndex,
    assumption_by_id: Mapping[str, Any],
    issues: _Issues,
) -> None:
    scope_by_id = _by_id(bundle.simulation_scopes, "simulation_scope_id")
    prototype_by_id = _by_id(bundle.prototype_policies, "policy_id")
    manifest_rules = {str(value) for value in bundle.manifest.source_rule_ids}
    policy_section_ids = {
        str(section.section_id)
        for document in real.policies
        for section in document.sections
    }
    gap_ids = {
        str(gap.gap_id)
        for target in real.coverage.targets
        for gap in target.gaps
    }

    for rule_id in sorted(manifest_rules):
        if rule_id not in real.rule_ids and rule_id not in prototype_by_id:
            # The manifest is allowed to name a compiled deterministic rule, but
            # that rule must use the explicit rule.* namespace rather than look
            # like an unresolvable source record.
            if not rule_id.startswith("rule."):
                issues.add(
                    "UNRESOLVED_MANIFEST_RULE",
                    "generation_manifest",
                    str(bundle.manifest.manifest_id),
                    "source_rule_ids",
                    "manifest rule is neither a real record, a prototype policy, nor a compiled rule",
                    referenced_id=rule_id,
                )

    records = _top_level_records(bundle)
    record_by_id = {_record_id(record): record for _, record in records}
    actual_dependents: dict[str, set[str]] = defaultdict(set)
    known_record_ids = {_record_id(record) for _, record in records}
    for dataset, record in records:
        record_id = _record_id(record)
        for field_path, assumption_ids in _named_id_lists(record, "assumption_ids"):
            for assumption_id in assumption_ids:
                actual_dependents[str(assumption_id)].add(record_id)
                if str(assumption_id) not in assumption_by_id:
                    issues.add(
                        "UNKNOWN_ASSUMPTION",
                        dataset,
                        record_id,
                        field_path,
                        "assumption reference does not resolve",
                        referenced_id=str(assumption_id),
                    )
        for field_path, source_rule_ids in _named_id_lists(record, "source_rule_ids"):
            for source_rule_id in source_rule_ids:
                if str(source_rule_id) not in manifest_rules:
                    issues.add(
                        "UNDECLARED_SOURCE_RULE",
                        dataset,
                        record_id,
                        field_path,
                        "source rule is not frozen by the generation manifest",
                        referenced_id=str(source_rule_id),
                    )
        for field_path, evidence_ids in _named_id_lists(record, "evidence_rule_ids"):
            for rule_id in evidence_ids:
                if str(rule_id) not in manifest_rules:
                    issues.add(
                        "UNDECLARED_EVIDENCE_RULE",
                        dataset,
                        record_id,
                        field_path,
                        "audit evidence rule is not frozen by the manifest",
                        referenced_id=str(rule_id),
                    )

    for assumption in bundle.audit_assumptions:
        assumption_id = str(assumption.assumption_id)
        if str(assumption.simulation_scope_id) not in scope_by_id:
            issues.add(
                "UNKNOWN_SIMULATION_SCOPE",
                "audit_assumptions",
                assumption_id,
                "simulation_scope_id",
                "assumption references an unknown simulation scope",
                referenced_id=str(assumption.simulation_scope_id),
            )
        declared = {str(value) for value in assumption.affected_record_ids}
        unknown = declared - known_record_ids
        for record_id in sorted(unknown):
            issues.add(
                "UNKNOWN_AFFECTED_RECORD",
                "audit_assumptions",
                assumption_id,
                "affected_record_ids",
                "assumption reverse dependency does not resolve",
                referenced_id=record_id,
            )
        for record_id in sorted(declared - unknown):
            affected = record_by_id[record_id]
            affected_scope = getattr(affected, "simulation_scope_id", None)
            if (
                affected_scope is not None
                and str(affected_scope) != str(assumption.simulation_scope_id)
            ):
                issues.add(
                    "ASSUMPTION_SCOPE_MISMATCH",
                    "audit_assumptions",
                    assumption_id,
                    "affected_record_ids",
                    "assumption affects a record in a different simulation scope",
                    referenced_id=record_id,
                )
        actual = actual_dependents.get(assumption_id, set())
        if declared != actual:
            issues.add(
                "ASSUMPTION_REVERSE_LINK_MISMATCH",
                "audit_assumptions",
                assumption_id,
                "affected_record_ids",
                "affected_record_ids must exactly equal records that cite the assumption",
            )
        prototype_id = getattr(assumption, "prototype_policy_id", None)
        if prototype_id is not None and str(prototype_id) not in prototype_by_id:
            issues.add(
                "UNKNOWN_PROTOTYPE_POLICY",
                "audit_assumptions",
                assumption_id,
                "prototype_policy_id",
                "prototype mapping references an unknown explicit simulated policy",
                referenced_id=str(prototype_id),
            )
        elif prototype_id is not None:
            policy = prototype_by_id[str(prototype_id)]
            scope = scope_by_id.get(str(assumption.simulation_scope_id))
            if scope is not None:
                applies = (
                    str(scope.simulation_academic_year)
                    in {str(value) for value in policy.applicable_academic_years}
                    or str(scope.admission_cohort)
                    in {
                        str(value)
                        for value in policy.applicable_admission_cohorts
                    }
                )
                if not applies:
                    issues.add(
                        "PROTOTYPE_POLICY_SCOPE_MISMATCH",
                        "audit_assumptions",
                        assumption_id,
                        "prototype_policy_id",
                        "prototype policy does not apply to the assumption scope",
                        referenced_id=str(prototype_id),
                    )

    manifest_policy_versions = {
        str(key): str(value)
        for key, value in bundle.manifest.prototype_policy_versions.items()
    }
    actual_policy_versions = {
        str(policy.policy_id): str(policy.version)
        for policy in bundle.prototype_policies
    }
    if manifest_policy_versions != actual_policy_versions:
        issues.add(
            "PROTOTYPE_POLICY_VERSION_MISMATCH",
            "generation_manifest",
            str(bundle.manifest.manifest_id),
            "prototype_policy_versions",
            "manifest policy versions must exactly match its inline prototype policies",
        )

    for scope in bundle.simulation_scopes:
        for gap_id in scope.accepted_gap_ids:
            if str(gap_id) not in gap_ids:
                issues.add(
                    "UNKNOWN_COVERAGE_GAP",
                    "simulation_scopes",
                    str(scope.simulation_scope_id),
                    "accepted_gap_ids",
                    "scope accepts a gap absent from the real coverage contract",
                    referenced_id=str(gap_id),
                )
    for case in bundle.exception_cases:
        for section_id in case.policy_section_ids:
            if str(section_id) not in policy_section_ids:
                issues.add(
                    "UNKNOWN_POLICY_SECTION",
                    "exception_cases",
                    str(case.case_id),
                    "policy_section_ids",
                    "case policy reference is not a real public-policy section",
                    referenced_id=str(section_id),
                )
    for approval in bundle.approvals:
        approval_id = str(approval.approval_id)
        for rule_id in approval.basis_rule_ids:
            if str(rule_id) not in manifest_rules:
                issues.add(
                    "UNDECLARED_APPROVAL_RULE",
                    "approvals",
                    approval_id,
                    "basis_rule_ids",
                    "approval basis rule is not frozen by the manifest",
                    referenced_id=str(rule_id),
                )
        basis = str(_value(approval.basis))
        cited_prototypes = {
            str(rule_id)
            for rule_id in approval.basis_rule_ids
            if str(rule_id) in prototype_by_id
        }
        if basis == "SIMULATED_POLICY" and not cited_prototypes:
            issues.add(
                "SIMULATED_APPROVAL_WITHOUT_POLICY",
                "approvals",
                approval_id,
                "basis_rule_ids",
                "SIMULATED_POLICY approval must cite an explicit prototype policy",
            )
        if basis == "VERIFIED_PUBLIC_ROUTE" and cited_prototypes:
            issues.add(
                "REAL_APPROVAL_CITES_SIMULATION",
                "approvals",
                approval_id,
                "basis_rule_ids",
                "verified public approval route cannot cite prototype policy",
            )


def _top_level_records(bundle: Stage3DataBundle) -> list[tuple[str, Any]]:
    return [
        (dataset, record)
        for dataset, records in _bundle_datasets(bundle).items()
        for record in records
    ]


def _named_id_lists(value: Any, target_name: str, path: str = "") -> Iterator[tuple[str, list[Any]]]:
    if isinstance(value, BaseModel):
        for name in value.__class__.model_fields:
            nested = getattr(value, name)
            next_path = f"{path}.{name}" if path else name
            if name == target_name and isinstance(nested, list):
                yield next_path, nested
            else:
                yield from _named_id_lists(nested, target_name, next_path)
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            yield from _named_id_lists(nested, target_name, f"{path}.{index}")
    elif isinstance(value, Mapping):
        for key, nested in value.items():
            yield from _named_id_lists(nested, target_name, f"{path}.{key}")


__all__ = [
    "EXPECTED_APPROVAL_STATUSES",
    "EXPECTED_FAMILY_COUNT",
    "EXPECTED_PROFILE_COUNT",
    "EXPECTED_RECORD_COUNTS",
    "EXPECTED_SPLITS_PER_FAMILY",
    "validate_stage3_data",
]
