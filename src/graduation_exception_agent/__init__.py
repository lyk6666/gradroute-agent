"""Foundation package for the graduation exception agent."""

from graduation_exception_agent.config import AppSettings, ExecutionMode, load_settings
from graduation_exception_agent.models import (
    ActionReceipt,
    Approval,
    Course,
    CourseCatalogueAppearance,
    CourseOffering,
    CoverageContract,
    Curriculum,
    CurriculumCoursePlanItem,
    DatasetCoverage,
    DegreeAudit,
    ExceptionCase,
    ExecutionContract,
    Programme,
    Registration,
    Scenario,
    SourceProvenance,
    SourceAccessStatus,
    Student,
    TransactionResult,
    ToolResponse,
)
from graduation_exception_agent.runtime.factory import (
    ScenarioRuntime,
    ScenarioRuntimeFactory,
    Stage4Tools,
)
from graduation_exception_agent.orchestration import Stage5ControlPlane

__all__ = [
    "AppSettings",
    "ActionReceipt",
    "Approval",
    "Course",
    "CourseCatalogueAppearance",
    "CourseOffering",
    "CoverageContract",
    "Curriculum",
    "CurriculumCoursePlanItem",
    "DatasetCoverage",
    "DegreeAudit",
    "ExceptionCase",
    "ExecutionContract",
    "ExecutionMode",
    "Programme",
    "Registration",
    "Scenario",
    "ScenarioRuntime",
    "ScenarioRuntimeFactory",
    "SourceProvenance",
    "SourceAccessStatus",
    "Student",
    "TransactionResult",
    "ToolResponse",
    "Stage4Tools",
    "Stage5ControlPlane",
    "load_settings",
]

__version__ = "0.1.0"
