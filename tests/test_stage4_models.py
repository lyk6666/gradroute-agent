from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from graduation_exception_agent.models import (
    ActionPostcondition,
    ActionReceipt,
    ClarificationImpact,
    ClarificationResume,
    ExecutionContract,
    ExecutionEdge,
    GoalEvaluation,
    GoalKind,
    GoalOperator,
    GoalPredicate,
    HumanRoute,
    PredicateEvaluation,
    ToolCallContext,
    ToolError,
    ToolErrorCode,
    ToolObservation,
    ToolProvenance,
    ToolResponse,
    ToolStatus,
    VerifierDecision,
    VerifierDecisionCode,
    VerifierPhase,
    VersionExpectation,
)


TIMESTAMP = "2028-08-30T12:00:00+08:00"


def _registration_predicate(predicate_id: str = "predicate.registered") -> GoalPredicate:
    return GoalPredicate(
        predicate_id=predicate_id,
        goal_kind=GoalKind.COURSE_REGISTERED,
        target_type="REGISTRATION",
        target_ids=["registration.sim.001"],
        field_path="items.course_code",
        operator=GoalOperator.CONTAINS,
        expected_value="SC4001",
        description="The target registration contains SC4001.",
    )


def _resolved_contract_payload() -> dict[str, object]:
    predicate = _registration_predicate()
    postcondition = _registration_predicate("postcondition.registered")
    return {
        "contract_id": "execution-contract.scenario.s1-001",
        "scenario_id": "scenario.s1-001",
        "case_id": "case.s1-001",
        "required_edges": [
            {"source": "action_gate", "destination": "transaction"},
            {"source": "transaction", "destination": "observation"},
        ],
        "forbidden_edges": [
            {"source": "action_gate", "destination": "final_response"}
        ],
        "pre_action_decisions": ["VALID"],
        "post_action_decisions": ["DONE"],
        "expected_actions": ["SUBMIT_REGISTRATION"],
        "required_observations": ["TRANSACTION_SUCCESS"],
        "goal_kind": "COURSE_REGISTERED",
        "goal_predicates": [predicate.model_dump(mode="json")],
        "postconditions": [postcondition.model_dump(mode="json")],
        "expected_outcome": "RESOLVED",
        "memory_update_allowed": True,
        "loop_expectations": {
            "replans": 0,
            "tool_retries": 0,
            "total_steps": 10,
        },
    }


def test_tool_response_is_strict_provenanced_and_round_trips() -> None:
    response = ToolResponse(
        request_id="request.read.001",
        status=ToolStatus.SUCCESS,
        data={"course_code": "SC4001", "available": True},
        provenance=[
            ToolProvenance(
                source_ids=["source.course.catalogue"],
                rule_ids=["rule.course.sc4001"],
                origin="VERIFIED_REAL",
                completeness="COMPLETE",
            )
        ],
        entity_versions={"offering-state.sc4001.10001": 1},
    )

    assert ToolResponse.model_validate(response.model_dump(mode="json")) == response
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ToolResponse.model_validate(
            {**response.model_dump(mode="python"), "hidden_script": "never"}
        )


def test_tool_provenance_requires_a_real_traceable_reference() -> None:
    provenance = ToolProvenance(
        rule_ids=["rule.simulated.overload"],
        origin="SIMULATED_POLICY",
        completeness="COMPLETE",
    )
    assert provenance.source_ids == []

    with pytest.raises(ValidationError, match="requires a source, rule"):
        ToolProvenance(
            origin="UNKNOWN",
            completeness="UNKNOWN",
        )


def test_failed_tool_response_requires_a_normalized_error() -> None:
    with pytest.raises(ValidationError, match="require a normalized error"):
        ToolResponse(
            request_id="request.read.002",
            status=ToolStatus.FAILURE,
        )

    response = ToolResponse(
        request_id="request.read.002",
        status=ToolStatus.FAILURE,
        error=ToolError(
            code=ToolErrorCode.NOT_FOUND,
            message="The requested course was not found.",
        ),
    )
    assert response.error is not None
    assert response.error.code is ToolErrorCode.NOT_FOUND


def test_tool_call_context_rejects_duplicate_version_targets() -> None:
    expectation = VersionExpectation(
        target_type="OFFERING_STATE",
        target_id="offering-state.sc4001.10001",
        expected_version=1,
    )
    with pytest.raises(ValidationError, match="must not repeat a target"):
        ToolCallContext(
            session_id="session.s1-001",
            request_id="request.write.001",
            case_id="case.s1-001",
            requested_at=TIMESTAMP,
            idempotency_key="idempotency.write.001",
            expected_versions=[expectation, expectation],
        )


