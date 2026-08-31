from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest


GENERATION = {
    "generator_version": "1.0.0",
    "seed": 42017,
    "source_rule_ids": ["rule.cs.ay2026"],
}


def valid_payloads() -> dict[str, dict[str, Any]]:
    path = {
        "path_id": "path.standard",
        "steps": [
            {
                "step_id": "step.audit",
                "action": "Run the deterministic degree audit",
                "parameters": {"student_id": "SIM-CS-001"},
                "requires_approval": False,
            }
        ],
        "rationale": "The audit establishes the outstanding requirement.",
        "source_rule_ids": ["rule.cs.ay2026"],
    }
    return {
        "source": {
            "source_id": "source.curriculum.cs.2026",
            "source_type": "curriculum",
            "programme": "CS",
            "admission_cohort": "2023",
            "effective_academic_year": "AY2026-27",
            "offering_academic_year": None,
            "source_url": "https://www.ntu.edu.sg/example/curriculum",
            "retrieved_at": "2026-08-30T12:00:00+08:00",
            "version": "2026.1",
            "origin": "VERIFIED_REAL",
            "effective_from": "2026-08-01",
            "effective_to": None,
            "dependent_records": ["curriculum.cs.2023"],
        },
        "programme": {
            "programme_id": "programme.cs",
            "code": "CS",
            "name": "Computer Science",
            "college": "College of Computing and Data Science",
            "active": True,
            "source_ids": ["source.curriculum.cs.2026"],
        },
        "curriculum": {
            "curriculum_id": "curriculum.cs.2023",
            "programme": "CS",
            "admission_cohort": "2023",
            "effective_academic_year": "AY2026-27",
            "graduation_aus": "120",
            "requirements": [
                {
                    "requirement_id": "requirement.cs.core",
                    "name": "Core requirement",
                    "category": "CORE",
                    "minimum_aus": "3",
                    "minimum_courses": 1,
                    "required_courses": ["SC1001"],
                    "elective_pool": [],
                    "constraints": [],
                    "course_lists_completeness": "COMPLETE",
                }
            ],
            "programme_constraints": [],
            "rules_completeness": "COMPLETE",
            "source_ids": ["source.curriculum.cs.2026"],
        },
        "course": {
            "code": "SC1001",
            "title": "Introduction to Computing",
            "aus": "3",
            "prerequisites": {
                "all_of": [],
                "any_of": [],
                "minimum_study_year": None,
                "raw_text": None,
            },
            "exclusions": ["CE1001"],
            "applicable_programmes": ["CS"],
            "programme_categories": {"CS": ["CORE"]},
            "documented_constraints": [],
            "prerequisites_completeness": "COMPLETE",
            "exclusions_completeness": "PARTIAL",
            "applicability_completeness": "COMPLETE",
            "constraints_completeness": "UNKNOWN",
            "source_ids": ["source.course.sc1001"],
        },
        "offering": {
            "offering_id": "offering.sc1001.ay2026.s1",
            "course_code": "SC1001",
            "academic_year": "AY2026-27",
            "semester": "SEMESTER_1",
            "status": "OFFERED",
            "indexes": [
                {
                    "index_id": "10001",
                    "meetings": [
                        {
                            "class_type": "LECTURE",
                            "day": "MONDAY",
                            "start_time": "09:00:00",
                            "end_time": "11:00:00",
                            "venue": "LT1",
                            "teaching_weeks": [1, 2, 3],
                        }
                    ],
                    "capacity": None,
                    "vacancies": None,
                    "waitlist_count": None,
                }
            ],
            "snapshot_at": "2026-08-30T12:00:00+08:00",
            "source_ids": ["source.offering.sc1001.ay2026.s1"],
        },
        "student": {
            "student_id": "SIM-CS-001",
            "programme": "CS",
            "additional_programmes": [],
            "curriculum_ids": ["curriculum.cs.2023"],
            "admission_cohort": "2023",
            "study_year": 4,
            "completed_courses": [
                {
                    "course_code": "SC1001",
                    "grade": "A",
                    "aus_earned": "3",
                    "academic_year": "AY2025-26",
                    "semester": "SEMESTER_2",
                    "attempt": 1,
                }
            ],
            "earned_aus": "120",
            "exemptions": [],
            **GENERATION,
        },
        "audit": {
            "audit_id": "audit.sim.cs.001",
            "student_id": "SIM-CS-001",
            "curriculum_ids": ["curriculum.cs.2023"],
            "academic_year": "AY2026-27",
            "semester": "SEMESTER_1",
            "requirement_results": [
                {
                    "requirement_id": "requirement.cs.core",
                    "status": "SATISFIED",
                    "required_aus": "3",
                    "earned_aus": "3",
                    "completed_courses": ["SC1001"],
                    "outstanding_courses": [],
                    "explanation": "The required course is complete.",
                }
            ],
            "total_earned_aus": "120",
            "total_required_aus": "120",
            "graduation_ready": True,
            **GENERATION,
        },
        "registration": {
            "registration_id": "registration.sim.cs.001",
            "student_id": "SIM-CS-001",
            "academic_year": "AY2026-27",
            "semester": "SEMESTER_1",
            "registered_courses": [
                {
                    "course_code": "SC1001",
                    "index_id": "10001",
                    "aus": "3",
                    "status": "REGISTERED",
                }
            ],
            "timetable": [],
            "workload_aus": "3",
            "missing_required_courses": [],
            **GENERATION,
        },
        "case": {
            "case_id": "case.sim.001",
            "student_id": "SIM-CS-001",
            "problem_type": "REGISTRATION_AFTER_DEADLINE",
            "reason": "A required registration issue was found after Add/Drop.",
            "goal": "Identify a valid path to satisfy the requirement.",
            "requested_action": "Assess the correct exception process.",
            "supporting_documents": [],
            "evidence": [
                {
                    "evidence_id": "evidence.audit.001",
                    "evidence_type": "DEGREE_AUDIT",
                    "reference": "audit.sim.cs.001",
                    "source_id": None,
                }
            ],
            "state": "OPEN",
            "created_at": "2026-08-30T12:00:00+08:00",
            **GENERATION,
        },
        "approval": {
            "approval_id": "approval.sim.001",
            "case_id": "case.sim.001",
            "approver_role": "School undergraduate office",
            "requested_action": "Approve late registration review",
            "status": "PENDING",
            "required_document_ids": [],
            "decision_reason": None,
            "requested_at": "2026-08-30T12:00:00+08:00",
            "decided_at": None,
            **GENERATION,
        },
        "transaction": {
            "transaction_id": "transaction.sim.001",
            "case_id": "case.sim.001",
            "action": "SUBMIT_REGISTRATION",
            "attempt_number": 1,
            "result_code": "SUCCESS",
            "observation": "TRANSACTION_SUCCESS",
            "retryable": False,
            "message": "Registration completed in the simulator.",
            "error_code": None,
            "state_changes": {"registration_status": "REGISTERED"},
            "occurred_at": "2026-08-30T12:05:00+08:00",
            **GENERATION,
        },
        "transaction_script": {
            "script_id": "script.sim.001",
            "case_id": "case.sim.001",
            "steps": [],
            **GENERATION,
        },
        "scenario": {
            "scenario_id": "S1-D01",
            "family": "S1",
            "split": "development",
            "student_id": "SIM-CS-001",
            "case_id": "case.sim.001",
            "transaction_script_id": "script.sim.001",
            "initial_state_refs": [
                "audit.sim.cs.001",
                "registration.sim.cs.001",
            ],
            "initial_state": {"request_received": True},
            "injected_event": None,
            "ground_truth": {
                "valid_initial_paths": [path],
                "valid_final_paths": [],
                "invalid_paths": [],
                "requires_human": False,
                "expected_outcome": "RESOLVED",
            },
            **GENERATION,
        },
    }


@pytest.fixture
def payloads() -> dict[str, dict[str, Any]]:
    values = valid_payloads()
    values["transaction_script"]["steps"] = [deepcopy(values["transaction"])]
    return values
