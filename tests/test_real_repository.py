from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from graduation_exception_agent.data.real import (
    RealDataRepository,
    load_course_offerings,
    load_courses,
    load_curricula,
    load_programmes,
    load_source_manifest,
    validate_real_data,
)
from graduation_exception_agent.errors import DataIntegrityError
from graduation_exception_agent.models import PolicyDocument, PolicySection, SourceOrigin


REAL_ROOT = Path(__file__).parents[1] / "data" / "real"


@pytest.fixture(scope="module")
def repository() -> RealDataRepository:
    return RealDataRepository.from_directory(REAL_ROOT)


def test_production_real_data_loads_without_network_or_credentials(
    repository: RealDataRepository,
) -> None:
    assert len(repository.sources) == 48
    assert {programme.code for programme in repository.programmes} == {
        "ACDA",
        "AISC",
        "BACF",
        "BCE",
        "BCG",
        "BTECH-COMP",
        "CE",
        "CE-BUS",
        "CE-DANA",
        "CE-ENT",
        "CE-ITP",
        "CE-SUST",
        "CEEC",
        "CSC",
        "CSC-ENT",
        "CSC-ITP",
        "CSC-SUST",
        "CSEC",
        "DSAI",
        "DSAI-SUST",
        "ECDS",
        "MACS",
    }
    assert len(repository.curricula) == 23
    assert sum(len(item.study_plan) for item in repository.curricula) == 1176
    assert len(repository.courses) == 219
    assert sum(
        len(course.catalogue_appearances) for course in repository.courses
    ) == 1035
    assert len(repository.offerings) == 210
    assert sum(len(offering.indexes) for offering in repository.offerings) == 2108
    assert len(repository.coverage.targets) == 8


def test_typed_file_loaders_cover_each_json_dataset() -> None:
    sources = load_source_manifest(REAL_ROOT / "source_manifest.json")

    assert len(sources) == 48
    assert len(
        load_programmes(REAL_ROOT / "programmes.json", sources=sources)
    ) == 22
    assert len(load_curricula(REAL_ROOT / "curriculum.json", sources=sources)) == 23
    assert len(load_courses(REAL_ROOT / "courses.json", sources=sources)) == 219
    offerings = load_course_offerings(
        REAL_ROOT / "course_offerings.json", sources=sources
    )
    assert offerings.status.value == "COLLECTED"
    assert len(offerings.offerings) == 210


def test_production_bundle_has_no_consistency_errors(
    repository: RealDataRepository,
) -> None:
    issues = validate_real_data(repository.bundle)

    assert not any(issue.severity.value == "ERROR" for issue in issues)
    assert {issue.code for issue in issues} == {"UNKNOWN_COURSE_REFERENCE"}
    assert issues == repository.consistency_issues


def test_provenance_is_preserved_and_reverse_linked(
    repository: RealDataRepository,
) -> None:
    curriculum = repository.get_curriculum("curriculum.csc.ay2025-26")
    provenance = repository.provenance_for(curriculum.source_ids)

    assert len(provenance) == 1
    assert provenance[0].origin is SourceOrigin.VERIFIED_REAL
    assert curriculum.curriculum_id in provenance[0].dependent_records
    assert provenance[0].source_url is not None


def test_curriculum_queries_are_cohort_and_year_specific(
    repository: RealDataRepository,
) -> None:
    found = repository.find_curricula(
        programme="csc",
        admission_cohort="ay2025-26",
        effective_academic_year="ay2025-26",
    )

    assert {item.curriculum_id for item in found} == {
        "curriculum.csc.ay2025-26",
        "curriculum.csc-business.ay2025-26",
    }
    assert repository.find_curricula(
        programme="CSC", admission_cohort="AY2026-27"
    ) == ()


def test_csc_curriculum_preserves_both_official_graduation_paths(
    repository: RealDataRepository,
) -> None:
    curriculum = repository.get_curriculum("curriculum.csc.ay2025-26")

    assert curriculum.graduation_aus is None
    assert {path.graduation_aus for path in curriculum.graduation_paths} == {135, 136}
    assert {path.category_aus["MPE"] for path in curriculum.graduation_paths} == {
        35,
        36,
    }
    assert {path.minimum_course_counts["MPE"] for path in curriculum.graduation_paths} == {
        9,
        12,
    }


