from __future__ import annotations

from collections import Counter
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterator

import pytest

from graduation_exception_agent.data.real import RealDataRepository
from graduation_exception_agent.data.simulated import (
    SimulatedDataRepository,
    validate_stage3_data,
)
from graduation_exception_agent.models import (
    ApprovalBasis,
    ApprovalStatus,
    EventType,
    ExceptionCaseType,
    ScenarioFamily,
    ScenarioSplit,
    TerminalProfile,
    TransactionCode,
)


DATA_ROOT = Path(__file__).resolve().parents[1] / "data"

EXPECTED_RECORD_COUNTS = {
    "simulation_scopes": 17,
    "audit_assumptions": 17,
    "prototype_policies": 3,
    "offering_states": 2108,
    "students": 240,
    "degree_audits": 240,
    "current_registrations": 240,
    "exception_cases": 140,
    "approvals": 60,
    "transaction_scripts": 140,
    "scenarios": 140,
}

EVALUATOR_ONLY_KEYS = {
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


@pytest.fixture(scope="module")
def real_repository() -> RealDataRepository:
    return RealDataRepository.from_directory(DATA_ROOT / "real")


@pytest.fixture(scope="module")
def simulated_repository(
    real_repository: RealDataRepository,
) -> SimulatedDataRepository:
    return SimulatedDataRepository.from_directory(
        DATA_ROOT / "simulated",
        real_repository=real_repository,
    )


def _nested_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key).strip().lower()
            yield from _nested_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _nested_keys(nested)


def _path_attachment(path_id: str | None) -> str | None:
    if path_id is None:
        return None
    lowered = path_id.lower()
    if ".pi" in lowered or "-pi" in lowered:
        return "pi"
    if ".pa" in lowered or "-pa" in lowered:
        return "pa"
    return None


def test_checked_in_package_reloads_without_stage3_consistency_issues(
    real_repository: RealDataRepository,
    simulated_repository: SimulatedDataRepository,
) -> None:
    # Stage 2 intentionally retains warning-level catalogue gaps, but neither
    # repository may have an integrity error and Stage 3 must be fully clean.
    assert not any(
        issue.severity.value == "ERROR"
        for issue in real_repository.consistency_issues
    )
    assert simulated_repository.consistency_issues == ()


def test_manifest_counts_exactly_match_the_checked_in_package(
    simulated_repository: SimulatedDataRepository,
) -> None:
    bundle = simulated_repository.bundle
    actual_counts = {
        "simulation_scopes": len(bundle.simulation_scopes),
        "audit_assumptions": len(bundle.audit_assumptions),
        "prototype_policies": len(bundle.prototype_policies),
        "offering_states": len(bundle.offering_states),
        "students": len(bundle.students),
        "degree_audits": len(bundle.degree_audits),
        "current_registrations": len(bundle.current_registrations),
        "exception_cases": len(bundle.exception_cases),
        "approvals": len(bundle.approvals),
        "transaction_scripts": len(bundle.transaction_scripts),
        "scenarios": len(bundle.scenarios),
    }

    assert bundle.manifest.record_counts == EXPECTED_RECORD_COUNTS
    assert actual_counts == EXPECTED_RECORD_COUNTS


def test_profile_family_split_and_approval_distributions_are_exact(
    simulated_repository: SimulatedDataRepository,
) -> None:
    bundle = simulated_repository.bundle

    assert Counter(student.terminal_profile for student in bundle.students) == {
        TerminalProfile.REQUIREMENT_OUTSTANDING: 60,
        TerminalProfile.INDEX_TIMETABLE_WORKLOAD_CONSTRAINED: 60,
        TerminalProfile.PREREQUISITE_OR_EVIDENCE_DEPENDENT: 60,
        TerminalProfile.NO_VERIFIED_RESOLUTION: 60,
    }
    assert Counter(scenario.family for scenario in bundle.scenarios) == {
        family: 20 for family in ScenarioFamily
    }
    assert Counter(scenario.split for scenario in bundle.scenarios) == {
        ScenarioSplit.DEVELOPMENT: 28,
        ScenarioSplit.DEMO: 7,
        ScenarioSplit.EVALUATION: 105,
    }
    assert Counter(approval.status for approval in bundle.approvals) == {
        ApprovalStatus.APPROVED: 24,
        ApprovalStatus.REJECTED: 24,
        ApprovalStatus.PENDING: 12,
    }


