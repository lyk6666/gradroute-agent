"""Safe parsing and three-valued evaluation of course prerequisites.

The public catalogue contains a small, useful expression language as well as
free-text annotations whose meaning cannot be inferred safely.  This module
parses the supported subset and represents everything else explicitly as an
unknown requirement.  It deliberately does not execute or dynamically
interpret source text.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias


class PrerequisiteResult(StrEnum):
    """The result of evaluating a prerequisite expression."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class CourseRequirement:
    """A requirement to have completed one exact course code."""

    course_code: str


@dataclass(frozen=True, slots=True)
class YearStandingRequirement:
    """A minimum numbered year of study."""

    minimum_year: int


@dataclass(frozen=True, slots=True)
class UnsupportedRequirement:
    """A nonempty source fragment that cannot be evaluated safely."""

    text: str


@dataclass(frozen=True, slots=True)
class AndRequirement:
    """All child requirements must pass."""

    children: tuple[PrerequisiteExpression, ...]


@dataclass(frozen=True, slots=True)
class OrRequirement:
    """At least one child requirement must pass."""

    children: tuple[PrerequisiteExpression, ...]


PrerequisiteExpression: TypeAlias = (
    CourseRequirement
    | YearStandingRequirement
    | UnsupportedRequirement
    | AndRequirement
    | OrRequirement
)


_COURSE_CODE = re.compile(r"[A-Z]{2,6}\d{3,5}[A-Z]?", re.IGNORECASE)
_YEAR_STANDING = re.compile(r"Year\s+(\d+)\s+standing", re.IGNORECASE)


def parse_prerequisite(raw_text: str | None) -> PrerequisiteExpression | None:
    """Parse a catalogue prerequisite into an immutable AST.

    ``None`` and whitespace-only input represent no prerequisite.  Malformed
    parentheses and all nonempty unsupported syntax become an
    :class:`UnsupportedRequirement` rather than raising or being guessed at.
    """

    if raw_text is None or not raw_text.strip():
        return None

    text = raw_text.strip()
    if not _parentheses_are_balanced(text):
        return UnsupportedRequirement(text)
    return _parse_or(text)


def evaluate_prerequisite(
    prerequisite: str | PrerequisiteExpression | None,
    *,
    completed_courses: Collection[str],
    study_year: int | None,
) -> PrerequisiteResult:
    """Evaluate a raw prerequisite or parsed AST with three-valued logic.

    A missing prerequisite passes.  Unsupported source text and unavailable
    year-standing data are unknown.  In an ``OR`` expression, an independently
    passing branch still makes the whole expression pass; in an ``AND``
    expression, an independently failing branch still makes it fail.
    """

    expression = (
        parse_prerequisite(prerequisite)
        if isinstance(prerequisite, str) or prerequisite is None
        else prerequisite
    )
    if expression is None:
        return PrerequisiteResult.PASS

    normalized_courses = {
        course_code.strip().upper()
        for course_code in completed_courses
        if course_code.strip()
    }
    return _evaluate_expression(expression, normalized_courses, study_year)


def prerequisite_ast_to_dict(
    prerequisite: str | PrerequisiteExpression | None,
) -> dict[str, object]:
    """Return a stable, JSON-compatible representation of the parsed AST."""

    expression = (
        parse_prerequisite(prerequisite)
        if isinstance(prerequisite, str) or prerequisite is None
        else prerequisite
    )
    if expression is None:
        return {"type": "EMPTY"}
    if isinstance(expression, CourseRequirement):
        return {"type": "COURSE", "course_code": expression.course_code}
    if isinstance(expression, YearStandingRequirement):
        return {"type": "YEAR_STANDING", "minimum_year": expression.minimum_year}
    if isinstance(expression, UnsupportedRequirement):
        return {"type": "UNSUPPORTED", "text": expression.text}
    if isinstance(expression, AndRequirement):
        return {
            "type": "AND",
            "children": [prerequisite_ast_to_dict(child) for child in expression.children],
        }
    return {
        "type": "OR",
        "children": [prerequisite_ast_to_dict(child) for child in expression.children],
    }


def _parse_or(text: str) -> PrerequisiteExpression:
    parts = _split_top_level(text, word_operators=("OR",))
    if len(parts) > 1:
        if any(not part.strip() for part in parts):
            return UnsupportedRequirement(text.strip())
        return _or_requirement(tuple(_parse_and(part) for part in parts))
    return _parse_and(text)


