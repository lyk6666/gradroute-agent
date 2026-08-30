"""UTF-8 JSON loading with strict Pydantic validation and safe errors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from graduation_exception_agent.errors import (
    DataDecodeError,
    DataFileNotFoundError,
    DataLoadError,
    DataSchemaError,
    DataShapeError,
)


ModelT = TypeVar("ModelT", bound=BaseModel)

_IDENTITY_FIELDS = (
    "source_id",
    "programme_id",
    "curriculum_id",
    "code",
    "offering_id",
    "state_id",
    "student_id",
    "audit_id",
    "registration_id",
    "case_id",
    "approval_id",
    "transaction_id",
    "script_id",
    "scenario_id",
)


def _load_json_document(path: str | Path) -> Any:
    """Decode one UTF-8 JSON document without applying a schema."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DataFileNotFoundError(source, "file does not exist") from exc
    except UnicodeDecodeError as exc:
        raise DataDecodeError(source, "file is not valid UTF-8") from exc
    except OSError as exc:
        raise DataLoadError(source, f"file could not be read ({exc.__class__.__name__})") from exc

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DataDecodeError(
            source,
            f"invalid JSON at line {exc.lineno}, column {exc.colno}",
        ) from exc


def load_model(path: str | Path, model_type: type[ModelT]) -> ModelT:
    """Load and validate one JSON object as `model_type`."""

    data = _load_json_document(path)
    if not isinstance(data, dict):
        raise DataShapeError(path, "expected a JSON object at the top level")
    try:
        return model_type.model_validate(data)
    except ValidationError as exc:
        raise DataSchemaError(
            path,
            exc.errors(include_input=False, include_url=False),
        ) from exc


def load_model_list(
    path: str | Path,
    model_type: type[ModelT],
    *,
    identity_field: str | None = None,
) -> list[ModelT]:
    """Load a JSON array of models and reject duplicate stable IDs."""

    data = _load_json_document(path)
    if not isinstance(data, list):
        raise DataShapeError(path, "expected a JSON array at the top level")

    records: list[ModelT] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise DataShapeError(path, f"record {index}: expected a JSON object")
        try:
            records.append(model_type.model_validate(item))
        except ValidationError as exc:
            raise DataSchemaError(
                path,
                exc.errors(include_input=False, include_url=False),
                record_index=index,
            ) from exc

    resolved_identity = identity_field or _infer_identity_field(model_type)
    if resolved_identity is not None:
        if resolved_identity not in model_type.model_fields:
            raise ValueError(
                f"{model_type.__name__} has no identity field {resolved_identity!r}"
            )
        seen: set[Any] = set()
        for index, record in enumerate(records):
            value = getattr(record, resolved_identity)
            if value in seen:
                raise DataShapeError(
                    path,
                    f"record {index}: duplicate {resolved_identity}",
                )
            seen.add(value)
    return records


def _infer_identity_field(model_type: type[BaseModel]) -> str | None:
    for field_name in _IDENTITY_FIELDS:
        if field_name in model_type.model_fields:
            return field_name
    return None
