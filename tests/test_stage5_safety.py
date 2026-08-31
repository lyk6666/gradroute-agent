from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from graduation_exception_agent.memory import (
    ExperienceMemoryQuery,
    ExperienceMemoryRecord,
)
from graduation_exception_agent.models.orchestration import (
    ActionCandidate,
    ClarificationPause,
)
from graduation_exception_agent.models.tooling import (
    ToolError,
    ToolErrorCode,
    ToolResponse,
    ToolStatus,
)
from graduation_exception_agent.models.workflow import ExceptionCaseType
from graduation_exception_agent.orchestration import (
    GroundedDecisionProvider,
    Stage5ControlPlane,
    Stage5Nodes,
)
from graduation_exception_agent.runtime import ScenarioRuntimeFactory
from graduation_exception_agent.tools.policy import PolicyExceptionTools


DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
SCENARIO_TIME = datetime.fromisoformat("2028-08-25T09:00:00+08:00")
CASES_BY_ID = {
    item["case_id"]: item
    for item in json.loads(
        (DATA_ROOT / "simulated" / "exception_cases.json").read_text(
            encoding="utf-8"
        )
    )
}
SCENARIOS_BY_ID = {
    item["scenario_id"]: item
    for item in json.loads(
        (DATA_ROOT / "tests" / "scenarios.json").read_text(encoding="utf-8")
    )
}


def _case(scenario_id: str) -> dict[str, Any]:
    return CASES_BY_ID[SCENARIOS_BY_ID[scenario_id]["case_id"]]


def _intake(
    plane: Stage5ControlPlane,
    scenario_id: str,
    *,
    problem_type: ExceptionCaseType | None = None,
    thread_id: str | None = None,
) -> Any:
    case = _case(scenario_id)
    return plane.create_intake(
        request_text=str(case["reason"]),
        problem_type=problem_type or ExceptionCaseType(case["problem_type"]),
        received_at=datetime.fromisoformat(case["scenario_time"]),
        thread_id=thread_id,
        submission_ready=case.get("submission_ready"),
        unresolved_questions=list(case.get("unresolved_questions", [])),
    )


@pytest.mark.parametrize(
    "answers",
    [
        {"irrelevant": None},
        {"submission_declaration": False},
        {"submission_declaration": 0},
    ],
)
def test_clarification_requires_every_requested_meaningful_answer(
    answers: dict[str, Any],
) -> None:
    runtime = ScenarioRuntimeFactory.from_data_directory(DATA_ROOT).build("S6-D01")
    plane = Stage5ControlPlane.build(tools=runtime.tools)
    intake = _intake(plane, "S6-D01")
    paused = plane.start(intake)
    pause = ClarificationPause.model_validate(paused["clarification_pause"])
    before = plane.state(intake.thread_id).values

    with pytest.raises(ValueError, match="missing meaningful answers"):
        plane.resume(
            thread_id=intake.thread_id,
            payload={
                "clarification_id": pause.clarification_id,
                "answers": answers,
                "impact": pause.impact.value,
                "responded_at": (SCENARIO_TIME + timedelta(minutes=1)).isoformat(),
            },
        )

    after = plane.state(intake.thread_id)
    assert after.values == before
    assert after.next == ("clarification",)
    assert runtime.evaluator.consumed_steps == 0
    assert runtime.evaluator.receipts() == ()


def test_problem_type_must_match_the_observable_exception_case() -> None:
    runtime = ScenarioRuntimeFactory.from_data_directory(DATA_ROOT).build("S1-D01")
    plane = Stage5ControlPlane.build(tools=runtime.tools)

    with pytest.raises(ValueError, match="problem_type does not match"):
        _intake(
            plane,
            "S1-D01",
            problem_type=ExceptionCaseType.PREREQUISITE_WAIVER,
        )

    assert runtime.evaluator.consumed_steps == 0
    assert runtime.evaluator.receipts() == ()