def test_verified_policy_query_excludes_every_unknown_section(
    repository: RealDataRepository,
) -> None:
    verified = repository.policy_sections(admission_cohort="AY2026-27")

    assert verified
    assert all(section.origin is SourceOrigin.VERIFIED_REAL for section in verified)
    assert not any(section.section_id.startswith("unknown.") for section in verified)


def test_policy_query_respects_explicit_empty_origin_filter(
    repository: RealDataRepository,
) -> None:
    assert repository.policy_sections(
        origins=frozenset(), admission_cohort="AY2026-27"
    ) == ()


def test_policy_query_requires_context_and_excludes_unscoped_by_default(
    repository: RealDataRepository,
) -> None:
    with pytest.raises(ValueError, match="require academic_year or admission_cohort"):
        repository.policy_sections()

    scoped = repository.policy_sections(admission_cohort="AY2026-27")
    with_unscoped = repository.policy_sections(
        admission_cohort="AY2026-27", include_unscoped=True
    )

    assert not any(section.section_id.startswith("policy.role.") for section in scoped)
    assert any(
        section.section_id == "policy.role.ccds_undergraduate_office"
        for section in with_unscoped
    )
    ay2025 = repository.policy_sections(admission_cohort="AY2025-26")
    assert ay2025
    assert any(
        section.section_id == "policy.registration.stars.ay2024-26"
        for section in ay2025
    )


def test_default_policy_query_excludes_simulated_policy(
    repository: RealDataRepository,
) -> None:
    simulated = PolicySection(
        section_id="simulated.policy.test",
        title="Prototype-only test rule",
        origin="SIMULATED_POLICY",
        source_ids=[],
        applicability="EXPLICIT",
        applicable_academic_years=["AY2026-27"],
        applicable_admission_cohorts=[],
        applicability_note="Deterministic test scope.",
        body_markdown=(
            "SIMULATED POLICY FOR PROTOTYPE\n\nA deterministic test-only rule."
        ),
        start_line=1,
        end_line=3,
    )
    first = repository.policies[0]
    document_payload = first.model_dump(mode="python")
    document_payload["sections"] = [*first.sections, simulated]
    document = PolicyDocument.model_validate(document_payload)
    coverage_payload = repository.coverage.model_dump(mode="python")
    registration_target = next(
        target
        for target in coverage_payload["targets"]
        if target["dataset"] == "REGISTRATION_GUIDANCE"
    )
    registration_target["expected_record_ids"].append(simulated.section_id)
    registration_target["expected_record_count"] += 1
    bundle = replace(
        repository.bundle,
        policies=(document, *repository.policies[1:]),
        coverage=type(repository.coverage).model_validate(coverage_payload),
    )
    mixed_repository = RealDataRepository(bundle)

    default_sections = mixed_repository.policy_sections(
        academic_year="AY2026-27"
    )
    simulated_sections = mixed_repository.policy_sections(
        origins=frozenset({SourceOrigin.SIMULATED_POLICY}),
        academic_year="AY2026-27",
    )

    assert simulated not in default_sections
    assert [section.section_id for section in simulated_sections] == [
        "simulated.policy.test"
    ]


def test_offerings_are_a_collected_public_schedule_snapshot(
    repository: RealDataRepository,
) -> None:
    collection = repository.bundle.offering_collection

    assert collection.status.value == "COLLECTED"
    assert len(repository.offerings) == 210
    assert collection.placeholder_reason is None
    assert all(
        index.capacity is None
        and index.vacancies is None
        and index.waitlist_count is None
        for offering in repository.offerings
        for index in offering.indexes
    )


def test_validator_detects_unknown_source_id(
    repository: RealDataRepository,
) -> None:
    unknown_source = "source.does.not.exist"
    original = repository.courses[0]
    bad_course = original.model_copy(
        update={
            "source_ids": [unknown_source],
            "catalogue_appearances": [
                appearance.model_copy(update={"source_ids": [unknown_source]})
                for appearance in original.catalogue_appearances
            ],
        }
    )
    bad_bundle = replace(
        repository.bundle,
        courses=(bad_course, *repository.courses[1:]),
    )

    issues = validate_real_data(bad_bundle)

    assert any(issue.code == "UNKNOWN_SOURCE_ID" for issue in issues)

    with pytest.raises(DataIntegrityError, match="UNKNOWN_SOURCE_ID"):
        RealDataRepository(bad_bundle)

    diagnostic_repository = RealDataRepository(bad_bundle, fail_on_errors=False)
    assert any(
        issue.code == "UNKNOWN_SOURCE_ID"
        for issue in diagnostic_repository.consistency_issues
    )