def test_zero_au_registration_and_s2_demo_are_grounded(
    simulated_repository: SimulatedDataRepository,
) -> None:
    bundle = simulated_repository.bundle
    hw0001_registrations = [
        (registration, item)
        for registration in bundle.current_registrations
        for item in registration.registered_courses
        if str(item.course_code) == "HW0001"
    ]

    assert len(hw0001_registrations) == 1
    registration, hw0001 = hw0001_registrations[0]
    assert hw0001.aus == Decimal("0")
    assert registration.workload_aus == sum(
        (item.aus for item in registration.registered_courses),
        Decimal("0"),
    )

    scenario = next(
        item for item in bundle.scenarios if str(item.scenario_id) == "S2-M01"
    )
    case = next(
        item for item in bundle.exception_cases if item.case_id == scenario.case_id
    )
    approval = next(
        item for item in bundle.approvals if item.case_id == scenario.case_id
    )

    assert scenario.family is ScenarioFamily.S2_PREREQUISITE_EXCEPTION
    assert scenario.split is ScenarioSplit.DEMO
    assert scenario.initial_state["target_course"] == "SC4002"
    assert "course.SC4002" in scenario.source_rule_ids
    assert case.policy_section_ids == [
        "policy.exception.exchange.pending_transfer"
    ]
    assert {
        str(document.document_type)
        for document in case.supporting_documents
        if document.provided
    } == {
        "UNOFFICIAL_TRANSCRIPT",
        "REQUESTED_COURSE_MAPPING",
        "PREREQUISITE_COURSE_MAPPING",
        "FOREIGN_COURSE_MAPPING",
    }
    assert approval.basis is ApprovalBasis.VERIFIED_PUBLIC_ROUTE
    assert approval.status is ApprovalStatus.APPROVED
    assert scenario.injected_event is not None
    assert scenario.injected_event.event_type is EventType.APPROVAL_GRANTED


def test_audit_ledgers_and_selected_paths_reconcile(
    real_repository: RealDataRepository,
    simulated_repository: SimulatedDataRepository,
) -> None:
    bundle = simulated_repository.bundle
    students = {str(student.student_id): student for student in bundle.students}
    curricula = {
        str(curriculum.curriculum_id): curriculum
        for curriculum in real_repository.curricula
    }

    for audit in bundle.degree_audits:
        student = students[str(audit.student_id)]
        assert audit.total_earned_aus == student.earned_aus
        assert sum(
            (result.earned_aus for result in audit.requirement_results),
            Decimal("0"),
        ) == audit.total_earned_aus
        if audit.total_required_aus is not None and all(
            result.required_aus is not None
            for result in audit.requirement_results
        ):
            assert sum(
                (
                    result.required_aus
                    for result in audit.requirement_results
                    if result.required_aus is not None
                ),
                Decimal("0"),
            ) == audit.total_required_aus

        assert audit.graduation_path_id == student.graduation_path_id
        assert audit.study_plan_path_label == student.study_plan_path_label

    for record in (*bundle.students, *bundle.degree_audits):
        curriculum = curricula[str(record.curriculum_id)]
        known_paths = {str(path.path_id) for path in curriculum.graduation_paths}
        known_labels = {
            str(item.path_label)
            for item in curriculum.study_plan
            if item.path_label is not None
        }
        selected_path = (
            str(record.graduation_path_id)
            if record.graduation_path_id is not None
            else None
        )
        selected_label = (
            str(record.study_plan_path_label)
            if record.study_plan_path_label is not None
            else None
        )

        if known_paths:
            assert selected_path in known_paths
        else:
            assert selected_path is None
        if known_labels:
            assert selected_label in known_labels
        else:
            assert selected_label is None

        attachment = _path_attachment(selected_path)
        if attachment is not None:
            assert selected_label is not None
            assert selected_label.lower().startswith(attachment)


def test_s5_uses_integrated_or_overlay_curricula(
    real_repository: RealDataRepository,
    simulated_repository: SimulatedDataRepository,
) -> None:
    curricula = {
        str(item.curriculum_id): item for item in real_repository.curricula
    }
    primary_programmes = {"AISC", "CE", "CSC", "DSAI"}

    for scenario in simulated_repository.bundle.scenarios:
        if scenario.family is not ScenarioFamily.S5_CROSS_PROGRAMME:
            continue
        curriculum = curricula[str(scenario.curriculum_id)]
        assert not (
            str(curriculum.configuration_kind) == "BASE"
            and str(curriculum.programme) in primary_programmes
        )


def test_each_failed_nonterminal_transaction_is_retryable(
    simulated_repository: SimulatedDataRepository,
) -> None:
    successful = {
        TransactionCode.SUCCESS,
        TransactionCode.EXCEPTION_SUBMISSION_SUCCESS,
    }
    for script in simulated_repository.bundle.transaction_scripts:
        for step in script.steps[:-1]:
            if step.result_code not in successful:
                assert step.retryable


def test_every_agent_context_excludes_evaluator_only_data(
    simulated_repository: SimulatedDataRepository,
) -> None:
    for scenario in simulated_repository.bundle.scenarios:
        context = simulated_repository.to_agent_context(str(scenario.scenario_id))
        payload = context.model_dump(mode="json")
        keys = set(_nested_keys(payload))

        assert keys.isdisjoint(EVALUATOR_ONLY_KEYS)
        assert scenario.transaction_script_id not in context.initial_state_refs
        assert "ground_truth" not in payload
        assert "injected_event" not in payload


