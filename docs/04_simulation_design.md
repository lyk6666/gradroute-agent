# 04 — Simulation Design

## Goal

Create a medium-scale, reproducible NTU/CCDS administrative simulator whose
academic evidence is traceable to the Stage 2 real-data snapshot and whose
private or live state is unmistakably synthetic.

The simulator does not claim to reproduce NTU's authenticated systems. It
constructs controlled terminal-stage student cases from public curriculum and
course templates, preserves all known gaps, and labels every prototype rule or
operational assumption.

## 1. Grounding baseline

Stage 3 starts from the official-public snapshot checked on 31 August 2026:

| Real dataset | Available Stage 2 scope |
| --- | ---: |
| CCDS programmes and named pathways | 22 |
| Curriculum configurations | 23 |
| Normalized study-plan rows | 1,176 |
| AY2026–27 Semester 1 catalogue courses | 219 |
| Catalogue appearances | 1,035 |
| Scheduled courses | 210 |
| Timetable indexes | 2,108 |
| Academic-calendar events | 45 |
| Registration, exception, and routing sections | 64 |
| Provenance sources | 48 |

The real repository has zero consistency errors, but content completeness is
not the same as inventory completeness:

- all 23 curricula are `PARTIAL`;
- detailed current AY2026–27 curricula require authentication;
- 26 exact/raw study-plan course codes have no current catalogue record;
- nine catalogue courses have no conventional timetable row;
- course requirement-category lists and elective pools are incomplete;
- every course's programme applicability is partial, and the current
  `programme_categories` mappings are empty;
- 147 courses retain raw prerequisite text, but the current normalized fields
  do not yet make those expressions executable;
- live capacity, vacancies, waitlist order, quotas, and personal eligibility
  are not public; and
- general late-registration, prerequisite-waiver, overload, substitution, and
  approval-chain processes remain `UNKNOWN`.

These are simulation boundaries, not values to fill silently.

## 2. Temporal contract

The real layers describe different but explicit periods:

- curriculum rule templates: principally admission cohort AY2025–26;
- catalogue and timetable templates: AY2026–27 Semester 1; and
- calendar template: AY2026–27.

To avoid portraying an AY2025–26 entrant as an actual final-year student in
AY2026–27, Stage 3 uses a counterfactual simulation period:

1. `admission_cohort` remains AY2025–26 and resolves to the selected public
   curriculum.
2. `study_year` is the maximum year represented by that curriculum's published
   study plan: Year 4 for most eligible configurations and Year 5 for CEEC and
   CSEC.
3. The simulated academic year is derived from the cohort and study year
   (normally AY2028–29 or AY2029–30).
4. AY2026–27 catalogue, index meetings, and calendar sequencing are retained as
   templates only. Their original period and source IDs are never rewritten as
   verified future facts.

Generated records must therefore distinguish:

```text
simulation_academic_year
simulation_scope_id
source_curriculum_id
graduation_path_id / study_plan_path_label
template_academic_year
template_offering_id / template_index_id
source_rule_ids
assumption_ids
```

All future availability, dates, eligibility, and transaction behavior are
simulated. This lets the prototype test a coherent terminal-stage case without
misstating what NTU will offer in a future semester.

## 3. Curriculum eligibility tiers

All 22 programme/pathway records remain searchable and routable. Detailed
scenario audits are limited to configurations whose public snapshot contains a
study plan, a graduation total or path, and typed course links.

### Detailed-audit templates

Seventeen configurations qualify as scenario-bounded audit templates:

- four mainstream configurations — AISC, CE, CSC, and DSAI;
- BCE and BCG;
- CE-DANA, CE-ENT, CE-SUST, and CEEC;
- the separately published CSC-with-Business configuration;
- CSC-ENT, CSC-ITP, CSC-SUST, and CSEC;
- DSAI-SUST; and
- MACS.

They cover 16 public programme/pathway codes plus the additional CSC Business
configuration. They are suitable for controlled simulation, not for an
official complete Degree Audit.

`Student.programme` uses the exact pathway code (`BCG`, `CSC-ENT`, `CE-SUST`,
and so on). `Programme.ccds_base_programmes` is used for grouping only;
`additional_programmes` does not duplicate the base-programme relationship.
Each student uses one integrated configuration unless composition has been
explicitly proven. In particular, the CSC-with-Business configuration is not
blindly added to the base CSC configuration.

### Coverage/routing-only configurations

Six configurations are not eligible for a positive complete-audit scenario
because their public record has no detailed study-plan rows:

