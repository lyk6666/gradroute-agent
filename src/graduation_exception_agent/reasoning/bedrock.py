"""Amazon Bedrock Converse adapter with forced structured tool output."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from graduation_exception_agent.config import AppSettings
from graduation_exception_agent.reasoning.models import (
    ReasoningTask,
    ReasoningUsage,
    StructuredReasoningResponse,
)


class ReasoningUnavailableError(RuntimeError):
    """The configured model endpoint could not provide a usable response."""


class ReasoningProtocolError(RuntimeError):
    """The model response did not satisfy the forced structured-output protocol."""


@runtime_checkable
class StructuredReasoningClient(Protocol):
    model_id: str

    def complete(
        self,
        *,
        task: ReasoningTask,
        system_prompt: str,
        input_payload: Mapping[str, Any],
        output_schema: Mapping[str, Any],
    ) -> StructuredReasoningResponse: ...


class BedrockConverseClient:
    """Small, injectable wrapper around ``bedrock-runtime.converse``."""

    def __init__(
        self,
        *,
        runtime_client: Any,
        model_id: str,
        temperature: float = 0.0,
        max_tokens: int = 1200,
    ) -> None:
        if not model_id.strip():
            raise ValueError("model_id must not be empty")
        if not 0.0 <= temperature <= 2.0:
            raise ValueError("temperature must be between 0 and 2")
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        self._runtime_client = runtime_client
        self.model_id = model_id
        self._temperature = temperature
        self._max_tokens = max_tokens

    @classmethod
    def from_settings(cls, settings: AppSettings) -> BedrockConverseClient:
        if not settings.bedrock_model_id:
            raise ValueError("BEDROCK_MODEL_ID is required for Bedrock reasoning")
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - dependency declaration gate
            raise ReasoningUnavailableError(
                "The boto3 Bedrock dependency is not installed."
            ) from exc

        session_kwargs: dict[str, Any] = {}
        if settings.aws_profile:
            session_kwargs["profile_name"] = settings.aws_profile
        elif settings.aws_access_key_id and settings.aws_secret_access_key:
            session_kwargs.update(
                {
                    "aws_access_key_id": (
                        settings.aws_access_key_id.get_secret_value()
                    ),
                    "aws_secret_access_key": (
                        settings.aws_secret_access_key.get_secret_value()
                    ),
                }
            )
            if settings.aws_session_token:
                session_kwargs["aws_session_token"] = (
                    settings.aws_session_token.get_secret_value()
                )
        session = boto3.Session(**session_kwargs)
        runtime_client = session.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            config=Config(
                connect_timeout=10,
                read_timeout=45,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )
        return cls(
            runtime_client=runtime_client,
            model_id=settings.bedrock_model_id,
            temperature=settings.bedrock_temperature,
            max_tokens=settings.bedrock_max_tokens,
        )

    def complete(
        self,
        *,
        task: ReasoningTask,
        system_prompt: str,
        input_payload: Mapping[str, Any],
        output_schema: Mapping[str, Any],
    ) -> StructuredReasoningResponse:
        schema = dict(output_schema)
        if schema.get("type") != "object":
            raise ValueError("Bedrock tool output schema must be a top-level object")
        tool_name = task.value
        request = {
            "modelId": self.model_id,
            "system": [{"text": system_prompt}],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": json.dumps(
                                dict(input_payload),
                                sort_keys=True,
                                separators=(",", ":"),
                                ensure_ascii=True,
                            )
                        }
                    ],
                }
            ],
            "toolConfig": {
                "tools": [
                    {
                        "toolSpec": {
                            "name": tool_name,
                            "description": (
                                "Return the conservative typed decision requested by "
                                "the supplied grounded evidence."
                            ),
                            "inputSchema": {"json": schema},
                        }
                    }
                ],
                "toolChoice": {"tool": {"name": tool_name}},
            },
            "inferenceConfig": {
                "maxTokens": self._max_tokens,
                "temperature": self._temperature,
            },
        }
        try:
            raw = self._runtime_client.converse(**request)
        except Exception as exc:
            raise ReasoningUnavailableError(
                "Bedrock reasoning request failed; no model output was accepted."
            ) from exc

        try:
            content = raw["output"]["message"]["content"]
            tool_uses = [
                block["toolUse"]
                for block in content
                if isinstance(block, dict)
                and isinstance(block.get("toolUse"), dict)
                and block["toolUse"].get("name") == tool_name
            ]
            if len(tool_uses) != 1:
                raise KeyError("exactly one matching tool use is required")
            output = tool_uses[0]["input"]
            if not isinstance(output, dict):
                raise TypeError("tool input must be an object")
            usage_raw = raw.get("usage", {})
            input_tokens = int(usage_raw.get("inputTokens", 0))
            output_tokens = int(usage_raw.get("outputTokens", 0))
            latency_raw = raw.get("metrics", {}).get("latencyMs")
            request_id_raw = raw.get("ResponseMetadata", {}).get("RequestId")
            return StructuredReasoningResponse(
                task=task,
                model_id=self.model_id,
                output=output,
                stop_reason=str(raw.get("stopReason", "tool_use")),
                request_id=(
                    str(request_id_raw) if request_id_raw is not None else None
                ),
                latency_ms=(int(latency_raw) if latency_raw is not None else None),
                usage=ReasoningUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                ),
            )
        except Exception as exc:
            raise ReasoningProtocolError(
                "Bedrock returned no valid forced structured decision."
            ) from exc


__all__ = [
    "BedrockConverseClient",
    "ReasoningProtocolError",
    "ReasoningUnavailableError",
    "StructuredReasoningClient",
]
