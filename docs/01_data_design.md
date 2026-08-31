# 01 — Data Design

## Purpose

Define the data contract for an **NTU CCDS-grounded administrative exception-resolution agent**.

The design separates:

- **real NTU/CCDS data**: academic rules and published operational information;
- **simulated data**: private student state, case state, approvals, transactions, and controlled failures;
- **test data**: deterministic scenarios with expected outcomes.

The agent must never treat simulated rules as official NTU policy.

## Directory Structure

```text
data/
├── real/
│   ├── source_manifest.json
│   ├── coverage.json
│   ├── programmes.json
│   ├── academic_calendar.md
│   ├── curriculum.json
│   ├── courses.json
│   ├── course_offerings.json
│   ├── course_catalogue_queries.json
│   ├── course_schedule_queries.json
│   └── public_policies/
│       ├── registration.md
│       ├── exceptions.md
│       └── approval_structure.md
│
├── simulated/
│   ├── generation_manifest.json
│   ├── simulation_scope.json
│   ├── audit_assumptions.json
│   ├── offering_states.json
│   ├── students.json
│   ├── degree_audits.json
│   ├── current_registrations.json
│   ├── exception_cases.json
│   ├── approvals.json
│   └── transaction_results.json
│
└── tests/
    ├── scenarios.json
    └── execution_contracts.json  # Stage 4 evaluator-only control-flow oracle
```

## Real Data

### `programmes.json`

Records the complete current public CCDS programme/pathway inventory: single,
double, second-major, joint, and part-time degrees. Each record declares its
kind, study mode, CCDS base programme where applicable, public identifiers, and
source IDs.

### `coverage.json`

Defines what “complete” means for each real dataset. Every target records the
scope parameters, exact expected record IDs, inventory and content status,
required fields, discovery sources, and dimension-specific gaps. A complete
query-result inventory can therefore coexist with partial content when an
official public source omits capacity, eligibility, or authenticated rules.

### `source_manifest.json`

Tracks provenance and freshness for every real source.

Minimum fields:

```json
{
  "source_id": "ntu.ccds.curriculum.csc.ay2025-26",
  "source_type": "curriculum",
  "programme": "CSC",
  "effective_academic_year": "AY2025-26",
  "source_url": "...",
  "retrieved_at": "...",
  "access_status": "RETRIEVED",
  "classification": "PUBLIC_RESTRICTED",
  "retrieval_method": "DIRECT_DOWNLOAD",
  "content_sha256": "...",
  "checksum_scope": "SOURCE_BYTES",
  "version": "...",
  "origin": "VERIFIED_REAL"
}
```

Use it to prevent stale or mixed-cohort rules.

### `academic_calendar.md`

Contains typed dates and public timing boundaries needed by the prototype:

- teaching, recess, revision/examination, vacation, and Special Term;
- registration, schedule release, allocation, and Add/Drop periods;
- CCDS internship/attachment periods;
- results, FGO, result-review, and convocation-related cutoffs.

### `curriculum.json`

Real curriculum rules for all current public CCDS programme configurations for
which official facts were found. Exact cohort sheets remain separate from
unversioned public pages and search-index-only records.

Minimum content:

- programme;
- cohort / academic year;
- graduation AU requirements;
- compulsory/core requirements;
- elective/category requirements;
- programme-specific constraints.

Unknown course-count or course-list fields are `null`/`UNKNOWN`, not zero or a
verified-empty list. A programme with conditional graduation totals uses
explicit `graduation_paths`; each path carries its total AU, category AU,
minimum course counts, required components, and constraints.

### `courses.json`

Term-specific public course metadata, retaining every observed programme,
elective-pool, or exact curriculum-course appearance:

- course code;
- title;
- AU;
- prerequisites;
- exclusions;
- applicable programme/category;
- other publicly documented constraints.

### `course_offerings.json`

Real semester offering data collected from official NTU sources where accessible:

- semester;
- course;
- index/class;
- timetable;
- offering status;
- vacancy snapshot if publicly/reliably obtainable;
- retrieval timestamp.

Dynamic scenario changes are injected by the simulator; they do not overwrite
the stored source snapshot. Public schedule rows do not establish individual
eligibility, capacity, waitlist priority, or a guaranteed future offering.

### Query audit files

`course_catalogue_queries.json` and `course_schedule_queries.json` record every
public request scope, response hash, result count, normalized dataset hash, and
known limitation. They make the current snapshot measurable and repeatable
without treating an empty portal response as a university policy fact.

### `public_policies/registration.md`

Public registration processes and rules relevant to the prototype.

Every policy section records an origin and typed applicability. Applicability
is either explicit (academic year and/or admission cohort), source-unspecified,
or unknown. Operational queries require year/cohort context and exclude
source-unspecified sections unless explicitly requested.

### `public_policies/exceptions.md`

Publicly documented exception/waiver guidance.

An unavailable real process remains an `UNKNOWN` section. If a later stage
intentionally adds a deterministic prototype-only rule, that section must begin:

```text
SIMULATED POLICY FOR PROTOTYPE
```

It must also declare `origin=SIMULATED_POLICY` and explicit academic-year or
admission-cohort applicability.

### `public_policies/approval_structure.md`

Approval roles and process structure, not personal names.

Examples:

- student;
- course coordinator;
- school academic office;
- programme approver;
- administrator.

## Simulated Data

### `generation_manifest.json` and `simulation_scope.json`

The generation manifest freezes the real-data coverage contract, source hashes,
generator version, global seed, record counts, and prototype-policy versions.
The simulation scope assigns each included curriculum its programme code,
cohort, counterfactual terminal period, student count, audit mode, permitted
paths, and accepted public-data gaps.

