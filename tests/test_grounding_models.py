from __future__ import annotations

import pytest
from pydantic import ValidationError

from graduation_exception_agent.models import (
    CalendarEvent,
    CalendarEventType,
    Course,
    CourseCatalogueAppearance,
    CourseOffering,
    CourseOfferingCollection,
    Curriculum,
    CurriculumCoursePlanItem,
    PolicyDocument,
    PolicySection,
    Programme,
    SourceProvenance,
    TimetableMeeting,
)


def test_simulated_policy_requires_exact_visible_banner() -> None:
    with pytest.raises(ValidationError, match="SIMULATED POLICY FOR PROTOTYPE"):
        PolicySection(
            section_id="simulated.rule",
            title="Prototype rule",
            origin="SIMULATED_POLICY",
            source_ids=[],
            applicability="EXPLICIT",
            applicable_academic_years=["AY2026-27"],
            applicable_admission_cohorts=[],
            applicability_note="Prototype scope.",
            body_markdown="A convenient invented process.",
            start_line=4,
            end_line=5,
        )


def test_simulated_policy_with_banner_remains_typed_as_simulated() -> None:
    section = PolicySection(
        section_id="simulated.rule",
        title="Prototype rule",
        origin="SIMULATED_POLICY",
        source_ids=[],
        applicability="EXPLICIT",
        applicable_academic_years=["AY2026-27"],
        applicable_admission_cohorts=[],
        applicability_note="Prototype scope.",
        body_markdown=(
            "SIMULATED POLICY FOR PROTOTYPE\n\nA deterministic test-only rule."
        ),
        start_line=4,
        end_line=6,
    )

    assert section.origin.value == "SIMULATED_POLICY"


def test_policy_section_requires_typed_applicability_scope() -> None:
    with pytest.raises(ValidationError, match="requires a year or cohort"):
        PolicySection(
            section_id="policy.test",
            title="Test rule",
            origin="VERIFIED_REAL",
            source_ids=["source.policy"],
            applicability="EXPLICIT",
            applicable_academic_years=[],
            applicable_admission_cohorts=[],
            applicability_note="Missing scope should fail.",
            body_markdown="A sourced statement.",
            start_line=1,
            end_line=1,
        )


def test_policy_document_rejects_section_source_not_declared_by_document() -> None:
    with pytest.raises(ValidationError, match="declared by the policy document"):
        PolicyDocument(
            document_id="policy.test",
            document_type="REGISTRATION",
            title="Test",
            status="AVAILABLE",
            source_ids=["source.document"],
            sections=[
                {
                    "section_id": "policy.test.section",
                    "title": "Section",
                    "origin": "VERIFIED_REAL",
                    "source_ids": ["source.other"],
                    "applicability": "EXPLICIT",
                    "applicable_academic_years": ["AY2026-27"],
                    "applicable_admission_cohorts": [],
                    "applicability_note": "Scoped test.",
                    "body_markdown": "Statement.",
                    "start_line": 1,
                    "end_line": 1,
                }
            ],
            raw_markdown="x",
            content_sha256="0" * 64,
        )


def test_unknown_calendar_event_cannot_gain_invented_dates() -> None:
    with pytest.raises(ValidationError, match="unknown calendar dates must remain null"):
        CalendarEvent(
            event_id="calendar.unknown",
            event_type="COURSE_REGISTRATION",
            name="Unknown personalised time",
            semester=None,
            start_date="2026-06-01",
            end_date=None,
            date_precision="UNKNOWN",
            description="Not publicly available.",
            origin="UNKNOWN",
            source_ids=[],
        )


def test_calendar_event_types_cover_public_academic_activity_inventory() -> None:
    assert {
        "VACATION",
        "SPECIAL_TERM",
        "INTERNSHIP",
        "SCHEDULE_RELEASE",
        "ALLOCATION_RESULTS",
        "RESULTS",
        "FGO",
        "RESULT_REVIEW",
        "CONVOCATION_CUTOFF",
    } <= {event.value for event in CalendarEventType}


def test_placeholder_offerings_are_not_a_verified_empty_collection() -> None:
    collection = CourseOfferingCollection(
        status="PLACEHOLDER",
        source_ids=[],
        offerings=[],
        placeholder_reason="No reproducible public snapshot has been collected.",
    )

    assert collection.status.value == "PLACEHOLDER"
    assert collection.placeholder_reason is not None


