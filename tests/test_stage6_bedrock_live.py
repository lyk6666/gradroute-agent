from __future__ import annotations

import os
from typing import Any

import pytest

from graduation_exception_agent.config import load_settings
from graduation_exception_agent.models.orchestration import SpecialistKind
from graduation_exception_agent.models.runtime import VerifierDecisionCode
from graduation_exception_agent.reasoning import (
    BedrockConverseClient,
    GroundedBedrockDecisionProvider,
)


pytestmark = pytest.mark.live_bedrock


class _RecordingClient:
    def __init__(self, delegate: BedrockConverseClient) -> None:
        self._delegate = delegate
        self.model_id = delegate.model_id
        self.outputs: list[dict[str, Any]] = []

    def complete(self, **kwargs: Any) -> Any:
        response = self._delegate.complete(**kwargs)
        self.outputs.append(response.output)
        return response


def _live_selection_state() -> dict[str, Any]:
    return {
        "intake_context": {
            "case_id": "case.live.stage6",
            "session_id": "session.live.stage6",
            "thread_id": "thread.live.stage6",
            "anonymous_student_id": "SIM-LIVE-STAGE6",
            "programme_code": "CSC",
            "admission_cohort": "AY2024-25",
            "request_text": "Resolve a late registration exception.",
            "problem_type": "REGISTRATION_AFTER_DEADLINE",
            "submission_ready": True,
            "unresolved_questions": [],
            "case_state": "INVESTIGATING",
            "goal_predicates": [
                {
                    "predicate_id": "goal.live.registration",
                    "goal_kind": "COURSE_REGISTERED",
                    "target_type": None,
                    "target_ids": [],
                    "field_path": "current_registration.registered_course_ids",
                    "operator": "CONTAINS",
                    "expected_value": "SC1001",
                    "required": True,
                    "description": "The required course is registered.",
                }
            ],
            "registration_id": "registration.live.stage6",
            "audit_id": None,
            "received_at": "2028-08-25T09:00:00+08:00",
        },
        "advisory_memories": [],
    }


def _live_valid_pre_action_state() -> dict[str, Any]:
    state = _live_selection_state()
    state.update(
        {
            "plan": {"plan_id": "plan.live.stage6"},
            "specialist_selection": {
                "required_specialists": ["POLICY", "COURSE"]
            },
            "specialist_evidence": [
                {
                    "evidence_id": "evidence.plan.live.stage6.policy",
                    "specialist": "POLICY",
                    "completeness_known": True,
                },
                {
                    "evidence_id": "evidence.plan.live.stage6.course",
                    "specialist": "COURSE",
                    "completeness_known": True,
                },
            ],
            "tool_results": {
                "exception_eligibility": {
                    "status": "SUCCESS",
                    "data": {
                        "eligibility": "ELIGIBLE_FOR_REVIEW",
                        "missing_document_ids": [],
                        "approval_required": True,
                    },
                    "provenance": [{"origin": "SIMULATED_POLICY"}],
                    "entity_versions": {},
                },
                "approval_requirement": {
                    "status": "SUCCESS",
                    "data": {"approval_required": True},
                    "provenance": [{"origin": "SIMULATED_POLICY"}],
                    "entity_versions": {},
                },
                "required_documents": {
                    "status": "SUCCESS",
                    "data": {
                        "required_document_ids": [],
                        "missing_document_ids": [],
                    },
                    "provenance": [{"origin": "SIMULATED_POLICY"}],
                    "entity_versions": {},
                },
            },
            "action_candidate": {
                "action": "REQUEST_APPROVAL",
                "evidence_ids": [
                    "evidence.plan.live.stage6.policy",
                    "evidence.plan.live.stage6.course",
                ],
                "expected_versions": [],
            },
        }
    )
    return state


@pytest.mark.skipif(
    os.getenv("RUN_BEDROCK_LIVE_TESTS") != "1",
    reason="set RUN_BEDROCK_LIVE_TESTS=1 to spend two live Bedrock requests",
)
def test_configured_bedrock_model_returns_both_typed_decisions() -> None:
    settings = load_settings()
    client = BedrockConverseClient.from_settings(settings)
    recording_client = _RecordingClient(client)
    provider = GroundedBedrockDecisionProvider(client=recording_client)
    selected = provider.select_specialists(_live_selection_state())
    assessment = provider.assess_pre_action(_live_valid_pre_action_state())
    audit = provider.audit_log

    assert {SpecialistKind.POLICY, SpecialistKind.COURSE} <= set(selected)
    assert assessment.decision in {
        VerifierDecisionCode.VALID,
        VerifierDecisionCode.REPLAN,
        VerifierDecisionCode.ESCALATE,
    }
    assert len(audit) == 2
    statuses = {item.task.value: item.status.value for item in audit}
    assert set(statuses.values()) == {"SUCCESS"}, {
        "statuses": statuses,
        "structured_outputs": recording_client.outputs,
    }
    assert {item.model_id for item in audit} == {settings.bedrock_model_id}
    assert all(
        item.usage is not None and item.usage.total_tokens > 0 for item in audit
    )
