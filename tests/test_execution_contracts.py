from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data"
CONTRACTS_PATH = DATA_ROOT / "tests" / "execution_contracts.json"
SCENARIOS_PATH = DATA_ROOT / "tests" / "scenarios.json"
TRANSACTIONS_PATH = DATA_ROOT / "simulated" / "transaction_results.json"
APPROVALS_PATH = DATA_ROOT / "simulated" / "approvals.json"
BUILDER_PATH = REPO_ROOT / "scripts" / "build_execution_contracts.py"


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _builder_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "build_execution_contracts", BUILDER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _package() -> dict[str, Any]:
    value = _load(CONTRACTS_PATH)
    assert isinstance(value, dict)
    return value


def _contracts_by_id() -> dict[str, dict[str, Any]]:
    contracts = _package()["contracts"]
    return {contract["scenario_id"]: contract for contract in contracts}


def test_checked_in_contracts_cover_every_stage3_scenario_exactly_once() -> None:
    package = _package()
    scenarios = _load(SCENARIOS_PATH)
    contracts = package["contracts"]

    scenario_ids = [scenario["scenario_id"] for scenario in scenarios]
    contract_ids = [contract["scenario_id"] for contract in contracts]
    assert package["schema_version"] == "1.0"
    assert package["generator_version"] == "stage4.0.0"
    assert package["evaluator_only"] is True
    assert package["contract_count"] == 140
    assert len(contracts) == 140
    assert len(contract_ids) == len(set(contract_ids))
    assert set(contract_ids) == set(scenario_ids)
    assert contract_ids == sorted(contract_ids)
    assert all(contract["evaluator_only"] is True for contract in contracts)


