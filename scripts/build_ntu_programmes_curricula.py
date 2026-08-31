"""Build the official-public CCDS programme and AY2025 curriculum inventories.

The programme list and non-PDF curriculum facts are transcribed from the public
NTU pages named in the source manifest.  Detailed study-plan rows are normalized
from ``tmp/extracted_curricula.json``, the intermediate produced from the
retrieved AY2025-26 curriculum PDFs.  Raw PDFs are intentionally not copied into
the repository because several carry an NTU ``Classification: Restricted``
footer despite being served from public URLs.

This script does not resolve source conflicts.  It preserves the selected value,
the competing source in ``source_ids``, and a human-readable ``known_gaps``
entry so downstream logic cannot mistake a partial public snapshot for an
authenticated degree audit.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROGRAMME_SOURCE_ID = "ntu.ccds.programmes.current"


def programme(
    code: str,
    name: str,
    kind: str,
    *,
    base: tuple[str, ...] = (),
    portal_code: str | None = None,
    study_mode: str = "FULL_TIME",
) -> dict[str, Any]:
    external_identifiers: dict[str, str] = {}
    if portal_code is not None:
        external_identifiers["ntu_course_portal_code"] = portal_code
    return {
        "programme_id": f"programme.{code.lower()}",
        "code": code,
        "name": name,
        "college": "College of Computing and Data Science",
        "programme_kind": kind,
        "study_mode": study_mode,
        "ccds_base_programmes": list(base),
        "external_identifiers": external_identifiers,
        "active": True,
        "source_ids": [PROGRAMME_SOURCE_ID],
    }


PROGRAMMES = [
    programme(
        "AISC",
        "Bachelor of Computing (Hons) in Artificial Intelligence (AI) and Society",
        "SINGLE_DEGREE",
        portal_code="AISC",
    ),
    programme(
        "CSC",
        "Bachelor of Computing (Hons) in Computer Science",
        "SINGLE_DEGREE",
        portal_code="CSC",
    ),
    programme(
        "CE",
        "Bachelor of Engineering (Hons) in Computer Engineering",
        "SINGLE_DEGREE",
        portal_code="CE",
    ),
    programme(
        "DSAI",
        "Bachelor of Computing (Hons) in Data Science and Artificial Intelligence",
        "SINGLE_DEGREE",
        portal_code="DSAI",
    ),
    programme(
        "BCG",
        "Double Degree in Computer Science and Business (specialisation in Business Analytics)",
        "DOUBLE_DEGREE",
        base=("CSC",),
        portal_code="BCG",
    ),
    programme(
        "BCE",
        "Double Degree in Computer Engineering and Business (specialisation in Business Analytics)",
        "DOUBLE_DEGREE",
        base=("CE",),
        portal_code="BCE",
    ),
    programme(
        "CSEC",
        "Double Degree in Computer Science and Economics",
        "DOUBLE_DEGREE",
        base=("CSC",),
        portal_code="CSEC",
    ),
    programme(
        "CEEC",
        "Double Degree in Computer Engineering and Economics",
        "DOUBLE_DEGREE",
        base=("CE",),
        portal_code="CEEC",
    ),
    programme(
        "ACDA",
        "Double Degree in Accountancy and Data Science and Artificial Intelligence",
        "DOUBLE_DEGREE",
        base=("DSAI",),
        portal_code="ACDA",
    ),
    programme(
        "CSC-ENT",
        "Bachelor of Computing (Hons) in Computer Science with a Second Major in Entrepreneurship",
        "SECOND_MAJOR",
        base=("CSC",),
    ),
    programme(
        "CSC-ITP",
        "Bachelor of Computing in Computer Science with Second Major in Business (International Trading)",
        "SECOND_MAJOR",
        base=("CSC",),
    ),
    programme(
        "CSC-SUST",
        "Bachelor of Computing (Hons) in Computer Science with a Second Major in Sustainability",
        "SECOND_MAJOR",
        base=("CSC",),
    ),
    programme(
        "CE-DANA",
        "Bachelor of Engineering (Hons) in Computer Engineering with a Second Major in Data Analytics",
        "SECOND_MAJOR",
        base=("CE",),
    ),
    programme(
        "CE-ENT",
        "Bachelor of Engineering (Hons) in Computer Engineering with Second Major in Entrepreneurship",
        "SECOND_MAJOR",
        base=("CE",),
    ),
    programme(
        "CE-ITP",
        "Bachelor of Engineering in Computer Engineering with Second Major in Business (International Trading)",
        "SECOND_MAJOR",
        base=("CE",),
    ),
    programme(
        "CE-SUST",
        "Bachelor of Engineering (Hons) in Computer Engineering with a Second Major in Sustainability",
        "SECOND_MAJOR",
        base=("CE",),
    ),
    programme(
        "CE-BUS",
        "Bachelor of Engineering in Computer Engineering with Second Major in Business",
        "SECOND_MAJOR",
        base=("CE",),
    ),
    programme(
        "DSAI-SUST",
        "Bachelor of Computing (Hons) in Data Science and Artificial Intelligence with a Second Major in Sustainability",
        "SECOND_MAJOR",
        base=("DSAI",),
    ),
    programme(
        "BACF",
        "Bachelor of Applied Computing in Finance",
        "JOINT_DEGREE",
        portal_code="BACF",
    ),
    programme(
        "ECDS",
        "Bachelor of Science in Economics and Data Science",
        "JOINT_DEGREE",
        portal_code="ECDS",
    ),
    programme(
        "MACS",
        "Bachelor of Science in Mathematical and Computer Sciences",
        "JOINT_DEGREE",
        portal_code="MACS",
    ),
    programme(
        "BTECH-COMP",
        "Bachelor of Technology in Computing (A SkillsFuture Work-Study Degree)",
        "PART_TIME_DEGREE",
        study_mode="PART_TIME",
    ),
]


def requirement(
    prefix: str,
    category: str,
    name: str,
    aus: int | None = None,
    *,
    minimum_courses: int | None = None,
    required_courses: tuple[str, ...] = (),
    constraints: tuple[str, ...] = (),
    course_lists_completeness: str | None = None,
) -> dict[str, Any]:
    if course_lists_completeness is None:
        course_lists_completeness = "PARTIAL" if required_courses else "UNAVAILABLE"
    return {
        "requirement_id": f"requirement.{prefix}.{category.lower()}",
        "name": name,
        "category": category,
        "minimum_aus": aus,
        "minimum_courses": minimum_courses,
        "required_courses": list(required_courses),
        "elective_pool": [],
        "constraints": list(constraints),
        "course_lists_completeness": course_lists_completeness,
    }


def path(
    path_id: str,
    name: str,
    total: int,
    category_aus: dict[str, int],
    *,
    course_counts: dict[str, int] | None = None,
    components: tuple[str, ...] = (),
    constraints: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "path_id": path_id,
        "name": name,
        "graduation_aus": total,
        "category_aus": category_aus,
        "minimum_course_counts": course_counts or {},
        "required_components": list(components),
        "constraints": list(constraints),
    }


def partial_curriculum(
    curriculum_id: str,
    name: str,
    programme_code: str,
    source_ids: tuple[str, ...],
    requirements: list[dict[str, Any]],
    gaps: tuple[str, ...],
    *,
    kind: str = "BASE",
    cohort: str = "AY2025-26",
    effective_year: str = "AY2025-26",
    total: int | None = None,
    paths: list[dict[str, Any]] | None = None,
    constraints: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "curriculum_id": curriculum_id,
        "name": name,
        "programme": programme_code,
        "configuration_kind": kind,
        "additional_applicable_programmes": [],
        "admission_cohort": cohort,
        "effective_academic_year": effective_year,
        "graduation_aus": total,
        "graduation_paths": paths or [],
        "requirements": requirements,
        "study_plan": [],
        "programme_constraints": list(constraints),
        "rules_completeness": "PARTIAL",
        "known_gaps": list(gaps),
        "unavailable_reason": None,
        "source_ids": list(source_ids),
    }


PUBLIC_AY25_GAPS = (
    "The exact AY2026-27 CCDS curriculum is available only through the authenticated student intranet; this record is the latest complete cohort sheet retrieved publicly.",
    "Published elective-pool membership and all conditional substitutions are not fully represented by the study-plan table.",
)


def build_pdf_curricula() -> dict[str, dict[str, Any]]:
    curricula: dict[str, dict[str, Any]] = {}

    curricula["aisc_ay2025.pdf"] = partial_curriculum(
        "curriculum.aisc.ay2025-26",
        "Artificial Intelligence and Society — AY2025-26",
        "AISC",
        ("ntu.ccds.curriculum.aisc.ay2025-26",),
        [
            requirement("aisc", "PROGRAMME_CORE", "Programme Core", 57),
            requirement(
                "aisc",
                "MPE",
                "Major Prescribed Electives",
                24,
                minimum_courses=8,
                constraints=(
                    "At least two MPE courses must be from the Technical group.",
                    "At least two MPE courses must be from the Society group.",
                ),
            ),
            requirement("aisc", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement("aisc", "PROFESSIONAL_SERIES", "Professional Series", 16),
            requirement("aisc", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
            requirement("aisc", "BDE", "Broadening and Deepening Electives", 17),
        ],
        PUBLIC_AY25_GAPS,
        total=131,
    )

    curricula["ce_ay2025.pdf"] = partial_curriculum(
        "curriculum.ce.ay2025-26",
        "Computer Engineering — revised AY2025-26",
        "CE",
        ("ntu.ccds.curriculum.ce.ay2025-26",),
        [
            requirement("ce", "PROGRAMME_CORE", "Programme Core", 65),
            requirement(
                "ce",
                "MPE",
                "Major Prescribed Electives",
                18,
                constraints=(
                    "The revised source assigns 18 AU to MPE.",
                    "The source study plan distinguishes SC3xxx/SC4xxx and SC4xxx MPE slots.",
                ),
            ),
            requirement("ce", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement("ce", "PROFESSIONAL_SERIES", "Professional Series", 16),
            requirement("ce", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
            requirement("ce", "BDE", "Broadening and Deepening Electives", 20),
        ],
        PUBLIC_AY25_GAPS,
        total=136,
    )

    curricula["csc_ay2025.pdf"] = partial_curriculum(
        "curriculum.csc.ay2025-26",
        "Computer Science — AY2025-26",
        "CSC",
        ("ntu.ccds.curriculum.csc.ay2025-26",),
        [
            requirement("csc", "PROGRAMME_CORE", "Programme Core", 47),
            requirement(
                "csc",
                "MPE",
                "Major Prescribed Electives and FYP alternative",
                None,
                constraints=("The AU requirement is path-dependent.",),
            ),
            requirement("csc", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement("csc", "PROFESSIONAL_SERIES", "Professional Series", 16),
            requirement("csc", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
            requirement("csc", "BDE", "Broadening and Deepening Electives", 20),
        ],
        PUBLIC_AY25_GAPS,
        paths=[
            path(
                "graduation_path.csc.fyp",
                "Final Year Project path",
                135,
                {"MPE": 35},
                course_counts={"MPE": 9},
                components=("SC4079 Final Year Project Parts 1 and 2 (8 AU total)",),
                constraints=("At least four MPE courses must be at SC4xxx level.",),
            ),
            path(
                "graduation_path.csc.coursework",
                "Additional MPE coursework path",
                136,
                {"MPE": 36},
                course_counts={"MPE": 12},
                constraints=(
                    "Three additional MPE courses replace the Final Year Project.",
                    "At least four MPE courses must be at SC4xxx level.",
                ),
            ),
        ],
        constraints=("Highest Distinction requires the Final Year Project path.",),
    )

    curricula["dsai_ay2025.pdf"] = partial_curriculum(
        "curriculum.dsai.ay2025-26",
        "Data Science and Artificial Intelligence — revised AY2025-26",
        "DSAI",
        ("ntu.ccds.curriculum.dsai.ay2025-26",),
        [
            requirement("dsai", "PROGRAMME_CORE", "Programme Core", 61),
            requirement("dsai", "MPE", "Major Prescribed Electives", 18),
            requirement("dsai", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement("dsai", "PROFESSIONAL_SERIES", "Professional Series", 16),
            requirement("dsai", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
            requirement("dsai", "BDE", "Broadening and Deepening Electives", 19),
        ],
        PUBLIC_AY25_GAPS,
        total=131,
    )

    curricula["bcg_ay2025.pdf"] = partial_curriculum(
        "curriculum.bcg.ay2025-26",
        "Computer Science and Business double degree — AY2025-26",
        "BCG",
        ("ntu.ccds.curriculum.bcg.ay2025-26",),
        [
            requirement("bcg", "CSC_CORE", "Computer Science Core", 44),
            requirement("bcg", "BUSINESS_CORE", "Business Core", 36),
            requirement(
                "bcg",
                "CSC_MPE",
                "Computer Science Major Prescribed Electives",
                None,
                constraints=("The AU requirement is path-dependent.",),
            ),
            requirement("bcg", "BUSINESS_MPE", "Business Major Prescribed Electives", 9),
            requirement("bcg", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement("bcg", "PROFESSIONAL_SERIES", "Professional Series", 14),
            requirement("bcg", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
        ],
        PUBLIC_AY25_GAPS,
        paths=[
            path(
                "graduation_path.bcg.fyp",
                "Final Year Project path",
                155,
                {"CSC_MPE": 35},
            ),
            path(
                "graduation_path.bcg.coursework",
                "Additional MPE coursework path",
                156,
                {"CSC_MPE": 36},
            ),
        ],
    )

    curricula["bce_ay2025.pdf"] = partial_curriculum(
        "curriculum.bce.ay2025-26",
        "Computer Engineering and Business double degree — AY2025-26",
        "BCE",
        ("ntu.ccds.curriculum.bce.ay2025-26",),
        [
            requirement("bce", "CE_CORE", "Computer Engineering Core", 65),
            requirement("bce", "BUSINESS_CORE", "Business Core", 36),
            requirement("bce", "CE_MPE", "Computer Engineering Major Prescribed Electives", 15),
            requirement("bce", "BUSINESS_MPE", "Business Major Prescribed Electives", 9),
            requirement("bce", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement("bce", "PROFESSIONAL_SERIES", "Professional Series", 14),
            requirement("bce", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
        ],
        PUBLIC_AY25_GAPS,
        total=156,
    )

    curricula["csec_ay2025.pdf"] = partial_curriculum(
        "curriculum.csec.ay2025-26",
        "Computer Science and Economics double degree — AY2025-26",
        "CSEC",
        ("ntu.ccds.curriculum.csec.ay2025-26",),
        [
            requirement("csec", "CSC_CORE", "Computer Science Core", 47),
            requirement("csec", "ECON_CORE", "Economics Core", 24),
            requirement(
                "csec",
                "CSC_MPE",
                "Computer Science Major Prescribed Electives",
                None,
                constraints=("The AU requirement is path-dependent.",),
            ),
            requirement("csec", "ECON_MPE", "Economics Major Prescribed Electives", 33),
            requirement("csec", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement(
                "csec",
                "PROFESSIONAL_SERIES",
                "Professional Series",
                None,
                constraints=("The AU requirement depends on the PI or PA path.",),
            ),
            requirement("csec", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
            requirement(
                "csec",
                "BDE",
                "Broadening and Deepening Electives",
                None,
                constraints=("The AU requirement depends on the PI or PA path.",),
            ),
        ],
        PUBLIC_AY25_GAPS,
        paths=[
            path(
                "graduation_path.csec.pi-fyp",
                "20-week Professional Internship with FYP",
                174,
                {"CSC_MPE": 35, "PROFESSIONAL_SERIES": 16, "BDE": 2},
            ),
            path(
                "graduation_path.csec.pi-coursework",
                "20-week Professional Internship with additional MPE coursework",
                175,
                {"CSC_MPE": 36, "PROFESSIONAL_SERIES": 16, "BDE": 2},
            ),
            path(
                "graduation_path.csec.pa-fyp",
                "10-week Professional Attachment with FYP",
                174,
                {"CSC_MPE": 35, "PROFESSIONAL_SERIES": 11, "BDE": 7},
            ),
            path(
                "graduation_path.csec.pa-coursework",
                "10-week Professional Attachment with additional MPE coursework",
                175,
                {"CSC_MPE": 36, "PROFESSIONAL_SERIES": 11, "BDE": 7},
            ),
        ],
    )

    curricula["ceec_ay2025.pdf"] = partial_curriculum(
        "curriculum.ceec.ay2025-26",
        "Computer Engineering and Economics double degree — AY2025-26",
        "CEEC",
        ("ntu.ccds.curriculum.ceec.ay2025-26",),
        [
            requirement("ceec", "CE_CORE", "Computer Engineering Core", 65),
            requirement("ceec", "ECON_CORE", "Economics Core", 24),
            requirement("ceec", "CE_MPE", "Computer Engineering Major Prescribed Electives", 18),
            requirement("ceec", "ECON_MPE", "Economics Major Prescribed Electives", 33),
            requirement("ceec", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement(
                "ceec",
                "PROFESSIONAL_SERIES",
                "Professional Series",
                None,
                constraints=("The AU requirement depends on the PI or PA path.",),
            ),
            requirement("ceec", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
            requirement(
                "ceec",
                "BDE",
                "Broadening and Deepening Electives",
                None,
                constraints=("The AU requirement depends on the PI or PA path.",),
            ),
        ],
        PUBLIC_AY25_GAPS,
        paths=[
            path(
                "graduation_path.ceec.pi",
                "20-week Professional Internship path",
                175,
                {"PROFESSIONAL_SERIES": 16, "BDE": 2},
            ),
            path(
                "graduation_path.ceec.pa",
                "10-week Professional Attachment path",
                175,
                {"PROFESSIONAL_SERIES": 11, "BDE": 7},
            ),
        ],
    )

    curricula["csc_ent_ay2025.pdf"] = partial_curriculum(
        "curriculum.csc-ent.ay2025-26",
        "Computer Science with Second Major in Entrepreneurship — AY2025-26",
        "CSC-ENT",
        ("ntu.ccds.curriculum.csc-ent.ay2025-26",),
        [
            requirement("csc-ent", "PROGRAMME_CORE", "Computer Science Core", 47),
            requirement(
                "csc-ent",
                "MPE",
                "Computer Science Major Prescribed Electives",
                None,
                constraints=("The AU requirement is path-dependent.",),
            ),
            requirement("csc-ent", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement("csc-ent", "PROFESSIONAL_SERIES", "Professional Series", 16),
            requirement("csc-ent", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
            requirement(
                "csc-ent",
                "ENTREPRENEURSHIP_SECOND_MAJOR",
                "Entrepreneurship second major",
                25,
            ),
        ],
        PUBLIC_AY25_GAPS,
        kind="OVERLAY",
        paths=[
            path(
                "graduation_path.csc-ent.fyp",
                "Final Year Project path",
                140,
                {"MPE": 35},
            ),
            path(
                "graduation_path.csc-ent.coursework",
                "Additional MPE coursework path",
                141,
                {"MPE": 36},
            ),
        ],
    )

    def csc_dual_path_overlay(
        filename: str,
        code: str,
        source_id: str,
        title: str,
        category: str,
        pi_overlay_aus: int,
        pa_overlay_aus: int,
        *,
        record_prefix: str | None = None,
    ) -> None:
        prefix = record_prefix or code.lower()
        curricula[filename] = partial_curriculum(
            f"curriculum.{prefix}.ay2025-26",
            f"{title} — AY2025-26",
            code,
            (source_id,),
            [
                requirement(prefix, "PROGRAMME_CORE", "Computer Science Core", 47),
                requirement(
                    prefix,
                    "MPE",
                    "Computer Science Major Prescribed Electives",
                    None,
                    constraints=("The AU requirement is path-dependent.",),
                ),
                requirement(prefix, "ICC_COMMON_CORE", "ICC Common Core", 14),
                requirement(
                    prefix,
                    "PROFESSIONAL_SERIES",
                    "Professional Series",
                    None,
                    constraints=("The AU requirement depends on the PI or PA path.",),
                ),
                requirement(prefix, "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
                requirement(
                    prefix,
                    category,
                    title.split(" with ", 1)[-1],
                    None,
                    constraints=("The AU requirement depends on the PI or PA path.",),
                ),
            ],
            PUBLIC_AY25_GAPS,
            kind="OVERLAY",
            paths=[
                path(
                    f"graduation_path.{prefix}.pi-fyp",
                    "20-week Professional Internship with FYP",
                    47 + 14 + 3 + 16 + pi_overlay_aus + 35,
                    {"MPE": 35, "PROFESSIONAL_SERIES": 16, category: pi_overlay_aus},
                ),
                path(
                    f"graduation_path.{prefix}.pi-coursework",
                    "20-week Professional Internship with additional MPE coursework",
                    47 + 14 + 3 + 16 + pi_overlay_aus + 36,
                    {"MPE": 36, "PROFESSIONAL_SERIES": 16, category: pi_overlay_aus},
                ),
                path(
                    f"graduation_path.{prefix}.pa-fyp",
                    "10-week Professional Attachment with FYP",
                    47 + 14 + 3 + 11 + pa_overlay_aus + 35,
                    {"MPE": 35, "PROFESSIONAL_SERIES": 11, category: pa_overlay_aus},
                ),
                path(
                    f"graduation_path.{prefix}.pa-coursework",
                    "10-week Professional Attachment with additional MPE coursework",
                    47 + 14 + 3 + 11 + pa_overlay_aus + 36,
                    {"MPE": 36, "PROFESSIONAL_SERIES": 11, category: pa_overlay_aus},
                ),
            ],
        )

    csc_dual_path_overlay(
        "csc_itp_ay2025.pdf",
        "CSC-ITP",
        "ntu.ccds.curriculum.csc-itp.ay2025-26",
        "Computer Science with Second Major in Business (International Trading)",
        "BUSINESS_ITP_SECOND_MAJOR",
        31,
        36,
    )
    csc_dual_path_overlay(
        "csc_sust_ay2025.pdf",
        "CSC-SUST",
        "ntu.ccds.curriculum.csc-sust.ay2025-26",
        "Computer Science with Second Major in Sustainability",
        "SUSTAINABILITY_SECOND_MAJOR",
        30,
        35,
    )

    # The mainstream CSC-Business curriculum is publicly listed in the current
    # curriculum overview but not as a separate pathway on the admissions index.
    # It therefore maps to the CSC programme rather than inventing a 23rd code.
    csc_dual_path_overlay(
        "csc_bus_ay2025.pdf",
        "CSC",
        "ntu.ccds.curriculum.csc-business.ay2025-26",
        "Computer Science with Second Major in Business",
        "BUSINESS_SECOND_MAJOR",
        30,
        35,
        record_prefix="csc-business",
    )

    curricula["ce_ent_ay2025.pdf"] = partial_curriculum(
        "curriculum.ce-ent.ay2025-26",
        "Computer Engineering with Second Major in Entrepreneurship — AY2025-26",
        "CE-ENT",
        ("ntu.ccds.curriculum.ce-ent.ay2025-26",),
        [
            requirement("ce-ent", "PROGRAMME_CORE", "Computer Engineering Core", 68),
            requirement("ce-ent", "MPE", "Computer Engineering Major Prescribed Electives", 15),
            requirement("ce-ent", "ENTREPRENEURSHIP_SECOND_MAJOR", "Entrepreneurship second major", 25),
            requirement("ce-ent", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement("ce-ent", "PROFESSIONAL_SERIES", "Professional Series", 16),
            requirement("ce-ent", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
        ],
        PUBLIC_AY25_GAPS,
        kind="OVERLAY",
        total=141,
    )

    curricula["ce_sust_ay2025.pdf"] = partial_curriculum(
        "curriculum.ce-sust.ay2025-26",
        "Computer Engineering with Second Major in Sustainability — AY2025-26",
        "CE-SUST",
        ("ntu.ccds.curriculum.ce-sust.ay2025-26",),
        [
            requirement("ce-sust", "PROGRAMME_CORE", "Computer Engineering Core", 65),
            requirement("ce-sust", "MPE", "Computer Engineering Major Prescribed Electives", 18),
            requirement("ce-sust", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement("ce-sust", "PROFESSIONAL_SERIES", "Professional Series", 16),
            requirement("ce-sust", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
            requirement("ce-sust", "SUSTAINABILITY_SECOND_MAJOR", "Sustainability second major / BDE", 28),
        ],
        PUBLIC_AY25_GAPS
        + (
            "The same published PDF reports 144 AU for the PI path but 116 AU for the PA path; the PA category cells also sum to 116. The anomalous 116-AU table is preserved in the path-labelled study plan but is not accepted as an alternative graduation total.",
        ),
        kind="OVERLAY",
        total=144,
    )

    curricula["dsai_sust_ay2025.pdf"] = partial_curriculum(
        "curriculum.dsai-sust.ay2025-26",
        "Data Science and Artificial Intelligence with Second Major in Sustainability — AY2025-26",
        "DSAI-SUST",
        (
            "ntu.ccds.curriculum.dsai-sust.ay2025-26",
            "ntu.ccds.curriculum.overview.current",
        ),
        [
            requirement("dsai-sust", "PROGRAMME_CORE", "DSAI Core", 61),
            requirement("dsai-sust", "MPE", "Major Prescribed Electives", 18),
            requirement("dsai-sust", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement("dsai-sust", "PROFESSIONAL_SERIES", "Professional Series", 16),
            requirement("dsai-sust", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
            requirement("dsai-sust", "SUSTAINABILITY_SECOND_MAJOR", "Sustainability second major / BDE", 30),
        ],
        PUBLIC_AY25_GAPS
        + (
            "The dated revised AY2025-26 PDF totals 142 AU, while the current public overview reports 141 AU; this record selects the dated cohort PDF and retains the conflict.",
        ),
        kind="OVERLAY",
        total=142,
    )

    # The current revised CE-DANA PDF is recoverable through NTU's indexed text,
    # even though a fresh direct request returns unavailable.  Its detailed plan
    # is transcribed below; the older accessible 156-AU PDF is retained only as
    # provenance for the source conflict.
    curricula["ce_dana_ay2025.pdf"] = partial_curriculum(
        "curriculum.ce-dana.ay2025-26",
        "Computer Engineering with Second Major in Data Analytics — AY2025-26 revised total",
        "CE-DANA",
        (
            "ntu.ccds.curriculum.ce-dana.ay2025-26.revised-index",
            "ntu.ccds.curriculum.ce-dana.ay2025-26.legacy",
        ),
        [
            requirement("ce-dana", "PROGRAMME_CORE", "Computer Engineering Core", 65),
            requirement(
                "ce-dana",
                "MPE",
                "Computer Engineering Major Prescribed Electives",
                18,
                minimum_courses=6,
                constraints=("At least four of the six MPE courses must be at SC4xxx level.",),
            ),
            requirement("ce-dana", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement("ce-dana", "PROFESSIONAL_SERIES", "Professional Series", 16),
            requirement("ce-dana", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
            requirement(
                "ce-dana",
                "DATA_ANALYTICS_BDE",
                "Second Major in Data Analytics / BDE",
                20,
                constraints=(
                    "The source distinguishes double-counted DANA core courses and three DANA electives.",
                ),
            ),
        ],
        (
            "The current revised PDF is available through NTU indexed text but a fresh direct request is unavailable; rows are therefore normalized from the indexed source rather than claimed as current source bytes.",
            "The linked DANA elective list is not fully normalized, so elective-pool membership remains partial.",
            "An accessible older PDF totals 156 AU; it is retained as conflict provenance but its rules and plan are not applied to this revised 136-AU record.",
            "The exact AY2026-27 CCDS curriculum is available only through the authenticated student intranet.",
        ),
        kind="OVERLAY",
        total=136,
    )

    overview_conflicts = {
        "ce_ay2025.pdf": (
            "The current unversioned CCDS overview allocates CE as 68 Core and 15 MPE, while the revised dated AY2025-26 PDF allocates 65 Core and 18 MPE; both total 136 AU. This record selects the dated revised cohort PDF.",
        ),
        "dsai_ay2025.pdf": (
            "The current unversioned CCDS overview allocates DSAI as 60 Core and 20 BDE, while the revised dated AY2025-26 PDF allocates 61 Core and 19 BDE; both total 131 AU. This record selects the dated revised cohort PDF.",
        ),
        "bcg_ay2025.pdf": (
            "The current unversioned CCDS overview allocates the Computer Science side differently from the dated AY2025-26 PDF while preserving the published 155-AU lower total; the dated cohort PDF is selected here.",
        ),
        "bce_ay2025.pdf": (
            "The current unversioned CCDS overview allocates CE Core/MPE and shared-core AUs differently from the dated AY2025-26 PDF while preserving the 156-AU total; the dated cohort PDF is selected here.",
        ),
        "csec_ay2025.pdf": (
            "The current unversioned CCDS overview reports 175 AU, while the dated AY2025-26 PDF publishes 174-AU and 175-AU configurations; this record preserves the dated paths.",
        ),
        "ceec_ay2025.pdf": (
            "The current unversioned CCDS overview reports 176 AU, while the dated AY2025-26 PDF publishes 175 AU for both PI and PA paths; this record selects the dated cohort PDF.",
        ),
        "ce_ent_ay2025.pdf": (
            "The current unversioned CCDS overview reflects the revised 65-Core/18-MPE CE allocation, while the retrieved dated Entrepreneurship PDF uses 68 Core/15 MPE; both configurations total 141 AU.",
        ),
    }
    for filename, gaps in overview_conflicts.items():
        curricula[filename]["source_ids"].append(
            "ntu.ccds.curriculum.overview.current"
        )
        curricula[filename]["known_gaps"].extend(gaps)

    return curricula


MANUAL_PLAN_ROW = tuple[int, str, str | None, str, str, int | None, str | None]


CE_DANA_PLAN_ROWS: tuple[MANUAL_PLAN_ROW, ...] = (
    (1, "SEMESTER_1", "SC1013", "Physics for Computing", "PROGRAMME_CORE", 2, None),
    (1, "SEMESTER_1", "SC1004", "Linear Algebra for Computing", "PROGRAMME_CORE", 4, "The source says 3 AU are double-counted to DANA core."),
    (1, "SEMESTER_1", "EG1001", "Engineers in Society", "PROGRAMME_CORE", 2, None),
    (1, "SEMESTER_1", "CC0003", "Ethics and Civics in a Multicultural World", "ICC_COMMON_CORE", 2, None),
    (1, "SEMESTER_1", "CC0015", "Health and Wellbeing", "ICC_COMMON_CORE", 2, None),
    (1, "SEMESTER_1", "SC1003", "Introduction to Computational Thinking and Programming", "PROFESSIONAL_SERIES", 3, "Double-counted to DANA core."),
    (1, "SEMESTER_1", None, "Broadening and Deepening Elective", "DATA_ANALYTICS_BDE", 2, None),
    (1, "SEMESTER_1", "HW0001", "Introduction to Academic Communication", "OTHER", None, "For a student who failed the Qualifying English Test."),
    (1, "SEMESTER_1", "HW0002", "Calculus", "OTHER", None, "For a student without prior Calculus."),
    (1, "SEMESTER_2", "SC1005", "Digital Logic", "PROGRAMME_CORE", 3, None),
    (1, "SEMESTER_2", "SC1007", "Data Structures and Algorithms", "PROGRAMME_CORE", 3, "Double-counted to DANA core."),
    (1, "SEMESTER_2", "SC1008", "C and C++ Programming", "PROGRAMME_CORE", 3, None),
    (1, "SEMESTER_2", "MH1812", "Discrete Mathematics", "PROGRAMME_CORE", 3, None),
    (1, "SEMESTER_2", "CC0001", "Inquiry and Communication in an Interdisciplinary World", "ICC_COMMON_CORE", 2, None),
    (2, "SEMESTER_1", "SC1006", "Computer Organisation and Architecture", "PROGRAMME_CORE", 3, None),
    (2, "SEMESTER_1", "SC2000", "Probability and Statistics for Computing", "PROGRAMME_CORE", 3, "Double-counted to DANA core."),
    (2, "SEMESTER_1", "SC2001", "Algorithm Design and Analysis", "PROGRAMME_CORE", 3, None),
    (2, "SEMESTER_1", "SC2002", "Object Oriented Design and Programming", "PROGRAMME_CORE", 3, None),
    (2, "SEMESTER_1", "SC2103", "Digital Systems Design", "PROGRAMME_CORE", 3, None),
    (2, "SEMESTER_1", "SC2207", "Introduction to Databases", "DATA_ANALYTICS_BDE", 3, "DANA core course counted in the second-major/BDE column."),
    (2, "SEMESTER_1", "ML0004", "Career Design and Workplace Readiness in the V.U.C.A World", "ICC_COMMON_CORE", 2, None),
    (2, "SEMESTER_1", "CC0007", "Science and Technology for Humanity", "ICC_COMMON_CORE", 3, None),
    (2, "SEMESTER_2", "SC2005", "Operating Systems", "PROGRAMME_CORE", 3, None),
    (2, "SEMESTER_2", "SC2006", "Software Engineering", "PROGRAMME_CORE", 3, None),
    (2, "SEMESTER_2", "SC2008", "Computer Network", "PROGRAMME_CORE", 3, None),
    (2, "SEMESTER_2", "SC2104", "Sensors, Interfacing and Digital Control", "PROGRAMME_CORE", 3, None),
    (2, "SEMESTER_2", "SC3102", "Signals, Systems and Transforms", "PROGRAMME_CORE", 3, None),
    (2, "SEMESTER_2", "CC0006", "Sustainability: Society, Economy and Environment", "ICC_COMMON_CORE", 3, None),
    (2, "SEMESTER_2", "CSL", "Care, Serve, Learn — Part 1", "CARE_SERVE_LEARN", 3, "Continues in Year 3 Semester 1."),
    (3, "SEMESTER_1", "SC2107", "Microprocessor System Design and Development", "PROGRAMME_CORE", 3, None),
    (3, "SEMESTER_1", "SC2079", "Multidisciplinary Design Project", "PROGRAMME_CORE", 4, None),
    (3, "SEMESTER_1", "HW0288", "Engineering Communication", "PROFESSIONAL_SERIES", 2, None),
    (3, "SEMESTER_1", "SC3xxx/SC4xxx", "Major Prescribed Elective 1", "MPE", 3, None),
    (3, "SEMESTER_1", "DANA-E", "Data Analytics Elective 1", "DATA_ANALYTICS_BDE", 3, None),
    (3, "SEMESTER_1", "DANA-E", "Data Analytics Elective 2", "DATA_ANALYTICS_BDE", 3, None),
    (3, "SEMESTER_1", "CSL", "Care, Serve, Learn — Part 2", "CARE_SERVE_LEARN", None, "Continuation from Year 2 Semester 2."),
    (3, "SEMESTER_2", "SC3920", "Professional Internship (Graded)", "PROFESSIONAL_SERIES", 10, None),
    (4, "SEMESTER_1", "SC4079", "Final Year Project — Part 1", "PROGRAMME_CORE", 4, None),
    (4, "SEMESTER_1", "SC3xxx/SC4xxx", "Major Prescribed Elective 2", "MPE", 3, None),
    (4, "SEMESTER_1", "SC4xxx", "Major Prescribed Elective 3", "MPE", 3, None),
    (4, "SEMESTER_1", "SC4xxx", "Major Prescribed Elective 4", "MPE", 3, None),
    (4, "SEMESTER_1", "ML0015", "Professional Preparation", "PROFESSIONAL_SERIES", 1, None),
    (4, "SEMESTER_1", "SC4020", "Data Analytics and Mining", "DATA_ANALYTICS_BDE", 3, None),
    (4, "SEMESTER_2", "SC4079", "Final Year Project — Part 2", "PROGRAMME_CORE", 4, None),
    (4, "SEMESTER_2", "SC4xxx", "Major Prescribed Elective 5", "MPE", 3, None),
    (4, "SEMESTER_2", "SC4xxx", "Major Prescribed Elective 6", "MPE", 3, None),
    (4, "SEMESTER_2", "SC4024/SC4023", "Data Visualisation / Big Data Management", "DATA_ANALYTICS_BDE", 3, "SC4024 is offered in Semester 1 and SC4023 in Semester 2 according to the source."),
    (4, "SEMESTER_2", "DANA-E", "Data Analytics Elective 3", "DATA_ANALYTICS_BDE", 3, None),
)


MACS_PLAN_ROWS: tuple[MANUAL_PLAN_ROW, ...] = (
    (1, "SEMESTER_1", "SC1003", "Introduction to Computational Thinking and Programming", "COMMON_CORE", 3, None),
    (1, "SEMESTER_1", "SC1005", "Digital Logic", "COMPUTER_SCIENCE_CORE", 3, None),
    (1, "SEMESTER_1", "MH1100", "Calculus I", "COMMON_CORE", 4, None),
    (1, "SEMESTER_1", "MH1200", "Linear Algebra I", "COMMON_CORE", 4, None),
    (1, "SEMESTER_1", "MH1300", "Foundations of Mathematics", "MATHEMATICS_CORE", 4, None),
    (1, "SEMESTER_1", "CC0003", "Ethics and Civics in a Multi-Cultural World", "ICC_COMMON_CORE", 2, None),
    (1, "SEMESTER_1", "HW0001", "Introduction to Academic Communication", "PROFESSIONAL_SERIES", 0, "Required only for students who have not passed the Qualifying English Test."),
    (1, "SEMESTER_2", "SC1006", "Computer Organisation and Architecture", "COMPUTER_SCIENCE_CORE", 3, None),
    (1, "SEMESTER_2", "SC1007", "Data Structures and Algorithms", "COMMON_CORE", 3, None),
    (1, "SEMESTER_2", "MH1101", "Calculus II", "MATHEMATICS_CORE", 4, None),
    (1, "SEMESTER_2", "MH1201", "Linear Algebra II", "MATHEMATICS_CORE", 4, None),
    (1, "SEMESTER_2", "MH1301", "Discrete Mathematics", "COMMON_CORE", 3, None),
    (1, "SEMESTER_2", "CC0001", "Inquiry and Communication in an Interdisciplinary World", "ICC_COMMON_CORE", 2, None),
    (1, "SEMESTER_2", "CC0015", "Health and Wellbeing", "ICC_COMMON_CORE", 2, None),
    (2, "SEMESTER_1", "SC2001", "Algorithm Design and Analysis", "COMMON_CORE", 3, None),
    (2, "SEMESTER_1", "SC2002", "Object Oriented Design and Programming", "COMPUTER_SCIENCE_CORE", 3, None),
    (2, "SEMESTER_1", "SC2005", "Operating Systems", "COMPUTER_SCIENCE_CORE", 3, None),
    (2, "SEMESTER_1", "MH2100", "Calculus III", "MATHEMATICS_CORE", 4, None),
    (2, "SEMESTER_1", "MH2500", "Probability", "MATHEMATICS_CORE", 4, None),
    (2, "SEMESTER_1", "ML0004", "Career Design and Workplace Readiness in a Dynamic World", "ICC_COMMON_CORE", 2, None),
    (2, "SEMESTER_2", "SC2006", "Software Engineering", "COMPUTER_SCIENCE_CORE", 3, None),
    (2, "SEMESTER_2", "SC2207", "Introduction to Databases", "COMPUTER_SCIENCE_CORE", 3, None),
    (2, "SEMESTER_2", "SC2008", "Computer Networks", "COMPUTER_SCIENCE_CORE", 3, None),
    (2, "SEMESTER_2", "PS0002", "Introduction to Data Science and Artificial Intelligence", "PROFESSIONAL_SERIES", 3, None),
    (2, "SEMESTER_2", "CC0006", "Sustainability: Society, Economy and Environment", "ICC_COMMON_CORE", 3, None),
    (2, "SEMESTER_2", "CC0007", "Science and Technology for Humanity", "ICC_COMMON_CORE", 3, None),
    (2, "SEMESTER_2", "CSL", "Care, Serve, Learn", "CARE_SERVE_LEARN", 3, None),
    (3, "SEMESTER_1", None, "Computer Science Prescribed Elective 1", "COMPUTER_SCIENCE_MPE", 3, None),
    (3, "SEMESTER_1", None, "Mathematics Prescribed Elective 1", "MATHEMATICS_MPE", 3, None),
    (3, "SEMESTER_1", None, "Broadening and Deepening Elective 1", "BDE", 3, None),
    (3, "SEMESTER_1", None, "Broadening and Deepening Elective 2", "BDE", 3, None),
    (3, "SEMESTER_1", None, "Broadening and Deepening Elective 3", "BDE", 3, None),
    (3, "SEMESTER_1", "HW0218", "Communication Across the Sciences", "PROFESSIONAL_SERIES", 2, None),
    (3, "SEMESTER_1", "MLXXXX", "Professional Preparation", "PROFESSIONAL_SERIES", 1, "The public page prints the placeholder code MLXXXX."),
    (3, "SEMESTER_2", "SC3079", "Professional Internship", "PROFESSIONAL_SERIES", 10, None),
    (4, "SEMESTER_1", "MH4916/SC4079", "Final Year Project", "COMMON_CORE", 8, "The source permits MH4916 in Semester 1 or 2, or SC4079 across Semesters 1 and 2; Semester 1 is only the first listed placement."),
    (4, "SEMESTER_1", None, "Computer Science Prescribed Elective 2", "COMPUTER_SCIENCE_MPE", 3, None),
    (4, "SEMESTER_1", None, "Computer Science Prescribed Elective 3", "COMPUTER_SCIENCE_MPE", 3, None),
    (4, "SEMESTER_1", None, "Mathematics Prescribed Elective 2", "MATHEMATICS_MPE", 4, None),
    (4, "SEMESTER_1", None, "Mathematics Prescribed Elective 3", "MATHEMATICS_MPE", 4, None),
    (4, "SEMESTER_1", None, "Broadening and Deepening Elective 4", "BDE", 3, "The source permits this elective in Semester 1 or 2; Semester 1 is only the first listed placement."),
    (4, "SEMESTER_2", None, "Computer Science Prescribed Elective 4", "COMPUTER_SCIENCE_MPE", 3, None),
    (4, "SEMESTER_2", None, "Computer Science Prescribed Elective 5", "COMPUTER_SCIENCE_MPE", 3, None),
    (4, "SEMESTER_2", None, "Mathematics Prescribed Elective 4", "MATHEMATICS_MPE", 4, None),
)


def build_manual_study_plan(
    curriculum: dict[str, Any],
    source_id: str,
    course_codes: set[str],
    rows: tuple[MANUAL_PLAN_ROW, ...],
    id_prefix: str,
) -> list[dict[str, Any]]:
    requirement_ids = {
        item["category"]: item["requirement_id"] for item in curriculum["requirements"]
    }
    positions: defaultdict[tuple[int, str], int] = defaultdict(int)
    plan: list[dict[str, Any]] = []
    for year, semester, raw_code, title, category, aus, note in rows:
        positions[(year, semester)] += 1
        typed_code = raw_code if raw_code in course_codes else None
        plan.append(
            {
                "plan_item_id": f"plan.{id_prefix}.{len(plan) + 1:03d}",
                "study_year": year,
                "semester": semester,
                "position": positions[(year, semester)],
                "path_label": None,
                "course_code": typed_code,
                "raw_course_code": raw_code,
                "label": title,
                "category": category,
                "aus": aus,
                "requirement_id": requirement_ids.get(category),
                "notes": [note] if note else [],
                "source_ids": [source_id],
            }
        )
    return plan


def build_macs_study_plan(
    curriculum: dict[str, Any],
    source_id: str,
    course_codes: set[str],
) -> list[dict[str, Any]]:
    return build_manual_study_plan(
        curriculum,
        source_id,
        course_codes,
        MACS_PLAN_ROWS,
        "macs.ay2025-26",
    )


def build_page_curricula(course_codes: set[str]) -> list[dict[str, Any]]:
    acda = partial_curriculum(
        "curriculum.acda.ay2025-26-public-snapshot",
        "Accountancy and Data Science and Artificial Intelligence — public curriculum snapshot",
        "ACDA",
        (
            "ntu.ccds.curriculum.acda.public-page",
            "ntu.ccds.curriculum.acda.unversioned-pdf",
        ),
        [
            requirement("acda", "ACCOUNTANCY_CORE", "Accountancy Core", 62),
            requirement("acda", "DSAI_CORE", "Data Science and Artificial Intelligence Core", 61),
            requirement("acda", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement("acda", "PROFESSIONAL_SERIES", "Professional Series", 20),
            requirement("acda", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
            requirement(
                "acda",
                "UNRESOLVED_PUBLISHED_COMPONENT",
                "Unresolved component in public total",
                None,
                constraints=(
                    "The public page reports 172 total AUs but the visible named category cells total 160 AUs; the remaining 12 AUs are not assigned to a category here.",
                ),
            ),
        ],
        (
            "The public programme page and downloadable curriculum list are not labelled with an admission cohort; AY2025-26 is a package snapshot key, not a claim that the rules apply to every AY2025-26 admit.",
            "The unversioned downloadable list has course titles but no course codes, AUs, or semester-by-semester study plan.",
            "The exact admission-cohort curriculum and the 12-AU difference between the visible categories and published total require an authenticated source.",
        ),
        total=172,
        constraints=("The programme is described publicly as four and a half years with direct honours.",),
    )

    bacf = partial_curriculum(
        "curriculum.bacf.ay2025-26-public-snapshot",
        "Applied Computing in Finance — public curriculum snapshot",
        "BACF",
        (
            "ntu.ccds.curriculum.bacf.public-page",
            "ntu.ccds.curriculum.bacf.unversioned-pdf",
        ),
        [
            requirement("bacf", "CORE", "Core", 72),
            requirement("bacf", "MPE", "Major Prescribed Electives", 15),
            requirement("bacf", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement("bacf", "PROFESSIONAL_SERIES", "Professional Series", 20),
            requirement("bacf", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
            requirement("bacf", "BDE", "Broadening and Deepening Electives", 11),
        ],
        (
            "The public programme page and curriculum list are unversioned by admission cohort; AY2025-26 is a package snapshot key.",
            "The retrieved unversioned PDF lists courses without a machine-readable cohort study plan, so required-course and elective-pool membership is incomplete.",
        ),
        total=135,
        constraints=(
            "The public page describes a compulsory 20-week professional internship, with an optional 10-week extension.",
            "The public page lists specialisations in Financial Analytics and WealthTech, Crypto Asset and Blockchain, and Digital Banking and Security.",
        ),
    )

    ecds_econ_core = (
        "HE1001",
        "HE1002",
        "HE2003",
        "HE3001",
        "HE3002",
    )
    ecds_ds_core = (
        "MH1805",
        "SC1003",
        "MH2802",
        "MH1812",
        "SC1007",
        "MH2100",
        "MH2500",
        "SC2001",
        "SC2207",
        "SC3000",
    )
    ecds_common_core = ("CC0001", "CC0003", "ML0004", "CC0015", "CC0006", "CC0007")
    ecds = partial_curriculum(
        "curriculum.ecds.ay2025-26",
        "Economics and Data Science — AY2025-26 intake",
        "ECDS",
        ("ntu.ccds.curriculum.ecds.ay2025-26",),
        [
            requirement(
                "ecds",
                "ECON_CORE",
                "Economics Core",
                24,
                required_courses=ecds_econ_core,
                constraints=(
                    "The public source also names HE2001, HE2002 and HE3003; those codes are retained in this note because they are absent from the current AY2026 Semester 1 catalogue snapshot.",
                ),
            ),
            requirement(
                "ecds",
                "DATA_SCIENCE_CORE",
                "Data Science Core",
                33,
                required_courses=ecds_ds_core,
            ),
            requirement(
                "ecds",
                "ECON_MPE",
                "Economics Major Prescribed Electives",
                15,
                constraints=(
                    "Choose one level-3000 and three level-4000 Economics courses; at least one must be from the published HE4xxx list.",
                ),
            ),
            requirement(
                "ecds",
                "DATA_SCIENCE_MPE",
                "Data Science Major Prescribed Electives",
                22,
                constraints=("Choose 22 AU from the linked Data Science prescribed-elective list.",),
            ),
            requirement(
                "ecds",
                "FINAL_YEAR_PROJECT",
                "Final Year Project or published coursework alternative",
                8,
                constraints=(
                    "Students with cGPA 3.90 or above must take HE4099 to be eligible for Honours (Highest Distinction) or Honours (Distinction).",
                    "Students not eligible for HE4099 take two additional level-4000 courses counted toward Major Prescribed Electives.",
                ),
            ),
            requirement(
                "ecds",
                "ICC_COMMON_CORE",
                "ICC Common Core",
                14,
                required_courses=ecds_common_core,
            ),
            requirement(
                "ecds",
                "PROFESSIONAL_SERIES",
                "Professional Series",
                15,
                constraints=(
                    "Includes two 10-week, 5-AU internships: one Economics-related and one Data-Science-related, during Special Terms in Years 2 and 3.",
                ),
            ),
            requirement("ecds", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
            requirement("ecds", "BDE", "Broadening and Deepening Electives", 6),
        ],
        (
            "The linked complete Major Prescribed Elective PDF is not normalized in this package, so elective-pool membership is partial.",
            "Three source-listed Economics core codes are outside the current AY2026 Semester 1 catalogue snapshot and therefore remain untyped in the explanatory constraint.",
            "The exact AY2026-27 curriculum is not asserted by this AY2025-26 intake record.",
        ),
        total=140,
        constraints=("The public page identifies this as a four-year programme.",),
    )

    macs = partial_curriculum(
        "curriculum.macs.ay2025-26",
        "Mathematical and Computer Sciences — Matriculation Year 2025",
        "MACS",
        ("ntu.ccds.curriculum.macs.ay2025-26",),
        [
            requirement(
                "macs",
                "COMMON_CORE",
                "Mathematical Sciences and Computer Science Common Core (including FYP)",
                28,
            ),
            requirement("macs", "MATHEMATICS_CORE", "Mathematical Sciences Core", 20),
            requirement(
                "macs",
                "MATHEMATICS_MPE",
                "Mathematical Sciences Major Prescribed Electives",
                15,
                constraints=("At least 8 AU must be from MH4xxx courses.",),
            ),
            requirement("macs", "COMPUTER_SCIENCE_CORE", "Computer Science Core", 21),
            requirement(
                "macs",
                "COMPUTER_SCIENCE_MPE",
                "Computer Science Major Prescribed Electives",
                15,
                minimum_courses=5,
                constraints=("Choose five SC3xxx/SC4xxx courses.",),
            ),
            requirement("macs", "ICC_COMMON_CORE", "ICC Common Core", 14),
            requirement("macs", "PROFESSIONAL_SERIES", "Professional Series", 16),
            requirement("macs", "CARE_SERVE_LEARN", "Care, Serve, Learn", 3),
            requirement("macs", "BDE", "Broadening and Deepening Electives", 12),
        ],
        (
            "Elective pools and specialisation lists on the public page are not copied wholesale into requirement arrays; the page remains the authoritative source.",
            "The public study plan gives the FYP as Semester 1 or 2 for MH4916 and across Semesters 1 and 2 for SC4079; the normalized row retains this ambiguity in notes.",
            "This record is specifically Matriculation Year 2025 and does not substitute for the separately published Matriculation Year 2026 page.",
        ),
        total=144,
        constraints=(
            "The FYP must be MH4916 or SC4079 and jointly supervised by SPMS and CCDS faculty.",
            "Specialisation requires at least 17 AU from a published specialisation list; the same course cannot count toward two specialisations.",
        ),
    )
    macs["study_plan"] = build_macs_study_plan(
        macs,
        "ntu.ccds.curriculum.macs.ay2025-26",
        course_codes,
    )

    ce_bus = partial_curriculum(
        "curriculum.ce-bus.ay2025-26-indexed",
        "Computer Engineering with Second Major in Business — indexed AY2025-26 summary",
        "CE-BUS",
        ("ntu.ccds.curriculum.ce-bus.ay2025-26.indexed",),
        [
            requirement(
                "ce-bus",
                "PUBLISHED_TOTAL",
                "Published indexed curriculum total",
                146,
                constraints=("The indexed source exposes a 146-AU total but its detailed PDF is no longer retrievable.",),
            )
        ],
        (
            "The current detailed PDF URL returns unavailable, so category AUs, course lists, internship-path conditions, and study-plan rows cannot be verified.",
            "The exact AY2026-27 curriculum is available only through the authenticated student intranet.",
        ),
        kind="OVERLAY",
        total=146,
    )

    ce_itp = partial_curriculum(
        "curriculum.ce-itp.ay2025-26-indexed",
        "Computer Engineering with Second Major in Business (International Trading) — indexed AY2025-26 summary",
        "CE-ITP",
        ("ntu.ccds.curriculum.ce-itp.ay2025-26.indexed",),
        [
            requirement(
                "ce-itp",
                "PUBLISHED_TOTAL",
                "Published indexed curriculum total",
                None,
                constraints=("The indexed source reports 146-AU and 147-AU configurations without a retrievable detailed table.",),
            )
        ],
        (
            "The current detailed PDF URL returns unavailable, so the conditions selecting the 146-AU versus 147-AU total, category AUs, course lists, and study-plan rows cannot be verified.",
            "The exact AY2026-27 curriculum is available only through the authenticated student intranet.",
        ),
        kind="OVERLAY",
        paths=[
            path(
                "graduation_path.ce-itp.published-146",
                "Published 146-AU configuration (selection condition unavailable)",
                146,
                {"PUBLISHED_TOTAL": 146},
            ),
            path(
                "graduation_path.ce-itp.published-147",
                "Published 147-AU configuration (selection condition unavailable)",
                147,
                {"PUBLISHED_TOTAL": 147},
            ),
        ],
    )

    btech = partial_curriculum(
        "curriculum.btech-comp.2025-public-snapshot",
        "Bachelor of Technology in Computing — 2025 public programme snapshot",
        "BTECH-COMP",
        ("ntu.ccds.curriculum.btech-comp.2025-public-page",),
        [
            requirement(
                "btech-comp",
                "FOUNDATION_STACK",
                "Foundation Stack",
                None,
                constraints=(
                    "Approximately 1.5 years covering computing design, programming and software development, operating systems, and databases.",
                    "Leads to an Advanced Specialist Certificate in Full Stack Development.",
                ),
            ),
            requirement(
                "btech-comp",
                "SPECIALIST_STACK",
                "Specialist Stack",
                None,
                constraints=(
                    "Approximately 1.5 years in Software Engineering, Artificial Intelligence Engineering, or Cybersecurity.",
                ),
            ),
            requirement(
                "btech-comp",
                "INDUSTRY_IMMERSION_STACK",
                "Industry Immersion Stack",
                None,
                constraints=(
                    "Approximately one year with full-time industry-immersive OJT, a company-sponsored final capstone, and Broadening and Deepening Electives.",
                ),
            ),
        ],
        (
            "The public page and 2025 brochure do not publish a total AU requirement or a cohort-versioned course-code study plan.",
            "AY2025-26 is used only as the package version for this 2025 public snapshot and must not be treated as confirmed cohort applicability.",
            "Specialisation-specific module lists, exemptions, and exact graduation audit rules remain unavailable from the retrieved public page.",
        ),
        cohort="AY2025-26",
        effective_year="AY2025-26",
        constraints=(
            "The programme is part-time and described as four years.",
            "The page states five bridging modules must be passed before matriculation.",
        ),
    )

    return [acda, bacf, ecds, macs, ce_bus, ce_itp, btech]


def normalize_category(
    raw_requirement_type: str | None,
    title: str,
    available_categories: set[str],
) -> str:
    raw = (raw_requirement_type or "").upper().replace("–", "-")
    title_upper = title.upper()

    def first(*candidates: str) -> str | None:
        return next((item for item in candidates if item in available_categories), None)

    if "C-CORE" in raw or "COMMON-CORE" in raw:
        return first("ICC_COMMON_CORE") or "ICC_COMMON_CORE"
    if "CSL" in raw or "CARE, SERVE" in title_upper:
        return first("CARE_SERVE_LEARN") or "CARE_SERVE_LEARN"
    if "P-SERIES" in raw or "PROFESSIONAL SERIES" in raw:
        return first("PROFESSIONAL_SERIES") or "PROFESSIONAL_SERIES"
    if any(term in title_upper for term in ("PROFESSIONAL INTERNSHIP", "PROFESSIONAL ATTACHMENT")):
        return first("PROFESSIONAL_SERIES") or "PROFESSIONAL_SERIES"
    if "BDE" in raw and "2M-" not in raw and "SUST" not in raw and "BUS" not in raw and "ENT" not in raw:
        return first("BDE") or "BDE"
    if "BROADENING AND DEEPENING" in title_upper:
        return first("BDE") or "BDE"
    if "SUST" in raw:
        return first("SUSTAINABILITY_SECOND_MAJOR") or "SUSTAINABILITY_SECOND_MAJOR"
    if "ENT" in raw:
        return first("ENTREPRENEURSHIP_SECOND_MAJOR") or "ENTREPRENEURSHIP_SECOND_MAJOR"
    if "ITP" in raw:
        return first("BUSINESS_ITP_SECOND_MAJOR") or "BUSINESS_ITP_SECOND_MAJOR"
    if "2M-BUS" in raw:
        return first("BUSINESS_SECOND_MAJOR", "BUSINESS_ITP_SECOND_MAJOR") or "BUSINESS_SECOND_MAJOR"
    if raw.startswith("DA-") or "DA-C" in raw:
        return first("DATA_ANALYTICS_SECOND_MAJOR") or "DATA_ANALYTICS_SECOND_MAJOR"
    if raw.startswith("BC-PE"):
        return first("BUSINESS_MPE") or "BUSINESS_MPE"
    if "MPE-ECON" in raw:
        return first("ECON_MPE") or "ECON_MPE"
    if "MPE" in raw:
        return first("CSC_MPE", "CE_MPE", "MPE") or "MPE"
    if "CORE-ECON" in raw:
        return first("ECON_CORE") or "ECON_CORE"
    if "CORE-BUS" in raw:
        return first("BUSINESS_CORE") or "BUSINESS_CORE"
    if "CORE-CE" in raw:
        return first("CE_CORE") or "CE_CORE"
    if "CORE-CS" in raw:
        return first("CSC_CORE") or "CSC_CORE"
    if "CORE/DA" in raw:
        return first("DATA_ANALYTICS_SECOND_MAJOR", "PROGRAMME_CORE") or "DATA_ANALYTICS_SECOND_MAJOR"
    if "CORE" in raw:
        return (
            first(
                "PROGRAMME_CORE",
                "CSC_CORE",
                "CE_CORE",
                "DSAI_CORE",
                "CORE",
            )
            or "PROGRAMME_CORE"
        )
    if "FINAL YEAR PROJECT" in title_upper or "CAPSTONE" in title_upper:
        return first("PROGRAMME_CORE", "CSC_CORE", "CE_CORE", "COMMON_CORE") or "OTHER"
    return "OTHER"


def parse_au(value: object) -> int | str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "–"}:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if number == number.to_integral_value():
        return int(number)
    return str(number)


def normalized_study_plan(
    curriculum: dict[str, Any],
    extracted: dict[str, Any],
    course_codes: set[str],
) -> list[dict[str, Any]]:
    available_categories = {
        item["category"] for item in curriculum["requirements"]
    }
    requirement_ids = {
        item["category"]: item["requirement_id"]
        for item in curriculum["requirements"]
    }
    is_legacy_ce_dana = curriculum["programme"] == "CE-DANA"
    source_id = (
        "ntu.ccds.curriculum.ce-dana.ay2025-26.legacy"
        if is_legacy_ce_dana
        else curriculum["source_ids"][0]
    )
    positions: defaultdict[tuple[int, str, str | None], int] = defaultdict(int)
    plan: list[dict[str, Any]] = []
    for row in extracted.get("study_plan", []):
        title = str(row.get("title") or "").strip()
        raw_code_value = row.get("raw_course_code") or row.get("course_code")
        raw_code = str(raw_code_value).strip() if raw_code_value else None
        if not title or title.upper() == "COURSE TITLE":
            continue
        if raw_code and raw_code.upper() == "COURSE CODE":
            continue
        year = int(row["study_year"])
        semester = str(row["semester"])
        path_label = row.get("path_label")
        if path_label is not None:
            path_label = str(path_label).strip() or None
        if is_legacy_ce_dana:
            path_label = "Legacy accessible 156-AU PDF; not the current 136-AU configuration"
        key = (year, semester, path_label)
        positions[key] += 1
        raw_type = row.get("requirement_type")
        category = normalize_category(
            str(raw_type) if raw_type is not None else None,
            title,
            available_categories,
        )
        parsed_code = row.get("course_code")
        typed_code = str(parsed_code).strip().upper() if parsed_code else None
        if typed_code not in course_codes:
            typed_code = None
        notes: list[str] = []
        if raw_type and str(raw_type).strip() not in {"-", "Type"}:
            notes.append(f"Published requirement type: {str(raw_type).strip()}")
        remark = row.get("prerequisite_or_remark")
        if remark and str(remark).strip() not in {"-", "Nil", "NIL"}:
            notes.append(f"Published prerequisite/remark: {str(remark).strip()}")
        if is_legacy_ce_dana:
            notes.append(
                "Legacy plan only: do not apply to the current 136-AU configuration without authenticated cohort confirmation."
            )
        # Preserve order while removing repeated notes.
        notes = list(dict.fromkeys(notes))
        plan.append(
            {
                "plan_item_id": (
                    f"plan.{curriculum['curriculum_id'].removeprefix('curriculum.')}"
                    f".{len(plan) + 1:03d}"
                ),
                "study_year": year,
                "semester": semester,
                "position": positions[key],
                "path_label": path_label,
                "course_code": typed_code,
                "raw_course_code": raw_code,
                "label": title,
                "category": category,
                "aus": parse_au(row.get("aus")),
                "requirement_id": requirement_ids.get(category),
                "notes": notes,
                "source_ids": [source_id],
            }
        )
    return plan


def build_curricula(
    extracted_documents: list[dict[str, Any]],
    course_codes: set[str],
) -> list[dict[str, Any]]:
    extracted_by_name = {
        str(item["filename"]): item for item in extracted_documents
    }
    pdf_curricula = build_pdf_curricula()
    missing = sorted(set(pdf_curricula) - set(extracted_by_name))
    if missing:
        raise ValueError(f"extracted curriculum input is missing: {missing}")
    for filename, curriculum in pdf_curricula.items():
        curriculum["study_plan"] = normalized_study_plan(
            curriculum,
            extracted_by_name[filename],
            course_codes,
        )
    ce_dana = pdf_curricula["ce_dana_ay2025.pdf"]
    ce_dana["study_plan"] = build_manual_study_plan(
        ce_dana,
        "ntu.ccds.curriculum.ce-dana.ay2025-26.revised-index",
        course_codes,
        CE_DANA_PLAN_ROWS,
        "ce-dana.ay2025-26",
    )
    curricula = [*pdf_curricula.values(), *build_page_curricula(course_codes)]
    curricula.sort(key=lambda item: item["curriculum_id"])
    ids = [item["curriculum_id"] for item in curricula]
    if len(curricula) != 23 or len(ids) != len(set(ids)):
        raise ValueError("expected exactly 23 unique curriculum configurations")
    return curricula


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extracted-input",
        type=Path,
        default=ROOT / "tmp" / "extracted_curricula.json",
        help="Normalized extraction from the retrieved AY2025 curriculum PDFs.",
    )
    parser.add_argument(
        "--courses-input",
        type=Path,
        default=ROOT / "data" / "real" / "courses.json",
        help="Current catalogue used to decide whether a raw plan code may be typed.",
    )
    parser.add_argument(
        "--programmes-output",
        type=Path,
        default=ROOT / "data" / "real" / "programmes.json",
    )
    parser.add_argument(
        "--curricula-output",
        type=Path,
        default=ROOT / "data" / "real" / "curriculum.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    extracted_documents = json.loads(args.extracted_input.read_text(encoding="utf-8"))
    courses = json.loads(args.courses_input.read_text(encoding="utf-8"))
    course_codes = {str(item["code"]).upper() for item in courses}
    programme_ids = [item["programme_id"] for item in PROGRAMMES]
    programme_codes = [item["code"] for item in PROGRAMMES]
    if (
        len(PROGRAMMES) != 22
        or len(programme_ids) != len(set(programme_ids))
        or len(programme_codes) != len(set(programme_codes))
    ):
        raise ValueError("expected exactly 22 unique programme/pathway records")
    curricula = build_curricula(extracted_documents, course_codes)
    write_json(args.programmes_output, PROGRAMMES)
    write_json(args.curricula_output, curricula)
    print(
        f"wrote {len(PROGRAMMES)} programmes and {len(curricula)} curricula; "
        f"{sum(len(item['study_plan']) for item in curricula)} study-plan rows"
    )


if __name__ == "__main__":
    main()
