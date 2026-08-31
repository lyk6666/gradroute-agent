"""Build the deterministic Stage 3 NTU CCDS simulation package.

The source data is deliberately treated as immutable input.  This generator
creates counterfactual operational and student records from the grounded Stage
2 snapshot; it does not claim that the synthetic values are NTU records.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from graduation_exception_agent.data.real.repository import RealDataRepository
from graduation_exception_agent.data.simulated.repository import Stage3DataBundle
from graduation_exception_agent.data.simulated.validator import validate_stage3_data
from graduation_exception_agent.rules import PrerequisiteResult, evaluate_prerequisite
from graduation_exception_agent.models import (
    Approval,
    ApprovalStatus,
    AuditAssumption,
    AuditAssumptionKind,
    AuditBasis,
    AuditOutcome,
    CaseState,
    CreditStatus,
    DegreeAudit,
    EventType,
    ExceptionCase,
    ExceptionCaseType,
    ExpectedOutcome,
    GenerationManifest,
    InjectedEvent,
    OfferingState,
    PrototypePolicy,
    Registration,
    RegistrationItem,
    RegistrationItemStatus,
    RegistrationMeeting,
    RegistrationPhase,
    RequirementProgress,
    RequirementStatus,
    ResolutionPath,
    ResolutionStep,
    RuntimeOfferingStatus,
    SIMULATED_POLICY_BANNER,
    Scenario,
    ScenarioFamily,
    ScenarioGroundTruth,
    ScenarioSplit,
    SimulationScope,
    StateMutation,
    StateTargetType,
    Student,
    SupportingDocument,
    TerminalProfile,
    TransactionAction,
    TransactionCode,
    TransactionResult,
    TransactionScript,
)


GENERATOR_VERSION = "stage3.4.0"
GLOBAL_SEED = 42017
SIMULATION_PERIOD_ID = "period.terminal.s1"
GENERATED_AT = "2026-08-31T12:30:00+08:00"
SCENARIO_TIME = "2028-08-25T09:00:00+08:00"
CASE_TIME = "2028-08-25T08:45:00+08:00"
EVENT_TIME = "2028-08-25T09:01:00+08:00"

POLICY_IDS = (
    "policy.prototype.scenario_bounded_audit",
    "policy.prototype.counterfactual_template_reuse",
    "policy.prototype.registration_operations",
)

PROFILE_ORDER = (
    TerminalProfile.REQUIREMENT_OUTSTANDING.value,
    TerminalProfile.INDEX_TIMETABLE_WORKLOAD_CONSTRAINED.value,
    TerminalProfile.PREREQUISITE_OR_EVIDENCE_DEPENDENT.value,
    TerminalProfile.NO_VERIFIED_RESOLUTION.value,
)
PROFILE_SHORT = dict(zip(PROFILE_ORDER, ("P1", "P2", "P3", "P4"), strict=True))
MAIN_PROFILE_ALLOCATION = {
    "curriculum.aisc.ay2025-26": (6, 5, 5, 5),
    "curriculum.ce.ay2025-26": (5, 6, 5, 5),
    "curriculum.csc.ay2025-26": (5, 5, 6, 5),
    "curriculum.dsai.ay2025-26": (5, 5, 5, 6),
}
CASE_FAMILIES_BY_PROFILE = {
    "P1": (("S1", 20), ("S3", 10)),
    "P2": (("S4", 20), ("S7", 20)),
    "P3": (("S2", 20), ("S5", 20)),
    "P4": (("S3", 10), ("S6", 20)),
}
FAMILY_ENUM = {member.value: member for member in ScenarioFamily}


def _seed(entity_type: str, stable_id: str) -> int:
    """Stable per-entity seed; never use Python's process-randomised hash()."""

    digest = hashlib.sha256(
        f"{GLOBAL_SEED}|{entity_type}|{stable_id}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big") % 2_000_000_000


def _generated(model: type[Any], record_id: str, source_rules: Iterable[str], **data: Any) -> Any:
    return model(
        generator_version=GENERATOR_VERSION,
        seed=_seed(model.__name__, record_id),
        source_rule_ids=sorted(set(source_rules)),
        **data,
    )


def _json_bytes(value: Any) -> bytes:
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json")
    elif isinstance(value, list):
        payload = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value]
    else:
        payload = value
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _year_for(cohort: str, terminal_year: int) -> str:
    start = int(cohort.upper().removeprefix("AY").split("-", 1)[0]) + terminal_year - 1
    return f"AY{start}-{str(start + 1)[-2:]}"


def _split_label(position: int) -> str:
    if position < 4:
        return f"D{position + 1:02d}"
    if position == 4:
        return "M01"
    return f"E{position - 4:02d}"


def _split_for(position: int) -> ScenarioSplit:
    if position < 4:
        return ScenarioSplit.DEVELOPMENT
    if position == 4:
        return ScenarioSplit.DEMO
    return ScenarioSplit.EVALUATION


def _family_for_profile_position(profile: str, position: int) -> str | None:
    """Return the case family assigned to a zero-based profile position."""

    cursor = 0
    for family, amount in CASE_FAMILIES_BY_PROFILE[profile]:
        if cursor <= position < cursor + amount:
            return family
        cursor += amount
    return None


def _observable_intake_readiness(
    family: str, position: int
) -> tuple[bool | None, list[str]]:
    """Derive user-visible intake facts before constructing any evaluator oracle."""

    if family != "S6":
        return None, []
    if position % 2 == 0:
        return False, ["submission_declaration"]
    return True, []


def _scope_time(academic_year: str, clock: str) -> str:
    """A fixed terminal-semester timestamp derived from the scope year."""

    return f"{academic_year[2:6]}-08-25T{clock}+08:00"


