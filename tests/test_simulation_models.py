from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from graduation_exception_agent.models import (
    AuditAssumption,
    DegreeAudit,
    ExceptionCase,
    GenerationManifest,
    OfferingState,
    PrototypePolicy,
    Registration,
    RegistrationItem,
    RequirementProgress,
    Scenario,
    SimulationScope,
    Student,
    TransactionResult,
)


@pytest.mark.parametrize(
    ("model_type", "payload_name"),
    [
        (GenerationManifest, "generation_manifest"),
        (SimulationScope, "simulation_scope"),
        (AuditAssumption, "audit_assumption"),
        (PrototypePolicy, "prototype_policy"),
    ],
)
def test_simulation_metadata_round_trips(
    payloads: dict[str, dict[str, object]],
    model_type: type,
    payload_name: str,
) -> None:
    model = model_type.model_validate(payloads[payload_name])
    assert model_type.model_validate(model.model_dump(mode="json")) == model


def test_offering_state_is_shared_by_abstract_period_not_owned_by_scope(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["offering_state"])
    payload["simulation_scope_id"] = "scope.cs.2023"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        OfferingState.model_validate(payload)


def test_runtime_status_is_independent_of_positive_vacancies(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["offering_state"])
    payload.update(
        {
            "runtime_status": "UNAVAILABLE",
            "available": False,
            "unavailable_reason": "The class was administratively withdrawn.",
        }
    )
    state = OfferingState.model_validate(payload)
    assert state.vacancies == 4
    assert not state.available


def test_open_zero_vacancy_state_is_not_available(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["offering_state"])
    payload.update({"vacancies": 0, "available": False})
    assert not OfferingState.model_validate(payload).available


def test_available_flag_must_match_status_and_vacancies(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["offering_state"])
    payload["available"] = False
    with pytest.raises(ValidationError, match="available must equal"):
        OfferingState.model_validate(payload)


def test_student_earned_aus_reconciles_exactly(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["student"])
    payload["earned_aus"] = "4"
    with pytest.raises(ValidationError, match="earned_aus must equal"):
        Student.model_validate(payload)


def test_non_earned_attempt_cannot_award_aus(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["student"])
    payload["completed_courses"][0]["credit_status"] = "NOT_EARNED"
    with pytest.raises(ValidationError, match="only EARNED"):
        Student.model_validate(payload)


def test_requirement_unknown_total_is_indeterminate() -> None:
    progress = RequirementProgress.model_validate(
        {
            "requirement_id": "requirement.unknown",
            "status": "INDETERMINATE",
            "required_aus": None,
            "earned_aus": "0",
            "completed_courses": [],
            "outstanding_courses": [],
            "explanation": "The public requirement total is unavailable.",
            "evidence_rule_ids": ["gap.requirement-total"],
            "assumption_ids": [],
            "limitations": ["No authenticated Degree Audit data is available."],
        }
    )
    assert progress.required_aus is None


def test_indeterminate_audit_requires_limitations(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["audit"])
    payload["audit_outcome"] = "INDETERMINATE"
    payload["total_required_aus"] = None
    payload["limitations"] = []
    with pytest.raises(ValidationError, match="indeterminate audits require"):
        DegreeAudit.model_validate(payload)


def test_registration_item_supports_zero_au() -> None:
    item = RegistrationItem.model_validate(
        {
            "registration_item_id": "registration-item.hw0001",
            "course_code": "HW0001",
            "template_offering_id": "offering.hw0001.ay2026.s1",
            "template_index_id": "10999",
            "offering_state_id": "offering-state.hw0001.10999.v1",
            "expected_state_version": 1,
            "aus": "0",
            "status": "REGISTERED",
            "eligibility": "ELIGIBLE",
            "eligibility_reason": "Eligible in this simulation scope.",
        }
    )
    assert item.aus == 0


def test_registration_attributed_meeting_must_resolve_to_item(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["registration"])
    payload["timetable"] = [
        {
            "meeting_id": "meeting.sim.001",
            "registration_item_id": "registration-item.unknown",
            "course_code": "SC1001",
            "template_offering_id": "offering.sc1001.ay2026.s1",
            "template_index_id": "10001",
            "meeting": {
                "class_type": "LECTURE",
                "day": "MONDAY",
                "start_time": "09:00:00",
                "end_time": "11:00:00",
                "venue": "LT1",
                "teaching_weeks": [1],
            },
        }
    ]
    with pytest.raises(ValidationError, match="must resolve"):
        Registration.model_validate(payload)


