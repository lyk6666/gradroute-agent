from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from graduation_exception_agent.config import AppSettings, ExecutionMode
from graduation_exception_agent.memory import (
    ExperienceMemoryQuery,
    ExperienceMemoryRecord,
    RankedInMemoryExperienceMemory,
)
from graduation_exception_agent.models.orchestration import SpecialistKind
from graduation_exception_agent.models.runtime import (
    GoalKind,
    VerifierDecisionCode,
)
from graduation_exception_agent.models.workflow import ExceptionCaseType
from graduation_exception_agent.orchestration import (
    GroundedDecisionProvider,
    Stage5ControlPlane,
)
from graduation_exception_agent.reasoning import (
    BedrockConverseClient,
    GroundedBedrockDecisionProvider,
    ReasoningProtocolError,
    ReasoningTask,
    ReasoningUsage,
    StructuredReasoningResponse,
    decision_provider_from_settings,
)
from graduation_exception_agent.runtime import ScenarioRuntimeFactory


DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
SCENARIO_TIME = datetime.fromisoformat("2028-08-25T09:00:00+08:00")


class _FakeReasoningClient:
    model_id = "fake.grounded-model"

    def __init__(self, outputs: dict[ReasoningTask, Any]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, Any]] = []

    def complete(self, **kwargs: Any) -> StructuredReasoningResponse:
        self.calls.append(kwargs)
        task = kwargs["task"]
        output = self.outputs[task]
        if isinstance(output, Exception):
            raise output
        return StructuredReasoningResponse(
            task=task,
            model_id=self.model_id,
            output=output,
            stop_reason="tool_use",
            request_id="request.fake.1",
            latency_ms=5,
            usage=ReasoningUsage(
                input_tokens=20,
                output_tokens=10,
                total_tokens=30,
            ),
        )


class _FakeBedrockRuntime:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.request: dict[str, Any] | None = None

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.request = kwargs
        return self.response


def _selection_state(scenario_id: str = "S1-D01") -> dict[str, Any]:
    runtime = ScenarioRuntimeFactory.from_data_directory(DATA_ROOT).build(scenario_id)
    plane = Stage5ControlPlane.build(tools=runtime.tools)
    intake = plane.create_intake(
        request_text="Resolve the observable registration exception.",
        problem_type=ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
        received_at=SCENARIO_TIME,
    )
    return {
        "intake_context": intake.model_dump(mode="json"),
        "advisory_memories": [],
        "scenario_id": "EVALUATOR-ONLY",
        "ground_truth": {"expected_outcome": "RESOLVED"},
    }


def _valid_pre_action_state() -> dict[str, Any]:
    runtime = ScenarioRuntimeFactory.from_data_directory(DATA_ROOT).build("S1-D01")
    plane = Stage5ControlPlane.build(tools=runtime.tools)
    intake = plane.create_intake(
        request_text="Resolve the observable registration exception.",
        problem_type=ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
        received_at=SCENARIO_TIME,
    )
    plane.start(intake)
    for snapshot in plane.history(intake.thread_id):
        state = dict(snapshot.values)
        if not state.get("action_candidate") or state.get("action_receipts"):
            continue
        if (
            GroundedDecisionProvider().assess_pre_action(state).decision
            is VerifierDecisionCode.VALID
        ):
            return state
    raise AssertionError("scenario did not persist a deterministic VALID checkpoint")


def test_bedrock_client_forces_one_typed_tool_response() -> None:
    runtime = _FakeBedrockRuntime(
        {
            "output": {
                "message": {
                    "content": [
                        {
                            "toolUse": {
                                "name": "select_specialists",
                                "toolUseId": "tool.1",
                                "input": {
                                    "specialists": ["POLICY", "COURSE"],
                                    "rationale": "Read current policy and course facts.",
                                },
                            }
                        }
                    ]
                }
            },
            "stopReason": "tool_use",
            "usage": {"inputTokens": 12, "outputTokens": 8},
            "metrics": {"latencyMs": 17},
            "ResponseMetadata": {"RequestId": "aws.request.1"},
        }
    )
    client = BedrockConverseClient(
        runtime_client=runtime,
        model_id="amazon.nova-micro-v1:0",
        temperature=0,
        max_tokens=1200,
    )
    schema = {
        "type": "object",
        "properties": {"specialists": {"type": "array"}},
        "required": ["specialists"],
    }

    result = client.complete(
        task=ReasoningTask.SELECT_SPECIALISTS,
        system_prompt="Use supplied evidence only.",
        input_payload={"problem_type": "REGISTRATION_AFTER_DEADLINE"},
        output_schema=schema,
    )

    assert result.output["specialists"] == ["POLICY", "COURSE"]
    assert result.usage.total_tokens == 20
    assert runtime.request is not None
    assert runtime.request["toolConfig"]["toolChoice"] == {
        "tool": {"name": "select_specialists"}
    }
    assert runtime.request["inferenceConfig"] == {
        "maxTokens": 1200,
        "temperature": 0,
    }