The materialized fields, populations, temporal mapping, and validation rules are
specified in [`stage_3_simulation_data_details.md`](stage_3_simulation_data_details.md).

### `audit_assumptions.json`

Records every source-backed derivation and every explicitly simulated mapping
needed by a scenario-bounded audit. Prototype rules remain visibly distinct
from verified NTU rules and resolve back to the generated records that use
them.

### `students.json`

Exactly **240 fictional terminal-stage students** distributed across the 17
curriculum configurations with detailed public study-plan rows. The exact
Stage 2-aligned allocation is defined in `04_simulation_design.md`; it replaces
the earlier four-programme/four-cohort assumption.

Fields:

- synthetic student ID;
- programme;
- cohort;
- year of study;
- completed courses;
- grades;
- earned AUs;
- exemptions.

Each record also identifies its simulation scope, selected integrated
curriculum, and selected graduation path or study-plan path where applicable.

No real student PII is needed.

### `degree_audits.json`

Exactly **240 audit results**, one per synthetic student.

These are **scenario-bounded prototype assessments**, derived rather than
randomly written:

```text
real curriculum
+ synthetic academic history
→ deterministic audit engine
→ satisfied / outstanding / indeterminate requirements
```

An audit records its basis, selected path, assumptions, and limitations. When a
decisive public rule is unavailable, the result is indeterminate rather than an
official pass or fail.

### `offering_states.json`

Exactly one generated baseline state per real timetable index: 2,108 for the
frozen Stage 2 snapshot. These records contain simulated capacity, vacancies,
waitlist, availability/status, future scenario period, and state version while
referencing the immutable real offering/index template.

### `current_registrations.json`

Exactly **240 current-semester registration states**:

- registered courses;
- class/index;
- workload;
- timetable;
- registration status.

The registration academic year is simulated. Stored timetable meetings retain
an explicit link to their AY2026–27 real index template rather than claiming
that the real index is a verified future offering.

### `exception_cases.json`

Exactly **140 administrative cases** covering the seven scenario families.

Fields:

- case ID;
- student ID;
- problem type;
- goal;
- observable submission readiness and unresolved intake questions;
- evidence/supporting information;
- state.

Expected human involvement belongs only to hidden scenario ground truth; it is
not stored in the agent-facing case.

### `approvals.json`

Exactly **60 approval records** distributed across:

- approved;
- rejected;
- pending.

Used only for cases that require human-in-the-loop behavior.

### `transaction_results.json`

Exactly **140 deterministic transaction scripts**, one per case.

Possible outcomes include:

- success;
- module/course full;
- prerequisite violation;
- approval rejection;
- stale state;
- temporary system failure;
- exception submission success.

## Test Data

### `scenarios.json`

Exactly **140 scenario definitions**.

The checked-in schema contains explicit entity links, an optional typed future
event, and evaluator-only ground truth. Selected fields from the materialized
`S7-M01` record are shown below:

```json
{
  "scenario_id": "S7-M01",
  "family": "S7",
  "split": "demo",
  "generator_version": "stage3.4.0",
  "simulation_scope_id": "scope.ce.terminal",
  "student_id": "SIM-CE-010",
  "curriculum_id": "curriculum.ce.ay2025-26",
  "audit_id": "audit.sim-ce-010",
  "registration_id": "registration.sim-ce-010",
  "case_id": "case.sim-ce-010",
  "offering_state_ids": [
    "state.ay2026-27.s1.ml0004.83008",
    "state.ay2026-27.s1.ml0004.83001"
  ],
  "transaction_script_id": "script.s7-m01",
  "injected_event": {
    "event_id": "event.s7-m01",
    "event_type": "VACANCY_BECOMES_ZERO",
    "target_type": "OFFERING_STATE",
    "target_id": "state.ay2026-27.s1.ml0004.83008",
    "expected_version": 1,
    "occurs_at": "2028-08-25T09:01:00+08:00"
  },
  "ground_truth": {
    "valid_initial_paths": [{"path_id": "path.s7-m01.pre-event-index"}],
    "valid_final_paths": [{"path_id": "path.s7-m01.post-event-alternative"}],
    "invalid_paths": [{"path_id": "path.s7-m01.invalidated-index"}],
    "requires_human": false,
    "expected_outcome": "RESOLVED"
  }
}
```

The full records in [`../data/tests/scenarios.json`](../data/tests/scenarios.json)
are the authoritative Stage 3 solution-path oracle for evaluation.

### `execution_contracts.json` — implemented Stage 4 addition

This evaluator-only companion attaches graph behavior to all 140 existing
`scenario_id` values without changing grounded academic facts. It declares
required/forbidden edges, both verifier phases, clarification impact, approval
versus human/admin review, checkpoint expectations, completion predicates,
memory-update permission, and loop budgets. Source hashes bind it to the frozen
scenario, transaction, and approval artifacts. It is never available through
agent-facing repositories or tools.

## Data Principles

1. **Real rules define the world.**
2. **Synthetic students create safe test cases inside that world.**
3. **Derived data should be computed whenever possible.**
4. **Dynamic changes are scenario injections, not fabricated source data.**
5. **Every real rule must be traceable through `source_manifest.json`.**
6. **Every simulated rule must use the exact banner, `SIMULATED_POLICY`
   origin, and explicit cohort/year applicability.**
7. **Every public loader resolves source IDs against the source manifest.**
8. **Conditional curriculum paths must remain separate and machine-readable.**