def test_builder_is_deterministic_current_and_does_not_change_stage3(
    tmp_path: Path,
) -> None:
    module = _builder_module()
    first = module.build_contract_package(
        SCENARIOS_PATH, TRANSACTIONS_PATH, APPROVALS_PATH
    )
    second = module.build_contract_package(
        SCENARIOS_PATH, TRANSACTIONS_PATH, APPROVALS_PATH
    )
    assert first == second
    assert module._json_bytes(first) == CONTRACTS_PATH.read_bytes()

    sources = (SCENARIOS_PATH, TRANSACTIONS_PATH, APPROVALS_PATH)
    hashes_before = {path: _sha256(path) for path in sources}
    generated = tmp_path / "execution_contracts.json"
    result = subprocess.run(
        [
            sys.executable,
            str(BUILDER_PATH),
            "--output-path",
            str(generated),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert generated.read_bytes() == CONTRACTS_PATH.read_bytes()
    assert {path: _sha256(path) for path in sources} == hashes_before

    check = subprocess.run(
        [sys.executable, str(BUILDER_PATH), "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stderr
    assert "are current" in check.stdout


def test_source_hashes_bind_the_contracts_to_the_frozen_stage3_inputs() -> None:
    hashes = _package()["source_artifacts_sha256"]
    assert hashes == {
        "approvals.json": _sha256(APPROVALS_PATH),
        "scenarios.json": _sha256(SCENARIOS_PATH),
        "transaction_results.json": _sha256(TRANSACTIONS_PATH),
    }


def test_approval_and_administrative_review_routes_remain_distinct() -> None:
    contracts = _contracts_by_id()
    scenarios = {
        scenario["scenario_id"]: scenario for scenario in _load(SCENARIOS_PATH)
    }
    approvals_by_case = {
        approval["case_id"]: approval for approval in _load(APPROVALS_PATH)
    }

    for scenario_id, contract in contracts.items():
        scenario = scenarios[scenario_id]
        approval = approvals_by_case.get(scenario["case_id"])
        routes = contract["human_routes"]
        assert routes["approval_required"] is (approval is not None)
        if approval is None:
            assert routes["approval_id"] is None
            assert routes["approval_outcome"] is None
            assert routes["approval_basis"] is None
        else:
            assert routes["approval_id"] == approval["approval_id"]
            assert routes["approval_outcome"] == approval["status"]
            assert routes["approval_basis"] == {
                "basis": approval["basis"],
                "basis_rule_ids": sorted(approval["basis_rule_ids"]),
            }

    direct_admin = [
        contract
        for contract in contracts.values()
        if contract["human_routes"]["admin_review_required"]
        and not contract["human_routes"]["approval_required"]
    ]
    assert len(direct_admin) == 10
    assert all(contract["scenario_id"].startswith("S6-") for contract in direct_admin)
    assert all(contract["expected_outcome"] == "ESCALATED" for contract in direct_admin)
    assert all(
        "ACTION_GATE:APPROVAL_REQUIRED->HUMAN_APPROVAL"
        in contract["forbidden_transitions"]
        for contract in direct_admin
    )


def test_approval_grant_is_intermediate_and_never_goal_completion() -> None:
    approved = [
        contract
        for contract in _contracts_by_id().values()
        if contract["human_routes"]["approval_outcome"] == "APPROVED"
    ]
    assert len(approved) == 24
    for contract in approved:
        assert contract["goal"]["approval_request_is_completion"] is False
        assert contract["goal"]["expected_satisfied"] is True
        assert "HUMAN_APPROVAL:APPROVED->TRANSACTION" in contract[
            "required_transitions"
        ]
        assert "REQUEST_APPROVAL:SUCCESS->GOAL_COMPLETE" in contract[
            "forbidden_transitions"
        ]
        assert contract["verifier_expectations"]["post_action"] == ["DONE"]


def test_rejected_approval_returns_to_planner_before_admin_review() -> None:
    rejected = [
        contract
        for contract in _contracts_by_id().values()
        if contract["human_routes"]["approval_outcome"] == "REJECTED"
    ]
    assert len(rejected) == 24
    for contract in rejected:
        assert contract["human_routes"]["admin_review_required"] is True
        assert "HUMAN_APPROVAL:REJECTED->PLANNER" in contract[
            "required_transitions"
        ]
        assert "PLANNER:NO_SAFE_ROUTE->HUMAN_ADMIN_REVIEW" in contract[
            "required_transitions"
        ]
        assert "HUMAN_APPROVAL:REJECTED->HUMAN_ADMIN_REVIEW" in contract[
            "forbidden_transitions"
        ]
        assert "HUMAN_APPROVAL:REJECTED->TRANSACTION" in contract[
            "forbidden_transitions"
        ]


def test_pending_approval_persists_a_checkpoint_and_pauses() -> None:
    pending = [
        contract
        for contract in _contracts_by_id().values()
        if contract["human_routes"]["approval_outcome"] == "PENDING"
    ]
    assert len(pending) == 12
    for contract in pending:
        checkpoint = contract["checkpoint"]
        assert checkpoint == {
            "pause_required": True,
            "persistence_required": True,
            "resume_trigger": "APPROVAL_STATUS_CHANGED",
            "resume_target": "HUMAN_APPROVAL",
        }
        assert "HUMAN_APPROVAL:PENDING->PAUSE_CHECKPOINT" in contract[
            "required_transitions"
        ]
        assert "HUMAN_APPROVAL:PENDING->TRANSACTION" in contract[
            "forbidden_transitions"
        ]
        assert contract["goal"]["expected_satisfied"] is False
        assert contract["memory_update_permitted"] is False


def test_clarification_contracts_cover_small_and_material_resume_paths() -> None:
    clarification = [
        contract
        for contract in _contracts_by_id().values()
        if contract["clarification"]["required"]
    ]
    assert len(clarification) == 20

    material = [
        contract
        for contract in clarification
        if contract["clarification"]["impact"] == "MATERIAL"
    ]
    small = [
        contract
        for contract in clarification
        if contract["clarification"]["impact"] == "SMALL"
    ]
    assert len(material) == 10
    assert len(small) == 10
    assert all(contract["scenario_id"].startswith("S3-") for contract in material)
    assert all(
        contract["clarification"]["resume_target"] == "PLANNER"
        and "CLARIFICATION:MATERIAL_CHANGE->PLANNER"
        in contract["required_transitions"]
        for contract in material
    )
    assert all(contract["scenario_id"].startswith("S6-") for contract in small)
    assert all(
        contract["clarification"]["resume_target"] == "VERIFIER_PRE_ACTION"
        and "CLARIFICATION:SMALL_CHANGE->VERIFIER_PRE_ACTION"
        in contract["required_transitions"]
        for contract in small
    )
    assert all(
        contract["verifier_expectations"]
        == {"pre_action": ["CLARIFY"], "post_action": []}
        for contract in clarification
    )


def test_verifier_memory_goal_and_loop_contracts_are_action_specific() -> None:
    contracts = list(_contracts_by_id().values())
    for contract in contracts:
        post = contract["verifier_expectations"]["post_action"]
        assert contract["memory_update_permitted"] is (
            contract["expected_outcome"] == "RESOLVED" and post[-1:] == ["DONE"]
        )
        assert contract["goal"]["kind"] in {
            "COURSE_REGISTERED",
            "WAIVER_SUBMITTED",
            "EXCEPTION_SUBMITTED",
        }
        assert contract["goal"]["completion_predicate"]["type"] in {
            "REGISTRATION_CONTAINS_COURSE",
            "COMMITTED_ACTION_RECEIPT",
        }
        assert contract["loop_expectations"]["max_replans"] == 4
        assert contract["loop_expectations"]["max_tool_retries"] == 2
        assert contract["loop_expectations"]["max_total_steps"] == 20

    s7 = [contract for contract in contracts if contract["scenario_id"].startswith("S7-")]
    assert len(s7) == 20
    assert all(
        contract["verifier_expectations"]
        == {
            "pre_action": ["VALID", "VALID"],
            "post_action": ["CONTINUE_FAILURE", "DONE"],
        }
        for contract in s7
    )
    assert all(contract["loop_expectations"]["expected_replans"] == 1 for contract in s7)
    assert all(
        contract["loop_expectations"]["expected_tool_retries"] == 1
        for contract in s7
    )
    assert all(
        "VERIFIER_POST_ACTION:CONTINUE_FAILURE->PLANNER"
        in contract["required_transitions"]
        for contract in s7
    )