```text
ACDA, BACF, BTECH-COMP, CE-BUS, CE-ITP, ECDS
```

They remain valid for programme discovery, source-gap explanation, routing,
clarification, and separate data-coverage tests. They are outside the 240
student and 140 scenario population because every generated case must reference
a generated student. They must not receive invented course lists or a
fabricated successful graduation plan.

## 4. Exact simulated scale

### Students

The materialized package contains exactly 240 fictional students across the 17
detailed-audit configurations:

| Configuration group | Students per configuration | Total |
| --- | ---: | ---: |
| AISC, CE, CSC mainstream, DSAI | 21 | 84 |
| Remaining 13 detailed-audit configurations | 12 | 156 |
| **Total** |  | **240** |

The remaining group is BCE, BCG, CE-DANA, CE-ENT, CE-SUST, CEEC,
CSC-with-Business, CSC-ENT, CSC-ITP, CSC-SUST, CSEC, DSAI-SUST, and MACS.

This replaces the obsolete `60 × four primary programmes` and `four real
cohorts per programme` assumptions. The generator uses one grounded curriculum
cohort and balances exactly 60 students across each synthetic terminal-state
profile:

```text
1. one explicit plan requirement outstanding
2. index/timetable/workload constrained
3. prerequisite or supporting-evidence dependent
4. no verified resolution in the declared scope
```

Histories vary in completed courses, attempts, grades, earned AUs, exemptions,
selected graduation path, current workload, and outstanding requirements. No
real student identity or PII is used.

### Derived and operational state

The materialized derived and operational records are exactly:

```text
240 scenario-bounded degree audits
240 current registration states
2,108 baseline simulated offering states
```

There is one `OfferingState` per collected real index in the frozen Stage 2
snapshot. Capacity, vacancies, waitlist count, availability, version, and
future simulation period are generated; the sourced course, index meetings,
and original source period remain immutable.

### Cases, approvals, transactions, and scenarios

The materialized workflow and evaluator records are exactly:

```text
140 exception/problem cases
60 approval records
140 transaction scripts
140 scenario definitions
```

Cases remain balanced at 20 per scenario family. Approval records remain:

```text
24 approved
24 rejected
12 pending
```

Only cases that require a human decision reference an approval. A published
role may ground routing, but the decision, service time, delegation, and status
are simulated unless the exact public workflow says otherwise.

Each case has one transaction script, and a script may contain ordered failure
and recovery attempts.

## 5. Real, derived, simulated, and unknown rules

### Verified real evidence

Use the Stage 2 source records for:

- programme identity and pathway kind;
- curriculum totals, graduation paths, requirement categories, constraints,
  and typed study-plan rows;
- course code, title, AU, raw prerequisites, exclusions, and documented
  applicability;
- published AY2026–27 Semester 1 course and index templates;
- public calendar ordering and registration/Add/Drop boundaries; and
- narrow published policy and routing sections.

### Deterministically derived evidence

The simulator may derive:

- a selected graduation path from an explicit source path;
- prerequisite truth from a tested conservative normalization of the verified
  raw expression;
- timetable overlaps from real index meeting patterns;
- AU totals from generated histories and selected source-backed mappings; and
- scenario ground truth from the deterministic rule engine.

Derived values retain the source rule IDs and the derivation version.
Rule checks expose `PASS`, `FAIL`, or `UNKNOWN` together with evidence and
completeness; an unavailable rule never collapses into `PASS`.

### Simulated state or rules

The following are simulated:

- student history, grades, exemptions, standing, and fee status;
- a student's authenticated curriculum entitlement and Degree Audit result;
- mappings needed for incomplete elective/category lists;
- current registration, workload ceiling, personalised slot, and scenario time;
- capacity, vacancies, waitlist, quotas, allocation priority, and personal
  eligibility;
- exception evidence, case state, approval decision, and service time;
- registration/exception transactions and controlled failures; and
- expected valid resolution and escalation ground truth.

Any invented academic or administrative workflow must begin with:

```text
SIMULATED POLICY FOR PROTOTYPE
```

It must also declare `origin=SIMULATED_POLICY` and explicit academic-year or
admission-cohort applicability. The banner alone is not sufficient metadata.

### Unknown remains unknown

Missing public information is not equivalent to permission, rejection, zero
capacity, or no prerequisite. An unsupported rule or expression yields
`UNKNOWN` and can produce clarification or escalation.

## 6. Scenario-bounded Degree Audit

Every generated audit is computed; it is never written independently.

