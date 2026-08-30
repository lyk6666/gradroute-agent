from __future__ import annotations

from pathlib import Path

import pytest

from graduation_exception_agent.data import load_model, load_model_list
from graduation_exception_agent.errors import (
    DataDecodeError,
    DataFileNotFoundError,
    DataSchemaError,
    DataShapeError,
)
from graduation_exception_agent.models import Course


FIXTURES = Path(__file__).parent / "fixtures"


def test_load_valid_model() -> None:
    course = load_model(FIXTURES / "valid" / "course.json", Course)
    assert course.code == "SC1001"


def test_load_valid_model_list() -> None:
    courses = load_model_list(FIXTURES / "valid" / "courses.json", Course)
    assert [course.code for course in courses] == ["SC1001", "SC1002"]


def test_missing_file_has_typed_error() -> None:
    missing = FIXTURES / "invalid" / "does-not-exist.json"
    with pytest.raises(DataFileNotFoundError, match="does not exist"):
        load_model(missing, Course)


def test_malformed_json_reports_location() -> None:
    path = FIXTURES / "invalid" / "malformed.json"
    with pytest.raises(DataDecodeError, match=r"line \d+, column \d+"):
        load_model(path, Course)


def test_wrong_top_level_shape_is_rejected() -> None:
    path = FIXTURES / "invalid" / "wrong_top_level.json"
    with pytest.raises(DataShapeError, match="expected a JSON array"):
        load_model_list(path, Course)


def test_non_object_array_item_is_rejected() -> None:
    path = FIXTURES / "invalid" / "array_with_scalar.json"
    with pytest.raises(DataShapeError, match="record 1"):
        load_model_list(path, Course)


def test_schema_error_contains_path_and_field_but_not_raw_value() -> None:
    path = FIXTURES / "invalid" / "course_extra.json"
    with pytest.raises(DataSchemaError) as caught:
        load_model(path, Course)
    message = str(caught.value)
    assert "course_extra.json" in message
    assert "secret" in message
    assert "DO_NOT_LEAK_THIS_VALUE" not in message


def test_duplicate_collection_identity_is_rejected() -> None:
    path = FIXTURES / "invalid" / "courses_duplicate.json"
    with pytest.raises(DataShapeError, match="duplicate code"):
        load_model_list(path, Course)


def test_explicit_unknown_identity_field_is_rejected() -> None:
    path = FIXTURES / "valid" / "courses.json"
    with pytest.raises(ValueError, match="has no identity field"):
        load_model_list(path, Course, identity_field="course_id")
