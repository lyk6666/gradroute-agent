from __future__ import annotations

from pathlib import Path


def test_package_imports_cleanly() -> None:
    import graduation_exception_agent as package

    assert package.__version__ == "0.1.0"
    assert package.Course.__name__ == "Course"
    assert package.Scenario.__name__ == "Scenario"


def test_stage_one_does_not_declare_langgraph_dependency() -> None:
    project_root = Path(__file__).parents[1]
    pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    assert "langgraph" not in pyproject.lower()
