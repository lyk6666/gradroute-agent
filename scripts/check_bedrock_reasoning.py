"""Make one secret-safe Bedrock structured-reasoning readiness check.

The script intentionally reports only model metadata, token counts, validated
specialist names, exception classes, and AWS error codes. It never prints
credentials, request identifiers, prompts, raw model output, or provider error
messages.
"""

from __future__ import annotations

from typing import Any

from graduation_exception_agent.config import load_settings
from graduation_exception_agent.reasoning.bedrock import BedrockConverseClient
from graduation_exception_agent.reasoning.models import (
    ReasoningTask,
    SpecialistSelectionOutput,
)


SYSTEM_PROMPT = """You route a grounded university exception case.
Use only the supplied facts. Select one or more relevant specialists.
Return the decision through the required tool and do not invent evidence.
"""

INPUT_PAYLOAD = {
    "case": {
        "problem_type": "REGISTRATION_AFTER_DEADLINE",
        "case_state": "OPEN",
        "goal_types": ["CASE_STATE_REACHED"],
    },
    "available_specialists": ["DEGREE_AUDIT", "POLICY", "COURSE"],
    "deterministic_requirements": ["POLICY", "COURSE"],
}


def _safe_failure_details(error: BaseException) -> list[str]:
    """Return a bounded cause chain without request or credential material."""

    details = [f"error_type={type(error).__name__}"]
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        if isinstance(response, dict):
            error_block: Any = response.get("Error")
            if isinstance(error_block, dict):
                code = error_block.get("Code")
                if code:
                    details.append(f"aws_error_code={code}")
        current = current.__cause__
        if current is not None:
            details.append(f"cause_type={type(current).__name__}")
    return details


def main() -> int:
    settings = load_settings()
    try:
        client = BedrockConverseClient.from_settings(settings)
        response = client.complete(
            task=ReasoningTask.SELECT_SPECIALISTS,
            system_prompt=SYSTEM_PROMPT,
            input_payload=INPUT_PAYLOAD,
            output_schema=SpecialistSelectionOutput.model_json_schema(),
        )
        decision = SpecialistSelectionOutput.model_validate(response.output)
    except Exception as exc:
        print("status=failed")
        for detail in _safe_failure_details(exc):
            print(detail)
        return 1

    print("status=success")
    print(f"model_id={response.model_id}")
    print(f"stop_reason={response.stop_reason}")
    print(
        "specialists="
        + ",".join(specialist.value for specialist in decision.specialists)
    )
    print(f"input_tokens={response.usage.input_tokens}")
    print(f"output_tokens={response.usage.output_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