def test_s6_intake_derives_observable_readiness_when_caller_omits_it() -> None:
    runtime = ScenarioRuntimeFactory.from_data_directory(DATA_ROOT).build("S6-D01")
    plane = Stage5ControlPlane.build(tools=runtime.tools)
    case = _case("S6-D01")

    intake = plane.create_intake(
        request_text=str(case["reason"]),
        problem_type=ExceptionCaseType.COURSE_UNAVAILABLE,
        received_at=datetime.fromisoformat(case["scenario_time"]),
    )

    assert intake.submission_ready is False
    assert intake.unresolved_questions == ["submission_declaration"]
    result = plane.start(intake)
    assert result["run_status"] == "WAITING_FOR_CLARIFICATION"
    assert runtime.evaluator.consumed_steps == 0
    assert runtime.evaluator.receipts() == ()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"submission_ready": True}, "submission_ready"),
        ({"unresolved_questions": []}, "unresolved_questions"),
    ],
)
def test_s6_intake_rejects_caller_readiness_that_conflicts_with_case(
    overrides: dict[str, Any],
    message: str,
) -> None:
    runtime = ScenarioRuntimeFactory.from_data_directory(DATA_ROOT).build("S6-D01")
    plane = Stage5ControlPlane.build(tools=runtime.tools)
    case = _case("S6-D01")

    with pytest.raises(ValueError, match=message):
        plane.create_intake(
            request_text=str(case["reason"]),
            problem_type=ExceptionCaseType.COURSE_UNAVAILABLE,
            received_at=datetime.fromisoformat(case["scenario_time"]),
            **overrides,
        )

    assert runtime.evaluator.consumed_steps == 0
    assert runtime.evaluator.receipts() == ()


def test_s6_intake_node_rechecks_readiness_for_forged_typed_input() -> None:
    runtime = ScenarioRuntimeFactory.from_data_directory(DATA_ROOT).build("S6-D01")
    plane = Stage5ControlPlane.build(tools=runtime.tools)
    grounded = _intake(plane, "S6-D01")
    forged = grounded.model_copy(
        update={"submission_ready": True, "unresolved_questions": []}
    )

    with pytest.raises(ValueError, match="intake readiness does not match"):
        plane.start(forged)

    assert runtime.evaluator.consumed_steps == 0
    assert runtime.evaluator.receipts() == ()


class _UnavailableMemory:
    def retrieve(
        self, query: ExperienceMemoryQuery
    ) -> list[ExperienceMemoryRecord]:
        raise ConnectionError("advisory store unavailable")

    def write(self, record: ExperienceMemoryRecord) -> Any:
        raise OSError("advisory store write unavailable")


class _MalformedMemory:
    def retrieve(self, query: ExperienceMemoryQuery) -> Any:
        return [{"unexpected": "unvalidated backend content"}]

    def write(self, record: ExperienceMemoryRecord) -> Any:
        return {"status": "STORED", "stored": "yes"}


class _PrivacyLeakingMemory:
    def retrieve(self, query: ExperienceMemoryQuery) -> Any:
        return [
            {
                "memory_id": "memory.pattern.safe-fixture",
                "schema_version": "alice@example.com",
                "advisory": True,
                "sensitivity": "DEIDENTIFIED_ADVISORY",
                "case_type": "REGISTRATION_AFTER_DEADLINE",
                "goal_kind": "CASE_STATE_REACHED",
                "successful_strategy": "Use a verified route.",
                "recovery_steps": [],
                "failed_strategy_patterns": [],
                "applicability": "Advisory only.",
                "tags": [],
                "verification_receipt_ids": [
                    "receipt.runtime.case.sim-S1-001.1"
                ],
                "verifier_decision": "DONE",
                "goal_complete": True,
                "verified_at": SCENARIO_TIME.isoformat(),
            }
        ]

    def write(self, record: ExperienceMemoryRecord) -> Any:
        return {
            "memory_id": record.memory_id,
            "status": "DISABLED",
            "stored": False,
            "reason": "Backend rejected alice@example.com",
        }


