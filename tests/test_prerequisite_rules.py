from __future__ import annotations

import json
from pathlib import Path

import pytest

from graduation_exception_agent.rules import (
    AndRequirement,
    CourseRequirement,
    OrRequirement,
    PrerequisiteResult,
    UnsupportedRequirement,
    evaluate_prerequisite,
    parse_prerequisite,
    prerequisite_ast_to_dict,
)


COURSES_PATH = Path(__file__).parents[1] / "data" / "real" / "courses.json"


@pytest.fixture(scope="module")
def prerequisite_raw_by_code() -> dict[str, str | None]:
    records = json.loads(COURSES_PATH.read_text(encoding="utf-8"))
    return {
        record["code"]: record["prerequisites"]["raw_text"] for record in records
    }


def _evaluate(
    raw_text: str | None,
    completed_courses: set[str] | None = None,
    study_year: int | None = 4,
) -> PrerequisiteResult:
    return evaluate_prerequisite(
        raw_text,
        completed_courses=completed_courses or set(),
        study_year=study_year,
    )


def test_sc4002_any_supported_alternative_passes(
    prerequisite_raw_by_code: dict[str, str | None],
) -> None:
    raw_text = prerequisite_raw_by_code["SC4002"]
    assert raw_text == "SC2001 OR MH1403 OR IE2108"
    assert _evaluate(raw_text, {"SC2001"}) is PrerequisiteResult.PASS
    assert _evaluate(raw_text, {"IE2108"}) is PrerequisiteResult.PASS
    assert _evaluate(raw_text) is PrerequisiteResult.FAIL


def test_sc2005_requires_both_courses(
    prerequisite_raw_by_code: dict[str, str | None],
) -> None:
    raw_text = prerequisite_raw_by_code["SC2005"]
    assert raw_text == "SC1006 & SC1007"
    assert _evaluate(raw_text, {"SC1006", "SC1007"}) is PrerequisiteResult.PASS
    assert _evaluate(raw_text, {"SC1006"}) is PrerequisiteResult.FAIL


def test_sc2001_and_precedence_produces_two_complete_paths(
    prerequisite_raw_by_code: dict[str, str | None],
) -> None:
    raw_text = prerequisite_raw_by_code["SC2001"]
    assert raw_text == "MH1812 & SC1007 OR SC1007 & SC1124"

    expression = parse_prerequisite(raw_text)
    assert expression == OrRequirement(
        (
            AndRequirement(
                (CourseRequirement("MH1812"), CourseRequirement("SC1007"))
            ),
            AndRequirement(
                (CourseRequirement("SC1007"), CourseRequirement("SC1124"))
            ),
        )
    )
    assert _evaluate(raw_text, {"MH1812", "SC1007"}) is PrerequisiteResult.PASS
    assert _evaluate(raw_text, {"SC1007", "SC1124"}) is PrerequisiteResult.PASS
    assert _evaluate(raw_text, {"MH1812", "SC1124"}) is PrerequisiteResult.FAIL


def test_sc3060_uses_year_standing(
    prerequisite_raw_by_code: dict[str, str | None],
) -> None:
    raw_text = prerequisite_raw_by_code["SC3060"]
    assert raw_text == "Year 2 standing"
    assert _evaluate(raw_text, study_year=2) is PrerequisiteResult.PASS
    assert _evaluate(raw_text, study_year=1) is PrerequisiteResult.FAIL
    assert _evaluate(raw_text, study_year=None) is PrerequisiteResult.UNKNOWN


def test_sc2207_corequisite_annotation_is_unknown_but_other_or_branch_can_pass(
    prerequisite_raw_by_code: dict[str, str | None],
) -> None:
    raw_text = prerequisite_raw_by_code["SC2207"]
    assert raw_text == "SC2001(Corequisite) OR MH1403 OR IE2108"

    expression = parse_prerequisite(raw_text)
    assert isinstance(expression, OrRequirement)
    assert expression.children[0] == UnsupportedRequirement("SC2001(Corequisite)")
    assert _evaluate(raw_text, {"MH1403"}) is PrerequisiteResult.PASS
    assert _evaluate(raw_text, {"SC2001"}) is PrerequisiteResult.UNKNOWN
    assert _evaluate(raw_text) is PrerequisiteResult.UNKNOWN


def test_sc4010_programme_annotation_is_unknown_but_other_or_branch_can_pass(
    prerequisite_raw_by_code: dict[str, str | None],
) -> None:
    raw_text = prerequisite_raw_by_code["SC4010"]
    assert raw_text == "SC2000 OR MH2500 (Applicable to DSAI) OR AB1202"

    assert _evaluate(raw_text, {"SC2000"}) is PrerequisiteResult.PASS
    assert _evaluate(raw_text, {"AB1202"}) is PrerequisiteResult.PASS
    assert _evaluate(raw_text, {"MH2500"}) is PrerequisiteResult.UNKNOWN
    assert _evaluate(raw_text) is PrerequisiteResult.UNKNOWN


@pytest.mark.parametrize("raw_text", [None, "", "   "])
def test_empty_prerequisite_passes(raw_text: str | None) -> None:
    assert _evaluate(raw_text) is PrerequisiteResult.PASS
    assert prerequisite_ast_to_dict(raw_text) == {"type": "EMPTY"}


def test_parentheses_override_and_precedence() -> None:
    ungrouped = "SC1001 OR SC1002 AND SC1003"
    grouped = "(SC1001 OR SC1002) AND SC1003"

    assert _evaluate(ungrouped, {"SC1001"}) is PrerequisiteResult.PASS
    assert _evaluate(grouped, {"SC1001"}) is PrerequisiteResult.FAIL
    assert isinstance(parse_prerequisite(ungrouped), OrRequirement)
    assert isinstance(parse_prerequisite(grouped), AndRequirement)


def test_ast_is_immutable_deterministic_and_json_compatible() -> None:
    raw_text = "SC1001 OR (SC1002 AND Year 3 standing)"
    first = parse_prerequisite(raw_text)
    second = parse_prerequisite(raw_text)

    assert first == second
    assert prerequisite_ast_to_dict(first) == {
        "type": "OR",
        "children": [
            {"type": "COURSE", "course_code": "SC1001"},
            {
                "type": "AND",
                "children": [
                    {"type": "COURSE", "course_code": "SC1002"},
                    {"type": "YEAR_STANDING", "minimum_year": 3},
                ],
            },
        ],
    }
    assert json.dumps(prerequisite_ast_to_dict(first), sort_keys=True) == json.dumps(
        prerequisite_ast_to_dict(second), sort_keys=True
    )


@pytest.mark.parametrize(
    "raw_text",
    [
        "CGPA >= 3.5",
        "SC2001(Corequisite)",
        "Applicable to DSAI",
        "SC1001 OR (SC1002",
        "__import__('os').system('echo unsafe')",
    ],
)
def test_unsupported_or_malformed_nonempty_text_is_unknown(raw_text: str) -> None:
    assert isinstance(parse_prerequisite(raw_text), UnsupportedRequirement)
    assert _evaluate(raw_text) is PrerequisiteResult.UNKNOWN
