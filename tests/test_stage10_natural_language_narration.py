"""Stage 10 natural-language runtime narration acceptance tests."""

from __future__ import annotations

from copy import deepcopy
import os
from time import monotonic, sleep
from typing import Any

import pytest

from graduation_exception_agent.api.narration import (
    BedrockRuntimeNarrator,
    RuntimeNarration,
)
from graduation_exception_agent.api.service import RunService
from graduation_exception_agent.api.models import RunStatus, StartRunRequest
from graduation_exception_agent.config import AppSettings, ExecutionMode, load_settings


def _settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        execution_mode=ExecutionMode.FIXTURE,
        data_dir="data",
        evaluation_dir="evaluation",
        frontend_origin="http://localhost:3000",
    )


def _wait(service: RunService, run_id: str, timeout: float = 12.0):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        snapshot = service.snapshot(run_id)
        if snapshot.status in {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.WAITING,
        }:
            return snapshot
        sleep(0.02)
    raise AssertionError("run did not reach a stable state")


class _ContextAwareNarrator:
    model_id = "fake.natural-language-model"

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def narrate(self, payload: Any) -> RuntimeNarration:
        captured = deepcopy(dict(payload))
        self.payloads.append(captured)
        node_name = str(captured["node"]["name"])
        inputs = captured["observed_input"]
        outputs = captured["observed_output"]
        changes = captured["persisted_changes"]
        final = captured.get("final_response")
        return RuntimeNarration(
            node_input=(
                f"{node_name} considered {inputs[0]['label'].lower()}: "
                f"{inputs[0]['value']}."
            ),
            node_output=(
                f"It recorded {outputs[0]['label'].lower()}: "
                f"{outputs[0]['value']}."
            ),
            state_change=(
                f"The case now records {changes[0]['label'].lower()}: "
                f"{changes[0]['value']}."
            ),
            action=f"The next action follows the recorded result from {node_name}.",
            working_state=(
                f"The case is at {captured['working_state']['current_step']} and "
                f"its status is {captured['working_state']['status']}."
            ),
            working_known=[
                (
                    f"{captured['case_profile']['student_id']} is a "
                    f"{captured['case_profile']['study_year']} student in "
                    f"{captured['case_profile']['programme']}."
                ),
                f"The current step is {captured['working_state']['current_step']}.",
            ],
            working_next="Continue with the next verified step in the case plan.",
            working_attention="",
            thread_memory=(
                f"This case remembers {captured['thread_memory']['checkpoints']} "
                "completed or waiting checkpoints."
            ),
            thread_highlights=[
                f"The request reached {node_name}.",
                f"{node_name} recorded its result for the next step.",
            ],
            memories=[
                {
                    "memory_id": item["memory_id"],
                    "explanation": (
                        "This earlier pattern may help only if the current evidence "
                        "shows the same conditions."
                    ),
                }
                for item in captured["long_term_memory"]
            ],
            final_response=(
                f"{final['headline']}. {final['resolution_summary']} "
                f"{final['approval_summary']} {final['transaction_summary']}"
                if final
                else ""
            ),
        )


class _UnavailableNarrator:
    model_id = "fake.unavailable-model"

    def narrate(self, payload: Any) -> RuntimeNarration:
        raise RuntimeError("provider unavailable")


def test_completed_nodes_receive_context_specific_narration() -> None:
    narrator = _ContextAwareNarrator()
    service = RunService(_settings(), node_delay_seconds=0, narrator=narrator)

    accepted = service.start(StartRunRequest(scenario_id="S2-M01"))
    final = _wait(service, accepted.run_id)

    assert final.status is RunStatus.COMPLETED
    assert narrator.payloads
    assert final.node_details["student_case"].narrative is not None
    assert final.node_details["policy_agent"].narrative is not None
    assert "Policy evidence" in final.node_details["policy_agent"].narrative.input
    assert final.working_state.narrative is not None
    assert final.working_state.narrative_known
    assert final.working_state.narrative_next is not None
    assert final.thread_memory.narrative is not None
    assert final.thread_memory.narrative_highlights
    assert final.final_response is not None
    assert final.final_response.narrative is not None
    assert final.final_response.headline in final.final_response.narrative

    serialized_payloads = repr(narrator.payloads).lower()
    assert "ground_truth" not in serialized_payloads
    assert "transaction_script" not in serialized_payloads
    assert "injected_events" not in serialized_payloads
    assert narrator.payloads[0]["case_profile"]["student_id"] == "SIM-AISC-016"
    assert narrator.payloads[0]["case_profile"]["registered_courses"]
    assert all(
        not item["label"].endswith("Context")
        for payload in narrator.payloads
        for item in payload["observed_input"]
    )


def test_narration_failure_keeps_recorded_runtime_details_available() -> None:
    service = RunService(
        _settings(), node_delay_seconds=0, narrator=_UnavailableNarrator()
    )

    accepted = service.start(StartRunRequest(scenario_id="S1-M01"))
    final = _wait(service, accepted.run_id)

    assert final.status is RunStatus.COMPLETED
    assert final.node_details["planner"].narrative is not None
    assert final.node_details["planner"].narrative.model_id == "deterministic-presentation"
    assert final.node_details["planner"].input_items
    assert final.node_details["planner"].output_items
    assert final.final_response is not None
    assert final.final_response.message


@pytest.mark.live_bedrock
@pytest.mark.skipif(
    os.getenv("RUN_BEDROCK_LIVE_TESTS") != "1",
    reason="set RUN_BEDROCK_LIVE_TESTS=1 to spend one live narration request",
)
def test_configured_bedrock_model_returns_grounded_natural_language() -> None:
    narrator = BedrockRuntimeNarrator.from_settings(load_settings())
    result = narrator.narrate(
        {
            "node": {"name": "Policy evidence", "attempt": 1, "status": "completed"},
            "case_profile": {
                "student_id": "SIM-CE-010",
                "programme": "Computer Engineering",
                "cohort": "AY2025-26",
                "study_year": "Year 4",
                "registered_courses": ["ML0004"],
                "request": "Register a required course after the deadline.",
            },
            "observed_input": [
                {"label": "Request", "value": "Register a required course after the deadline."}
            ],
            "observed_output": [
                {"label": "Eligibility", "value": "Eligible for review with approval required"}
            ],
            "persisted_changes": [
                {"label": "Policy evidence", "value": "Current route recorded"}
            ],
            "tools_used": ["Policy Search", "Approval Requirement"],
            "evidence_references": ["policy.registration.add-drop"],
            "working_state": {
                "current_step": "Policy evidence",
                "status": "Running",
                "outstanding_items": ["Course feasibility"],
            },
            "thread_memory": {
                "checkpoints": 4,
                "latest_checkpoint": "Policy evidence",
            },
            "long_term_memory": [],
            "final_response": None,
        }
    )

    assert result.node_input
    assert result.node_output
    assert result.state_change
    assert result.action
    assert result.working_state
    assert result.working_known
    assert result.working_next
    assert result.thread_memory
    assert result.thread_highlights
    assert result.final_response == ""
