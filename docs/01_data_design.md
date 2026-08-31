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
│   ├── programmes.json
│   ├── academic_calendar.md
│   ├── curriculum.json
│   ├── courses.json
│   ├── course_offerings.json
│   └── public_policies/
│       ├── registration.md
│       ├── exceptions.md
│       └── approval_structure.md
│
├── simulated/
│   ├── students.json
│   ├── degree_audits.json
│   ├── current_registrations.json
│   ├── exception_cases.json
│   ├── approvals.json
│   └── transaction_results.json
│
└── tests/
    └── scenarios.json
```

## Real Data

### `programmes.json`

Records the primary CCDS programme codes and names used by the prototype. This
small additive file lets cross-file validation distinguish a known programme
from an unverified code; it does not claim that other NTU joint, double-degree,
second-major, or part-time pathways do not exist.

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
  "version": "...",
  "origin": "VERIFIED_REAL"
}
```

Use it to prevent stale or mixed-cohort rules.

### `academic_calendar.md`

Contains only dates needed by the prototype:

- semester boundaries;
- registration periods;
- Add/Drop periods;
- relevant academic deadlines.

### `curriculum.json`

Real curriculum rules for the selected CCDS programmes/cohorts.

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

Real, relatively stable course metadata:

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

Dynamic scenario changes are injected by the simulator; they do not overwrite the stored source snapshot.

When no reproducible public snapshot has been collected, this file is a typed
`PLACEHOLDER` with a reason and an empty `offerings` list. That state means
“unknown/not collected,” never “NTU offers no courses.”

### `public_policies/registration.md`

Public registration processes and rules relevant to the prototype.

Every policy section records an origin and typed applicability. Applicability
is either explicit (academic year and/or admission cohort), source-unspecified,
or unknown. Operational queries require year/cohort context and exclude
source-unspecified sections unless explicitly requested.

### `public_policies/exceptions.md`

Publicly documented exception/waiver guidance.

Any rule that cannot be verified must be marked:

```text
SIMULATED POLICY FOR PROTOTYPE
```

### `public_policies/approval_structure.md`

Approval roles and process structure, not personal names.

Examples:

- student;
- course coordinator;
- school academic office;
- programme approver;
- administrator.

## Simulated Data

### `students.json`

Exactly **240 fictional students**:

- 60 Computer Science;
- 60 Computer Engineering;
- 60 Data Science & Artificial Intelligence;
- 60 Artificial Intelligence & Society.

Fields:

- synthetic student ID;
- programme;
- cohort;
- year of study;
- completed courses;
- grades;
- earned AUs;
- exemptions.

No real student PII is needed.

### `degree_audits.json`

Exactly **240 audit results**, one per synthetic student.

These are **derived**, not randomly written:

```text
real curriculum
+ synthetic academic history
→ deterministic audit engine
→ satisfied / outstanding requirements
```

### `current_registrations.json`

Exactly **240 current-semester registration states**:

- registered courses;
- class/index;
- workload;
- timetable;
- registration status.

### `exception_cases.json`

Exactly **140 administrative cases** covering the seven scenario families.

Fields:

- case ID;
- student ID;
- problem type;
- goal;
- evidence/supporting information;
- state;
- expected human involvement.

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

Each scenario contains:

```json
{
  "scenario_id": "S7-E08",
  "student_id": "SIM-CS-042",
  "case_id": "CASE-108",
  "initial_state": {},
  "expected_valid_paths": [],
  "expected_invalid_paths": [],
  "requires_human": false,
  "injected_event": "VACANCY_BECOMES_ZERO",
  "expected_outcome": "RESOLVED"
}
```

This file is the main ground-truth contract for evaluation.

## Data Principles

1. **Real rules define the world.**
2. **Synthetic students create safe test cases inside that world.**
3. **Derived data should be computed whenever possible.**
4. **Dynamic changes are scenario injections, not fabricated source data.**
5. **Every real rule must be traceable through `source_manifest.json`.**
6. **Every simulated rule must be explicitly labeled as simulated.**
7. **Every public loader resolves source IDs against the source manifest.**
8. **Conditional curriculum paths must remain separate and machine-readable.**
