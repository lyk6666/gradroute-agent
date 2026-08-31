"""Validated local data access."""

from graduation_exception_agent.data.json_loader import load_model, load_model_list
from graduation_exception_agent.data.real import (
    RealDataRepository,
    load_academic_calendar,
    load_policy_document,
    validate_real_data,
)

__all__ = [
    "RealDataRepository",
    "load_academic_calendar",
    "load_model",
    "load_model_list",
    "load_policy_document",
    "validate_real_data",
]