@pytest.mark.parametrize(
    ("submission_ready", "unresolved_questions", "message"),
    [
        (False, [], "incomplete submission requires"),
        (True, ["submission_declaration"], "unresolved questions require"),
        (None, ["submission_declaration"], "unresolved questions require"),
    ],
)
def test_exception_case_intake_readiness_is_cross_field_strict(
    payloads: dict[str, dict[str, object]],
    submission_ready: bool | None,
    unresolved_questions: list[str],
    message: str,
) -> None:
    payload = deepcopy(payloads["case"])
    payload["submission_ready"] = submission_ready
    payload["unresolved_questions"] = unresolved_questions

    with pytest.raises(ValidationError, match=message):
        ExceptionCase.model_validate(payload)


def test_transaction_rejects_event_result_mismatch(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["transaction"])
    payload.update(
        {
            "result_code": "CLASS_UNAVAILABLE",
            "observation": "CLASS_UNAVAILABLE",
            "retryable": False,
            "error_code": "CLASS_UNAVAILABLE",
            "event": {
                "event_id": "event.sim.001.vacancy",
                "event_type": "VACANCY_BECOMES_ZERO",
                "target_type": "OFFERING_STATE",
                "target_id": "offering-state.sc1001.10001.v1",
                "expected_version": 1,
                "occurs_at": "2028-08-30T12:04:00+08:00",
            },
            "precondition_state_versions": {
                "offering-state.sc1001.10001.v1": 1
            },
            "mutations": [
                {
                    "mutation_id": "mutation.sim.001.vacancy",
                    "target_type": "OFFERING_STATE",
                    "target_id": "offering-state.sc1001.10001.v1",
                    "expected_version": 1,
                    "resulting_version": 2,
                    "changes": {"vacancies": 0, "available": False},
                }
            ],
        }
    )
    with pytest.raises(ValidationError, match="event type and transaction"):
        TransactionResult.model_validate(payload)


def test_stale_transaction_must_be_retryable(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["transaction"])
    payload.update(
        {
            "result_code": "STALE_STATE",
            "observation": "STALE_STATE",
            "retryable": False,
            "error_code": "STALE_STATE",
        }
    )
    with pytest.raises(ValidationError, match="must be retryable"):
        TransactionResult.model_validate(payload)


@pytest.mark.parametrize(
    "hidden_key",
    [
        "ground_truth",
        "injected_event",
        "transaction_script_id",
        "expected_outcome",
        "valid_final_paths",
    ],
)
def test_scenario_recursively_rejects_evaluator_leakage(
    payloads: dict[str, dict[str, object]],
    hidden_key: str,
) -> None:
    payload = deepcopy(payloads["scenario"])
    payload["initial_state"] = {"nested": [{hidden_key: "secret"}]}
    with pytest.raises(ValidationError, match="evaluator-only"):
        Scenario.model_validate(payload)


def test_agent_context_is_a_defensive_copy(
    payloads: dict[str, dict[str, object]],
) -> None:
    scenario = Scenario.model_validate(payloads["scenario"])
    context = scenario.to_agent_context()
    context.initial_state["request_received"] = False
    assert scenario.initial_state["request_received"] is True


def test_prototype_policy_requires_exact_first_line_banner(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["prototype_policy"])
    payload["body_markdown"] = "# SIMULATED POLICY FOR PROTOTYPE\nBody"
    with pytest.raises(ValidationError, match="exact banner"):
        PrototypePolicy.model_validate(payload)


def test_prototype_policy_requires_simulated_origin(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["prototype_policy"])
    payload["origin"] = "VERIFIED_REAL"
    with pytest.raises(ValidationError, match="SIMULATED_POLICY"):
        PrototypePolicy.model_validate(payload)


def test_prototype_policy_requires_explicit_applicability(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["prototype_policy"])
    payload["applicable_academic_years"] = []
    payload["applicable_admission_cohorts"] = []
    with pytest.raises(ValidationError, match="applicability"):
        PrototypePolicy.model_validate(payload)


def test_manifest_rejects_non_sha256_input_hash(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["generation_manifest"])
    payload["real_data_hashes"]["courses"] = "not-a-hash"
    with pytest.raises(ValidationError, match="SHA-256"):
        GenerationManifest.model_validate(payload)
