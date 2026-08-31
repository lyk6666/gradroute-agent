"""Collect a normalized NTU CCDS course-content snapshot from the public OWA portal.

The collector intentionally keeps catalogue appearances separate from live class
offerings.  It stores no course descriptions and does not attempt to infer complex
Boolean prerequisite expressions beyond preserving the official raw text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


COURSE_URL = (
    "https://wish.wis.ntu.edu.sg/webexe/owa/"
    "AUS_SUBJ_CONT.main_display1"
)
SOURCE_ID = "ntu.course_content.ay2026-27.s1"
ACADEMIC_PERIOD = "2026_1"
ACADEMIC_YEAR = "AY2026-27"
SEMESTER = "SEMESTER_1"
COURSE_CODE_RE = re.compile(r"^[A-Z]{2,6}\d{3,5}[A-Z]?$")
COURSE_CODE_FIND_RE = re.compile(r"\b[A-Z]{2,6}\d{3,5}[A-Z]?\b")


@dataclass(frozen=True)
class Query:
    selector: str
    programme: str | None
    study_year: int | None
    context: str = "PROGRAMME"


def _programme_queries(code: str, years: range) -> list[Query]:
    return [Query(f"{code};;{year};F", code, year) for year in years]


QUERIES: tuple[Query, ...] = tuple(
    _programme_queries("AISC", range(1, 5))
    + _programme_queries("BACF", range(1, 5))
    + _programme_queries("CE", range(1, 5))
    + _programme_queries("CSC", range(1, 5))
    + _programme_queries("DSAI", range(1, 5))
    + _programme_queries("ECDS", range(1, 5))
    + _programme_queries("MACS", range(1, 5))
    + _programme_queries("ACDA", range(1, 6))
    + _programme_queries("BCE", range(1, 5))
    + _programme_queries("BCG", range(1, 5))
    + _programme_queries("CEEC", range(1, 6))
    + _programme_queries("CSEC", range(1, 6))
    + [
        Query("ACDA;GA;1;F", "ACDA", 1),
        Query("ACDA;GA;2;F", "ACDA", 2),
        Query("ACDA;GB;1;F", "ACDA", 1),
        Query("ACDA;GB;2;F", "ACDA", 2),
        Query("GLOAD;CE;X;F", "CE", None, "BDE_POOL"),
        Query("GLOAD;CSC;X;F", "CSC", None, "BDE_POOL"),
    ]
)


class RowParser(HTMLParser):
    """Extract normalized table rows without relying on third-party HTML parsers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag.lower() == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"} and self._cell is not None:
            assert self._row is not None
            value = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            self._row.append(value)
            self._cell = None
        elif tag.lower() == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


@dataclass
class ParsedCourse:
    code: str
    title: str
    aus: str
    maintainer: str | None
    attributes: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def parse_courses(payload: bytes) -> list[ParsedCourse]:
    parser = RowParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    courses: list[ParsedCourse] = []
    current: ParsedCourse | None = None
    active_key: str | None = None
    for cells in parser.rows:
        if len(cells) >= 3 and COURSE_CODE_RE.fullmatch(cells[0]):
            au_match = re.search(r"\d+(?:\.\d+)?", cells[2])
            if au_match is None:
                current = None
                active_key = None
                continue
            current = ParsedCourse(
                code=cells[0],
                title=cells[1],
                aus=au_match.group(0),
                maintainer=cells[3] if len(cells) > 3 and cells[3] else None,
            )
            courses.append(current)
            active_key = None
            continue
        if current is None:
            continue
        if len(cells) >= 2 and cells[0].endswith(":"):
            active_key = cells[0][:-1].strip()
            value = " ".join(cell for cell in cells[1:] if cell)
            if value:
                current.attributes[active_key] = value
            continue
        if (
            len(cells) >= 2
            and not cells[0]
            and active_key
            and any(cells[1:])
        ):
            addition = " ".join(cell for cell in cells[1:] if cell)
            existing = current.attributes.get(active_key, "")
            current.attributes[active_key] = f"{existing} {addition}".strip()
            continue
        active_key = None
        if len(cells) == 1 and cells[0].startswith(("Not ", "Grade Type")):
            current.notes.append(cells[0])
    return courses


