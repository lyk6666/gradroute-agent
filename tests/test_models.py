from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from graduation_exception_agent.models import (
    Approval,
    Course,
    CourseOffering,
    Curriculum,
    DegreeAudit,
    EventType,
    ExceptionCase,
    Programme,
    Registration,
    Scenario,
    SourceProvenance,
    Student,
    TransactionResult,
    TransactionScript,
)


@pytest.mark.parametrize(
    ("model_type", "payload_name"),
    [
        (SourceProvenance, "source"),
        (Programme, "programme"),
        (Curriculum, "curriculum"),
        (Course, "course"),
        (CourseOffering, "offering"),
        (Student, "student"),
        (DegreeAudit, "audit"),
        (Registration, "registration"),
        (ExceptionCase, "case"),
        (Approval, "approval"),
        (TransactionResult, "transaction"),
        (TransactionScript, "transaction_script"),
        (Scenario, "scenario"),
    ],
)
def test_top_level_models_validate_and_round_trip(
    payloads: dict[str, dict[str, object]],
    model_type: type,
    payload_name: str,
) -> None:
    instance = model_type.model_validate(payloads[payload_name])
    dumped = instance.model_dump(mode="json")
    assert model_type.model_validate(dumped) == instance


def test_unknown_offering_values_remain_unknown(
    payloads: dict[str, dict[str, object]],
) -> None:
    offering = CourseOffering.model_validate(payloads["offering"])
    assert offering.indexes[0].capacity is None
    assert offering.indexes[0].vacancies is None


def test_unknown_fields_are_rejected(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["student"])
    payload["student_name"] = "This field must never be accepted"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Student.model_validate(payload)


def test_student_identifier_must_be_explicitly_synthetic(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["student"])
    payload["student_id"] = "U1234567A"
    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        Student.model_validate(payload)


def test_course_rejects_self_exclusion(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["course"])
    payload["exclusions"] = [payload["code"]]
    with pytest.raises(ValidationError, match="cannot exclude itself"):
        Course.model_validate(payload)


def test_curriculum_rejects_duplicate_requirement_ids(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["curriculum"])
    payload["requirements"].append(deepcopy(payload["requirements"][0]))
    with pytest.raises(ValidationError, match="requirement_ids"):
        Curriculum.model_validate(payload)


def test_registration_workload_must_match_items(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["registration"])
    payload["workload_aus"] = "6"
    with pytest.raises(ValidationError, match="workload_aus"):
        Registration.model_validate(payload)


def test_graduation_ready_must_match_requirement_results(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["audit"])
    payload["graduation_ready"] = False
    with pytest.raises(ValidationError, match="graduation_ready"):
        DegreeAudit.model_validate(payload)


def test_rejected_approval_requires_reason_and_decision_time(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["approval"])
    payload["status"] = "REJECTED"
    with pytest.raises(ValidationError, match="decision_reason"):
        Approval.model_validate(payload)


def test_pending_approval_rejects_final_decision(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["approval"])
    payload["decision_reason"] = "Not yet a valid final decision"
    with pytest.raises(ValidationError, match="pending approval"):
        Approval.model_validate(payload)


def test_transaction_script_supports_ordered_multi_step_recovery(
    payloads: dict[str, dict[str, object]],
) -> None:
    failure = deepcopy(payloads["transaction"])
    failure.update(
        {
            "transaction_id": "transaction.sim.001.failure",
            "result_code": "MODULE_FULL",
            "observation": "MODULE_FULL",
            "retryable": False,
            "error_code": "MODULE_FULL",
            "state_changes": {"vacancies": 0},
        }
    )
    success = deepcopy(payloads["transaction"])
    success["transaction_id"] = "transaction.sim.001.recovery"
    success["attempt_number"] = 2
    payload = deepcopy(payloads["transaction_script"])
    payload["steps"] = [failure, success]
    assert len(TransactionScript.model_validate(payload).steps) == 2


def test_transaction_script_rejects_unordered_attempts(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["transaction_script"])
    payload["steps"][0]["attempt_number"] = 2
    with pytest.raises(ValidationError, match="ordered consecutively"):
        TransactionScript.model_validate(payload)


def test_event_enum_contains_exactly_the_eight_specified_events() -> None:
    assert {event.value for event in EventType} == {
        "VACANCY_BECOMES_ZERO",
        "CLASS_BECOMES_UNAVAILABLE",
        "APPROVAL_GRANTED",
        "APPROVAL_REJECTED",
        "APPROVAL_PENDING",
        "TEMPORARY_TRANSACTION_FAILURE",
        "STATE_CHANGED_BEFORE_COMMIT",
        "REQUIRED_INFORMATION_MISSING",
    }


def test_normal_scenario_allows_no_injected_event(
    payloads: dict[str, dict[str, object]],
) -> None:
    scenario = Scenario.model_validate(payloads["scenario"])
    assert scenario.injected_event is None


def test_dynamic_failure_scenario_requires_an_event(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["scenario"])
    payload["family"] = "S7"
    with pytest.raises(ValidationError, match="require an injected event"):
        Scenario.model_validate(payload)


def test_ground_truth_is_excluded_from_agent_context(
    payloads: dict[str, dict[str, object]],
) -> None:
    scenario = Scenario.model_validate(payloads["scenario"])
    safe_payload = scenario.to_agent_context().model_dump(mode="json")
    assert "ground_truth" not in safe_payload
    assert "injected_event" not in safe_payload
    assert "expected_outcome" not in str(safe_payload)


def test_scenario_rejects_path_overlap(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["scenario"])
    path = deepcopy(payload["ground_truth"]["valid_initial_paths"][0])
    payload["ground_truth"]["invalid_paths"] = [path]
    with pytest.raises(ValidationError, match="path_ids"):
        Scenario.model_validate(payload)


def test_verified_source_requires_timezone_aware_retrieval(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["source"])
    payload["retrieved_at"] = "2026-08-30T12:00:00"
    with pytest.raises(ValidationError, match="timezone"):
        SourceProvenance.model_validate(payload)


def test_verified_source_requires_url_and_retrieval_time(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["source"])
    payload["source_url"] = None
    with pytest.raises(ValidationError, match="source_url"):
        SourceProvenance.model_validate(payload)


def test_simulated_policy_is_explicitly_distinct_from_verified_source(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["source"])
    payload.update(
        {
            "source_id": "source.policy.prototype",
            "source_type": "policy",
            "source_url": None,
            "retrieved_at": None,
            "checked_at": None,
            "origin": "SIMULATED_POLICY",
            "access_status": None,
            "classification": None,
            "retrieval_method": None,
            "content_sha256": None,
            "checksum_scope": None,
        }
    )
    source = SourceProvenance.model_validate(payload)
    assert source.origin.value == "SIMULATED_POLICY"


def test_generated_models_require_nonempty_source_rules(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["student"])
    payload["source_rule_ids"] = []
    with pytest.raises(ValidationError, match="at least 1 item"):
        Student.model_validate(payload)


def test_invalid_scenario_enum_is_rejected(
    payloads: dict[str, dict[str, object]],
) -> None:
    payload = deepcopy(payloads["scenario"])
    payload["family"] = "S8"
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)