def _meeting_conflicts(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return whether two sourced timetable meetings can overlap."""

    required = ("day", "start_time", "end_time")
    if any(left.get(field) is None or right.get(field) is None for field in required):
        return True
    if left["day"] != right["day"]:
        return False
    left_weeks = set(left.get("teaching_weeks") or ())
    right_weeks = set(right.get("teaching_weeks") or ())
    if left_weeks and right_weeks and left_weeks.isdisjoint(right_weeks):
        return False
    return (
        left["start_time"] < right["end_time"]
        and right["start_time"] < left["end_time"]
    )


def _index_is_concrete(index: dict[str, Any]) -> bool:
    meetings = index.get("meetings") or ()
    return bool(meetings) and all(
        meeting.get("day") is not None
        and meeting.get("start_time") is not None
        and meeting.get("end_time") is not None
        for meeting in meetings
    )


def _indexes_conflict(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return any(
        _meeting_conflicts(left_meeting, right_meeting)
        for left_meeting in left.get("meetings") or ()
        for right_meeting in right.get("meetings") or ()
    )


def _raw_real(real_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    curricula = json.loads((real_dir / "curriculum.json").read_text(encoding="utf-8"))
    courses = json.loads((real_dir / "courses.json").read_text(encoding="utf-8"))
    offerings = json.loads((real_dir / "course_offerings.json").read_text(encoding="utf-8"))["offerings"]
    return ({item["curriculum_id"]: item for item in curricula}, {item["code"]: item for item in courses}, {item["offering_id"]: item for item in offerings})


def _policies() -> list[PrototypePolicy]:
    definitions = (
        (POLICY_IDS[0], "Scenario-bounded audit", "Audits are bounded to the declared curriculum configuration, path, and assumptions; they are not official graduation clearances."),
        (POLICY_IDS[1], "Counterfactual template reuse", "AY2026-27 Semester 1 course indexes are timetable templates only for the declared terminal simulation period."),
        (POLICY_IDS[2], "Prototype registration operations", "Vacancy, availability, retry, and approval outcomes are controlled prototype state for evaluation only."),
    )
    return [
        _generated(
            PrototypePolicy,
            policy_id,
            ["rule.stage3.prototype_policy_contract"],
            policy_id=policy_id,
            title=title,
            origin="SIMULATED_POLICY",
            body_markdown=f"{SIMULATED_POLICY_BANNER}\n\n{body}",
            applicable_academic_years=["AY2028-29", "AY2029-30"],
            applicable_admission_cohorts=["AY2025-26"],
            applicability_note="Applies only to the deterministic Stage 3 prototype package.",
            version="1.0.0",
        )
        for policy_id, title, body in definitions
    ]


def _state_id(offering_id: str, index_id: str) -> str:
    return f"state.{offering_id.removeprefix('offering.')}.{index_id}"


def _config_slug(curriculum_id: str) -> str:
    """A unique ID-safe configuration label, not merely its programme code."""

    return curriculum_id.removeprefix("curriculum.").split(".", 1)[0]


def _student_config_slug(curriculum_id: str) -> str:
    return "".join(character for character in _config_slug(curriculum_id).upper() if character.isalnum())


def _build(real_dir: Path) -> tuple[dict[str, Any], Stage3DataBundle]:
    curricula, courses, offerings = _raw_real(real_dir)
    real_repository = RealDataRepository.from_directory(real_dir)
    detailed = [item for item in curricula.values() if item.get("study_plan") and item.get("requirements")]
    detailed.sort(key=lambda item: item["curriculum_id"])
    if len(detailed) != 17:
        raise ValueError(f"Stage 3 requires 17 detailed curricula, found {len(detailed)}")
    if not set(MAIN_PROFILE_ALLOCATION).issubset({item["curriculum_id"] for item in detailed}):
        raise ValueError("the four mainstream detailed curricula are not available")

    indexes: list[tuple[dict[str, Any], dict[str, Any]]] = []
    by_course: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for offering in sorted(offerings.values(), key=lambda row: row["offering_id"]):
        for index in sorted(offering["indexes"], key=lambda row: row["index_id"]):
            indexes.append((offering, index))
            by_course[offering["course_code"]].append((offering, index))
    if len(indexes) != 2108:
        raise ValueError(f"Stage 3 requires 2,108 real indexes, found {len(indexes)}")

    policies = _policies()
    scopes: list[SimulationScope] = []
    scope_info: dict[str, dict[str, Any]] = {}
    for curriculum in detailed:
        programme = curriculum["programme"]
        configuration = _config_slug(curriculum["curriculum_id"])
        scope_id = f"scope.{configuration}.terminal"
        plan = curriculum["study_plan"]
        terminal_year = max(int(item["study_year"]) for item in plan)
        paths = [path["path_id"] for path in curriculum.get("graduation_paths", [])]
        labels = sorted({item["path_label"] for item in plan if item.get("path_label")})
        scope = _generated(
            SimulationScope,
            scope_id,
            [curriculum["curriculum_id"], POLICY_IDS[0], POLICY_IDS[1]],
            simulation_scope_id=scope_id,
            curriculum_id=curriculum["curriculum_id"],
            programme=programme,
            admission_cohort=curriculum["admission_cohort"],
            simulation_period_id=SIMULATION_PERIOD_ID,
            simulation_academic_year=_year_for(curriculum["admission_cohort"], terminal_year),
            simulation_semester="SEMESTER_1",
            template_academic_year="AY2026-27",
            template_semester="SEMESTER_1",
            terminal_study_year=terminal_year,
            student_count=21 if curriculum["curriculum_id"] in MAIN_PROFILE_ALLOCATION else 12,
            audit_basis=AuditBasis.SCENARIO_BOUNDED_SIMULATION,
            counterfactual_time_basis="Counterfactual terminal Semester 1 using AY2026-27 Semester 1 timetable templates.",
            permitted_graduation_path_ids=paths,
            permitted_study_plan_path_labels=labels,
            accepted_gap_ids=[],
            assumption_ids=[f"assumption.{configuration}.terminal"],
        )
        scopes.append(scope)
        scope_info[scope_id] = {"curriculum": curriculum, "scope": scope, "labels": labels, "paths": paths, "configuration": configuration}

    offering_states: list[OfferingState] = []
    state_by_pair: dict[tuple[str, str], OfferingState] = {}
    multi_index_first: dict[str, int] = defaultdict(int)
    for offering, index in indexes:
        key = (offering["offering_id"], index["index_id"])
        ordinal = multi_index_first[offering["offering_id"]]
        multi_index_first[offering["offering_id"]] += 1
        capacity = 25 + (_seed("capacity", f"{key[0]}|{key[1]}") % 46)
        # Keep the first two indexes of every multi-index offering usable so
        # normal recovery and dynamic-failure scenarios always have a fallback.
        # Every baseline state is initially usable.  Controlled failures are
        # introduced only through explicit events, never hidden in the seed.
        vacancy = 1 + (
            _seed("vacancy", f"{key[0]}|{key[1]}") % min(12, capacity)
        )
        status = RuntimeOfferingStatus.OPEN
        state = _generated(
            OfferingState,
            _state_id(*key),
            [offering["offering_id"], POLICY_IDS[1], POLICY_IDS[2]],
            state_id=_state_id(*key),
            simulation_period_id=SIMULATION_PERIOD_ID,
            template_offering_id=offering["offering_id"],
            template_index_id=index["index_id"],
            template_academic_year=offering["academic_year"],
            template_semester=offering["semester"],
            capacity=capacity,
            vacancies=vacancy,
            waitlist_count=_seed("waitlist", f"{key[0]}|{key[1]}") % 8,
            runtime_status=status,
            available=vacancy > 0,
            version=1,
            assumption_ids=[],
        )
        offering_states.append(state)
        state_by_pair[key] = state

    students: list[Student] = []
    audits: list[DegreeAudit] = []
    registrations: list[Registration] = []
    students_by_profile: dict[str, list[Student]] = defaultdict(list)
    profile_positions: dict[str, int] = defaultdict(int)
    p3_family_counts: dict[str, int] = defaultdict(int)
    family_by_student: dict[str, str | None] = {}
    target_by_student: dict[
        str,
        tuple[
            dict[str, Any],
            dict[str, Any],
            dict[str, Any],
            dict[str, Any],
            dict[str, Any],
        ],
    ] = {}
    for scope in sorted(scopes, key=lambda row: str(row.simulation_scope_id)):
        details = scope_info[str(scope.simulation_scope_id)]
        curriculum = details["curriculum"]
        programme = curriculum["programme"]
        plan_candidates = [
            item for item in curriculum["study_plan"]
            if item.get("course_code") in courses and item.get("requirement_id")
            and Decimal(str(courses[item["course_code"]]["aus"])) > 0
            and len({offering["offering_id"] for offering, _ in by_course.get(item["course_code"], [])}) > 0
        ]
        multi_candidates = [
            item for item in plan_candidates
            if len(by_course.get(item["course_code"], [])) >= 2
        ]
        candidates = multi_candidates or plan_candidates
        if not candidates:
            raise ValueError(f"No offered positive-AU study-plan course for {curriculum['curriculum_id']}")
        counts = MAIN_PROFILE_ALLOCATION.get(curriculum["curriculum_id"], (3, 3, 3, 3))
        grounded_plan_codes = sorted({
            item["course_code"] for item in plan_candidates if item["course_code"] in by_course
        })
        serial = 0
        for profile, count in zip(PROFILE_ORDER, counts, strict=True):
            for local in range(count):
                serial += 1
                student_id = f"SIM-{_student_config_slug(curriculum['curriculum_id'])}-{serial:03d}"
                profile_short = PROFILE_SHORT[profile]
                profile_position = profile_positions[profile_short]
                profile_positions[profile_short] += 1
                family_hint = _family_for_profile_position(
                    profile_short, profile_position
                )
                selected_path = details["paths"][(serial - 1) % len(details["paths"])] if details["paths"] else None
                if not details["labels"]:
                    selected_label = None
                elif selected_path is None:
                    selected_label = details["labels"][(serial - 1) % len(details["labels"])]
                else:
                    lowered_path = selected_path.lower()
                    attachment = (
                        "pi"
                        if ".pi" in lowered_path or "-pi" in lowered_path
                        else "pa"
                        if ".pa" in lowered_path or "-pa" in lowered_path
                        else None
                    )
                    selected_label = next(
                        (
                            label
                            for label in details["labels"]
                            if attachment is not None
                            and label.lower().startswith(attachment)
                        ),
                        details["labels"][(serial - 1) % len(details["labels"])],
                    )
                if profile_short == "P3":
                    if selected_path is None and p3_family_counts["S2"] < 20:
                        family_hint = "S2"
                    elif (
                        selected_path is not None
                        and p3_family_counts["S5"] < 20
                        and (
                            curriculum["configuration_kind"] != "BASE"
                            or programme not in {"AISC", "CE", "CSC", "DSAI"}
                        )
                    ):
                        family_hint = "S5"
                    else:
                        family_hint = None
                    if family_hint is not None:
                        p3_family_counts[family_hint] += 1
                family_by_student[student_id] = family_hint
                needs_feasible_registration = family_hint in {"S1", "S4", "S7"}
                target_candidates = [
                    item
                    for item in candidates
                    if item.get("path_label") is None
                    or item.get("path_label") == selected_label
                ]
                if needs_feasible_registration:
                    target_candidates = [
                        item
                        for item in target_candidates
                        if evaluate_prerequisite(
                            courses[item["course_code"]]["prerequisites"].get(
                                "raw_text"
                            ),
                            completed_courses=(),
                            study_year=scope.terminal_study_year,
                        )
                        is PrerequisiteResult.PASS
                    ]
                    if not target_candidates:
                        raise ValueError(
                            "No prerequisite-safe multi-index target for "
                            f"{curriculum['curriculum_id']}"
                        )
                elif family_hint == "S2":
                    target_candidates = [
                        item
                        for item in target_candidates
                        if re.search(
                            r"\b[A-Z]{2}\d{4}\b",
                            courses[item["course_code"]]["prerequisites"].get(
                                "raw_text"
                            )
                            or "",
                        )
                    ]
                    if not target_candidates:
                        raise ValueError(
                            "No course-code-prerequisite target for "
                            f"{curriculum['curriculum_id']}"
                        )
                target_item = target_candidates[
                    (serial - 1) % len(target_candidates)
                ]
                if (
                    curriculum["curriculum_id"] == "curriculum.aisc.ay2025-26"
                    and profile == TerminalProfile.PREREQUISITE_OR_EVIDENCE_DEPENDENT.value
                    and local == 4
                ):
                    target_item = next(
                        item
                        for item in target_candidates
                        if item["course_code"] == "SC4002"
                    )
                target_code = target_item["course_code"]
                target_offering, target_index = by_course[target_code][(serial - 1) % len(by_course[target_code])]
                def available_requirement_aus(plan_item: dict[str, Any]) -> Decimal:
                    plan_requirement = next(
                        item
                        for item in curriculum["requirements"]
                        if item["requirement_id"] == plan_item["requirement_id"]
                    )
                    path_category_aus = next(
                        (
                            path.get("category_aus", {}).get(
                                plan_requirement["category"]
                            )
                            for path in curriculum.get("graduation_paths", [])
                            if path["path_id"] == selected_path
                        ),
                        None,
                    )
                    minimum = Decimal(
                        str(
                            plan_requirement["minimum_aus"]
                            if plan_requirement["minimum_aus"] is not None
                            else path_category_aus or 0
                        )
                    )
                    if plan_item["requirement_id"] == target_item["requirement_id"]:
                        minimum -= Decimal(str(courses[target_code]["aus"]))
                    return minimum

                completed_item = next(
                    (
                        item
                        for item in plan_candidates
                        if item["course_code"] != target_code
                        and (
                            item.get("path_label") is None
                            or item.get("path_label") == selected_label
                        )
                        and available_requirement_aus(item)
                        >= Decimal(str(courses[item["course_code"]]["aus"]))
                        and (
                            family_hint != "S2"
                            or evaluate_prerequisite(
                                courses[target_code]["prerequisites"].get(
                                    "raw_text"
                                ),
                                completed_courses=(item["course_code"],),
                                study_year=scope.terminal_study_year,
                            )
                            is not PrerequisiteResult.PASS
                        )
                        and (
                            not needs_feasible_registration
                            or (
                                item["course_code"]
                                not in courses[target_code]["exclusions"]
                                and target_code
                                not in courses[item["course_code"]]["exclusions"]
                            )
                        )
                    ),
                    None,
                )
                if completed_item is None:
                    raise ValueError(
                        f"No requirement-mappable completed course for {student_id}"
                    )
                completed_code = completed_item["course_code"]
                completed = courses[completed_code]
                completed_aus = Decimal(str(completed["aus"]))
                total_required = next((Decimal(str(path["graduation_aus"])) for path in curriculum.get("graduation_paths", []) if path["path_id"] == selected_path), Decimal(str(curriculum.get("graduation_aus") or 120)))
                target_aus = Decimal(str(courses[target_code]["aus"]))
                earned_total = total_required - target_aus
                requirement = next(item for item in curriculum["requirements"] if item["requirement_id"] == target_item["requirement_id"])
                requirement_minimums: dict[str, Decimal] = {}
                requirement_earned: dict[str, Decimal] = {}
                for item in curriculum["requirements"]:
                    path_category_aus = next((path.get("category_aus", {}).get(item["category"]) for path in curriculum.get("graduation_paths", []) if path["path_id"] == selected_path), None)
                    minimum = Decimal(str(item["minimum_aus"] if item["minimum_aus"] is not None else path_category_aus or 0))
                    is_target = item["requirement_id"] == requirement["requirement_id"]
                    if is_target and minimum < target_aus:
                        raise ValueError(
                            f"Target course {target_code} exceeds requirement "
                            f"{item['requirement_id']} for {student_id}"
                        )
                    requirement_minimums[item["requirement_id"]] = minimum
                    requirement_earned[item["requirement_id"]] = (
                        minimum - target_aus if is_target else minimum
                    )
                if sum(requirement_earned.values(), Decimal("0")) != earned_total:
                    raise ValueError(
                        f"Requirement credits do not reconcile for {student_id}"
                    )

                completed_requirement_id = completed_item["requirement_id"]
                exemptions = []
                for item in curriculum["requirements"]:
                    requirement_id = item["requirement_id"]
                    completed_credit = (
                        completed_aus
                        if requirement_id == completed_requirement_id
                        else Decimal("0")
                    )
                    exemption_credit = (
                        requirement_earned[requirement_id] - completed_credit
                    )
                    if exemption_credit < 0:
                        raise ValueError(
                            f"Completed course exceeds requirement credit for {student_id}"
                        )
                    if exemption_credit > 0:
                        exemptions.append({
                            "exemption_id": (
                                f"exemption.{student_id.lower()}."
                                f"{item['category'].lower()}"
                            ),
                            "aus_awarded": exemption_credit,
                            "category": item["category"],
                            "reason": (
                                "Scenario-bounded prior credit allocated to this "
                                "curriculum requirement category."
                            ),
                        })
                assumption_id = f"assumption.{details['configuration']}.terminal"
                student = _generated(
                    Student,
                    student_id,
                    [
                        curriculum["curriculum_id"],
                        f"course.{target_code}",
                        f"course.{completed_code}",
                        POLICY_IDS[0],
                    ],
                    student_id=student_id,
                    simulation_scope_id=scope.simulation_scope_id,
                    simulation_period_id=SIMULATION_PERIOD_ID,
                    programme=programme,
                    curriculum_id=curriculum["curriculum_id"],
                    graduation_path_id=selected_path,
                    study_plan_path_label=selected_label,
                    admission_cohort=curriculum["admission_cohort"],
                    study_year=scope.terminal_study_year,
                    terminal_profile=profile,
                    academic_standing="GOOD_STANDING",
                    has_outstanding_fees=False,
                    completed_courses=[{
                        "course_code": completed["code"],
                        "grade": ("A-", "B+", "B", "C+")[(serial - 1) % 4],
                        "aus_earned": completed_aus,
                        "credit_status": CreditStatus.EARNED,
                        "academic_year": ("AY2026-27", "AY2027-28")[(serial - 1) % 2],
                        "semester": "SEMESTER_2",
                        "attempt": 2 if serial % 5 == 0 else 1,
                    }],
                    earned_aus=earned_total,
                    exemptions=exemptions,
                    assumption_ids=[assumption_id],
                )
                students.append(student)
                students_by_profile[PROFILE_SHORT[profile]].append(student)

                indeterminate = profile == TerminalProfile.NO_VERIFIED_RESOLUTION.value
                progress = []
                for item in curriculum["requirements"]:
                    is_target = item["requirement_id"] == requirement["requirement_id"]
                    minimum = requirement_minimums[item["requirement_id"]]
                    progress.append({
                        "requirement_id": item["requirement_id"],
                        "status": RequirementStatus.INDETERMINATE if (is_target and indeterminate) else RequirementStatus.OUTSTANDING if is_target else RequirementStatus.SATISFIED,
                        "required_aus": None if (is_target and indeterminate) else minimum,
                        "earned_aus": requirement_earned[item["requirement_id"]],
                        "completed_courses": [completed_code] if item["requirement_id"] == completed_requirement_id else [], "outstanding_courses": [target_code] if is_target else [],
                        "explanation": "Published curriculum coverage is insufficient to verify this terminal requirement." if (is_target and indeterminate) else "The selected required course remains outstanding in this scenario-bounded audit." if is_target else "Requirement is treated as satisfied within the bounded scenario assumptions.",
                        "evidence_rule_ids": [
                            curriculum["curriculum_id"],
                            item["requirement_id"],
                            *(
                                [f"course.{target_code}"]
                                if is_target
                                else []
                            ),
                            *(
                                [f"course.{completed_code}"]
                                if item["requirement_id"]
                                == completed_requirement_id
                                else []
                            ),
                        ],
                        "assumption_ids": [assumption_id],
                        "limitations": ["Published requirement mapping remains partial."] if (is_target and indeterminate) else [],
                    })
                audit = _generated(
                    DegreeAudit,
                    f"audit.{student_id.lower()}",
                    [curriculum["curriculum_id"], *(item["requirement_id"] for item in curriculum["requirements"]), f"course.{target_code}", f"course.{completed_code}", POLICY_IDS[0]],
                    audit_id=f"audit.{student_id.lower()}", student_id=student_id,
                    simulation_scope_id=scope.simulation_scope_id, simulation_period_id=SIMULATION_PERIOD_ID,
                    curriculum_id=curriculum["curriculum_id"], audit_basis=AuditBasis.SCENARIO_BOUNDED_SIMULATION,
                    audit_outcome=AuditOutcome.INDETERMINATE if indeterminate else AuditOutcome.NOT_READY,
                    graduation_path_id=selected_path, study_plan_path_label=selected_label,
                    simulation_academic_year=scope.simulation_academic_year, semester="SEMESTER_1",
                    requirement_results=progress, total_earned_aus=earned_total,
                    total_required_aus=None if indeterminate else total_required,
                    assumption_ids=[assumption_id], limitations=["Public sources do not establish an official graduation clearance."] if indeterminate else [],
                )
                audits.append(audit)

                # The exception target remains missing; registration contains a
                # different grounded course/index from the real template set.
                base_codes = [
                    code
                    for code in grounded_plan_codes
                    if code != target_code
                    and code != completed["code"]
                    and by_course.get(code)
                ]
                if not base_codes:
                    raise ValueError(f"No registration base course for {student_id}")
                alternative_offering: dict[str, Any]
                alternative_index: dict[str, Any]
                if needs_feasible_registration:
                    feasible_tuple = next(
                        (
                            (
                                primary_offering,
                                primary_index,
                                alternate_offering,
                                alternate_index,
                                candidate_base_code,
                                candidate_base_offering,
                                candidate_base_index,
                            )
                            for primary_offering, primary_index in by_course[target_code]
                            for alternate_offering, alternate_index in by_course[target_code]
                            if (
                                primary_index["index_id"]
                                != alternate_index["index_id"]
                                and _index_is_concrete(primary_index)
                                and _index_is_concrete(alternate_index)
                                and (
                                    family_hint != "S7"
                                    or profile_position != 24
                                    or state_by_pair[
                                        (
                                            primary_offering["offering_id"],
                                            primary_index["index_id"],
                                        )
                                    ].vacancies
                                    == 1
                                )
                            )
                            for candidate_base_code in base_codes
                            if (
                                Decimal(str(courses[target_code]["aus"]))
                                + Decimal(str(courses[candidate_base_code]["aus"]))
                                <= Decimal("21")
                                and candidate_base_code
                                not in courses[target_code]["exclusions"]
                                and target_code
                                not in courses[candidate_base_code]["exclusions"]
                                and evaluate_prerequisite(
                                    courses[candidate_base_code][
                                        "prerequisites"
                                    ].get("raw_text"),
                                    completed_courses=(completed_code,),
                                    study_year=scope.terminal_study_year,
                                )
                                is PrerequisiteResult.PASS
                            )
                            for candidate_base_offering, candidate_base_index in by_course[
                                candidate_base_code
                            ]
                            if (
                                _index_is_concrete(candidate_base_index)
                                and (
                                    _indexes_conflict(
                                        primary_index, candidate_base_index
                                    )
                                    if family_hint in {"S1", "S4"}
                                    else not _indexes_conflict(
                                        primary_index, candidate_base_index
                                    )
                                )
                                and not _indexes_conflict(
                                    alternate_index, candidate_base_index
                                )
                            )
                        ),
                        None,
                    )
                    if feasible_tuple is None:
                        raise ValueError(
                            "No prerequisite/timetable/workload-safe tuple for "
                            f"{student_id}"
                        )
                    (
                        target_offering,
                        target_index,
                        alternative_offering,
                        alternative_index,
                        base_code,
                        base_offering,
                        base_index,
                    ) = feasible_tuple
                else:
                    base_code = base_codes[0]
                    base_offering, base_index = by_course[base_code][
                        serial % len(by_course[base_code])
                    ]
                    alternative_offering, alternative_index = next(
                        pair
                        for pair in by_course[target_code]
                        if pair[1]["index_id"] != target_index["index_id"]
                    )
                target_by_student[student_id] = (
                    target_item,
                    target_offering,
                    target_index,
                    alternative_offering,
                    alternative_index,
                )
                base_state = state_by_pair[(base_offering["offering_id"], base_index["index_id"])]
                registration_item = {
                    "registration_item_id": f"regitem.{student_id.lower()}.1", "course_code": base_code,
                    "template_offering_id": base_offering["offering_id"], "template_index_id": base_index["index_id"],
                    "offering_state_id": base_state.state_id, "expected_state_version": 1,
                    "aus": Decimal(str(courses[base_code]["aus"])), "status": RegistrationItemStatus.REGISTERED,
                    "eligibility": "ELIGIBLE", "eligibility_reason": "Eligible under the scenario-bounded record.",
                }
                registered_items = [registration_item]
                # Preserve the real 0-AU HW0001 contract in one actual registration.
                if student_id == students[0].student_id and "HW0001" in by_course:
                    hw_offering, hw_index = by_course["HW0001"][0]
                    hw_state = state_by_pair[(hw_offering["offering_id"], hw_index["index_id"])]
                    registered_items.append({
                        "registration_item_id": f"regitem.{student_id.lower()}.hw0001", "course_code": "HW0001",
                        "template_offering_id": hw_offering["offering_id"], "template_index_id": hw_index["index_id"],
                        "offering_state_id": hw_state.state_id, "expected_state_version": 1, "aus": Decimal("0"),
                        "status": RegistrationItemStatus.REGISTERED, "eligibility": "ELIGIBLE", "eligibility_reason": "QET support course retained at its sourced zero AU.",
                    })
                timetable = []
                for item in registered_items:
                    _, template_index = next(pair for pair in indexes if pair[0]["offering_id"] == item["template_offering_id"] and pair[1]["index_id"] == item["template_index_id"])
                    for meeting_no, meeting in enumerate(template_index["meetings"], start=1):
                        timetable.append({"meeting_id": f"meeting.{item['registration_item_id']}.{meeting_no}", "registration_item_id": item["registration_item_id"], "course_code": item["course_code"], "template_offering_id": item["template_offering_id"], "template_index_id": item["template_index_id"], "meeting": meeting})
                registrations.append(_generated(
                    Registration, f"registration.{student_id.lower()}", [curriculum["curriculum_id"], f"course.{base_code}", POLICY_IDS[1], POLICY_IDS[2]],
                    registration_id=f"registration.{student_id.lower()}", student_id=student_id,
                    simulation_scope_id=scope.simulation_scope_id, simulation_period_id=SIMULATION_PERIOD_ID,
                    simulation_academic_year=scope.simulation_academic_year, semester="SEMESTER_1",
                    template_academic_year="AY2026-27", template_semester="SEMESTER_1", scenario_time=_scope_time(str(scope.simulation_academic_year), "09:00:00"),
                    phase=RegistrationPhase.ADD_DROP if family_hint in {"S1", "S7"} else RegistrationPhase.POST_ADD_DROP, registered_courses=registered_items, timetable=timetable,
                    workload_aus=sum((Decimal(str(item["aus"])) for item in registered_items), Decimal("0")), workload_limit_aus=21,
                    missing_required_courses=[target_code], assumption_ids=[assumption_id],
                ))

    if len(students) != 240 or {key: len(value) for key, value in students_by_profile.items()} != {"P1": 60, "P2": 60, "P3": 60, "P4": 60}:
        raise ValueError("student allocation does not satisfy the Stage 3 contract")
    audit_by_student = {str(audit.student_id): audit for audit in audits}
    registration_by_student = {str(record.student_id): record for record in registrations}

    cases: list[ExceptionCase] = []
    approvals: list[Approval] = []
    scripts: list[TransactionScript] = []
    scenarios: list[Scenario] = []
    cases_by_family: dict[str, list[Student]] = defaultdict(list)
    for student in students:
        family = family_by_student[str(student.student_id)]
        if family is not None:
            cases_by_family[family].append(student)

    # Make the polished version-conflict demo use the documented DSAI source
    # conflict while preserving the 10 P1 + 10 P4 S3 profile allocation.
    s3_students = cases_by_family["S3"]
    dsai_demo = next(
        student
        for student in students_by_profile["P1"]
        if str(student.curriculum_id) == "curriculum.dsai.ay2025-26"
        and student not in cases_by_family["S1"]
    )
    if dsai_demo in s3_students:
        dsai_position = s3_students.index(dsai_demo)
        s3_students[4], s3_students[dsai_position] = (
            s3_students[dsai_position],
            s3_students[4],
        )
    else:
        replaced_p1_position = next(
            position
            for position, student in enumerate(s3_students)
            if student.terminal_profile
            is TerminalProfile.REQUIREMENT_OUTSTANDING
        )
        if replaced_p1_position == 4:
            s3_students[4] = dsai_demo
        else:
            s3_students[4], s3_students[replaced_p1_position] = (
                dsai_demo,
                s3_students[4],
            )

    expected_family_counts = {family: 20 for family in FAMILY_ENUM}
    actual_family_counts = {
        family: len(cases_by_family[family]) for family in FAMILY_ENUM
    }
    if actual_family_counts != expected_family_counts:
        raise ValueError(
            f"case family allocation mismatch: {actual_family_counts}"
        )
    case_students = [
        str(student.student_id)
        for family in sorted(cases_by_family)
        for student in cases_by_family[family]
    ]
    if len(case_students) != len(set(case_students)):
        raise ValueError("case allocation reused a student across families")

    approval_lookup: dict[str, Approval] = {}
    for family in sorted(cases_by_family):
        for position, student in enumerate(cases_by_family[family]):
            label = _split_label(position)
            scenario_id = f"{family}-{label}"
            submission_ready, unresolved_questions = _observable_intake_readiness(
                family, position
            )
            case_key = str(student.student_id).lower()
            case_id = f"case.{case_key}"
            script_id = f"script.{scenario_id.lower()}"
            audit = audit_by_student[str(student.student_id)]
            registration = registration_by_student[str(student.student_id)]
            (
                target_item,
                target_offering,
                target_index,
                alternative_offering,
                alternative_index,
            ) = target_by_student[str(student.student_id)]
            target_code = target_item["course_code"]
            scope = next(scope for scope in scopes if str(scope.simulation_scope_id) == str(student.simulation_scope_id))
            assumption_id = f"assumption.{scope_info[str(student.simulation_scope_id)]['configuration']}.terminal"
            scenario_time = _scope_time(str(scope.simulation_academic_year), "09:00:00")
            case_time = _scope_time(str(scope.simulation_academic_year), "08:45:00")
            event_time = _scope_time(str(scope.simulation_academic_year), "09:01:00")
            retry_time = _scope_time(str(scope.simulation_academic_year), "09:02:00")
            problem = {
                "S1": ExceptionCaseType.REGISTRATION_AFTER_DEADLINE, "S2": ExceptionCaseType.PREREQUISITE_WAIVER,
                "S3": ExceptionCaseType.GRADUATION_REQUIREMENT, "S4": ExceptionCaseType.TIMETABLE_CONFLICT,
                "S5": ExceptionCaseType.CROSS_PROGRAMME, "S6": ExceptionCaseType.COURSE_UNAVAILABLE,
                "S7": ExceptionCaseType.REGISTRATION_AFTER_DEADLINE,
            }[family]
            if family == "S2":
                case_policy_ids = [
                    "policy.exception.exchange.pending_transfer"
                    if position < 12
                    else "unknown.exception.general_prerequisite_waiver"
                ]
                document_types = (
                    "UNOFFICIAL_TRANSCRIPT",
                    "REQUESTED_COURSE_MAPPING",
                    "PREREQUISITE_COURSE_MAPPING",
                    "FOREIGN_COURSE_MAPPING",
                )
            else:
                case_policy_ids = {
                    "S1": ["policy.registration.stars_guide.functions"],
                    "S3": ["policy.registration.graduation_baseline"],
                    "S4": ["unknown.exception.general_clash_waiver"],
                    "S5": ["unknown.exception.substitution"],
                    "S6": ["unknown.exception.substitution"],
                    "S7": ["unknown.registration.live_allocation"],
                }[family]
                document_types = ("SCENARIO_SUPPORTING_RECORD",)
            documents = [
                {
                    "document_id": (
                        f"document.{case_key}.{document_type.lower()}"
                    ),
                    "document_type": document_type,
                    "provided": True,
                    "verified": None,
                }
                for document_type in document_types
            ]
            case_evidence = [
                {
                    "evidence_id": f"evidence.{case_key}.audit",
                    "evidence_type": "SCENARIO_AUDIT",
                    "reference": str(audit.audit_id),
                }
            ]
            if family == "S2":
                prerequisite_codes = re.findall(
                    r"\b[A-Z]{2}\d{4}\b",
                    courses[target_code]["prerequisites"]["raw_text"] or "",
                )
                if not prerequisite_codes:
                    raise ValueError(
                        f"S2 target {target_code} has no mappable prerequisite code"
                    )
                mapped_prerequisite = prerequisite_codes[0]
                case_evidence.extend(
                    [
                        {
                            "evidence_id": f"evidence.{case_key}.foreign-course",
                            "evidence_type": "SIMULATED_FOREIGN_COURSE_RESULT",
                            "reference": (
                                "SIMULATED foreign course FX2001 completed with "
                                "a passing result; transfer remains pending."
                            ),
                        },
                        {
                            "evidence_id": f"evidence.{case_key}.requested-mapping",
                            "evidence_type": "REQUESTED_COURSE_MAPPING",
                            "reference": f"Requested NTU course: {target_code}.",
                        },
                        {
                            "evidence_id": f"evidence.{case_key}.prerequisite-mapping",
                            "evidence_type": "PREREQUISITE_COURSE_MAPPING",
                            "reference": (
                                "SIMULATED mapping: foreign course FX2001 is "
                                f"proposed as equivalent to NTU prerequisite "
                                f"{mapped_prerequisite}. Published expression for "
                                f"{target_code}: "
                                f"{courses[target_code]['prerequisites']['raw_text']}."
                            ),
                        },
                    ]
                )
            case_rules = [
                str(student.curriculum_id),
                f"course.{target_code}",
                *case_policy_ids,
                POLICY_IDS[0],
            ]
            case = _generated(
                ExceptionCase, case_id, case_rules,
                case_id=case_id, student_id=student.student_id, simulation_scope_id=student.simulation_scope_id,
                audit_id=audit.audit_id, registration_id=registration.registration_id, scenario_time=scenario_time,
                problem_type=problem, reason=f"Terminal-stage registration or graduation exception concerning {target_code} after normal registration.",
                goal="Identify the supported exception route or the correct escalation.", requested_action="Assess and submit the appropriate exception action.",
                submission_ready=submission_ready,
                unresolved_questions=unresolved_questions,
                policy_section_ids=case_policy_ids, assumption_ids=[assumption_id], supporting_documents=documents,
                evidence=case_evidence,
                state=CaseState.WAITING_FOR_APPROVAL if family in {"S2", "S4", "S5"} else CaseState.OPEN, created_at=case_time,
            )
            cases.append(case)

            approval: Approval | None = None
            if family in {"S2", "S4", "S5"}:
                status = (ApprovalStatus.APPROVED if position < 8 else ApprovalStatus.REJECTED if position < 16 else ApprovalStatus.PENDING)
                verified_exchange_route = family == "S2" and position < 12
                approval_basis = (
                    "VERIFIED_PUBLIC_ROUTE"
                    if verified_exchange_route
                    else "SIMULATED_POLICY"
                )
                approval_basis_rules = (
                    case_policy_ids
                    if verified_exchange_route
                    else [POLICY_IDS[2], *case_policy_ids]
                )
                approval = _generated(
                    Approval, f"approval.{case_key}", [*approval_basis_rules, f"course.{target_code}"],
                    approval_id=f"approval.{case_key}", case_id=case_id, simulation_scope_id=student.simulation_scope_id,
                    approver_role="CCDS Undergraduate Office", requested_action="Review a scenario-bounded exception request.", status=status,
                    observable=False, basis=approval_basis, basis_rule_ids=approval_basis_rules, version=1,
                    required_document_ids=[item["document_id"] for item in documents],
                    decision_reason="The simulated evidence does not support this exception." if status is ApprovalStatus.REJECTED else None,
                    requested_at=scenario_time, decided_at=None if status is ApprovalStatus.PENDING else event_time,
                )
                approvals.append(approval)
                approval_lookup[case_id] = approval

            state = state_by_pair[(target_offering["offering_id"], target_index["index_id"])]
            alternative_state = state_by_pair[
                (
                    alternative_offering["offering_id"],
                    alternative_index["index_id"],
                )
            ]
            event: InjectedEvent | None = None
            steps: list[TransactionResult] = []
            if approval is not None:
                event_type = {ApprovalStatus.APPROVED: EventType.APPROVAL_GRANTED, ApprovalStatus.REJECTED: EventType.APPROVAL_REJECTED, ApprovalStatus.PENDING: EventType.APPROVAL_PENDING}[approval.status]
                event = InjectedEvent(event_id=f"event.{scenario_id.lower()}", event_type=event_type, target_type=StateTargetType.APPROVAL, target_id=approval.approval_id, expected_version=1, occurs_at=event_time)
                result = {ApprovalStatus.APPROVED: TransactionCode.SUCCESS, ApprovalStatus.REJECTED: TransactionCode.APPROVAL_REJECTED, ApprovalStatus.PENDING: TransactionCode.APPROVAL_PENDING}[approval.status]
                steps.append(_generated(TransactionResult, f"transaction.{scenario_id.lower()}.1", [POLICY_IDS[2]], transaction_id=f"transaction.{scenario_id.lower()}.1", case_id=case_id, action=TransactionAction.REQUEST_APPROVAL, action_parameters={"approval_id": approval.approval_id}, attempt_number=1, result_code=result, observation={TransactionCode.SUCCESS: "TRANSACTION_SUCCESS", TransactionCode.APPROVAL_REJECTED: "APPROVAL_REJECTED", TransactionCode.APPROVAL_PENDING: "APPROVAL_PENDING"}[result], retryable=False, message="Simulated approval state recorded.", error_code=None if result is TransactionCode.SUCCESS else "SIMULATED_APPROVAL_RESULT", event=event, precondition_state_versions={approval.approval_id: 1}, mutations=[{"mutation_id": f"mutation.{scenario_id.lower()}.approval", "target_type": "APPROVAL", "target_id": approval.approval_id, "expected_version": 1, "resulting_version": 2, "changes": {"status": approval.status.value, "observable": True}}], occurred_at=event_time))
                if approval.status is ApprovalStatus.APPROVED:
                    followup_action = {
                        "S2": TransactionAction.SUBMIT_WAIVER,
                        "S4": TransactionAction.SUBMIT_REGISTRATION,
                        "S5": TransactionAction.SUBMIT_EXCEPTION,
                    }[family]
                    followup_parameters: dict[str, Any] = {
                        "approval_id": approval.approval_id,
                        "course_code": target_code,
                    }
                    if family == "S4":
                        followup_parameters["offering_state_id"] = (
                            alternative_state.state_id
                        )
                    if family == "S5":
                        followup_parameters["curriculum_id"] = str(
                            student.curriculum_id
                        )
                        followup_parameters["graduation_path_id"] = str(
                            student.graduation_path_id
                        )
                    followup_versions = {str(approval.approval_id): 2}
                    if family == "S4":
                        followup_versions[str(alternative_state.state_id)] = 1
                    steps.append(
                        _generated(
                            TransactionResult,
                            f"transaction.{scenario_id.lower()}.2",
                            [POLICY_IDS[0], POLICY_IDS[2]],
                            transaction_id=f"transaction.{scenario_id.lower()}.2",
                            case_id=case_id,
                            action=followup_action,
                            action_parameters=followup_parameters,
                            attempt_number=2,
                            result_code=TransactionCode.SUCCESS,
                            observation="TRANSACTION_SUCCESS",
                            retryable=False,
                            message="The observable approval enables the bounded follow-up action.",
                            error_code=None,
                            precondition_state_versions=followup_versions,
                            occurred_at=retry_time,
                        )
                    )
            elif family == "S7":
                event_type = (EventType.VACANCY_BECOMES_ZERO, EventType.CLASS_BECOMES_UNAVAILABLE, EventType.TEMPORARY_TRANSACTION_FAILURE, EventType.STATE_CHANGED_BEFORE_COMMIT)[position % 4]
                event = InjectedEvent(event_id=f"event.{scenario_id.lower()}", event_type=event_type, target_type=StateTargetType.OFFERING_STATE, target_id=state.state_id, expected_version=1, occurs_at=event_time)
                result = {EventType.VACANCY_BECOMES_ZERO: TransactionCode.MODULE_FULL, EventType.CLASS_BECOMES_UNAVAILABLE: TransactionCode.CLASS_UNAVAILABLE, EventType.TEMPORARY_TRANSACTION_FAILURE: TransactionCode.TEMPORARY_SYSTEM_FAILURE, EventType.STATE_CHANGED_BEFORE_COMMIT: TransactionCode.STALE_STATE}[event_type]
                mutation = []
                if event_type is EventType.VACANCY_BECOMES_ZERO:
                    mutation = [{"mutation_id": f"mutation.{scenario_id.lower()}.vacancy", "target_type": "OFFERING_STATE", "target_id": state.state_id, "expected_version": 1, "resulting_version": 2, "changes": {"vacancies": 0, "available": False}}]
                elif event_type is EventType.CLASS_BECOMES_UNAVAILABLE:
                    mutation = [{"mutation_id": f"mutation.{scenario_id.lower()}.unavailable", "target_type": "OFFERING_STATE", "target_id": state.state_id, "expected_version": 1, "resulting_version": 2, "changes": {"runtime_status": "UNAVAILABLE", "available": False, "unavailable_reason": "Controlled simulator withdrawal."}}]
                elif event_type is EventType.STATE_CHANGED_BEFORE_COMMIT:
                    mutation = [{
                        "mutation_id": f"mutation.{scenario_id.lower()}.stale",
                        "target_type": "OFFERING_STATE",
                        "target_id": state.state_id,
                        "expected_version": 1,
                        "resulting_version": 2,
                        "changes": {
                            "waitlist_count": state.waitlist_count + 1,
                        },
                    }]
                steps.append(_generated(TransactionResult, f"transaction.{scenario_id.lower()}.1", [POLICY_IDS[2]], transaction_id=f"transaction.{scenario_id.lower()}.1", case_id=case_id, action=TransactionAction.SUBMIT_REGISTRATION, action_parameters={"offering_state_id": state.state_id}, attempt_number=1, result_code=result, observation={TransactionCode.MODULE_FULL: "MODULE_FULL", TransactionCode.CLASS_UNAVAILABLE: "CLASS_UNAVAILABLE", TransactionCode.TEMPORARY_SYSTEM_FAILURE: "TEMPORARY_FAILURE", TransactionCode.STALE_STATE: "STALE_STATE"}[result], retryable=True, message="Controlled dynamic event occurred; the case may retry only after refreshing or replanning.", error_code="SIMULATED_DYNAMIC_EVENT", event=event, precondition_state_versions={state.state_id: 1}, mutations=mutation, occurred_at=event_time))
                steps.append(_generated(TransactionResult, f"transaction.{scenario_id.lower()}.2", [POLICY_IDS[2]], transaction_id=f"transaction.{scenario_id.lower()}.2", case_id=case_id, action=TransactionAction.SUBMIT_REGISTRATION, action_parameters={"retry": True, "offering_state_id": alternative_state.state_id}, attempt_number=2, result_code=TransactionCode.SUCCESS, observation="TRANSACTION_SUCCESS", retryable=False, message="Alternative index or refreshed state resolves the simulated retry.", error_code=None, precondition_state_versions={alternative_state.state_id: 1}, occurred_at=retry_time))
            elif family == "S6":
                if position % 2 == 0:
                    event = InjectedEvent(event_id=f"event.{scenario_id.lower()}", event_type=EventType.REQUIRED_INFORMATION_MISSING, target_type=StateTargetType.CASE, target_id=case_id, occurs_at=event_time)
                    steps.append(_generated(TransactionResult, f"transaction.{scenario_id.lower()}.1", [POLICY_IDS[2]], transaction_id=f"transaction.{scenario_id.lower()}.1", case_id=case_id, action=TransactionAction.SUBMIT_EXCEPTION, action_parameters={}, attempt_number=1, result_code=TransactionCode.REQUIRED_INFORMATION_MISSING, observation="REQUIRED_INFORMATION_MISSING", retryable=False, message="The submission is missing a required simulated declaration.", error_code="MISSING_DECLARATION", event=event, precondition_state_versions={}, mutations=[], occurred_at=event_time))
                else:
                    event = InjectedEvent(
                        event_id=f"event.{scenario_id.lower()}",
                        event_type=EventType.CLASS_BECOMES_UNAVAILABLE,
                        target_type=StateTargetType.OFFERING_STATE,
                        target_id=state.state_id,
                        expected_version=1,
                        occurs_at=event_time,
                    )
                    steps.append(_generated(TransactionResult, f"transaction.{scenario_id.lower()}.1", [POLICY_IDS[0], POLICY_IDS[2]], transaction_id=f"transaction.{scenario_id.lower()}.1", case_id=case_id, action=TransactionAction.SUBMIT_EXCEPTION, action_parameters={"offering_state_id": state.state_id}, attempt_number=1, result_code=TransactionCode.CLASS_UNAVAILABLE, observation="CLASS_UNAVAILABLE", retryable=False, message="The last in-scope class becomes unavailable and no verified exception route remains.", error_code="NO_VERIFIED_ROUTE", event=event, precondition_state_versions={state.state_id: 1}, mutations=[{"mutation_id": f"mutation.{scenario_id.lower()}.unavailable", "target_type": "OFFERING_STATE", "target_id": state.state_id, "expected_version": 1, "resulting_version": 2, "changes": {"runtime_status": "UNAVAILABLE", "available": False, "unavailable_reason": "Controlled simulator withdrawal."}}], occurred_at=event_time))
            else:
                code = (
                    TransactionCode.REQUIRED_INFORMATION_MISSING
                    if family == "S3"
                    and student.terminal_profile
                    == TerminalProfile.NO_VERIFIED_RESOLUTION
                    else TransactionCode.SUCCESS
                )
                action = TransactionAction.SUBMIT_REGISTRATION if family == "S1" else TransactionAction.SUBMIT_EXCEPTION
                parameters = {"offering_state_id": alternative_state.state_id} if family == "S1" else {}
                steps.append(_generated(TransactionResult, f"transaction.{scenario_id.lower()}.1", [POLICY_IDS[0]], transaction_id=f"transaction.{scenario_id.lower()}.1", case_id=case_id, action=action, action_parameters=parameters, attempt_number=1, result_code=code, observation="REQUIRED_INFORMATION_MISSING" if code is TransactionCode.REQUIRED_INFORMATION_MISSING else "TRANSACTION_SUCCESS", retryable=False, message="The deterministic scenario route was assessed.", error_code="INSUFFICIENT_VERIFIED_INFORMATION" if code is TransactionCode.REQUIRED_INFORMATION_MISSING else None, precondition_state_versions={alternative_state.state_id: 1} if family == "S1" else {}, occurred_at=event_time))
            script = _generated(TransactionScript, script_id, [str(student.curriculum_id), f"course.{target_code}", POLICY_IDS[2]], script_id=script_id, case_id=case_id, simulation_scope_id=student.simulation_scope_id, steps=steps)
            scripts.append(script)
            resolved = family in {"S1", "S7"} or (family == "S3" and student.terminal_profile == TerminalProfile.REQUIREMENT_OUTSTANDING) or (approval is not None and approval.status is ApprovalStatus.APPROVED)
            expected = (
                ExpectedOutcome.RESOLVED
                if resolved
                else ExpectedOutcome.PENDING_APPROVAL
                if approval is not None and approval.status is ApprovalStatus.PENDING
                else ExpectedOutcome.CLARIFICATION_REQUIRED
                if (
                    (family == "S6" and position % 2 == 0)
                    or (
                        family == "S3"
                        and student.terminal_profile
                        == TerminalProfile.NO_VERIFIED_RESOLUTION
                    )
                )
                else ExpectedOutcome.ESCALATED
            )
            path_rules = [
                str(student.curriculum_id),
                f"course.{target_code}",
                *case_policy_ids,
                POLICY_IDS[0],
            ]

            def make_path(
                suffix: str,
                action: str,
                parameters: dict[str, Any],
                *,
                requires_approval: bool = False,
            ) -> dict[str, Any]:
                return {
                    "path_id": f"path.{scenario_id.lower()}.{suffix}",
                    "steps": [
                        {
                            "step_id": f"step.{suffix}",
                            "action": action,
                            "parameters": parameters,
                            "requires_approval": requires_approval,
                        }
                    ],
                    "rationale": (
                        "The path is constrained by the selected curriculum, "
                        "observable workflow state, and grounded index templates."
                    ),
                    "source_rule_ids": sorted(set(path_rules)),
                }

            valid_initial_paths: list[dict[str, Any]] = []
            valid_final_paths: list[dict[str, Any]] = []
            invalid_paths: list[dict[str, Any]] = []
            if approval is not None:
                valid_initial_paths.append(
                    make_path(
                        "request-approval",
                        "Request the declared human approval.",
                        {"approval_id": approval.approval_id},
                        requires_approval=True,
                    )
                )
                if family == "S4":
                    invalid_paths.append(
                        make_path(
                            "invalid-conflicting-index",
                            "Attempt the timetable-conflicting index.",
                            {"offering_state_id": state.state_id},
                        )
                    )
                if approval.status is ApprovalStatus.APPROVED:
                    followup_parameters = {
                        "approval_id": approval.approval_id,
                        "course_code": target_code,
                    }
                    followup_action = "Submit the approved exception action."
                    if family == "S4":
                        followup_parameters["offering_state_id"] = (
                            alternative_state.state_id
                        )
                        followup_action = (
                            "Register the conflict-free index after approval."
                        )
                    elif family == "S5":
                        followup_parameters.update(
                            {
                                "curriculum_id": str(student.curriculum_id),
                                "graduation_path_id": str(
                                    student.graduation_path_id
                                ),
                            }
                        )
                        followup_action = (
                            "Apply the approved integrated-programme path action."
                        )
                    valid_final_paths.append(
                        make_path(
                            "approved-followup",
                            followup_action,
                            followup_parameters,
                        )
                    )
            elif family == "S1":
                valid_initial_paths.append(
                    make_path(
                        "conflict-free-alternative",
                        "Register the conflict-free index during Add/Drop.",
                        {"offering_state_id": alternative_state.state_id},
                    )
                )
                invalid_paths.append(
                    make_path(
                        "invalid-conflicting-index",
                        "Attempt the timetable-conflicting preferred index.",
                        {"offering_state_id": state.state_id},
                    )
                )
            elif family == "S7":
                valid_initial_paths.append(
                    make_path(
                        "pre-event-index",
                        "Register the initially feasible index.",
                        {
                            "offering_state_id": state.state_id,
                            "expected_state_version": 1,
                        },
                    )
                )
                valid_final_paths.append(
                    make_path(
                        "post-event-alternative",
                        "Retry through the conflict-free alternative index.",
                        {"offering_state_id": alternative_state.state_id},
                    )
                )
                if event_type in {
                    EventType.TEMPORARY_TRANSACTION_FAILURE,
                    EventType.STATE_CHANGED_BEFORE_COMMIT,
                }:
                    valid_final_paths.append(
                        make_path(
                            "refreshed-original-index",
                            (
                                "Retry the original index after the transient "
                                "failure."
                                if event_type
                                is EventType.TEMPORARY_TRANSACTION_FAILURE
                                else "Re-query and retry the original index at its fresh version."
                            ),
                            {
                                "offering_state_id": state.state_id,
                                "expected_state_version": (
                                    1
                                    if event_type
                                    is EventType.TEMPORARY_TRANSACTION_FAILURE
                                    else 2
                                ),
                            },
                        )
                    )
                if event_type is not EventType.TEMPORARY_TRANSACTION_FAILURE:
                    invalid_parameters: dict[str, Any] = {
                        "offering_state_id": state.state_id
                    }
                    invalid_action = (
                        "Retry the index invalidated by the controlled event."
                    )
                    if event_type is EventType.STATE_CHANGED_BEFORE_COMMIT:
                        invalid_parameters["expected_state_version"] = 1
                        invalid_action = (
                            "Retry the original index with the stale observed version."
                        )
                    invalid_paths.append(
                        make_path(
                            "invalidated-index",
                            invalid_action,
                            invalid_parameters,
                        )
                    )
            elif resolved:
                valid_initial_paths.append(
                    make_path(
                        "grounded-resolution",
                        "Apply the scenario-bounded grounded resolution.",
                        {
                            "curriculum_id": str(student.curriculum_id),
                            "course_code": target_code,
                        },
                    )
                )
            ground_truth = ScenarioGroundTruth(
                valid_initial_paths=valid_initial_paths,
                valid_final_paths=valid_final_paths,
                invalid_paths=invalid_paths,
                requires_human=approval is not None,
                expected_outcome=expected,
            )
            multi_state_family = family in {"S1", "S4", "S7"}
            scenario_state_ids = (
                [state.state_id, alternative_state.state_id]
                if multi_state_family
                else [state.state_id]
            )
            initial_state = {
                "request_time": scenario_time,
                "target_course": target_code,
                "observed_state_versions": {
                    str(state_id): 1 for state_id in scenario_state_ids
                },
            }
            if multi_state_family:
                initial_state.update(
                    {
                        "preferred_offering_state_id": str(state.state_id),
                        "alternative_offering_state_id": str(
                            alternative_state.state_id
                        ),
                    }
                )
            scenarios.append(
                _generated(
                    Scenario,
                    scenario_id,
                    [
                        str(student.curriculum_id),
                        f"course.{target_code}",
                        POLICY_IDS[0],
                    ],
                    scenario_id=scenario_id,
                    family=FAMILY_ENUM[family],
                    split=_split_for(position),
                    simulation_scope_id=student.simulation_scope_id,
                    student_id=student.student_id,
                    curriculum_id=student.curriculum_id,
                    audit_id=audit.audit_id,
                    registration_id=registration.registration_id,
                    case_id=case_id,
                    offering_state_ids=scenario_state_ids,
                    transaction_script_id=script_id,
                    initial_state_refs=[
                        student.student_id,
                        audit.audit_id,
                        registration.registration_id,
                        case_id,
                        *scenario_state_ids,
                    ],
                    initial_state=initial_state,
                    injected_event=event,
                    ground_truth=ground_truth,
                )
            )

    assumptions: list[AuditAssumption] = []
    for scope in scopes:
        configuration = scope_info[str(scope.simulation_scope_id)]["configuration"]
        assumption_id = f"assumption.{configuration}.terminal"
        affected = [str(scope.simulation_scope_id)] + [
            str(record.student_id) for record in students if str(record.simulation_scope_id) == str(scope.simulation_scope_id)
        ] + [
            str(record.audit_id) for record in audits if str(record.simulation_scope_id) == str(scope.simulation_scope_id)
        ] + [
            str(record.registration_id) for record in registrations if str(record.simulation_scope_id) == str(scope.simulation_scope_id)
        ] + [
            str(record.case_id) for record in cases if str(record.simulation_scope_id) == str(scope.simulation_scope_id)
        ]
        assumptions.append(_generated(AuditAssumption, assumption_id, [str(scope.curriculum_id), POLICY_IDS[0]], assumption_id=assumption_id, simulation_scope_id=scope.simulation_scope_id, kind=AuditAssumptionKind.PROTOTYPE_MAPPING, description="Maps partial public curriculum content into a bounded terminal-stage audit scenario.", declared_value={"simulation_period_id": SIMULATION_PERIOD_ID, "template_semester": "SEMESTER_1"}, affected_record_ids=sorted(affected), limitations=["This is not an official NTU graduation audit."], prototype_policy_id=POLICY_IDS[0]))

    all_records = [*policies, *scopes, *assumptions, *offering_states, *students, *audits, *registrations, *cases, *approvals, *scripts, *scenarios]
    source_rules = {"rule.stage3.prototype_policy_contract"}
    for record in all_records:
        source_rules.update(str(value) for value in record.source_rule_ids)
        # Nested audit and resolution evidence is intentionally included too.
        if isinstance(record, DegreeAudit):
            source_rules.update(str(value) for progress in record.requirement_results for value in progress.evidence_rule_ids)
        if isinstance(record, Scenario):
            for path in (*record.ground_truth.valid_initial_paths, *record.ground_truth.valid_final_paths, *record.ground_truth.invalid_paths):
                source_rules.update(str(value) for value in path.source_rule_ids)
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(real_dir.rglob("*")) if path.is_file()}
    if len(hashes) != len([path for path in real_dir.rglob("*") if path.is_file()]):
        raise ValueError("real-data basenames must be unique for safe frozen hashes")
    manifest = GenerationManifest(manifest_id="manifest.stage3.ntu_ccds", generator_version=GENERATOR_VERSION, global_seed=GLOBAL_SEED, generated_at=GENERATED_AT, coverage_contract_id=str(real_repository.coverage.contract_id), real_data_hashes=hashes, source_rule_ids=sorted(source_rules), simulation_period_ids=[SIMULATION_PERIOD_ID], simulation_period_rule="One abstract terminal Semester 1 period maps to a scope-specific counterfactual academic year; AY2026-27 Semester 1 offerings are templates only.", prototype_policies=policies, prototype_policy_versions={str(policy.policy_id): str(policy.version) for policy in policies}, record_counts={"simulation_scopes": len(scopes), "audit_assumptions": len(assumptions), "prototype_policies": len(policies), "offering_states": len(offering_states), "students": len(students), "degree_audits": len(audits), "current_registrations": len(registrations), "exception_cases": len(cases), "approvals": len(approvals), "transaction_scripts": len(scripts), "scenarios": len(scenarios)})
    bundle = Stage3DataBundle(manifest=manifest, simulation_scopes=tuple(scopes), audit_assumptions=tuple(assumptions), offering_states=tuple(offering_states), students=tuple(students), degree_audits=tuple(audits), current_registrations=tuple(registrations), exception_cases=tuple(cases), approvals=tuple(approvals), transaction_scripts=tuple(scripts), scenarios=tuple(scenarios))
    issues = validate_stage3_data(real_repository, bundle, real_directory=real_dir)
    errors = [issue for issue in issues if issue.severity.value == "ERROR"]
    if errors:
        rendered = "\n".join(f"{issue.code}: {issue.dataset}/{issue.record_id} {issue.field}" for issue in errors[:20])
        raise ValueError(f"generated package failed cross-file validation:\n{rendered}")
    files = {
        "generation_manifest.json": manifest,
        "simulation_scope.json": sorted(scopes, key=lambda row: str(row.simulation_scope_id)),
        "audit_assumptions.json": sorted(assumptions, key=lambda row: str(row.assumption_id)),
        "offering_states.json": sorted(offering_states, key=lambda row: str(row.state_id)),
        "students.json": sorted(students, key=lambda row: str(row.student_id)),
        "degree_audits.json": sorted(audits, key=lambda row: str(row.audit_id)),
        "current_registrations.json": sorted(registrations, key=lambda row: str(row.registration_id)),
        "exception_cases.json": sorted(cases, key=lambda row: str(row.case_id)),
        "approvals.json": sorted(approvals, key=lambda row: str(row.approval_id)),
        "transaction_results.json": sorted(scripts, key=lambda row: str(row.script_id)),
        "__scenarios__": sorted(scenarios, key=lambda row: str(row.scenario_id)),
    }
    return files, bundle


def _write_atomically(files: dict[str, Any], output_dir: Path, scenarios_path: Path, *, check: bool) -> int:
    encoded = {name: _json_bytes(value) for name, value in files.items()}
    destinations = {name: (scenarios_path if name == "__scenarios__" else output_dir / name) for name in encoded}
    if check:
        drift = [str(destination) for name, destination in destinations.items() if not destination.exists() or destination.read_bytes() != encoded[name]]
        if drift:
            print("Stage 3 generated data differs: " + ", ".join(drift), file=sys.stderr)
            return 1
        print("Stage 3 generated data is current.")
        return 0
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".stage3-data-", dir=output_dir.parent) as temporary:
        temporary_root = Path(temporary)
        staged = {name: temporary_root / name for name in encoded}
        for name, path in staged.items():
            path.write_bytes(encoded[name])
        for name, destination in destinations.items():
            os.replace(staged[name], destination)
    print(f"Generated {len(encoded) - 1} simulated files and {scenarios_path}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-dir", type=Path, default=REPO_ROOT / "data" / "real")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "data" / "simulated")
    parser.add_argument("--scenarios-path", type=Path, default=REPO_ROOT / "data" / "tests" / "scenarios.json")
    parser.add_argument("--check", action="store_true", help="validate deterministic output without writing files")
    args = parser.parse_args(argv)
    files, _ = _build(args.real_dir.resolve())
    return _write_atomically(files, args.output_dir.resolve(), args.scenarios_path.resolve(), check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