def _parse_and(text: str) -> PrerequisiteExpression:
    parts = _split_top_level(text, word_operators=("AND",), ampersand=True)
    if len(parts) > 1:
        if any(not part.strip() for part in parts):
            return UnsupportedRequirement(text.strip())
        return _and_requirement(tuple(_parse_atom(part) for part in parts))
    return _parse_atom(text)


def _parse_atom(text: str) -> PrerequisiteExpression:
    atom = text.strip()
    if not atom:
        return UnsupportedRequirement(text)

    while _is_whole_parenthesized_group(atom):
        atom = atom[1:-1].strip()
        if not atom:
            return UnsupportedRequirement(text.strip())
        return _parse_or(atom)

    course_match = _COURSE_CODE.fullmatch(atom)
    if course_match:
        return CourseRequirement(course_match.group(0).upper())

    year_match = _YEAR_STANDING.fullmatch(atom)
    if year_match:
        minimum_year = int(year_match.group(1))
        if minimum_year >= 1:
            return YearStandingRequirement(minimum_year)

    return UnsupportedRequirement(atom)


def _split_top_level(
    text: str,
    *,
    word_operators: tuple[str, ...],
    ampersand: bool = False,
) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    index = 0

    while index < len(text):
        character = text[index]
        if character == "(":
            depth += 1
            index += 1
            continue
        if character == ")":
            depth -= 1
            index += 1
            continue

        if depth == 0:
            if ampersand and character == "&":
                parts.append(text[start:index])
                index += 1
                start = index
                continue
            matched_operator = next(
                (
                    operator
                    for operator in word_operators
                    if _word_operator_at(text, index, operator)
                ),
                None,
            )
            if matched_operator is not None:
                parts.append(text[start:index])
                index += len(matched_operator)
                start = index
                continue
        index += 1

    if not parts:
        return [text]
    parts.append(text[start:])
    return parts


def _word_operator_at(text: str, index: int, operator: str) -> bool:
    end = index + len(operator)
    if text[index:end].upper() != operator:
        return False
    before = text[index - 1] if index > 0 else ""
    after = text[end] if end < len(text) else ""
    return not _is_word_character(before) and not _is_word_character(after)


def _is_word_character(character: str) -> bool:
    return bool(character) and (character.isalnum() or character == "_")


def _parentheses_are_balanced(text: str) -> bool:
    depth = 0
    for character in text:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _is_whole_parenthesized_group(text: str) -> bool:
    if len(text) < 2 or text[0] != "(" or text[-1] != ")":
        return False

    depth = 0
    for index, character in enumerate(text):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0 and index != len(text) - 1:
                return False
    return depth == 0


def _and_requirement(
    children: tuple[PrerequisiteExpression, ...],
) -> AndRequirement:
    flattened: list[PrerequisiteExpression] = []
    for child in children:
        if isinstance(child, AndRequirement):
            flattened.extend(child.children)
        else:
            flattened.append(child)
    return AndRequirement(tuple(flattened))


def _or_requirement(children: tuple[PrerequisiteExpression, ...]) -> OrRequirement:
    flattened: list[PrerequisiteExpression] = []
    for child in children:
        if isinstance(child, OrRequirement):
            flattened.extend(child.children)
        else:
            flattened.append(child)
    return OrRequirement(tuple(flattened))


def _evaluate_expression(
    expression: PrerequisiteExpression,
    completed_courses: set[str],
    study_year: int | None,
) -> PrerequisiteResult:
    if isinstance(expression, CourseRequirement):
        return (
            PrerequisiteResult.PASS
            if expression.course_code in completed_courses
            else PrerequisiteResult.FAIL
        )
    if isinstance(expression, YearStandingRequirement):
        if study_year is None:
            return PrerequisiteResult.UNKNOWN
        return (
            PrerequisiteResult.PASS
            if study_year >= expression.minimum_year
            else PrerequisiteResult.FAIL
        )
    if isinstance(expression, UnsupportedRequirement):
        return PrerequisiteResult.UNKNOWN
    if isinstance(expression, AndRequirement):
        results = tuple(
            _evaluate_expression(child, completed_courses, study_year)
            for child in expression.children
        )
        if PrerequisiteResult.FAIL in results:
            return PrerequisiteResult.FAIL
        if PrerequisiteResult.UNKNOWN in results:
            return PrerequisiteResult.UNKNOWN
        return PrerequisiteResult.PASS

    results = tuple(
        _evaluate_expression(child, completed_courses, study_year)
        for child in expression.children
    )
    if PrerequisiteResult.PASS in results:
        return PrerequisiteResult.PASS
    if PrerequisiteResult.UNKNOWN in results:
        return PrerequisiteResult.UNKNOWN
    return PrerequisiteResult.FAIL
