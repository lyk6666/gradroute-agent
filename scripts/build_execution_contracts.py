"""Build deterministic, evaluator-only execution contracts.

Scenario, transaction, and approval artifacts are immutable inputs.
This builder adds only control-flow expectations; it does not reinterpret any
academic fact or simulated transaction result.

Mappings are deliberately explicit:

* S1/S4/S7 goals are registration commits, S2 goals are waiver submissions,
  and S3/S5/S6 goals are exception submissions.
* S3 missing-information cases require a material clarification because the
  missing cohort/path fact changes the plan; they resume at Planner.
* S6 missing-declaration cases require a small clarification because the
  declaration completes the existing candidate; they resume at PRE_ACTION.
* ``requires_human`` means an approval record exists. Administrative
  review is represented separately: it follows a rejected approval through
  Planner, or follows a no-route S6 failure without fabricating an approval.
* A successful REQUEST_APPROVAL is always intermediate.  Only the final
  action-specific postcondition can satisfy the student's goal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0"
GENERATOR_VERSION = "stage4.0.0"
EXPECTED_SCENARIO_COUNT = 140

MAX_REPLANS = 4
MAX_TOOL_RETRIES = 2
MAX_TOTAL_STEPS = 20

GOAL_ACTION_BY_FAMILY = {
    "S1": "SUBMIT_REGISTRATION",
    "S2": "SUBMIT_WAIVER",
    "S3": "SUBMIT_EXCEPTION",
    "S4": "SUBMIT_REGISTRATION",
    "S5": "SUBMIT_EXCEPTION",
    "S6": "SUBMIT_EXCEPTION",
    "S7": "SUBMIT_REGISTRATION",
}

GOAL_KIND_BY_ACTION = {
    "SUBMIT_REGISTRATION": "COURSE_REGISTERED",
    "SUBMIT_WAIVER": "WAIVER_SUBMITTED",
    "SUBMIT_EXCEPTION": "EXCEPTION_SUBMITTED",
}

COMMON_REQUIRED_TRANSITIONS = (
    "INTAKE:CONTEXT_READY->MEMORY_RETRIEVER",
    "MEMORY_RETRIEVER:READY->PLANNER",
    "RESOLUTION_BUILDER:CANDIDATES_BUILT->VERIFIER_PRE_ACTION",
)

COMMON_FORBIDDEN_TRANSITIONS = (
    "REQUEST_APPROVAL:SUCCESS->GOAL_COMPLETE",
    "TRANSACTION:SUCCESS->FINAL_RESPONSE",
    "VERIFIER_POST_ACTION:CONTINUE_FAILURE->MEMORY_UPDATER",
)


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _index_unique(rows: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = str(row.get(key, ""))
        if not value:
            raise ValueError(f"{label} contains a record without {key}")
        if value in index:
            raise ValueError(f"{label} contains duplicate {key} {value}")
        index[value] = row
    return index


def _completion_predicate(
    scenario: dict[str, Any], script: dict[str, Any], action: str
) -> dict[str, Any]:
    successful_step = next(
        (
            step
            for step in reversed(script["steps"])
            if step["action"] == action and step["result_code"] == "SUCCESS"
        ),
        None,
    )
    action_parameters = (
        {
            key: value
            for key, value in successful_step["action_parameters"].items()
            if key != "retry"
        }
        if successful_step is not None
        else {}
    )
    if action == "SUBMIT_REGISTRATION":
        expected: dict[str, Any] = {
            "course_code": scenario["initial_state"]["target_course"],
        }
        # A resolved script supplies the exact operational choice.  Pending and
        # rejected approvals intentionally retain only the course-level goal.
        if "offering_state_id" in action_parameters:
            expected["offering_state_id"] = action_parameters[
                "offering_state_id"
            ]
        return {
            "type": "REGISTRATION_CONTAINS_COURSE",
            "subject_id": scenario["registration_id"],
            "expected": expected,
        }
    expected = {"action": action, "status": "COMMITTED"}
    if action_parameters:
        expected["action_parameters"] = action_parameters
    return {
        "type": "COMMITTED_ACTION_RECEIPT",
        "subject_id": scenario["case_id"],
        "expected": expected,
    }


def _clarification_contract(
    scenario: dict[str, Any], expected_outcome: str
) -> dict[str, Any]:
    if expected_outcome != "CLARIFICATION_REQUIRED":
        return {"required": False, "impact": None, "resume_target": None}
    family = scenario["family"]
    if family == "S3":
        return {
            "required": True,
            "impact": "MATERIAL",
            "resume_target": "PLANNER",
        }
    if family == "S6":
        return {
            "required": True,
            "impact": "SMALL",
            "resume_target": "VERIFIER_PRE_ACTION",
        }
    raise ValueError(
        f"{scenario['scenario_id']} has an unmapped clarification family {family}"
    )


def _verifier_expectations(
    scenario: dict[str, Any], expected_outcome: str, approval_status: str | None
) -> dict[str, list[str]]:
    if expected_outcome == "CLARIFICATION_REQUIRED":
        return {"pre_action": ["CLARIFY"], "post_action": []}
    if approval_status in {"REJECTED", "PENDING"}:
        return {"pre_action": ["VALID"], "post_action": []}
    if scenario["family"] == "S7":
        return {
            "pre_action": ["VALID", "VALID"],
            "post_action": ["CONTINUE_FAILURE", "DONE"],
        }
    if expected_outcome == "ESCALATED":
        return {"pre_action": ["VALID"], "post_action": ["CONTINUE_FAILURE"]}
    if expected_outcome == "RESOLVED":
        return {"pre_action": ["VALID"], "post_action": ["DONE"]}
    raise ValueError(
        f"{scenario['scenario_id']} has unsupported expected outcome {expected_outcome}"
    )


def _required_transitions(
    *,
    scenario: dict[str, Any],
    expected_outcome: str,
    approval_status: str | None,
    clarification: dict[str, Any],
) -> list[str]:
    transitions = list(COMMON_REQUIRED_TRANSITIONS)

    if clarification["required"]:
        transitions.append("VERIFIER_PRE_ACTION:CLARIFY->CLARIFICATION")
        if clarification["impact"] == "SMALL":
            transitions.append(
                "CLARIFICATION:SMALL_CHANGE->VERIFIER_PRE_ACTION"
            )
        else:
            transitions.append("CLARIFICATION:MATERIAL_CHANGE->PLANNER")
        return sorted(set(transitions))

    transitions.append("VERIFIER_PRE_ACTION:VALID->ACTION_GATE")
    if approval_status is not None:
        transitions.append("ACTION_GATE:APPROVAL_REQUIRED->HUMAN_APPROVAL")
        if approval_status == "APPROVED":
            transitions.append("HUMAN_APPROVAL:APPROVED->TRANSACTION")
        elif approval_status == "REJECTED":
            transitions.extend(
                (
                    "HUMAN_APPROVAL:REJECTED->PLANNER",
                    "PLANNER:NO_SAFE_ROUTE->HUMAN_ADMIN_REVIEW",
                    "HUMAN_ADMIN_REVIEW:HANDOFF_PREPARED->FINAL_RESPONSE",
                )
            )
            return sorted(set(transitions))
        elif approval_status == "PENDING":
            transitions.extend(
                (
                    "HUMAN_APPROVAL:PENDING->PAUSE_CHECKPOINT",
                    "PAUSE_CHECKPOINT:APPROVAL_OBSERVED->HUMAN_APPROVAL",
                )
            )
            return sorted(set(transitions))
        else:
            raise ValueError(
                f"{scenario['scenario_id']} has unsupported approval status {approval_status}"
            )
    else:
        transitions.append("ACTION_GATE:NO_APPROVAL->TRANSACTION")

    transitions.extend(
        (
            "TRANSACTION:RESULT->OBSERVATION",
            "OBSERVATION:NORMALIZED->VERIFIER_POST_ACTION",
        )
    )
    if expected_outcome == "RESOLVED":
        transitions.extend(
            (
                "VERIFIER_POST_ACTION:DONE->FINAL_RESPONSE",
                "VERIFIER_POST_ACTION:DONE->MEMORY_UPDATER",
            )
        )
        if scenario["family"] == "S7":
            transitions.append(
                "VERIFIER_POST_ACTION:CONTINUE_FAILURE->PLANNER"
            )
    elif expected_outcome == "ESCALATED":
        transitions.extend(
            (
                "VERIFIER_POST_ACTION:CONTINUE_FAILURE->PLANNER",
                "PLANNER:NO_SAFE_ROUTE->HUMAN_ADMIN_REVIEW",
                "HUMAN_ADMIN_REVIEW:HANDOFF_PREPARED->FINAL_RESPONSE",
            )
        )
    return sorted(set(transitions))


def _forbidden_transitions(
    *,
    expected_outcome: str,
    approval_status: str | None,
    clarification: dict[str, Any],
) -> list[str]:
    transitions = list(COMMON_FORBIDDEN_TRANSITIONS)
    if clarification["required"]:
        transitions.extend(
            (
                "VERIFIER_PRE_ACTION:CLARIFY->ACTION_GATE",
                "ACTION_GATE:APPROVAL_REQUIRED->HUMAN_APPROVAL",
                "ACTION_GATE:NO_APPROVAL->TRANSACTION",
            )
        )
    elif approval_status is None:
        transitions.append("ACTION_GATE:APPROVAL_REQUIRED->HUMAN_APPROVAL")
    else:
        transitions.append("ACTION_GATE:NO_APPROVAL->TRANSACTION")
        if approval_status == "REJECTED":
            transitions.extend(
                (
                    "HUMAN_APPROVAL:REJECTED->TRANSACTION",
                    "HUMAN_APPROVAL:REJECTED->HUMAN_ADMIN_REVIEW",
                )
            )
        elif approval_status == "PENDING":
            transitions.extend(
                (
                    "HUMAN_APPROVAL:PENDING->TRANSACTION",
                    "HUMAN_APPROVAL:PENDING->FINAL_RESPONSE",
                )
            )
    if expected_outcome != "RESOLVED":
        transitions.append("VERIFIER_POST_ACTION:DONE->MEMORY_UPDATER")
    return sorted(set(transitions))


def _contract_for(
    scenario: dict[str, Any],
    script: dict[str, Any],
    approval: dict[str, Any] | None,
) -> dict[str, Any]:
    scenario_id = scenario["scenario_id"]
    expected_outcome = scenario["ground_truth"]["expected_outcome"]
    requires_human = scenario["ground_truth"]["requires_human"]
    if requires_human != (approval is not None):
        raise ValueError(
            f"{scenario_id} requires_human does not match approval presence"
        )

    family = scenario["family"]
    try:
        goal_action = GOAL_ACTION_BY_FAMILY[family]
    except KeyError as error:
        raise ValueError(f"{scenario_id} has unsupported family {family}") from error

    approval_status = approval["status"] if approval is not None else None
    if approval is not None:
        first_action = script["steps"][0]["action"] if script["steps"] else None
        if first_action != "REQUEST_APPROVAL":
            raise ValueError(f"{scenario_id} approval script must request approval first")
        expected_for_status = {
            "APPROVED": "RESOLVED",
            "REJECTED": "ESCALATED",
            "PENDING": "PENDING_APPROVAL",
        }
        if expected_for_status.get(approval_status) != expected_outcome:
            raise ValueError(
                f"{scenario_id} approval status/outcome mismatch: "
                f"{approval_status}/{expected_outcome}"
            )

    clarification = _clarification_contract(scenario, expected_outcome)
    admin_review_required = (
        approval_status == "REJECTED"
        or (expected_outcome == "ESCALATED" and approval is None)
    )
    verifier = _verifier_expectations(
        scenario, expected_outcome, approval_status
    )
    required_transitions = _required_transitions(
        scenario=scenario,
        expected_outcome=expected_outcome,
        approval_status=approval_status,
        clarification=clarification,
    )
    forbidden_transitions = _forbidden_transitions(
        expected_outcome=expected_outcome,
        approval_status=approval_status,
        clarification=clarification,
    )

    same_action_retries = sum(
        left["action"] == right["action"]
        for left, right in zip(script["steps"], script["steps"][1:])
    )
    expected_replans = int(
        family == "S7"
        or approval_status == "REJECTED"
        or (expected_outcome == "ESCALATED" and approval is None)
        or clarification.get("resume_target") == "PLANNER"
    )

    checkpoint_required = approval_status == "PENDING"
    return {
        "evaluator_only": True,
        "scenario_id": scenario_id,
        "case_id": scenario["case_id"],
        "expected_outcome": expected_outcome,
        "goal": {
            "kind": GOAL_KIND_BY_ACTION[goal_action],
            "completion_predicate": _completion_predicate(
                scenario, script, goal_action
            ),
            "expected_satisfied": expected_outcome == "RESOLVED",
            "approval_request_is_completion": False,
        },
        "human_routes": {
            "approval_required": approval is not None,
            "approval_id": approval["approval_id"] if approval else None,
            "approval_outcome": approval_status,
            "approval_basis": (
                {
                    "basis": approval["basis"],
                    "basis_rule_ids": sorted(approval["basis_rule_ids"]),
                }
                if approval
                else None
            ),
            "admin_review_required": admin_review_required,
        },
        "clarification": clarification,
        "verifier_expectations": verifier,
        "required_transitions": required_transitions,
        "forbidden_transitions": forbidden_transitions,
        "checkpoint": {
            "pause_required": checkpoint_required,
            "persistence_required": checkpoint_required,
            "resume_trigger": (
                "APPROVAL_STATUS_CHANGED" if checkpoint_required else None
            ),
            "resume_target": "HUMAN_APPROVAL" if checkpoint_required else None,
        },
        "memory_update_permitted": expected_outcome == "RESOLVED"
        and verifier["post_action"][-1:] == ["DONE"],
        "loop_expectations": {
            "max_replans": MAX_REPLANS,
            "max_tool_retries": MAX_TOOL_RETRIES,
            "max_total_steps": MAX_TOTAL_STEPS,
            "expected_replans": expected_replans,
            "expected_tool_retries": same_action_retries,
        },
    }


def build_contract_package(
    scenarios_path: Path,
    transactions_path: Path,
    approvals_path: Path,
) -> dict[str, Any]:
    scenarios = _read_json(scenarios_path)
    transactions = _read_json(transactions_path)
    approvals = _read_json(approvals_path)
    if not all(isinstance(rows, list) for rows in (scenarios, transactions, approvals)):
        raise ValueError("Stage 3 scenario, transaction, and approval files must be arrays")
    if len(scenarios) != EXPECTED_SCENARIO_COUNT:
        raise ValueError(
            f"expected {EXPECTED_SCENARIO_COUNT} scenarios, found {len(scenarios)}"
        )

    scenario_by_id = _index_unique(scenarios, "scenario_id", "scenarios")
    script_by_id = _index_unique(transactions, "script_id", "transactions")
    approval_by_case = _index_unique(approvals, "case_id", "approvals")

    referenced_script_ids = {
        scenario["transaction_script_id"] for scenario in scenarios
    }
    if referenced_script_ids != set(script_by_id):
        raise ValueError("scenario and transaction-script IDs do not have 1:1 coverage")

    contracts: list[dict[str, Any]] = []
    referenced_approval_cases: set[str] = set()
    for scenario_id in sorted(scenario_by_id):
        scenario = scenario_by_id[scenario_id]
        script = script_by_id[scenario["transaction_script_id"]]
        if script["case_id"] != scenario["case_id"]:
            raise ValueError(f"{scenario_id} script case_id does not match")
        approval = approval_by_case.get(scenario["case_id"])
        if approval is not None:
            referenced_approval_cases.add(scenario["case_id"])
        contracts.append(_contract_for(scenario, script, approval))

    if referenced_approval_cases != set(approval_by_case):
        raise ValueError("approval records do not map 1:1 to approval-backed scenarios")
    if len({item["scenario_id"] for item in contracts}) != EXPECTED_SCENARIO_COUNT:
        raise ValueError("execution contracts do not cover scenarios exactly once")

    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "evaluator_only": True,
        "contract_count": len(contracts),
        "source_artifacts_sha256": {
            "approvals.json": _sha256(approvals_path),
            "scenarios.json": _sha256(scenarios_path),
            "transaction_results.json": _sha256(transactions_path),
        },
        "contracts": contracts,
    }


def _write(output_path: Path, value: Any, *, check: bool) -> int:
    encoded = _json_bytes(value)
    if check:
        if not output_path.exists() or output_path.read_bytes() != encoded:
            print(
                f"Stage 4 execution contracts differ: {output_path}",
                file=sys.stderr,
            )
            return 1
        print("Stage 4 execution contracts are current.")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".stage4-contracts-", dir=output_path.parent
    ) as temporary:
        staged = Path(temporary) / output_path.name
        staged.write_bytes(encoded)
        os.replace(staged, output_path)
    print(f"Generated {len(value['contracts'])} execution contracts at {output_path}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios-path",
        type=Path,
        default=REPO_ROOT / "data" / "tests" / "scenarios.json",
    )
    parser.add_argument(
        "--transactions-path",
        type=Path,
        default=REPO_ROOT / "data" / "simulated" / "transaction_results.json",
    )
    parser.add_argument(
        "--approvals-path",
        type=Path,
        default=REPO_ROOT / "data" / "simulated" / "approvals.json",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=REPO_ROOT / "data" / "tests" / "execution_contracts.json",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate deterministic output without writing files",
    )
    args = parser.parse_args(argv)
    package = build_contract_package(
        args.scenarios_path.resolve(),
        args.transactions_path.resolve(),
        args.approvals_path.resolve(),
    )
    return _write(args.output_path.resolve(), package, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