def test_placeholder_offerings_cannot_contain_records() -> None:
    with pytest.raises(ValidationError, match="cannot contain offerings"):
        CourseOfferingCollection(
            status="PLACEHOLDER",
            source_ids=[],
            offerings=[
                {
                    "offering_id": "offering.sc1003",
                    "course_code": "SC1003",
                    "academic_year": "AY2026-27",
                    "semester": "SEMESTER_1",
                    "status": "UNKNOWN",
                    "indexes": [],
                    "snapshot_at": None,
                    "source_ids": ["source.offering"],
                }
            ],
            placeholder_reason="No reproducible snapshot.",
        )


def test_collected_offerings_require_sources_and_records() -> None:
    with pytest.raises(ValidationError, match="sources and offerings"):
        CourseOfferingCollection(
            status="COLLECTED",
            source_ids=[],
            offerings=[],
        )


def test_known_course_applicability_cannot_be_marked_unknown() -> None:
    with pytest.raises(ValidationError, match="programme applicability"):
        Course(
            code="SC1003",
            title="Introduction to Computing",
            aus=3,
            applicable_programmes=["CSC"],
            programme_categories={"CSC": ["PROGRAMME_CORE"]},
            applicability_completeness="UNKNOWN",
            source_ids=["source.curriculum"],
        )


def test_populated_curriculum_must_declare_coverage() -> None:
    with pytest.raises(ValidationError, match="COMPLETE, PARTIAL, or UNAVAILABLE"):
        Curriculum(
            curriculum_id="curriculum.csc.test",
            programme="CSC",
            admission_cohort="AY2025-26",
            effective_academic_year="AY2025-26",
            graduation_aus=3,
            requirements=[
                {
                    "requirement_id": "requirement.core",
                    "name": "Core",
                    "category": "PROGRAMME_CORE",
                    "minimum_aus": 3,
                }
            ],
            rules_completeness="UNKNOWN",
            source_ids=["source.curriculum"],
        )


def test_curriculum_requires_one_fixed_total_or_explicit_paths() -> None:
    with pytest.raises(ValidationError, match="at most one"):
        Curriculum(
            curriculum_id="curriculum.csc.test",
            programme="CSC",
            admission_cohort="AY2025-26",
            effective_academic_year="AY2025-26",
            graduation_aus=135,
            graduation_paths=[
                {
                    "path_id": "path.alternative",
                    "name": "Alternative",
                    "graduation_aus": 136,
                }
            ],
            requirements=[
                {
                    "requirement_id": "requirement.core",
                    "name": "Core",
                    "category": "PROGRAMME_CORE",
                    "minimum_aus": 3,
                }
            ],
            rules_completeness="PARTIAL",
            source_ids=["source.curriculum"],
        )


def test_unavailable_curriculum_requires_reason_and_contains_no_rules() -> None:
    curriculum = Curriculum(
        curriculum_id="curriculum.overlay.unavailable",
        name="Official overlay curriculum",
        programme="CSC",
        configuration_kind="OVERLAY",
        additional_applicable_programmes=["DSAI"],
        admission_cohort="AY2025-26",
        effective_academic_year="AY2025-26",
        rules_completeness="UNAVAILABLE",
        unavailable_reason="The exact curriculum is available only on the intranet.",
        source_ids=["source.curriculum.index"],
    )

    assert curriculum.rules_completeness.value == "UNAVAILABLE"


def test_unavailable_curriculum_rejects_invented_rule_payload() -> None:
    with pytest.raises(ValidationError, match="unverified rule payloads"):
        Curriculum(
            curriculum_id="curriculum.overlay.unavailable",
            name="Official overlay curriculum",
            programme="CSC",
            admission_cohort="AY2025-26",
            effective_academic_year="AY2025-26",
            graduation_aus=120,
            rules_completeness="UNAVAILABLE",
            unavailable_reason="The exact curriculum is unavailable.",
            source_ids=["source.curriculum.index"],
        )


def test_partial_curriculum_requires_an_explicit_gap() -> None:
    with pytest.raises(ValidationError, match="known_gaps"):
        Curriculum(
            curriculum_id="curriculum.csc.partial",
            name="Computer Science curriculum",
            programme="CSC",
            admission_cohort="AY2025-26",
            effective_academic_year="AY2025-26",
            graduation_aus=135,
            rules_completeness="PARTIAL",
            source_ids=["source.curriculum"],
        )


