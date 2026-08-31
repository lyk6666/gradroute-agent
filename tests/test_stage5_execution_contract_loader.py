from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest
from pydantic import ValidationError

import graduation_exception_agent
from graduation_exception_agent.evaluation.execution_contracts import (
    ExecutionContractPackage,
    load_execution_contract_package,
    load_execution_contracts,
)
from graduation_exception_agent.models.runtime import (
    VerifierDecision,
    VerifierDecisionCode,
    VerifierPhase,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data"
CONTRACTS_PATH = DATA_ROOT / "tests" / "execution_contracts.json"


def _raw_package() -> dict[str, object]:
    value = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_loader_validates_all_frozen_contracts_and_source_hashes() -> None:
    package = load_execution_contract_package(CONTRACTS_PATH)

    assert package.contract_count == 140
    assert len(package.contracts) == 140
    assert len(package.by_scenario_id) == 140
    assert package.contract_for("S1-D01").expected_outcome.value == "RESOLVED"
    assert load_execution_contracts(CONTRACTS_PATH) == package


def test_models_reject_extra_fields_and_non_evaluator_records() -> None:
    payload = _raw_package()
    payload["unexpected"] = "leak"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExecutionContractPackage.model_validate(payload)

    payload = _raw_package()
    contracts = payload["contracts"]
    assert isinstance(contracts, list)
    contracts[0]["evaluator_only"] = False
    with pytest.raises(ValidationError, match="Input should be True"):
        ExecutionContractPackage.model_validate(payload)


def test_package_rejects_count_drift_and_duplicate_scenarios() -> None:
    payload = _raw_package()
    payload["contract_count"] = 139
    with pytest.raises(ValidationError, match="contract_count"):
        ExecutionContractPackage.model_validate(payload)

    payload = _raw_package()
    contracts = payload["contracts"]
    assert isinstance(contracts, list)
    contracts[1]["scenario_id"] = contracts[0]["scenario_id"]
    with pytest.raises(ValidationError, match="scenario_id must be unique"):
        ExecutionContractPackage.model_validate(payload)


def test_contract_rejects_inconsistent_approval_route() -> None:
    payload = _raw_package()
    contracts = payload["contracts"]
    assert isinstance(contracts, list)
    approved = next(
        contract
        for contract in contracts
        if contract["human_routes"]["approval_outcome"] == "APPROVED"
    )
    approved["required_transitions"].remove(
        "HUMAN_APPROVAL:APPROVED->TRANSACTION"
    )

    with pytest.raises(ValidationError, match="missing required route contract"):
        ExecutionContractPackage.model_validate(payload)


def test_contract_rejects_inconsistent_clarification_resume() -> None:
    payload = _raw_package()
    contracts = payload["contracts"]
    assert isinstance(contracts, list)
    clarification = next(
        contract for contract in contracts if contract["clarification"]["required"]
    )
    clarification["clarification"]["resume_target"] = "VERIFIER_PRE_ACTION"

    with pytest.raises(ValidationError, match="MATERIAL clarification must resume"):
        ExecutionContractPackage.model_validate(payload)


def test_loader_detects_frozen_source_artifact_drift(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    (data_root / "tests").mkdir(parents=True)
    (data_root / "simulated").mkdir()
    shutil.copy2(CONTRACTS_PATH, data_root / "tests" / "execution_contracts.json")
    shutil.copy2(DATA_ROOT / "tests" / "scenarios.json", data_root / "tests")
    shutil.copy2(DATA_ROOT / "simulated" / "approvals.json", data_root / "simulated")
    shutil.copy2(
        DATA_ROOT / "simulated" / "transaction_results.json",
        data_root / "simulated",
    )
    scenarios_path = data_root / "tests" / "scenarios.json"
    scenarios_path.write_text(
        scenarios_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="hash mismatch for scenarios.json"):
        load_execution_contract_package(
            data_root / "tests" / "execution_contracts.json"
        )


def test_continue_failure_is_a_concrete_post_action_verifier_decision() -> None:
    decision = VerifierDecision(
        decision_id="decision.post.continue-failure",
        phase=VerifierPhase.POST_ACTION,
        decision=VerifierDecisionCode.CONTINUE_FAILURE,
        reason="A retryable write failed before the goal was satisfied.",
        violation_codes=["violation.retryable-write"],
        decided_at="2026-08-31T12:00:00+08:00",
    )
    assert decision.decision is VerifierDecisionCode.CONTINUE_FAILURE

    invalid = deepcopy(decision.model_dump(mode="python"))
    invalid["violation_codes"] = []
    with pytest.raises(ValidationError, match="requires at least one violation_code"):
        VerifierDecision.model_validate(invalid)

    invalid["phase"] = VerifierPhase.PRE_ACTION
    invalid["violation_codes"] = ["violation.wrong-phase"]
    with pytest.raises(ValidationError, match="not valid during PRE_ACTION"):
        VerifierDecision.model_validate(invalid)


def test_evaluator_contracts_are_not_exported_from_agent_root() -> None:
    assert not hasattr(graduation_exception_agent, "ExecutionContractPackage")
    assert not hasattr(graduation_exception_agent, "load_execution_contracts")