@pytest.mark.parametrize("memory", [_UnavailableMemory(), _MalformedMemory()])
def test_memory_backend_failure_cannot_block_a_verified_resolution(
    memory: Any,
) -> None:
    runtime = ScenarioRuntimeFactory.from_data_directory(DATA_ROOT).build("S1-D01")
    plane = Stage5ControlPlane.build(
        tools=runtime.tools,
        memory=memory,
    )
    result = plane.start(_intake(plane, "S1-D01"))

    assert result["final_outcome"]["status"] == "DONE"
    assert result["goal_evaluation"]["complete"] is True
    assert result["memory_write_completed"] is False
    assert {item["code"] for item in result["errors"]} == {
        "MEMORY_RETRIEVAL_FAILED",
        "MEMORY_WRITE_FAILED",
    }


def test_memory_backend_cannot_echo_sensitive_text_into_graph_state() -> None:
    runtime = ScenarioRuntimeFactory.from_data_directory(DATA_ROOT).build("S1-D01")
    plane = Stage5ControlPlane.build(
        tools=runtime.tools,
        memory=_PrivacyLeakingMemory(),
    )
    result = plane.start(_intake(plane, "S1-D01"))

    assert result["final_outcome"]["status"] == "DONE"
    assert result["memory_write_completed"] is False
    assert {item["code"] for item in result["errors"]} == {
        "MEMORY_RETRIEVAL_FAILED",
        "MEMORY_WRITE_FAILED",
    }
    assert "alice@example.com" not in json.dumps(result, sort_keys=True)


def test_second_facade_cannot_claim_an_already_leased_mutable_session() -> None:
    runtime = ScenarioRuntimeFactory.from_data_directory(DATA_ROOT).build("S1-D01")
    first = Stage5ControlPlane.build(tools=runtime.tools)
    assert first.start(_intake(first, "S1-D01"))["final_outcome"]["status"] == "DONE"

    second = Stage5ControlPlane.build(tools=runtime.tools)
    with pytest.raises(ValueError, match="already leased"):
        second.start(
            _intake(second, "S1-D01", thread_id="thread.stage5.mutated-session")
        )
    assert runtime.evaluator.consumed_steps == 1


def test_same_case_runtime_instances_do_not_collide_in_a_shared_saver() -> None:
    factory = ScenarioRuntimeFactory.from_data_directory(DATA_ROOT)
    runtime_a = factory.build("S3-D01")
    runtime_b = factory.build("S3-D01")
    saver = InMemorySaver()
    plane_a = Stage5ControlPlane.build(tools=runtime_a.tools, checkpointer=saver)
    plane_b = Stage5ControlPlane.build(tools=runtime_b.tools, checkpointer=saver)
    public_thread = "thread.stage5.same-case-shared-saver"

    result_a = plane_a.start(_intake(plane_a, "S3-D01", thread_id=public_thread))
    result_b = plane_b.start(_intake(plane_b, "S3-D01", thread_id=public_thread))

    assert result_a["run_status"] == result_b["run_status"] == (
        "WAITING_FOR_CLARIFICATION"
    )
    snapshot_a = plane_a.state(public_thread)
    snapshot_b = plane_b.state(public_thread)
    assert snapshot_a.config["configurable"]["thread_id"] != (
        snapshot_b.config["configurable"]["thread_id"]
    )
    assert snapshot_a.values["thread_id"] == snapshot_b.values["thread_id"] == (
        public_thread
    )