def test_action_receipt_proves_a_final_goal_effect() -> None:
    receipt = ActionReceipt(
        receipt_id="receipt.s1-001.1",
        transaction_id="transaction.s1-001.1",
        session_id="session.s1-001",
        request_id="request.s1-001.1",
        idempotency_key="idempotency.s1-001.1",
        case_id="case.s1-001",
        action="SUBMIT_REGISTRATION",
        status="SUCCESS",
        result_code="SUCCESS",
        observation=ToolObservation(
            observation_id="observation.s1-001.1",
            code="TRANSACTION_SUCCESS",
            message="Registration was committed.",
            retryable=False,
            occurred_at=TIMESTAMP,
            state_versions={"registration.sim.001": 2},
        ),
        message="Registration was committed.",
        mutation_ids=["mutation.registration.s1-001"],
        entity_versions={"registration.sim.001": 2},
        postconditions=[
            ActionPostcondition(
                postcondition_id="postcondition.registered",
                target_type="REGISTRATION",
                target_id="registration.sim.001",
                field_path="items.course_code",
                expected_value="SC4001",
                observed_value="SC4001",
                satisfied=True,
            )
        ],
        committed=True,
        intermediate=False,
        retryable=False,
        goal_effect=True,
        session_revision=2,
        committed_at=TIMESTAMP,
    )

    assert ActionReceipt.model_validate(receipt.model_dump(mode="json")) == receipt
    assert receipt.goal_effect
    assert receipt.committed


def test_approval_request_receipt_is_always_intermediate() -> None:
    payload: dict[str, object] = {
        "receipt_id": "receipt.s2-001.1",
        "transaction_id": "transaction.s2-001.1",
        "session_id": "session.s2-001",
        "request_id": "request.s2-001.1",
        "idempotency_key": "idempotency.s2-001.1",
        "case_id": "case.s2-001",
        "action": "REQUEST_APPROVAL",
        "status": "SUCCESS",
        "result_code": "SUCCESS",
        "observation": {
            "observation_id": "observation.s2-001.1",
            "code": "TRANSACTION_SUCCESS",
            "message": "Approval was granted.",
            "retryable": False,
            "occurred_at": TIMESTAMP,
            "state_versions": {"approval.s2-001": 2},
        },
        "message": "Approval was granted.",
        "entity_versions": {"approval.s2-001": 2},
        "committed": True,
        "intermediate": True,
        "retryable": False,
        "goal_effect": False,
        "session_revision": 2,
        "committed_at": TIMESTAMP,
    }
    receipt = ActionReceipt.model_validate(payload)
    assert receipt.intermediate
    assert not receipt.goal_effect

    invalid = deepcopy(payload)
    invalid["intermediate"] = False
    with pytest.raises(ValidationError, match="marked intermediate"):
        ActionReceipt.model_validate(invalid)


def test_verifier_decisions_are_phase_specific() -> None:
    decision = VerifierDecision(
        decision_id="decision.pre.001",
        phase=VerifierPhase.PRE_ACTION,
        decision=VerifierDecisionCode.VALID,
        reason="All deterministic constraints passed.",
        checked_predicate_ids=["predicate.registered"],
        decided_at=TIMESTAMP,
    )
    assert decision.decision is VerifierDecisionCode.VALID

    with pytest.raises(ValidationError, match="not valid during PRE_ACTION"):
        VerifierDecision(
            decision_id="decision.pre.invalid",
            phase="PRE_ACTION",
            decision="DONE",
            reason="Wrong phase.",
            decided_at=TIMESTAMP,
        )


def test_goal_evaluation_requires_every_required_predicate() -> None:
    with pytest.raises(ValidationError, match="every required predicate"):
        GoalEvaluation(
            evaluation_id="goal-evaluation.s1-001",
            goal_kind="COURSE_REGISTERED",
            complete=True,
            predicate_results=[
                PredicateEvaluation(
                    predicate_id="predicate.registered",
                    required=True,
                    satisfied=False,
                    observed_value=[],
                    reason="The course is not present.",
                )
            ],
            evaluated_at=TIMESTAMP,
        )


def test_execution_contract_is_evaluator_only_and_round_trips() -> None:
    contract = ExecutionContract.model_validate(_resolved_contract_payload())
    assert contract.evaluator_only is True
    assert contract.post_action_decision is VerifierDecisionCode.DONE
    assert ExecutionContract.model_validate(contract.model_dump(mode="json")) == contract

    payload = _resolved_contract_payload()
    payload["evaluator_only"] = False
    with pytest.raises(ValidationError):
        ExecutionContract.model_validate(payload)