def test_bedrock_client_rejects_missing_forced_tool_output() -> None:
    runtime = _FakeBedrockRuntime(
        {
            "output": {"message": {"content": [{"text": "unstructured"}]}},
            "usage": {},
        }
    )
    client = BedrockConverseClient(
        runtime_client=runtime,
        model_id="amazon.nova-micro-v1:0",
    )

    with pytest.raises(ReasoningProtocolError, match="structured decision"):
        client.complete(
            task=ReasoningTask.SELECT_SPECIALISTS,
            system_prompt="Use evidence.",
            input_payload={"problem_type": "TEST"},
            output_schema={"type": "object", "properties": {}, "required": []},
        )


def test_model_cannot_remove_deterministically_required_specialists() -> None:
    client = _FakeReasoningClient(
        {
            ReasoningTask.SELECT_SPECIALISTS: {
                "specialists": ["DEGREE_AUDIT"],
                "rationale": "Also inspect degree requirements.",
            }
        }
    )
    provider = GroundedBedrockDecisionProvider(client=client)
    state = _selection_state()

    selected = provider.select_specialists(state)  # type: ignore[arg-type]

    assert selected == (
        SpecialistKind.DEGREE_AUDIT,
        SpecialistKind.POLICY,
        SpecialistKind.COURSE,
    )
    prompt_payload = client.calls[0]["input_payload"]
    assert "scenario_id" not in prompt_payload
    assert "ground_truth" not in prompt_payload
    assert provider.audit_log[0].applied is True


def test_model_failure_falls_back_to_deterministic_specialist_floor() -> None:
    client = _FakeReasoningClient(
        {ReasoningTask.SELECT_SPECIALISTS: RuntimeError("provider unavailable")}
    )
    provider = GroundedBedrockDecisionProvider(client=client)

    selected = provider.select_specialists(_selection_state())  # type: ignore[arg-type]

    assert selected == (SpecialistKind.POLICY, SpecialistKind.COURSE)
    assert provider.audit_log[0].status.value == "FALLBACK"


def test_deterministic_non_valid_gate_is_never_sent_to_the_model() -> None:
    client = _FakeReasoningClient({})
    provider = GroundedBedrockDecisionProvider(client=client)
    state = _selection_state()
    state["resolution_error"] = {
        "code": "NO_GROUNDED_CANDIDATE",
        "message": "No candidate exists.",
    }

    assessment = provider.assess_pre_action(state)  # type: ignore[arg-type]

    assert assessment.decision is VerifierDecisionCode.ESCALATE
    assert client.calls == []
    assert provider.audit_log[0].status.value == "SKIPPED_SAFETY_GATE"


def test_model_may_only_make_a_deterministic_valid_route_more_conservative() -> None:
    client = _FakeReasoningClient(
        {
            ReasoningTask.ASSESS_PRE_ACTION: {
                "decision": "ESCALATE",
                "reason": "A human should inspect the bounded ambiguity.",
                "clarification_impact": "NONE",
                "violation_codes": ["MODEL_CONSERVATIVE_ESCALATION"],
                "missing_fields": [],
            }
        }
    )
    provider = GroundedBedrockDecisionProvider(client=client)
    state = _valid_pre_action_state()
    state["scenario_id"] = "EVALUATOR-ONLY"
    state["ground_truth"] = {"expected_outcome": "RESOLVED"}
    state["tool_results"]["ground_truth"] = {
        "status": "SUCCESS",
        "data": {"expected_outcome": "RESOLVED"},
    }

    assert GroundedDecisionProvider().assess_pre_action(state).decision is (
        VerifierDecisionCode.VALID
    )
    assessment = provider.assess_pre_action(state)

    assert assessment.decision is VerifierDecisionCode.ESCALATE
    assert assessment.violation_codes == ("MODEL_CONSERVATIVE_ESCALATION",)
    prompt_payload = client.calls[0]["input_payload"]
    assert "scenario_id" not in prompt_payload
    assert "ground_truth" not in str(prompt_payload)