```text
selected curriculum and graduation path
+ typed study-plan rows
+ declared prototype assumption mappings
+ synthetic completed courses and exemptions
→ deterministic requirement progress
```

The Stage 3 audit contract records:

```text
audit_basis
audit_outcome
graduation_path_id
study_plan_path_label
assumption_ids
limitations
```

Rules:

1. Typed study-plan rows may map their course to their published
   `requirement_id`.
2. The builder selects exactly one graduation path and compatible study-plan
   path label. Common rows plus the selected path are evaluated; PI/PA or
   FYP/coursework alternatives are never summed together.
3. An untyped placeholder or incomplete elective pool may be satisfied only by
   an explicit assumption record; it is never converted into an official rule.
4. The target requirement of a positive action scenario should use a typed
   source-backed row or an explicit graduation-path total.
5. `Student.earned_aus`, completed attempts, exemptions, requirement progress,
   and the audit total must reconcile exactly.
6. A variable-total curriculum requires a selected `graduation_path_id`.
7. A requirement or overall audit whose decisive public rules are unavailable
   is `INDETERMINATE`, not satisfied or failed. The implemented audit outcome
   therefore represents indeterminacy directly instead of collapsing it into a
   Boolean `graduation_ready` value.
8. The 26 unresolved curriculum codes fail closed and cannot support a positive
   registration path without a separate verified course record.
9. Every audit is labelled `SCENARIO_BOUNDED_SIMULATION`; it must not be
   described as an official NTU Degree Audit.

## 7. Prerequisite and eligibility evaluation

The course snapshot contains raw prerequisite text for 147 courses, but the
current normalized `all_of`, `any_of`, and minimum-year fields do not encode all
of those expressions. Stage 3 implements a conservative evaluator for the
curated scenario grammar and fails closed on unsupported text.

Rules:

- preserve the raw expression and its source;
- normalize only a tested supported grammar, including the source tokens
  `AND`, `OR`, and `&` (meaning AND), grouping, and stated study-year
  conditions;
- manually fixture-test every course used in a prerequisite demo;
- return `UNKNOWN` for unsupported text instead of treating it as empty; and
- keep personal eligibility and programme allocation as simulated state because
  catalogue appearance alone does not prove either.

The `observed_programmes` attached to catalogue or index queries are provenance
about how a record was found, not an authorization list. Composite pathway
codes must not fail eligibility merely because the public portal was queried
through a base programme selector.

The documented pending-exchange-credit route may support a narrow prerequisite
exception case. A general waiver must remain unknown or use an explicitly
simulated policy.

## 8. Timetable and live offering state

`CourseOffering` is immutable real snapshot evidence. `OfferingState` is the
generated operational layer.

For every one of the 2,108 indexes, generate a deterministic baseline with:

```text
state_id
template_offering_id
template_index_id
template_academic_year
template_semester
simulation_period_id
capacity
vacancies
waitlist_count
available
runtime_status
unavailable_reason
version
assumption_ids
generator_version
seed
source_rule_ids
```

Dynamic events create a new state version and never modify
`data/real/course_offerings.json`. Current registrations use the real meeting
pattern as a timetable template while identifying the generated future period.

`CLASS_BECOMES_UNAVAILABLE` is representable independently from
`VACANCY_BECOMES_ZERO`. The operational status/reason prevents administrative
unavailability from being reduced to only `vacancies > 0`.

Registration validation must prove that each course exists, each template
index belongs to its template offering, each stored AU matches the course,
every meeting is attributable to its course/index, and workload equals the AU
sum. Because the simulation period is deliberately future-counterfactual, term
validation checks the explicit template-to-simulation mapping rather than
pretending the AY2026–27 offering itself occurs in the future period.

The `RegistrationItem` contract deliberately supports zero AU. One generated
registration retains `HW0001` at its sourced zero AU, and workload reconciliation
proves that it contributes zero rather than silently changing its value.

## 9. Controlled dynamic events

Retain exactly eight event types:

```text
1. VACANCY_BECOMES_ZERO
2. CLASS_BECOMES_UNAVAILABLE
3. APPROVAL_GRANTED
4. APPROVAL_REJECTED
5. APPROVAL_PENDING
6. TEMPORARY_TRANSACTION_FAILURE
7. STATE_CHANGED_BEFORE_COMMIT
8. REQUIRED_INFORMATION_MISSING
```

Events are deterministic per scenario. Event type, transaction result,
observation, retryability, state mutation, and expected outcome must be
cross-validated.

