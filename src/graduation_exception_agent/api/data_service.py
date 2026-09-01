"""Read-only, evaluator-safe projections for the Stage 8 data explorer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from graduation_exception_agent.api.models import (
    DataCatalogResponse,
    DataCatalogStats,
    DataColumn,
    DataDatasetSummary,
    DataDomainSummary,
    DataField,
    DataFilterOptions,
    DataPageResponse,
    DataRecord,
    DataRelationship,
    DataSection,
)
from graduation_exception_agent.config import AppSettings
from graduation_exception_agent.data.real.repository import RealDataRepository
from graduation_exception_agent.data.simulated.repository import (
    SimulatedDataRepository,
)


@dataclass(frozen=True, slots=True)
class _Dataset:
    summary: DataDatasetSummary
    records: tuple[DataRecord, ...]


DOMAINS = (
    DataDomainSummary(
        domain="academic",
        label="Academic & policy",
        description="Official-public CCDS academic rules and source material.",
        dataset_ids=[],
    ),
    DataDomainSummary(
        domain="operational",
        label="Operational simulation",
        description="Observable, anonymous student and registration state.",
        dataset_ids=[],
    ),
    DataDomainSummary(
        domain="cases",
        label="Case operations",
        description="Exception cases, approvals and safe scenario metadata.",
        dataset_ids=[],
    ),
    DataDomainSummary(
        domain="governance",
        label="Sources & quality",
        description="Coverage, provenance, limitations and consistency checks.",
        dataset_ids=[],
    ),
)


class DataService:
    """Build safe, processed records without exposing evaluator-only payloads."""

    def __init__(self, settings: AppSettings) -> None:
        root = Path(settings.data_dir)
        real = RealDataRepository.from_directory(root / "real")
        simulated = SimulatedDataRepository.from_directory(
            root / "simulated", real_repository=real
        )
        self._datasets = self._build(real, simulated)

    def catalog(self) -> DataCatalogResponse:
        datasets = [dataset.summary for dataset in self._datasets.values()]
        domains = []
        for domain in DOMAINS:
            domains.append(
                domain.model_copy(
                    update={
                        "dataset_ids": [
                            item.dataset_id
                            for item in datasets
                            if item.domain == domain.domain
                        ]
                    }
                )
            )
        accessible = [item for item in datasets if item.accessible]
        return DataCatalogResponse(
            domains=domains,
            datasets=datasets,
            stats=DataCatalogStats(
                datasets=len(datasets),
                accessible_records=sum(item.record_count for item in accessible),
                real_records=sum(
                    item.record_count for item in accessible if item.provenance == "real"
                ),
                simulated_records=sum(
                    item.record_count
                    for item in accessible
                    if item.provenance == "simulated"
                ),
                restricted_records=sum(
                    item.record_count for item in datasets if not item.accessible
                ),
            ),
        )

    def page(
        self,
        dataset_id: str,
        *,
        page: int,
        page_size: int,
        search: str = "",
        programme: str = "",
        status: str = "",
        sort: str = "",
        direction: str = "asc",
    ) -> DataPageResponse:
        dataset = self._datasets.get(dataset_id)
        if dataset is None:
            raise KeyError(f"unknown data set {dataset_id!r}")
        if not dataset.summary.accessible:
            raise PermissionError(
                "This evaluator-only data set is intentionally unavailable to UI-4."
            )
        all_records = list(dataset.records)
        programme_options = _options(all_records, ("programme", "programmes"))
        status_options = _options(
            all_records,
            ("status", "state", "outcome", "completeness", "runtime_status"),
        )
        needle = search.strip().casefold()
        if needle:
            all_records = [
                record
                for record in all_records
                if needle in _searchable_text(record).casefold()
            ]
        if programme:
            target = programme.casefold()
            all_records = [
                record
                for record in all_records
                if target
                in " ".join(
                    [record.cells.get("programme", ""), record.cells.get("programmes", "")]
                ).casefold()
            ]
        if status:
            target = status.casefold()
            all_records = [
                record
                for record in all_records
                if target
                in " ".join(
                    [
                        record.status or "",
                        record.cells.get("status", ""),
                        record.cells.get("state", ""),
                        record.cells.get("outcome", ""),
                        record.cells.get("completeness", ""),
                        record.cells.get("runtime_status", ""),
                    ]
                ).casefold()
            ]
        allowed_sort = {column.key for column in dataset.summary.columns}
        sort_key = sort if sort in allowed_sort else dataset.summary.default_sort
        if sort_key:
            column = next(
                (
                    item
                    for item in dataset.summary.columns
                    if item.key == sort_key
                ),
                None,
            )
            all_records.sort(
                key=lambda record: _sort_value(
                    record.cells.get(sort_key, ""),
                    column.kind if column is not None else "text",
                ),
                reverse=direction == "desc",
            )
        total = len(all_records)
        start = (page - 1) * page_size
        return DataPageResponse(
            dataset=dataset.summary,
            page=page,
            page_size=page_size,
            total=total,
            records=all_records[start : start + page_size],
            filters=DataFilterOptions(
                programmes=programme_options, statuses=status_options
            ),
        )

    def _build(
        self,
        real: RealDataRepository,
        simulated: SimulatedDataRepository,
    ) -> dict[str, _Dataset]:
        real_bundle = real.bundle
        # Access is confined to this projection boundary. Every scenario and student
        # adapter below positively selects fields and never serialises ground truth,
        # injected events, terminal profiles or transaction steps.
        sim_bundle = simulated.bundle
        datasets: dict[str, _Dataset] = {}

        def add(
            dataset_id: str,
            domain: str,
            label: str,
            description: str,
            provenance: str,
            columns: list[tuple[str, str, str]],
            records: Iterable[DataRecord],
            default_sort: str | None = None,
            accessible: bool = True,
            record_count: int | None = None,
        ) -> None:
            frozen = tuple(records)
            summary = DataDatasetSummary(
                dataset_id=dataset_id,
                domain=domain,
                label=label,
                description=description,
                provenance=provenance,
                record_count=len(frozen) if record_count is None else record_count,
                accessible=accessible,
                columns=[
                    DataColumn(key=key, label=column_label, kind=kind)
                    for key, column_label, kind in columns
                ],
                default_sort=default_sort,
            )
            datasets[dataset_id] = _Dataset(summary=summary, records=frozen)

        programmes = [item.model_dump(mode="json") for item in real.programmes]
        curricula = [item.model_dump(mode="json") for item in real.curricula]
        courses = [item.model_dump(mode="json") for item in real.courses]
        offerings = [item.model_dump(mode="json") for item in real.offerings]
        sources = [item.model_dump(mode="json") for item in real.sources]

        add(
            "programmes", "academic", "Programmes", "Current public CCDS programme inventory.", "real",
            [("code", "Code", "text"), ("name", "Programme", "text"), ("programme_kind", "Kind", "status"), ("study_mode", "Mode", "status"), ("active", "Active", "status")],
            (_record(item, "programme_id", "code", "name", "real", ["code", "name", "college", "programme_kind", "study_mode", "ccds_base_programmes", "active"], source_ids=item.get("source_ids", []), relationships=[_rel("Curricula", "curricula", [c["curriculum_id"] for c in curricula if c["programme"] == item["code"] or item["code"] in c.get("additional_applicable_programmes", [])])]) for item in programmes),
            "code",
        )
        add(
            "curricula", "academic", "Curricula", "Cohort and pathway-specific graduation rules.", "real",
            [("programme", "Programme", "text"), ("name", "Curriculum", "text"), ("admission_cohort", "Cohort", "text"), ("graduation_aus", "Required AUs", "number"), ("rules_completeness", "Completeness", "status")],
            (_record(item, "curriculum_id", "name", "programme", "real", ["programme", "configuration_kind", "admission_cohort", "effective_academic_year", "graduation_aus", "graduation_paths", "requirements", "programme_constraints", "rules_completeness", "known_gaps", "unavailable_reason"], status=item.get("rules_completeness"), source_ids=item.get("source_ids", []), relationships=[_rel("Programme", "programmes", [next((p["programme_id"] for p in programmes if p["code"] == item["programme"]), item["programme"])]), _rel("Referenced courses", "courses", _curriculum_courses(item))], quality_notes=item.get("known_gaps", [])) for item in curricula),
            "programme",
        )
        add(
            "courses", "academic", "Courses", "Grounded CCDS-relevant course catalogue subset.", "real",
            [("code", "Code", "text"), ("title", "Title", "text"), ("aus", "AUs", "number"), ("programmes", "Programmes", "list"), ("prerequisites_completeness", "Prerequisites", "status")],
            (_record({**item, "programmes": item.get("applicable_programmes", [])}, "code", "code", "title", "real", ["code", "title", "aus", "prerequisites", "exclusions", "applicable_programmes", "programme_categories", "documented_constraints", "prerequisites_completeness", "exclusions_completeness", "applicability_completeness", "constraints_completeness"], status=item.get("prerequisites_completeness"), source_ids=item.get("source_ids", []), relationships=[_rel("Offerings", "offerings", [o["offering_id"] for o in offerings if o["course_code"] == item["code"]])]) for item in courses),
            "code",
        )
        add(
            "offerings", "academic", "Course offerings", "AY2026-27 Semester 1 offering templates.", "real",
            [("course_code", "Course", "text"), ("academic_year", "Academic year", "text"), ("semester", "Semester", "status"), ("status", "Status", "status"), ("index_count", "Indexes", "number")],
            (_record({**item, "index_count": len(item.get("indexes", []))}, "offering_id", "course_code", "academic_year", "real", ["course_code", "academic_year", "semester", "status", "observed_programmes", "scope_completeness", "index_count"], status=item.get("status"), source_ids=item.get("source_ids", []), relationships=[_rel("Course", "courses", [item["course_code"]]), _rel("Indexes", "indexes", [f'{item["offering_id"]}:{index["index_id"]}' for index in item.get("indexes", [])])]) for item in offerings),
            "course_code",
        )
        index_records = []
        for offering in offerings:
            for index in offering.get("indexes", []):
                meetings = index.get("meetings", [])
                index_records.append(_record({**index, "record_id": f'{offering["offering_id"]}:{index["index_id"]}', "course_code": offering["course_code"], "academic_year": offering["academic_year"], "semester": offering["semester"], "schedule": [_meeting_text(meeting) for meeting in meetings], "programmes": index.get("observed_programmes", [])}, "record_id", "index_id", "course_code", "real", ["index_id", "course_code", "academic_year", "semester", "schedule", "observed_programmes", "capacity", "vacancies", "waitlist_count"], relationships=[_rel("Offering", "offerings", [offering["offering_id"]]), _rel("Course", "courses", [offering["course_code"]])]))
        add("indexes", "academic", "Indexes & timetable", "Flattened class indexes and meeting patterns.", "real", [("index_id", "Index", "text"), ("course_code", "Course", "text"), ("semester", "Semester", "status"), ("schedule", "Meeting", "list"), ("programmes", "Programmes", "list")], index_records, "course_code")

        calendar = real_bundle.academic_calendar.model_dump(mode="json")
        add("calendar_events", "academic", "Academic calendar", "Parsed semester, registration and Add/Drop dates.", "real", [("name", "Event", "text"), ("event_type", "Type", "status"), ("semester", "Semester", "status"), ("start_date", "Start", "date"), ("end_date", "End", "date")], (_record(event, "event_id", "name", "description", "real", ["event_type", "semester", "start_date", "end_date", "date_precision", "description", "origin"], status=event.get("date_precision"), source_ids=event.get("source_ids", [])) for event in calendar.get("events", [])), "start_date")

        policy_records = []
        for policy in real_bundle.policies:
            document = policy.model_dump(mode="json")
            for section in document.get("sections", []):
                policy_records.append(_record({**section, "document_type": document["document_type"], "document_title": document["title"], "cohorts": section.get("applicable_admission_cohorts", [])}, "section_id", "title", "document_title", "real", ["document_type", "origin", "applicability", "applicable_academic_years", "applicable_admission_cohorts", "applicability_note", "body_markdown"], status=section.get("applicability"), source_ids=section.get("source_ids", [])))
        add("policy_sections", "academic", "Policy sections", "Parsed registration, exception and approval guidance.", "real", [("title", "Section", "text"), ("document_type", "Document", "status"), ("origin", "Origin", "status"), ("applicability", "Applicability", "status"), ("cohorts", "Cohorts", "list")], policy_records, "title")

        students = [item.model_dump(mode="json") for item in sim_bundle.students]
        audits = [item.model_dump(mode="json") for item in sim_bundle.degree_audits]
        registrations = [item.model_dump(mode="json") for item in sim_bundle.current_registrations]
        states = [item.model_dump(mode="json") for item in sim_bundle.offering_states]
        cases = [item.model_dump(mode="json") for item in sim_bundle.exception_cases]
        approvals = [item.model_dump(mode="json") for item in sim_bundle.approvals]
        scenarios = [item.model_dump(mode="json") for item in sim_bundle.scenarios]

        add("students", "operational", "Student records", "Anonymous observable student profiles; evaluator terminal profiles are omitted.", "simulated", [("student_id", "Student", "text"), ("programme", "Programme", "text"), ("admission_cohort", "Cohort", "text"), ("study_year", "Study year", "number"), ("earned_aus", "Earned AUs", "number")], (_record(item, "student_id", "student_id", "programme", "simulated", ["programme", "additional_programmes", "admission_cohort", "study_year", "academic_standing", "earned_aus", "completed_courses", "exemptions", "has_outstanding_fees", "curriculum_id", "simulation_period_id"], status=item.get("academic_standing"), lineage_ids=item.get("source_rule_ids", []), relationships=[_rel("Curriculum", "curricula", [item["curriculum_id"]]), _rel("Degree audit", "degree_audits", [a["audit_id"] for a in audits if a["student_id"] == item["student_id"]]), _rel("Registration", "registrations", [r["registration_id"] for r in registrations if r["student_id"] == item["student_id"]]), _rel("Cases", "exception_cases", [c["case_id"] for c in cases if c["student_id"] == item["student_id"]])]) for item in students), "student_id")
        add("degree_audits", "operational", "Degree audits", "Completed, outstanding and partially satisfied requirements.", "simulated", [("audit_id", "Audit", "text"), ("student_id", "Student", "text"), ("outcome", "Outcome", "status"), ("total_earned_aus", "Earned AUs", "number"), ("total_required_aus", "Required AUs", "number")], (_record({**item, "outcome": item.get("audit_outcome")}, "audit_id", "audit_id", "student_id", "simulated", ["student_id", "curriculum_id", "audit_basis", "audit_outcome", "total_earned_aus", "total_required_aus", "requirement_results", "limitations", "simulation_academic_year", "semester"], status=item.get("audit_outcome"), lineage_ids=item.get("source_rule_ids", []), quality_notes=item.get("limitations", []), relationships=[_rel("Student", "students", [item["student_id"]]), _rel("Curriculum", "curricula", [item["curriculum_id"]])]) for item in audits), "audit_id")
        add("registrations", "operational", "Current registrations", "Workload, timetable and missing required courses.", "simulated", [("registration_id", "Registration", "text"), ("student_id", "Student", "text"), ("phase", "Phase", "status"), ("workload_aus", "Workload", "number"), ("missing_count", "Missing", "number")], (_record({**item, "missing_count": len(item.get("missing_required_courses", []))}, "registration_id", "registration_id", "student_id", "simulated", ["student_id", "phase", "scenario_time", "simulation_academic_year", "semester", "registered_courses", "missing_required_courses", "timetable", "workload_aus", "workload_limit_aus"], status=item.get("phase"), lineage_ids=item.get("source_rule_ids", []), relationships=[_rel("Student", "students", [item["student_id"]]), _rel("Offering states", "offering_states", [row.get("offering_state_id") for row in item.get("registered_courses", []) if row.get("offering_state_id")])]) for item in registrations), "registration_id")
        add("offering_states", "operational", "Live offering state", "Simulated capacity, vacancy, waitlist and runtime status.", "simulated", [("state_id", "State", "text"), ("template_index_id", "Index", "text"), ("runtime_status", "Status", "status"), ("vacancies", "Vacancies", "number"), ("waitlist_count", "Waitlist", "number")], (_record(item, "state_id", "template_index_id", "state_id", "simulated", ["template_offering_id", "template_index_id", "template_academic_year", "template_semester", "runtime_status", "available", "capacity", "vacancies", "waitlist_count", "unavailable_reason", "version"], status=item.get("runtime_status"), lineage_ids=item.get("source_rule_ids", []), relationships=[_rel("Offering", "offerings", [item["template_offering_id"]])]) for item in states), "state_id")
        scopes = [item.model_dump(mode="json") for item in sim_bundle.simulation_scopes]
        add("simulation_scopes", "operational", "Simulation scopes", "Declared time, cohort and curriculum boundaries.", "simulated", [("simulation_scope_id", "Scope", "text"), ("programme", "Programme", "text"), ("admission_cohort", "Cohort", "text"), ("simulation_academic_year", "Simulated year", "text"), ("student_count", "Students", "number")], (_record(item, "simulation_scope_id", "simulation_scope_id", "programme", "simulated", ["programme", "admission_cohort", "curriculum_id", "simulation_academic_year", "simulation_semester", "template_academic_year", "template_semester", "terminal_study_year", "student_count", "counterfactual_time_basis", "audit_basis", "accepted_gap_ids"], lineage_ids=item.get("source_rule_ids", []), quality_notes=item.get("accepted_gap_ids", []), relationships=[_rel("Curriculum", "curricula", [item["curriculum_id"]])]) for item in scopes), "programme")
        assumptions = [item.model_dump(mode="json") for item in sim_bundle.audit_assumptions]
        add("audit_assumptions", "operational", "Audit assumptions", "Explicit assumptions and limitations used for simulation.", "simulated", [("assumption_id", "Assumption", "text"), ("kind", "Kind", "status"), ("description", "Description", "text"), ("scope", "Scope", "text")], (_record({**item, "scope": item.get("simulation_scope_id")}, "assumption_id", "assumption_id", "description", "simulated", ["kind", "description", "declared_value", "limitations", "simulation_scope_id", "prototype_policy_id", "affected_record_ids"], lineage_ids=item.get("source_rule_ids", []), quality_notes=item.get("limitations", [])) for item in assumptions), "assumption_id")

        add("exception_cases", "cases", "Exception cases", "Requests, evidence readiness and current case state.", "simulated", [("case_id", "Case", "text"), ("student_id", "Student", "text"), ("problem_type", "Type", "status"), ("state", "State", "status"), ("submission_ready", "Ready", "status")], (_record(item, "case_id", "case_id", "reason", "simulated", ["student_id", "problem_type", "state", "goal", "reason", "requested_action", "submission_ready", "supporting_documents", "unresolved_questions", "evidence", "scenario_time", "policy_section_ids"], status=item.get("state"), lineage_ids=item.get("source_rule_ids", []), relationships=[_rel("Student", "students", [item["student_id"]]), _rel("Audit", "degree_audits", [item["audit_id"]]), _rel("Registration", "registrations", [item["registration_id"]]), _rel("Approvals", "approvals", [a["approval_id"] for a in approvals if a["case_id"] == item["case_id"]])]) for item in cases), "case_id")
        add("approvals", "cases", "Approvals", "Observable simulated approval state and authority.", "simulated", [("approval_id", "Approval", "text"), ("case_id", "Case", "text"), ("approver_role", "Approver", "text"), ("status", "Status", "status"), ("observable", "Observable", "status")], (_record(item, "approval_id", "approval_id", "approver_role", "simulated", ["case_id", "approver_role", "requested_action", "status", "observable", "requested_at", "decided_at", "decision_reason", "required_document_ids", "basis"], status=item.get("status"), lineage_ids=item.get("source_rule_ids", []), relationships=[_rel("Case", "exception_cases", [item["case_id"]])]) for item in approvals), "approval_id")
        safe_scenarios = []
        for item in scenarios:
            student = next((row for row in students if row["student_id"] == item["student_id"]), {})
            safe_scenarios.append(_record({"scenario_id": item["scenario_id"], "family": item["family"], "split": item["split"], "student_id": item["student_id"], "case_id": item["case_id"], "audit_id": item["audit_id"], "registration_id": item["registration_id"], "curriculum_id": item["curriculum_id"], "programme": student.get("programme", ""), "offering_state_count": len(item.get("offering_state_ids", [])), "source_rule_ids": item.get("source_rule_ids", [])}, "scenario_id", "scenario_id", "family", "simulated", ["family", "split", "programme", "student_id", "case_id", "audit_id", "registration_id", "curriculum_id", "offering_state_count"], status=item.get("split"), lineage_ids=item.get("source_rule_ids", []), relationships=[_rel("Student", "students", [item["student_id"]]), _rel("Case", "exception_cases", [item["case_id"]]), _rel("Audit", "degree_audits", [item["audit_id"]]), _rel("Registration", "registrations", [item["registration_id"]])]))
        add("scenarios", "cases", "Scenario catalogue", "Safe metadata for demo, development and evaluation cases; oracles are omitted.", "simulated", [("scenario_id", "Scenario", "text"), ("family", "Family", "status"), ("split", "Split", "status"), ("programme", "Programme", "text"), ("student_id", "Student", "text")], safe_scenarios, "scenario_id")

        add("sources", "governance", "Source manifest", "Public-source retrieval, scope and dependency lineage.", "real", [("source_id", "Source", "text"), ("source_type", "Type", "status"), ("origin", "Origin", "status"), ("access_status", "Access", "status"), ("checked_at", "Checked", "date")], (_record(item, "source_id", "source_id", "version", "real", ["source_type", "programme", "admission_cohort", "effective_academic_year", "offering_academic_year", "source_url", "retrieved_at", "checked_at", "version", "origin", "access_status", "classification", "retrieval_method", "access_note", "effective_from", "effective_to", "dependent_records"], status=item.get("access_status"), relationships=_source_relationships(item.get("dependent_records", []))) for item in sources), "source_id")
        coverage = real.coverage.model_dump(mode="json")
        add("coverage_targets", "governance", "Coverage & known gaps", "Declared inventory targets, completeness and unresolved gaps.", "derived", [("target_id", "Target", "text"), ("dataset", "Dataset", "status"), ("inventory_status", "Inventory", "status"), ("content_status", "Content", "status"), ("expected_record_count", "Expected", "number")], (_record(target, "target_id", "target_id", "scope_description", "derived", ["dataset", "scope_description", "scope_parameters", "expected_record_count", "inventory_status", "content_status", "required_fields", "discovery_source_ids", "gaps"], status=target.get("content_status"), source_ids=target.get("discovery_source_ids", []), quality_notes=[_value(gap) for gap in target.get("gaps", [])]) for target in coverage.get("targets", [])), "target_id")
        issues = [item.model_dump(mode="json") for item in (*real.consistency_issues, *simulated.consistency_issues)]
        add("consistency_issues", "governance", "Consistency checks", "Cross-file validation results from both grounded and simulated packages.", "derived", [("code", "Check", "text"), ("severity", "Severity", "status"), ("dataset", "Dataset", "status"), ("record_id", "Record", "text"), ("message", "Message", "text")], (_record({**item, "issue_id": f'{item["code"]}:{index}'}, "issue_id", "code", "message", "derived", ["severity", "dataset", "record_id", "field", "referenced_id", "message"], status=item.get("severity"), quality_notes=[item["message"]]) for index, item in enumerate(issues)), "severity")
        add("transaction_scripts", "cases", "Transaction scripts", "Evaluator-only injected outcomes used for deterministic testing.", "restricted", [], (), accessible=False, record_count=len(sim_bundle.transaction_scripts))
        add("evaluation_contracts", "governance", "Evaluation ground truth", "Evaluator-only expected paths, approvals and escalation oracles.", "restricted", [], (), accessible=False, record_count=len(sim_bundle.scenarios))
        return datasets


def _record(
    item: dict[str, Any],
    id_key: str,
    title_key: str,
    subtitle_key: str,
    provenance: str,
    fields: list[str],
    *,
    status: str | None = None,
    source_ids: list[str] | None = None,
    lineage_ids: list[str] | None = None,
    relationships: list[DataRelationship] | None = None,
    quality_notes: list[str] | None = None,
) -> DataRecord:
    cells = {key: _value(item.get(key)) for key in fields}
    cells.update(
        {
            key: _value(value)
            for key, value in item.items()
            if key
            in {
                "code", "name", "title", "programme", "programmes", "programme_kind", "study_mode", "active",
                "admission_cohort", "graduation_aus", "rules_completeness", "aus", "prerequisites_completeness",
                "course_code", "academic_year", "semester", "status", "index_count", "index_id", "schedule",
                "document_type", "origin", "applicability", "cohorts", "student_id", "study_year", "earned_aus",
                "audit_id", "outcome", "total_earned_aus", "total_required_aus", "registration_id", "phase",
                "workload_aus", "missing_count", "state_id", "template_index_id", "runtime_status", "vacancies",
                "waitlist_count", "simulation_scope_id", "student_count", "assumption_id", "kind", "description",
                "scope", "case_id", "problem_type", "state", "submission_ready", "approval_id", "approver_role",
                "observable", "scenario_id", "family", "split", "source_id", "source_type", "access_status", "checked_at",
                "target_id", "dataset", "inventory_status", "content_status", "expected_record_count", "severity", "record_id", "message",
            }
        }
    )
    return DataRecord(
        record_id=str(item[id_key]),
        title=_value(item.get(title_key)),
        subtitle=_value(item.get(subtitle_key)),
        provenance=provenance,
        status=_value(status) if status is not None else None,
        cells=cells,
        sections=[
            DataSection(
                title="Processed summary",
                fields=[DataField(label=_label(key), value=_value(item.get(key))) for key in fields],
            )
        ],
        relationships=[relation for relation in (relationships or []) if relation.total_count],
        source_ids=list(source_ids or []),
        lineage_ids=list(lineage_ids or []),
        quality_notes=[str(note) for note in (quality_notes or []) if note],
    )


def _rel(label: str, dataset_id: str, record_ids: Iterable[str | None]) -> DataRelationship:
    ids = [str(item) for item in record_ids if item]
    return DataRelationship(label=label, dataset_id=dataset_id, record_ids=ids[:24], total_count=len(ids))


def _value(value: Any) -> str:
    if value is None:
        return "Not available"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        if not value:
            return "None"
        rendered = [_value(item) for item in value[:8]]
        suffix = f" +{len(value) - 8} more" if len(value) > 8 else ""
        return "; ".join(rendered) + suffix
    if isinstance(value, dict):
        pairs = [f"{_label(str(key))}: {_value(item)}" for key, item in list(value.items())[:8]]
        suffix = f" +{len(value) - 8} more" if len(value) > 8 else ""
        return "; ".join(pairs) + suffix
    return str(value)


def _label(key: str) -> str:
    return key.replace("_", " ").strip().title()


def _searchable_text(record: DataRecord) -> str:
    return " ".join(
        [record.record_id, record.title, record.subtitle, *record.cells.values(), *record.source_ids, *record.lineage_ids]
    )


def _options(records: list[DataRecord], keys: tuple[str, ...]) -> list[str]:
    values: set[str] = set()
    for record in records:
        for key in keys:
            value = record.cells.get(key)
            if value and value not in {"None", "Not available"}:
                values.update(
                    part.strip()
                    for part in value.replace(";", ",").split(",")
                    if part.strip()
                )
    return sorted(values)


def _sort_value(value: str, kind: str) -> tuple[int, float | str]:
    if kind == "number":
        try:
            return (0, float(value))
        except ValueError:
            return (1, value.casefold())
    return (0, value.casefold())


def _curriculum_courses(curriculum: dict[str, Any]) -> list[str]:
    course_ids: set[str] = set()
    for requirement in curriculum.get("requirements", []):
        course_ids.update(requirement.get("required_courses", []))
        course_ids.update(requirement.get("elective_pool", []))
    for path in curriculum.get("graduation_paths", []):
        course_ids.update(path.get("required_courses", []))
    return sorted(course_ids)


def _meeting_text(meeting: dict[str, Any]) -> str:
    return " ".join(
        str(part)
        for part in (
            meeting.get("class_type"), meeting.get("day"),
            f'{meeting.get("start_time", "")}–{meeting.get("end_time", "")}', meeting.get("venue"),
        )
        if part
    )


def _source_relationships(dependent_records: list[str]) -> list[DataRelationship]:
    mappings = {
        "programmes": [item for item in dependent_records if item.startswith("programme.")],
        "curricula": [item for item in dependent_records if item.startswith("curriculum.")],
        "courses": [item.removeprefix("course.") for item in dependent_records if item.startswith("course.")],
        "calendar_events": [item for item in dependent_records if item.startswith("calendar.")],
        "policy_sections": [item for item in dependent_records if item.startswith(("policy.", "unknown."))],
    }
    return [_rel(_label(dataset_id), dataset_id, ids) for dataset_id, ids in mappings.items()]


__all__ = ["DataService"]
