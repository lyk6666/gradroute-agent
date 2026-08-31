"""Collect the public AY2026-27 Semester 1 CCDS class-schedule union.

This snapshot contains course indexes and timetable meetings only.  It does not
invent capacity, vacancy, waitlist, eligibility, or allocation-priority fields.
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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from collect_ntu_course_catalogue import (
    COURSE_CODE_RE,
    QUERIES,
    Query,
    RowParser,
    canonical_sha256,
)


SCHEDULE_URL = (
    "https://wish.wis.ntu.edu.sg/webexe/owa/"
    "AUS_SCHEDULE.main_display1"
)
DIRECT_SCHEDULE_URL = (
    "https://wish.wis.ntu.edu.sg/webexe/owa/"
    "AUS_SCHEDULE.outgen_search"
)
SOURCE_ID = "ntu.class_schedule.ay2026-27.s1"
ACADEMIC_YEAR = "AY2026-27"
SEMESTER = "SEMESTER_1"
DAY_MAP = {
    "MON": "MONDAY",
    "TUE": "TUESDAY",
    "WED": "WEDNESDAY",
    "THU": "THURSDAY",
    "FRI": "FRIDAY",
    "SAT": "SATURDAY",
    "SUN": "SUNDAY",
}


def fetch(query: Query, timeout: int) -> bytes:
    body = urllib.parse.urlencode(
        {
            "acadsem": "2026;1",
            "r_course_yr": query.selector,
            "r_subj_code": "Enter Keywords or Course Code",
            "r_search_type": "F",
            "boption": "CLoad",
            "staff_access": "false",
        }
    ).encode("ascii")
    request = urllib.request.Request(
        SCHEDULE_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (compatible; CCDS-stage2-research/1.0)",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_direct(course_code: str, full_part: str, timeout: int) -> bytes:
    """Fetch the current-term full- or part-time schedule for one course."""

    query_string = urllib.parse.urlencode(
        {
            "Acad": "2026",
            "FullPart": full_part,
            "Semester": "1",
            "subject": course_code,
        }
    )
    request = urllib.request.Request(
        f"{DIRECT_SCHEDULE_URL}?{query_string}",
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; CCDS-stage2-research/1.0)"
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _parse_time(raw: str) -> tuple[str | None, str | None]:
    match = re.fullmatch(r"(\d{2})(\d{2})-(\d{2})(\d{2})", raw)
    if match is None:
        return None, None
    return (
        f"{match.group(1)}:{match.group(2)}:00",
        f"{match.group(3)}:{match.group(4)}:00",
    )


def _teaching_weeks(remark: str) -> list[int]:
    match = re.search(r"Teaching Wk(?:s)?\s*([0-9,\- ]+)", remark, re.I)
    if match is None:
        return []
    weeks: set[int] = set()
    for part in match.group(1).replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", maxsplit=1)
            if start.isdigit() and end.isdigit():
                weeks.update(range(int(start), int(end) + 1))
        elif part.isdigit():
            weeks.add(int(part))
    return sorted(week for week in weeks if 1 <= week <= 20)


def parse_schedule(payload: bytes) -> dict[str, dict[str, list[dict[str, Any]]]]:
    parser = RowParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    schedules: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    current_course: str | None = None
    current_index: str | None = None
    in_index_table = False
    for cells in parser.rows:
        if len(cells) >= 3 and COURSE_CODE_RE.fullmatch(cells[0]):
            current_course = cells[0]
            current_index = None
            in_index_table = False
            continue
        if cells[:7] == ["INDEX", "TYPE", "GROUP", "DAY", "TIME", "VENUE", "REMARK"]:
            in_index_table = True
            current_index = None
            continue
        if not in_index_table or current_course is None or len(cells) != 7:
            continue
        index, class_type, group, raw_day, raw_time, venue, remark = cells
        if index:
            if not re.fullmatch(r"[A-Za-z0-9-]+", index):
                continue
            current_index = index
        if current_index is None or not class_type:
            continue
        start_time, end_time = _parse_time(raw_time)
        day = DAY_MAP.get(raw_day)
        if (day is None) != (start_time is None or end_time is None):
            day = None
            start_time = None
            end_time = None
        schedules[current_course][current_index].append(
            {
                "class_type": class_type,
                "group": group or None,
                "day": day,
                "start_time": start_time,
                "end_time": end_time,
                "raw_day": raw_day or None,
                "raw_time": raw_time or None,
                "venue": venue or None,
                "teaching_weeks": _teaching_weeks(remark),
                "remark": remark or None,
            }
        )
    return schedules


def _meeting_key(meeting: dict[str, Any]) -> str:
    return json.dumps(meeting, ensure_ascii=False, sort_keys=True)


def _merge_schedule(
    combined: dict[str, dict[str, dict[str, Any]]],
    parsed: dict[str, dict[str, list[dict[str, Any]]]],
    *,
    programme: str | None,
) -> int:
    index_count = 0
    for course_code, indexes in parsed.items():
        for index_id, meetings in indexes.items():
            index_count += 1
            stored = combined[course_code].setdefault(
                index_id, {"meetings": {}, "programmes": set()}
            )
            if programme is not None:
                stored["programmes"].add(programme)
            for meeting in meetings:
                stored["meetings"][_meeting_key(meeting)] = meeting
    return index_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument(
        "--catalogue-input",
        type=Path,
        help=(
            "Optionally query direct full- and part-time schedules for every "
            "collected catalogue code."
        ),
    )
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    # GLOAD represents an elective pool rather than a programme schedule.
    queries = [query for query in QUERIES if query.context == "PROGRAMME"]
    combined: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    observed_programmes: dict[str, set[str]] = defaultdict(set)
    query_audit: list[dict[str, Any]] = []
    singapore_tz = timezone(timedelta(hours=8), name="Asia/Singapore")
    retrieved_at = datetime.now(singapore_tz).isoformat()
    for query in queries:
        assert query.programme is not None
        payload = fetch(query, args.timeout)
        parsed = parse_schedule(payload)
        index_count = _merge_schedule(
            combined, parsed, programme=query.programme
        )
        for course_code in parsed:
            observed_programmes[course_code].add(query.programme)
        query_audit.append(
            {
                "query_type": "PROGRAMME_MATRIX",
                "selector": query.selector,
                "programme": query.programme,
                "study_year": query.study_year,
                "course_count": len(parsed),
                "index_count": index_count,
                "response_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
        print(
            f"{query.selector}: {len(parsed)} courses / {index_count} indexes",
            file=sys.stderr,
        )

    direct_unscheduled_codes: list[str] = []
    if args.catalogue_input is not None:
        catalogue = json.loads(args.catalogue_input.read_text(encoding="utf-8"))
        for course_code in sorted(item["code"] for item in catalogue):
            direct_found = False
            for full_part in ("F", "P"):
                payload = fetch_direct(course_code, full_part, args.timeout)
                parsed = parse_schedule(payload)
                index_count = _merge_schedule(combined, parsed, programme=None)
                direct_found = direct_found or bool(parsed)
                query_audit.append(
                    {
                        "query_type": "DIRECT_COURSE",
                        "course_code": course_code,
                        "full_part": full_part,
                        "course_count": len(parsed),
                        "index_count": index_count,
                        "response_sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
            if not direct_found:
                direct_unscheduled_codes.append(course_code)
            print(
                f"DIRECT:{course_code}: {'scheduled' if direct_found else 'no rows'}",
                file=sys.stderr,
            )

    offerings: list[dict[str, Any]] = []
    for course_code in sorted(combined):
        indexes: list[dict[str, Any]] = []
        for index_id in sorted(combined[course_code]):
            stored = combined[course_code][index_id]
            indexes.append(
                {
                    "index_id": index_id,
                    "meetings": list(stored["meetings"].values()),
                    "observed_programmes": sorted(stored["programmes"]),
                    "capacity": None,
                    "vacancies": None,
                    "waitlist_count": None,
                }
            )
        offerings.append(
            {
                "offering_id": f"offering.ay2026-27.s1.{course_code.lower()}",
                "course_code": course_code,
                "academic_year": ACADEMIC_YEAR,
                "semester": SEMESTER,
                "status": "OFFERED",
                "indexes": indexes,
                "observed_programmes": sorted(observed_programmes[course_code]),
                "scope_completeness": "PARTIAL",
                "snapshot_at": retrieved_at,
                "source_ids": [SOURCE_ID],
            }
        )

    collection = {
        "status": "COLLECTED",
        "source_ids": [SOURCE_ID],
        "offerings": offerings,
        "placeholder_reason": None,
    }
    audit = {
        "source_id": SOURCE_ID,
        "source_url": SCHEDULE_URL,
        "direct_source_url": DIRECT_SCHEDULE_URL,
        "academic_period": "2026;1",
        "retrieved_at": retrieved_at,
        "queries": query_audit,
        "offering_count": len(offerings),
        "index_count": sum(len(item["indexes"]) for item in offerings),
        "normalized_sha256": canonical_sha256(collection),
        "direct_unscheduled_codes": direct_unscheduled_codes,
        "known_limits": [
            "Programme-schedule exposure is not proof of individual eligibility.",
            "Capacity, vacancies, waitlist order, and allocation priority are not present in this source.",
            "Some courses without conventional timetable rows may still be active project or self-paced courses.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(collection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.audit_output.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "offerings": len(offerings),
                "indexes": audit["index_count"],
                "sha256": audit["normalized_sha256"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