Vacancy loss and class withdrawal persistently invalidate the affected index.
`STATE_CHANGED_BEFORE_COMMIT` advances its offering state from version 1 to 2,
so the old plan is stale even when the refreshed index remains feasible.
`TEMPORARY_TRANSACTION_FAILURE` has no persistent mutation. S7 ground truth
therefore accepts a refreshed original retry for stale/transient variants as
well as a pre-verified alternative, while persistent variants accept only an
unaffected alternative.

## 10. Stage 3 data package

Stage 3 adds:

```text
data/
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
└── tests/
    └── scenarios.json
```

`generation_manifest.json` freezes the Stage 2 coverage-contract ID, source
hashes, generator version, global seed, simulation-period rules, record counts,
and prototype-policy versions. `simulation_scope.json` records, per curriculum,
the programme code, cohort, simulated period, student count, audit mode,
permitted graduation paths and study-plan labels, accepted gaps, and
counterfactual time basis. `audit_assumptions.json` separates source-backed
mappings from explicit prototype mappings.

## 11. Generation order

Never generate the JSON files independently:

```text
validate frozen REAL DATA
        ↓
compile supported curriculum and prerequisite rules
        ↓
write generation manifest, simulation scope, and assumption registry
        ↓
generate 2,108 offering states
        ↓
generate 240 synthetic students
        ↓
compute 240 scenario-bounded degree audits
        ↓
build 240 consistent registration states
        ↓
construct and validate 140 administrative cases
        ↓
generate 60 approvals and 140 transaction scripts
        ↓
materialize 140 scenarios and hidden ground truth
        ↓
reload every file and run cross-file validation
```

Every generated entity includes `generator_version`, `seed`, and
`source_rule_ids`. A failed evaluation case must be exactly reproducible.

## 12. Scenario construction and interfaces

The deterministic builder constructs each expected result, and the independent
cross-file validator checks its references, state versions, event/result
mapping, mutations, distributions, and visibility boundary before files are
written:

```text
select eligible curriculum and path
→ construct a terminal-stage student history
→ compute the outstanding requirement
→ select source-backed candidate records
→ apply simulated operational state
→ define valid initial/final and invalid paths
→ define event and transaction script
→ validate the complete bundle
→ save deterministic bytes
```

The environment exposes state only through tools such as:

```python
get_student_record(...)
run_degree_audit(...)
search_courses(...)
check_prerequisite(...)
check_timetable(...)
check_availability(...)
search_policy(...)
request_approval(...)
submit_registration(...)
submit_exception(...)
```

Audit, policy, timetable, and availability tools require the relevant
curriculum/path, admission cohort, academic year/semester, and current state
version. A policy search cannot silently apply a different cohort handbook,
and an availability check cannot accept a stale version.

The agent never reads transaction scripts, future events, valid/invalid path
sets, or expected outcomes directly.

## 13. Stage 3 completion gate

All seven Stage 3 gates are complete:

1. The temporal, audit, path, assumption, indeterminate-outcome, and operational
   state contracts are implemented.
2. Strict loaders and a defensive simulated-data repository perform full
   cross-file validation.
3. The conservative prerequisite evaluator is fixture-tested on the curated
   scenario grammar and returns `UNKNOWN` for unsupported expressions.
4. Seventeen explicit simulation scopes and assumption records bound the
   scenario-audit mappings.
5. Source resolution, AU ledgers, event/result replay, state mutations, and
   ground-truth isolation are enforced.
6. `HW0001` is retained at zero AU while timetable ownership and workload sums
   reconcile.
7. All seven families are materialized with four development, one demo, and
   fifteen evaluation cases each.

Readiness evidence:

```text
48 sources resolve through provenance
22 programmes and 23 curricula load
219 courses and 210 offerings load
2,108 real indexes map to 2,108 simulated offering-state baselines
17 scopes, 240 students/audits/registrations, 140 cases/scenarios, 60 approvals
0 real-repository consistency errors
0 simulated-repository consistency issues
deterministic generator --check passes
```

Stage 4 now implements the executable tools and isolated transaction runtime
against this frozen package. It also adds the control-flow oracle,
action-specific postconditions, and approval/clarification/checkpoint
expectations described in [`05_evaluation_plan.md`](05_evaluation_plan.md),
without reclassifying unknown NTU rules as verified facts. See
[`stage_4_runtime_and_tools.md`](stage_4_runtime_and_tools.md) for the delivered
tool boundary. Stage 5 now executes the normative graph in
[`02_solution_architecture.md`](02_solution_architecture.md), as recorded in
[`stage_5_langgraph_control_plane.md`](stage_5_langgraph_control_plane.md).