def test_execution_contract_keeps_approval_and_admin_review_distinct() -> None:
    predicate = GoalPredicate(
        predicate_id="predicate.admin-handoff",
        goal_kind="ADMIN_HANDOFF_CREATED",
        target_type="CASE",
        target_ids=["case.s6-001"],
        field_path="state",
        operator="EQUALS",
        expected_value="ESCALATED",
        description="A bounded administrative handoff exists.",
    )
    contract = ExecutionContract(
        contract_id="execution-contract.scenario.s6-001",
        scenario_id="scenario.s6-001",
        case_id="case.s6-001",
        pre_action_decisions=["ESCALATE"],
        human_route=HumanRoute.ADMIN_REVIEW,
        admin_review_expected=True,
        goal_kind="ADMIN_HANDOFF_CREATED",
        goal_predicates=[predicate],
        expected_outcome="ESCALATED",
    )
    assert contract.human_route is HumanRoute.ADMIN_REVIEW
    assert not contract.approval_required

    payload = contract.model_dump(mode="python")
    payload["approval_required"] = True
    payload["expected_approval_status"] = "APPROVED"
    with pytest.raises(ValidationError, match="APPROVAL route"):
        ExecutionContract.model_validate(payload)


def test_approval_contract_requires_basis_and_basis_rules() -> None:
    payload = _resolved_contract_payload()
    payload.update(
        {
            "human_route": "APPROVAL",
            "approval_required": True,
            "expected_approval_status": "APPROVED",
        }
    )
    with pytest.raises(ValidationError, match="approval_basis"):
        ExecutionContract.model_validate(payload)

    payload.update(
        {
            "approval_basis": "SIMULATED_POLICY",
            "approval_basis_rule_ids": ["rule.simulated.approval"],
        }
    )
    contract = ExecutionContract.model_validate(payload)
    assert contract.approval_basis is not None


def test_clarification_impact_determines_resume_node() -> None:
    predicate = GoalPredicate(
        predicate_id="predicate.information-requested",
        goal_kind="INFORMATION_REQUESTED",
        target_type="CASE",
        target_ids=["case.s3-001"],
        field_path="clarification.requested",
        operator="EQUALS",
        expected_value=True,
        description="A material missing fact was requested.",
    )
    contract = ExecutionContract(
        contract_id="execution-contract.scenario.s3-001",
        scenario_id="scenario.s3-001",
        case_id="case.s3-001",
        pre_action_decisions=["CLARIFY"],
        clarification_impact=ClarificationImpact.SMALL_CHANGE,
        clarification_resume=ClarificationResume.PRE_ACTION_VERIFIER,
        goal_kind="INFORMATION_REQUESTED",
        goal_predicates=[predicate],
        expected_outcome="CLARIFICATION_REQUIRED",
    )
    assert contract.clarification_resume is ClarificationResume.PRE_ACTION_VERIFIER

    payload = contract.model_dump(mode="python")
    payload["clarification_resume"] = "PLANNER"
    with pytest.raises(ValidationError, match="must resume"):
        ExecutionContract.model_validate(payload)


def test_execution_contract_edges_cannot_be_both_required_and_forbidden() -> None:
    payload = _resolved_contract_payload()
    payload["forbidden_edges"] = [
        ExecutionEdge(
            source="action_gate",
            destination="transaction",
        ).model_dump(mode="json")
    ]
    with pytest.raises(ValidationError, match="must be disjoint"):
        ExecutionContract.model_validate(payload)


def test_execution_contract_supports_multi_attempt_verifier_sequences() -> None:
    payload = _resolved_contract_payload()
    payload["pre_action_decisions"] = ["VALID", "VALID"]
    payload["post_action_decisions"] = ["CONTINUE_FAILURE", "DONE"]
    contract = ExecutionContract.model_validate(payload)

    assert contract.pre_action_decisions == [
        VerifierDecisionCode.VALID,
        VerifierDecisionCode.VALID,
    ]
    assert contract.post_action_decision is VerifierDecisionCode.DONE

    retry_decision = VerifierDecision(
        decision_id="decision.post.continue-failure",
        phase="POST_ACTION",
        decision="CONTINUE_FAILURE",
        reason="A retryable partial effect requires another planning cycle.",
        violation_codes=["violation.partial-effect"],
        decided_at=TIMESTAMP,
    )
    assert retry_decision.decision is VerifierDecisionCode.CONTINUE_FAILURE