def fetch(query: Query, timeout: int) -> bytes:
    academic, semester = ACADEMIC_PERIOD.split("_", maxsplit=1)
    body = urllib.parse.urlencode(
        {
            "acadsem": ACADEMIC_PERIOD,
            "r_course_yr": query.selector,
            "r_subj_code": "",
            "boption": "CLoad",
            "acad": academic,
            "semester": semester,
        }
    ).encode("ascii")
    request = urllib.request.Request(
        COURSE_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (compatible; CCDS-stage2-research/1.0)",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_exact(course_code: str, timeout: int) -> bytes:
    """Fetch one exact current-term catalogue record outside programme selectors."""

    academic, semester = ACADEMIC_PERIOD.split("_", maxsplit=1)
    body = urllib.parse.urlencode(
        {
            "acadsem": ACADEMIC_PERIOD,
            "r_course_yr": "",
            "r_subj_code": course_code,
            "boption": "Search",
            "acad": academic,
            "semester": semester,
        }
    ).encode("ascii")
    request = urllib.request.Request(
        COURSE_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (compatible; CCDS-stage2-research/1.0)",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _constraint_lines(course: ParsedCourse) -> list[str]:
    constraints = [
        f"{key}: {value}"
        for key, value in course.attributes.items()
        if key not in {"Prerequisite", "Mutually exclusive with"}
    ]
    constraints.extend(course.notes)
    if course.maintainer:
        constraints.append(f"Portal maintainer: {course.maintainer}")
    return constraints


def normalize(results: list[tuple[Query, bytes, list[ParsedCourse]]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    appearances: dict[str, dict[tuple[str | None, str], set[int]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for query, _payload, courses in results:
        for course in courses:
            record = merged.setdefault(
                course.code,
                {
                    "code": course.code,
                    "title": course.title,
                    "aus": course.aus,
                    "prerequisite_texts": [],
                    "exclusion_texts": [],
                    "exclusions": [],
                    "applicable_programmes": [],
                    "documented_constraints": [],
                },
            )
            if record["title"] != course.title or record["aus"] != course.aus:
                raise ValueError(
                    f"conflicting current catalogue metadata for {course.code}: "
                    f"{record['title']!r}/{record['aus']} versus "
                    f"{course.title!r}/{course.aus}"
                )
            prerequisite = course.attributes.get("Prerequisite")
            if prerequisite:
                record["prerequisite_texts"].append(prerequisite)
            exclusion = course.attributes.get("Mutually exclusive with")
            if exclusion:
                record["exclusion_texts"].append(exclusion)
                record["exclusions"].extend(COURSE_CODE_FIND_RE.findall(exclusion))
            record["documented_constraints"].extend(_constraint_lines(course))
            if query.context == "PROGRAMME" and query.programme is not None:
                record["applicable_programmes"].append(query.programme)
            key = (query.programme, query.context)
            if query.study_year is not None:
                appearances[course.code][key].add(query.study_year)
            else:
                appearances[course.code][key]

    normalized: list[dict[str, Any]] = []
    for code in sorted(merged):
        raw = merged[code]
        prerequisite_texts = _ordered_unique(raw.pop("prerequisite_texts"))
        exclusion_texts = _ordered_unique(raw.pop("exclusion_texts"))
        exclusions = sorted(set(raw["exclusions"]) - {code})
        appearance_records = [
            {
                "academic_year": ACADEMIC_YEAR,
                "semester": SEMESTER,
                "programme": programme,
                "study_years": sorted(years),
                "catalogue_context": context,
                "source_ids": [SOURCE_ID],
            }
            for (programme, context), years in sorted(
                appearances[code].items(),
                key=lambda item: (item[0][0] or "", item[0][1]),
            )
        ]
        normalized.append(
            {
                "code": code,
                "title": raw["title"],
                "aus": raw["aus"],
                "prerequisites": {
                    "all_of": [],
                    "any_of": [],
                    "minimum_study_year": None,
                    "raw_text": " | ".join(prerequisite_texts) or None,
                },
                "exclusions": exclusions,
                "exclusions_raw_text": " | ".join(exclusion_texts) or None,
                "applicable_programmes": sorted(
                    set(raw["applicable_programmes"])
                ),
                "programme_categories": {},
                "documented_constraints": _ordered_unique(
                    raw["documented_constraints"]
                ),
                "catalogue_appearances": appearance_records,
                "prerequisites_completeness": "COMPLETE",
                "exclusions_completeness": "COMPLETE",
                "applicability_completeness": "PARTIAL",
                "constraints_completeness": "COMPLETE",
                "source_ids": [SOURCE_ID],
            }
        )
    return normalized


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def curriculum_course_codes(path: Path) -> list[str]:
    """Return exact study-plan codes that need catalogue resolution."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = {
        item.get("course_code") or item.get("raw_course_code")
        for curriculum in payload
        for item in curriculum.get("study_plan", [])
    }
    return sorted(
        code
        for code in candidates
        if isinstance(code, str) and COURSE_CODE_RE.fullmatch(code)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument(
        "--curriculum-input",
        type=Path,
        help=(
            "Optionally exact-query typed study-plan codes missing from the "
            "programme-selector union."
        ),
    )
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    singapore_tz = timezone(timedelta(hours=8), name="Asia/Singapore")
    retrieved_at = datetime.now(singapore_tz).isoformat()

    results: list[tuple[Query, bytes, list[ParsedCourse]]] = []
    query_audit: list[dict[str, Any]] = []
    for query in QUERIES:
        payload = fetch(query, args.timeout)
        courses = parse_courses(payload)
        results.append((query, payload, courses))
        query_audit.append(
            {
                "query_type": "PROGRAMME_MATRIX",
                "selector": query.selector,
                "programme": query.programme,
                "study_year": query.study_year,
                "catalogue_context": query.context,
                "record_count": len(courses),
                "response_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
        print(f"{query.selector}: {len(courses)}", file=sys.stderr)

    unresolved_supplemental_codes: list[str] = []
    if args.curriculum_input is not None:
        observed_codes = {
            course.code for _query, _payload, courses in results for course in courses
        }
        for course_code in curriculum_course_codes(args.curriculum_input):
            if course_code in observed_codes:
                continue
            payload = fetch_exact(course_code, args.timeout)
            parsed = [
                course for course in parse_courses(payload) if course.code == course_code
            ]
            query = Query(
                selector=f"SEARCH:{course_code}",
                programme=None,
                study_year=None,
                context="AUXILIARY",
            )
            results.append((query, payload, parsed))
            query_audit.append(
                {
                    "query_type": "EXACT_CURRICULUM_COURSE",
                    "course_code": course_code,
                    "programme": None,
                    "study_year": None,
                    "catalogue_context": "AUXILIARY",
                    "record_count": len(parsed),
                    "response_sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
            if parsed:
                observed_codes.add(course_code)
            else:
                unresolved_supplemental_codes.append(course_code)
            print(f"SEARCH:{course_code}: {len(parsed)}", file=sys.stderr)

    courses = normalize(results)
    audit = {
        "source_id": SOURCE_ID,
        "source_url": COURSE_URL,
        "academic_period": ACADEMIC_PERIOD,
        "retrieved_at": retrieved_at,
        "queries": query_audit,
        "course_record_count": len(courses),
        "normalized_sha256": canonical_sha256(courses),
        "unresolved_supplemental_codes": unresolved_supplemental_codes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(courses, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.audit_output.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"courses": len(courses), "sha256": audit["normalized_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