def test_student_getter_excludes_evaluator_only_profile(
    simulated_repository: SimulatedDataRepository,
) -> None:
    evaluator_student = simulated_repository.bundle.students[0]
    observable_student = simulated_repository.get_student(
        str(evaluator_student.student_id)
    )

    assert "terminal_profile" not in observable_student.model_dump(mode="json")
    assert observable_student.student_id == evaluator_student.student_id


def test_observable_case_artifacts_do_not_encode_family_or_split(
    simulated_repository: SimulatedDataRepository,
) -> None:
    family_or_split = re.compile(
        r"(?:^|[.\-_])(?:s[1-7]|d\d{2}|m\d{2}|e\d{2})(?:$|[.\-_])",
        re.IGNORECASE,
    )
    bundle = simulated_repository.bundle
    cases = {str(case.case_id): case for case in bundle.exception_cases}
    approvals = {str(item.case_id): item for item in bundle.approvals}

    for scenario in bundle.scenarios:
        context = simulated_repository.to_agent_context(str(scenario.scenario_id))
        case = cases[str(scenario.case_id)]
        observable_ids = [
            str(context.context_id),
            str(case.case_id),
            *(str(item.document_id) for item in case.supporting_documents),
            *(str(item.evidence_id) for item in case.evidence),
        ]
        approval = approvals.get(str(case.case_id))
        if approval is not None:
            observable_ids.append(str(approval.approval_id))

        assert all(family_or_split.search(value) is None for value in observable_ids)
        assert family_or_split.search(str(case.reason)) is None


def test_exception_cases_publish_independent_observable_intake_readiness(
    simulated_repository: SimulatedDataRepository,
) -> None:
    cases = simulated_repository.bundle.exception_cases
    s6_cases = [
        case
        for case in cases
        if case.problem_type is ExceptionCaseType.COURSE_UNAVAILABLE
    ]
    non_s6_cases = [case for case in cases if case not in s6_cases]

    assert len(s6_cases) == 20
    assert Counter(
        (case.submission_ready, tuple(case.unresolved_questions))
        for case in s6_cases
    ) == {
        (False, ("submission_declaration",)): 10,
        (True, ()): 10,
    }
    assert len(non_s6_cases) == 120
    assert all(
        case.submission_ready is None and case.unresolved_questions == []
        for case in non_s6_cases
    )


def test_validator_rejects_s6_case_readiness_that_disagrees_with_its_event(
    real_repository: RealDataRepository,
    simulated_repository: SimulatedDataRepository,
) -> None:
    bundle = simulated_repository.bundle
    scenario = next(
        item
        for item in bundle.scenarios
        if item.family is ScenarioFamily.S6_NO_VALID_PATH
        and item.injected_event is not None
        and item.injected_event.event_type
        is EventType.REQUIRED_INFORMATION_MISSING
    )
    case = next(
        item for item in bundle.exception_cases if item.case_id == scenario.case_id
    )
    bad_case = case.model_copy(
        update={"submission_ready": True, "unresolved_questions": []}
    )
    changed = replace(
        bundle,
        exception_cases=tuple(
            bad_case if item.case_id == case.case_id else item
            for item in bundle.exception_cases
        ),
    )

    issues = validate_stage3_data(
        real_repository,
        changed,
        real_directory=DATA_ROOT / "real",
    )

    assert any(issue.code == "S6_MISSING_INTAKE_DECLARATION" for issue in issues)


def test_checked_in_stage3_data_matches_the_deterministic_generator() -> None:
    repository_root = DATA_ROOT.parent
    completed = subprocess.run(
        [sys.executable, "scripts/build_simulated_data.py", "--check"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_validator_rejects_pi_pa_path_label_mismatch(
    real_repository: RealDataRepository,
    simulated_repository: SimulatedDataRepository,
) -> None:
    bundle = simulated_repository.bundle
    student = next(
        item
        for item in bundle.students
        if _path_attachment(str(item.graduation_path_id)) == "pi"
        and item.study_plan_path_label is not None
    )
    curriculum = real_repository.get_curriculum(str(student.curriculum_id))
    pa_label = next(
        str(item.path_label)
        for item in curriculum.study_plan
        if item.path_label is not None
        and str(item.path_label).lower().startswith("pa")
    )
    bad_student = student.model_copy(update={"study_plan_path_label": pa_label})
    changed = replace(
        bundle,
        students=tuple(
            bad_student if item.student_id == student.student_id else item
            for item in bundle.students
        ),
    )

    issues = validate_stage3_data(
        real_repository,
        changed,
        real_directory=DATA_ROOT / "real",
    )

    assert any(issue.code == "PATH_LABEL_MISMATCH" for issue in issues)