def test_study_plan_preserves_untyped_source_slot() -> None:
    item = CurriculumCoursePlanItem(
        plan_item_id="plan.csc.y4s1.mpe",
        study_year=4,
        semester="SEMESTER_1",
        position=1,
        course_code=None,
        raw_course_code="SC4xxx",
        label="Major Prescribed Elective",
        category="MPE",
        aus=3,
        source_ids=["source.curriculum"],
    )

    assert item.course_code is None
    assert item.raw_course_code == "SC4xxx"


def test_study_plan_allows_parallel_path_rows_at_same_position() -> None:
    common = {
        "study_year": 3,
        "semester": "SEMESTER_1",
        "position": 1,
        "raw_course_code": "SC4xxx",
        "label": "Major Prescribed Elective",
        "category": "MPE",
        "aus": 3,
        "source_ids": ["source.curriculum"],
    }
    curriculum = Curriculum(
        curriculum_id="curriculum.ce.paths",
        name="Computer Engineering pathway curriculum",
        programme="CE",
        admission_cohort="AY2025-26",
        effective_academic_year="AY2025-26",
        study_plan=[
            {
                **common,
                "plan_item_id": "plan.ce.pi.y3s1.1",
                "path_label": "PI",
            },
            {
                **common,
                "plan_item_id": "plan.ce.pa.y3s1.1",
                "path_label": "PA",
            },
        ],
        rules_completeness="PARTIAL",
        known_gaps=["Other source rows are not included in this fixture."],
        source_ids=["source.curriculum"],
    )

    assert {item.path_label for item in curriculum.study_plan} == {"PI", "PA"}


def test_programme_catalogue_context_requires_a_programme() -> None:
    with pytest.raises(ValidationError, match="require programme"):
        CourseCatalogueAppearance(
            academic_year="AY2025-26",
            semester="SEMESTER_1",
            catalogue_context="PROGRAMME",
            programme=None,
            source_ids=["source.catalogue"],
        )


def test_bde_catalogue_context_does_not_imply_programme_applicability() -> None:
    appearance = CourseCatalogueAppearance(
        academic_year="AY2025-26",
        semester="SEMESTER_1",
        catalogue_context="BDE_POOL",
        programme=None,
        source_ids=["source.catalogue"],
    )

    assert appearance.programme is None


def test_zero_au_official_course_is_valid() -> None:
    course = Course(
        code="HW0001",
        title="Introduction to Academic Communication",
        aus=0,
        source_ids=["source.catalogue"],
    )

    assert course.aus == 0


def test_timetable_meeting_preserves_legacy_class_and_tba_fields() -> None:
    meeting = TimetableMeeting(
        class_type="LEC/STUDIO",
        group="A",
        day=None,
        start_time=None,
        end_time=None,
        raw_day="TBA",
        raw_time="TBA",
        remark="Online arrangement to be announced",
    )

    assert meeting.class_type == "LEC/STUDIO"
    assert meeting.raw_day == "TBA"


def test_timetable_parsed_day_and_times_are_all_or_none() -> None:
    with pytest.raises(ValidationError, match="provided or omitted together"):
        TimetableMeeting(
            class_type="LEC",
            day="MONDAY",
            start_time=None,
            end_time=None,
        )


def test_offering_observed_programmes_require_scope_completeness() -> None:
    with pytest.raises(ValidationError, match="programme scope"):
        CourseOffering(
            offering_id="offering.sc1001.ay2025.s1",
            course_code="SC1001",
            academic_year="AY2025-26",
            semester="SEMESTER_1",
            status="OFFERED",
            observed_programmes=["CSC"],
            scope_completeness="UNKNOWN",
            indexes=[{"index_id": "10001"}],
            source_ids=["source.schedule"],
        )


def test_second_major_requires_one_ccds_base_programme() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        Programme(
            programme_id="programme.csc-entre",
            code="CSC-ENTRE",
            name="Computer Science with a Second Major in Entrepreneurship",
            programme_kind="SECOND_MAJOR",
            ccds_base_programmes=[],
            source_ids=["source.programmes"],
        )


def test_explicit_retrieved_source_requires_checksum() -> None:
    with pytest.raises(ValidationError, match="content_sha256"):
        SourceProvenance(
            source_id="source.catalogue",
            source_type="course_catalogue",
            source_url="https://wish.wis.ntu.edu.sg/example",
            retrieved_at="2026-08-31T12:00:00+08:00",
            checked_at="2026-08-31T12:00:00+08:00",
            version="test",
            origin="VERIFIED_REAL",
            access_status="RETRIEVED",
            classification="PUBLIC",
            retrieval_method="HTML_FORM",
        )