def test_model_cannot_invent_a_clarification_field() -> None:
    client = _FakeReasoningClient(
        {
            ReasoningTask.ASSESS_PRE_ACTION: {
                "decision": "CLARIFY",
                "reason": "Ask for an ungrounded field.",
                "clarification_impact": "SMALL_CHANGE",
                "violation_codes": ["MODEL_REQUESTED_CLARIFICATION"],
                "missing_fields": ["private_student_statement"],
            }
        }
    )
    provider = GroundedBedrockDecisionProvider(client=client)

    assessment = provider.assess_pre_action(_valid_pre_action_state())

    assert assessment.decision is VerifierDecisionCode.ESCALATE
    assert assessment.violation_codes == ("LLM_UNGROUNDED_CLARIFICATION",)


def test_graph_checkpoints_only_the_bounded_reasoning_audit() -> None:
    client = _FakeReasoningClient(
        {
            ReasoningTask.SELECT_SPECIALISTS: {
                "specialists": ["POLICY", "COURSE"],
                "rationale": "Read both current evidence domains.",
            },
            ReasoningTask.ASSESS_PRE_ACTION: {
                "decision": "VALID",
                "reason": "The deterministic evidence gate is complete.",
                "clarification_impact": "NONE",
                "violation_codes": [],
                "missing_fields": [],
            },
        }
    )
    provider = GroundedBedrockDecisionProvider(client=client)
    runtime = ScenarioRuntimeFactory.from_data_directory(DATA_ROOT).build("S1-D01")
    plane = Stage5ControlPlane.build(tools=runtime.tools, decisions=provider)
    intake = plane.create_intake(
        request_text="Resolve the observable registration exception.",
        problem_type=ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
        received_at=SCENARIO_TIME,
    )

    result = plane.start(intake)

    assert result["final_outcome"]["status"] == "DONE"
    assert [item["task"] for item in result["reasoning_audit"]] == [
        "select_specialists",
        "assess_pre_action",
    ]
    serialized = str(result["reasoning_audit"])
    assert "ground_truth" not in serialized
    assert "scenario_id" not in serialized


def test_fixture_mode_keeps_the_deterministic_provider() -> None:
    settings = AppSettings(_env_file=None, EXECUTION_MODE="fixture")
    provider = decision_provider_from_settings(settings)
    assert isinstance(provider, GroundedDecisionProvider)
    assert settings.execution_mode is ExecutionMode.FIXTURE


def _memory(
    memory_id: str,
    *,
    case_type: str,
    goal_kind: GoalKind,
    tags: list[str],
    minute: int,
) -> ExperienceMemoryRecord:
    return ExperienceMemoryRecord(
        memory_id=memory_id,
        case_type=case_type,
        goal_kind=goal_kind,
        successful_strategy="Re-check current tools before acting.",
        applicability="Advisory pattern only.",
        tags=tags,
        verification_receipt_ids=[
            f"receipt.runtime.case.sim-S1-001.{minute + 1}"
        ],
        verified_at=SCENARIO_TIME.replace(minute=minute),
    )


def test_ranked_memory_returns_exact_then_related_advisory_patterns() -> None:
    exact = _memory(
        "memory.pattern.exact",
        case_type="REGISTRATION_AFTER_DEADLINE",
        goal_kind=GoalKind.COURSE_REGISTERED,
        tags=["late-registration"],
        minute=1,
    )
    same_goal = _memory(
        "memory.pattern.same-goal",
        case_type="TIMETABLE_CONFLICT",
        goal_kind=GoalKind.COURSE_REGISTERED,
        tags=["schedule"],
        minute=2,
    )
    unrelated = _memory(
        "memory.pattern.unrelated",
        case_type="GRADUATION_REQUIREMENT",
        goal_kind=GoalKind.CASE_STATE_REACHED,
        tags=["audit"],
        minute=3,
    )
    store = RankedInMemoryExperienceMemory([same_goal, unrelated, exact])

    results = store.retrieve(
        ExperienceMemoryQuery(
            case_type="REGISTRATION_AFTER_DEADLINE",
            goal_kind=GoalKind.COURSE_REGISTERED,
            limit=5,
        )
    )

    assert [item.memory_id for item in results] == [
        "memory.pattern.exact",
        "memory.pattern.same-goal",
    ]