def test_directory_loading_enforces_source_registry(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "real"
    shutil.copytree(REAL_ROOT, data_root)
    courses_path = data_root / "courses.json"
    payload = json.loads(courses_path.read_text(encoding="utf-8"))
    payload[0]["source_ids"] = ["source.does.not.exist"]
    for appearance in payload[0]["catalogue_appearances"]:
        appearance["source_ids"] = ["source.does.not.exist"]
    courses_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with pytest.raises(DataIntegrityError, match="UNKNOWN_SOURCE_ID"):
        RealDataRepository.from_directory(data_root)


def test_repository_defensive_copies_prevent_external_mutation(
    repository: RealDataRepository,
) -> None:
    exposed_course = repository.courses[0]
    exposed_course.source_ids.append("source.does.not.exist")
    exposed_bundle = repository.bundle
    exposed_bundle.sources[0].dependent_records.append("record.does.not.exist")

    assert "source.does.not.exist" not in repository.courses[0].source_ids
    assert "record.does.not.exist" not in repository.sources[0].dependent_records
    assert not any(
        issue.severity.value == "ERROR"
        for issue in repository.consistency_issues
    )


def test_validator_detects_curriculum_course_outside_collected_subset(
    repository: RealDataRepository,
) -> None:
    curriculum = repository.curricula[0]
    requirement = curriculum.requirements[0].model_copy(
        update={"required_courses": ["SC9999"]}
    )
    bad_curriculum = curriculum.model_copy(
        update={
            "requirements": [requirement, *curriculum.requirements[1:]]
        }
    )
    bad_bundle = replace(
        repository.bundle,
        curricula=(bad_curriculum, *repository.curricula[1:]),
    )

    issues = validate_real_data(bad_bundle)

    assert any(issue.code == "UNKNOWN_CURRICULUM_COURSE" for issue in issues)


def test_validator_detects_source_academic_year_mismatch(
    repository: RealDataRepository,
) -> None:
    target_id = "ntu.ccds.curriculum.csc.ay2025-26"
    sources = tuple(
        source.model_copy(update={"effective_academic_year": "AY2026-27"})
        if source.source_id == target_id
        else source
        for source in repository.sources
    )
    bad_bundle = replace(repository.bundle, sources=sources)

    issues = validate_real_data(bad_bundle)

    assert any(
        issue.code == "SOURCE_ACADEMIC_YEAR_MISMATCH"
        and issue.referenced_id == target_id
        for issue in issues
    )


def test_validator_detects_source_type_origin_and_reverse_link_failures(
    repository: RealDataRepository,
) -> None:
    target_id = "ntu.ccds.curriculum.csc.ay2025-26"
    curriculum_id = "curriculum.csc.ay2025-26"
    sources = tuple(
        source.model_copy(
            update={
                "source_type": "registration_guidance",
                "origin": "SIMULATED_POLICY",
                "dependent_records": [
                    record_id
                    for record_id in source.dependent_records
                    if record_id != curriculum_id
                ],
            }
        )
        if source.source_id == target_id
        else source
        for source in repository.sources
    )
    bad_bundle = replace(repository.bundle, sources=sources)

    codes = {issue.code for issue in validate_real_data(bad_bundle)}

    assert "SOURCE_TYPE_MISMATCH" in codes
    assert "SOURCE_ORIGIN_MISMATCH" in codes
    assert "MISSING_REVERSE_PROVENANCE" in codes


def test_reloading_same_tree_is_deterministic(
    repository: RealDataRepository,
) -> None:
    second = RealDataRepository.from_directory(REAL_ROOT)

    assert second.bundle == repository.bundle


def test_missing_record_raises_key_error_without_fallback(
    repository: RealDataRepository,
) -> None:
    with pytest.raises(KeyError):
        repository.get_source("missing.source")