def test_default_verifier_fails_closed_on_unknown_policy_or_missing_documents() -> None:
    runtime = ScenarioRuntimeFactory.from_data_directory(DATA_ROOT).build("S1-D01")
    plane = Stage5ControlPlane.build(tools=runtime.tools)
    intake = _intake(plane, "S1-D01")
    base_state: dict[str, Any] = {
        "intake_context": intake.model_dump(mode="json"),
        "plan": {"plan_id": "plan.safety.1"},
        "specialist_selection": {"required_specialists": ["POLICY"]},
        "specialist_evidence": [
            {
                "evidence_id": "evidence.plan.safety.1.policy",
                "specialist": "POLICY",
                "completeness_known": True,
            }
        ],
        "action_candidate": {"expected_versions": []},
        "tool_results": {
            "exception_eligibility": {
                "status": "SUCCESS",
                "provenance": [{"origin": "SIMULATED_POLICY"}],
                "data": {
                    "eligibility": "UNKNOWN",
                    "missing_document_ids": [],
                }
            },
            "approval_requirement": {
                "status": "SUCCESS",
                "provenance": [{"origin": "SIMULATED_POLICY"}],
                "data": {"required": False},
            },
            "required_documents": {
                "status": "SUCCESS",
                "provenance": [{"origin": "SIMULATED_POLICY"}],
                "data": {"missing_document_ids": []},
            },
        },
    }
    provider = GroundedDecisionProvider()
    unknown = provider.assess_pre_action(base_state)  # type: ignore[arg-type]
    assert unknown.decision.value == "ESCALATE"
    assert unknown.violation_codes == ("ELIGIBILITY_NOT_GROUNDED",)

    base_state["tool_results"]["exception_eligibility"]["data"] = {
        "eligibility": "ELIGIBLE_FOR_REVIEW",
        "missing_document_ids": [],
    }
    base_state["tool_results"]["exception_eligibility"]["provenance"] = [
        {"origin": "UNKNOWN"}
    ]
    ungrounded = provider.assess_pre_action(base_state)  # type: ignore[arg-type]
    assert ungrounded.decision.value == "ESCALATE"
    assert ungrounded.violation_codes == (
        "POLICY_PROVENANCE_NOT_AUTHORITATIVE",
    )

    base_state["tool_results"]["exception_eligibility"]["provenance"] = [
        {"origin": "SIMULATED_POLICY"}
    ]
    base_state["tool_results"]["exception_eligibility"]["data"] = {
        "eligibility": "INCOMPLETE",
        "missing_document_ids": ["document.required.declaration"],
    }
    missing = provider.assess_pre_action(base_state)  # type: ignore[arg-type]
    assert missing.decision.value == "CLARIFY"
    assert missing.missing_fields == ("document.required.declaration",)


def test_final_receipt_predicates_are_bound_to_one_candidate_write() -> None:
    runtime = ScenarioRuntimeFactory.from_data_directory(DATA_ROOT).build("S2-D01")
    plane = Stage5ControlPlane.build(tools=runtime.tools)
    result = plane.start(_intake(plane, "S2-D01"))
    candidate = ActionCandidate.model_validate(result["action_candidate"])

    predicates = Stage5Nodes._bound_goal_predicates(result, candidate)
    final_receipts = [
        item
        for item in result["action_receipts"]
        if item["idempotency_key"] == candidate.idempotency_key
        and item["action"] == candidate.action.value
        and not item["intermediate"]
    ]

    assert len(final_receipts) == 1
    assert {tuple(item.target_ids) for item in predicates} == {
        (final_receipts[0]["receipt_id"],)
    }


def test_intake_read_failure_routes_to_admin_without_a_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = ScenarioRuntimeFactory.from_data_directory(DATA_ROOT).build("S1-D01")
    plane = Stage5ControlPlane.build(tools=runtime.tools)
    intake = _intake(plane, "S1-D01")

    def unavailable(
        self: PolicyExceptionTools, request: Any
    ) -> ToolResponse:
        return ToolResponse(
            request_id=request.context.request_id,
            status=ToolStatus.FAILURE,
            error=ToolError(
                code=ToolErrorCode.DATA_UNAVAILABLE,
                message="The observable case service is temporarily unavailable.",
                retryable=True,
            ),
        )

    monkeypatch.setattr(
        PolicyExceptionTools,
        "check_exception_eligibility",
        unavailable,
    )
    result = plane.start(intake)

    assert result["final_outcome"]["status"] == "ADMIN_HANDOFF"
    assert "INTAKE_TOOL_FAILURE" in {item["code"] for item in result["errors"]}
    assert runtime.evaluator.consumed_steps == 0
    assert runtime.evaluator.receipts() == ()
