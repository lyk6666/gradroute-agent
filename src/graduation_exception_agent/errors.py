"""Safe, typed errors for local data loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class DataLoadError(Exception):
    """Base class for errors raised while loading project data."""

    def __init__(self, path: str | Path, message: str) -> None:
        self.path = Path(path)
        self.detail = message
        super().__init__(f"{self.path}: {message}")


class DataFileNotFoundError(DataLoadError):
    """Raised when a requested data file does not exist."""


class DataDecodeError(DataLoadError):
    """Raised when a file is not valid UTF-8 JSON."""


class DataShapeError(DataLoadError):
    """Raised when the JSON top-level shape is not what the caller requested."""


class DataSchemaError(DataLoadError):
    """Raised when decoded JSON fails Pydantic validation.

    Only field locations and validation messages are retained. Raw record
    values are intentionally excluded so secrets or student data cannot leak
    through an exception message.
    """

    def __init__(
        self,
        path: str | Path,
        issues: list[dict[str, Any]],
        *,
        record_index: int | None = None,
    ) -> None:
        self.issues = tuple(
            {
                "location": tuple(issue.get("loc", ())),
                "message": str(issue.get("msg", "invalid value")),
                "type": str(issue.get("type", "validation_error")),
            }
            for issue in issues
        )
        self.record_index = record_index
        prefix = f"record {record_index}: " if record_index is not None else ""
        summary = "; ".join(
            f"{'.'.join(map(str, issue['location'])) or '<root>'}: {issue['message']}"
            for issue in self.issues
        )
        super().__init__(path, f"{prefix}schema validation failed: {summary}")
