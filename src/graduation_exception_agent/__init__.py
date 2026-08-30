"""Foundation package for the graduation exception agent."""

from graduation_exception_agent.config import AppSettings, ExecutionMode, load_settings
from graduation_exception_agent.models import (
    Approval,
    Course,
    CourseOffering,
    Curriculum,
    DegreeAudit,
    ExceptionCase,
    Programme,
    Registration,
    Scenario,
    SourceProvenance,
    Student,
    TransactionResult,
)

__all__ = [
    "AppSettings",
    "Approval",
    "Course",
    "CourseOffering",
    "Curriculum",
    "DegreeAudit",
    "ExceptionCase",
    "ExecutionMode",
    "Programme",
    "Registration",
    "Scenario",
    "SourceProvenance",
    "Student",
    "TransactionResult",
    "load_settings",
]

__version__ = "0.1.0"
