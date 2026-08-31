"""Foundation package for the graduation exception agent."""

from graduation_exception_agent.config import AppSettings, ExecutionMode, load_settings
from graduation_exception_agent.models import (
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
    Programme,
    Registration,
    Scenario,
    SourceProvenance,
    SourceAccessStatus,
    Student,
    TransactionResult,
)

__all__ = [
    "AppSettings",
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
    "ExecutionMode",
    "Programme",
    "Registration",
    "Scenario",
    "SourceProvenance",
    "SourceAccessStatus",
    "Student",
    "TransactionResult",
    "load_settings",
]

__version__ = "0.1.0"
