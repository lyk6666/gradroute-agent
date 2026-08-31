"""End-to-end Stage 5 conformance against all 140 hidden contracts.

The execution-contract package is used only by this evaluator test.  The graph
receives a typed intake assembled from observable exception-case fields; no
contract expectation is copied into ``WorkflowState``.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

import pytest

from graduation_exception_agent.data.simulated import load_exception_cases
from graduation_exception_agent.evaluation.execution_contracts import (
    EvaluatorExecutionContract,
    load_execution_contract_package,
)
from graduation_exception_agent.models.orchestration import (
    ApprovalPause,
    ApprovalResumePayload,
    ClarificationPause,
    ClarificationResumePayload,
)
from graduation_exception_agent.models.workflow import (
    ApprovalStatus,
    CaseState,
    ExceptionCaseType,
    ExpectedOutcome,
    TransactionAction,
)
from graduation_exception_agent.orchestration import Stage5ControlPlane
from graduation_exception_agent.runtime import ScenarioRuntimeFactory


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data"
CONTRACTS_PATH = DATA_ROOT / "tests" / "execution_contracts.json"
CASES_PATH = DATA_ROOT / "simulated" / "exception_cases.json"

CONTRACT_PACKAGE = load_execution_contract_package(CONTRACTS_PATH)
CONTRACTS = tuple(CONTRACT_PACKAGE.contracts)
CASES_BY_ID = {
    str(item.case_id): item for item in load_exception_cases(CASES_PATH)
}

# These names belong exclusively to scenario ground truth or the hidden
# evaluator package.  Observable case identifiers, tool observations, and
# approval statuses are intentionally not prohibited.
EVALUATOR_ONLY_KEYS = {
    "evaluator_only",
    "expected_outcome",
    "family",
    "forbidden_transitions",
    "ground_truth",
    "human_routes",
    "injected_event",
    "invalid_paths",
    "loop_expectations",
    "memory_update_permitted",
    "required_transitions",
    "scenario_id",
    "source_artifacts_sha256",
    "split",
    "transaction_script",
    "transaction_script_id",
    "valid_final_paths",
    "valid_initial_paths",
    "verifier_expectations",
}


@pytest.fixture(scope="module")
def runtime_factory() -> ScenarioRuntimeFactory:
    return ScenarioRuntimeFactory.from_data_directory(DATA_ROOT)


@pytest.mark.parametrize(
    "contract",
    CONTRACTS,
    ids=[contract.scenario_id for contract in CONTRACTS],
)
def test_all_frozen_scenarios_follow_the_stage5_contract(
    contract: EvaluatorExecutionContract,
    runtime_factory: ScenarioRuntimeFactory,
) -> None:
    """Run one isolated graph and compare its observable trace with the oracle."""

    runtime = runtime_factory.build(contract.scenario_id)
    control_plane = Stage5ControlPlane.build(tools=runtime.tools)
    case = CASES_BY_ID[str(runtime.tools.context.case_id)]
    received_at = case.scenario_time

    intake = control_plane.create_intake(
        request_text=str(case.reason),
        problem_type=ExceptionCaseType(case.problem_type),
        received_at=received_at,
        case_state=CaseState(case.state),
        submission_ready=case.submission_ready,
        unresolved_questions=list(case.unresolved_questions),
    )
    result = control_plane.start(intake)

    initial_receipts = _receipt_ids(result)
    initial_consumed_steps = runtime.evaluator.consumed_steps
    initial_revision = runtime.evaluator.session_revision

    if contract.expected_outcome is ExpectedOutcome.CLARIFICATION_REQUIRED:
        assert result["run_status"] == "WAITING_FOR_CLARIFICATION"
        _assert_interrupt_kind(result, "CLARIFICATION")
        pause = ClarificationPause.model_validate(result["clarification_pause"])
        expected_impact = contract.clarification.impact
        assert expected_impact is not None
        assert pause.impact.value.startswith(expected_impact.value)

        result = control_plane.resume(
            thread_id=intake.thread_id,
            payload=ClarificationResumePayload(
                clarification_id=pause.clarification_id,
                answers={
                    field: (
                        True
                        if field == "submission_declaration"
                        else "Provided by the student"
                    )
                    for field in pause.missing_fields
                },
                impact=pause.impact,
                responded_at=received_at + timedelta(minutes=1),
            ),
        )
        # The resume itself must materialize the small/material edge before any
        # later hypothetical processing.  The matching checkpoint is the
        # contract boundary for a scenario whose frozen outcome is still
        # CLARIFICATION_REQUIRED.
        contract_state = _matching_contract_checkpoint(
            control_plane, intake.thread_id, result, contract
        )
        assert _receipt_ids(contract_state) == initial_receipts == []

    elif contract.expected_outcome is ExpectedOutcome.PENDING_APPROVAL:
        assert result["run_status"] == "WAITING_FOR_APPROVAL"
        _assert_interrupt_kind(result, "APPROVAL")
        pause = ApprovalPause.model_validate(result["approval_pause"])
        assert pause.approval_id == contract.human_routes.approval_id

        result = control_plane.resume(
            thread_id=intake.thread_id,
            payload=ApprovalResumePayload(
                approval_id=pause.approval_id,
                expected_version=pause.approval_version,
                observed_version=pause.approval_version,
                status=ApprovalStatus.PENDING,
                observed_at=received_at + timedelta(minutes=1),
            ),
        )
        _assert_interrupt_kind(result, "APPROVAL")
        assert result["run_status"] == "WAITING_FOR_APPROVAL"
        # Re-entering the pending checkpoint reuses the committed approval
        # request and must not consume a second simulator write.
        assert runtime.evaluator.consumed_steps == initial_consumed_steps == 1
        assert runtime.evaluator.session_revision == initial_revision
        assert _receipt_ids(result) == initial_receipts
        contract_state = _matching_contract_checkpoint(
            control_plane, intake.thread_id, result, contract
        )

    else:
        assert "__interrupt__" not in result
        final_status = result["final_outcome"]["status"]
        expected_status = {
            ExpectedOutcome.RESOLVED: "DONE",
            ExpectedOutcome.ESCALATED: "ADMIN_HANDOFF",
        }[contract.expected_outcome]
        assert final_status == expected_status
        contract_state = result

    trace = _transition_keys(contract_state)
    assert set(contract.required_transitions) <= trace
    assert not (set(contract.forbidden_transitions) & trace)
    assert "REQUEST_APPROVAL:SUCCESS->GOAL_COMPLETE" not in trace

    _assert_approval_request_is_intermediate(contract_state)
    _assert_memory_is_done_gated(contract_state, contract)
    _assert_receipts_are_unique_and_not_replayed(result)

    if contract.scenario_id.startswith("S7-"):
        counters = result["loop_counters"]
        assert counters["replans"] == 1
        assert counters["tool_retries"] == 1
        assert contract.loop_expectations.expected_replans == 1
        assert contract.loop_expectations.expected_tool_retries == 1

    # Scan the persisted graph state rather than the invocation-only
    # ``__interrupt__`` envelope returned by LangGraph.
    persisted = dict(control_plane.state(intake.thread_id).values)
    leaked_paths = list(_find_evaluator_only_keys(persisted))
    assert leaked_paths == []


def _assert_interrupt_kind(result: Mapping[str, Any], expected: str) -> None:
    interrupts = result.get("__interrupt__")
    assert isinstance(interrupts, list) and len(interrupts) == 1
    value = interrupts[0].value
    assert value["kind"] == expected


def _matching_contract_checkpoint(
    control_plane: Stage5ControlPlane,
    thread_id: str,
    latest: Mapping[str, Any],
    contract: EvaluatorExecutionContract,
) -> dict[str, Any]:
    """Return the shortest persisted prefix satisfying an interrupted contract."""

    candidates = [dict(latest)]
    candidates.extend(dict(snapshot.values) for snapshot in control_plane.history(thread_id))
    required = set(contract.required_transitions)
    forbidden = set(contract.forbidden_transitions)
    matches = [
        candidate
        for candidate in candidates
        if required <= _transition_keys(candidate)
        and not (forbidden & _transition_keys(candidate))
    ]
    assert matches, "no persisted checkpoint matches the frozen interrupted route"
    return min(matches, key=lambda candidate: len(_transition_keys(candidate)))


def _transition_keys(state: Mapping[str, Any]) -> set[str]:
    return {
        str(item["transition_key"])
        for item in state.get("trace", [])
        if isinstance(item, Mapping) and "transition_key" in item
    }


def _receipt_ids(state: Mapping[str, Any]) -> list[str]:
    return [str(item["receipt_id"]) for item in state.get("action_receipts", [])]


def _assert_receipts_are_unique_and_not_replayed(state: Mapping[str, Any]) -> None:
    receipts = state.get("action_receipts", [])
    receipt_ids = [item["receipt_id"] for item in receipts]
    assert len(receipt_ids) == len(set(receipt_ids))
    assert all(item.get("replayed") is not True for item in receipts)


def _assert_approval_request_is_intermediate(state: Mapping[str, Any]) -> None:
    receipts = state.get("action_receipts", [])
    approval_receipts = [
        item
        for item in receipts
        if item.get("action") == TransactionAction.REQUEST_APPROVAL.value
    ]
    for receipt in approval_receipts:
        assert receipt["intermediate"] is True
        assert receipt["goal_effect"] is False

    final = state.get("final_outcome")
    if final and final.get("status") == "DONE" and approval_receipts:
        assert any(
            item.get("action") != TransactionAction.REQUEST_APPROVAL.value
            and item.get("goal_effect") is True
            for item in receipts
        )


def _assert_memory_is_done_gated(
    state: Mapping[str, Any], contract: EvaluatorExecutionContract
) -> None:
    final = state.get("final_outcome")
    done = bool(final and final.get("status") == "DONE")
    trace = _transition_keys(state)
    memory_routes = {
        transition
        for transition in trace
        if transition.endswith("->MEMORY_UPDATER")
    }
    assert memory_routes <= {"VERIFIER_POST_ACTION:DONE->MEMORY_UPDATER"}
    assert bool(memory_routes) is done
    # The default Stage 5 memory port is deliberately disabled; DONE permits
    # and invokes the write path, but does not pretend that durable storage was
    # configured.  Non-DONE routes must never invoke it at all.
    assert ("memory_write_completed" in state) is done
    assert ("memory_write_result" in state) is done
    if final:
        assert bool(final["memory_write_permitted"]) is done
    assert contract.memory_update_permitted is done


def _find_evaluator_only_keys(
    value: Any, path: str = "$"
) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            nested_path = f"{path}.{key_text}"
            if key_text.casefold() in EVALUATOR_ONLY_KEYS:
                yield nested_path
            yield from _find_evaluator_only_keys(nested, nested_path)
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            yield from _find_evaluator_only_keys(nested, f"{path}[{index}]")
