# Stage 3 — Simulation Data Details

## Purpose and status

Stage 3 turns the validated Stage 2 NTU/CCDS public-data snapshot into a
deterministic, fictional administrative world for development, demonstration,
and evaluation. It supplies synthetic student records, scenario-bounded degree
audits, future-counterfactual registration state, exception workflows, and
hidden evaluator ground truth.

The package is not an NTU system export, an official Degree Audit, or a
prediction of future course availability. Public academic facts retain their
Stage 2 provenance. Private student facts, future time, live capacity,
eligibility, decisions, and transaction outcomes are simulated and are kept
structurally separate from verified rules.

Completion status: generator `stage3.5.0` is materialized and byte-current.
Offline repository reload reports zero consistency issues. The delivered
population and distributions match the declared contract, including 60 students
per terminal profile, 20 scenarios per family, a 28/7/105
development/demo/evaluation split, and 24/24/12
approved/rejected/pending approvals.
The final offline verification suite passes all 189 tests, and generator
`--check` confirms that every checked-in JSON file is byte-current.

## 1. Frozen real-data basis

The generator accepts only the validated Stage 2 snapshot and freezes a
SHA-256 digest for every direct input in `generation_manifest.json`. The
grounded inventory is:

| Real-data layer | Frozen scope |
| --- | ---: |
| CCDS programmes and named pathways | 22 |
| Curriculum configurations | 23 |
| Detailed-audit curriculum configurations used in Stage 3 | 17 |
| Normalized study-plan rows | 1,176 |
| AY2026–27 Semester 1 catalogue courses | 219 |
| AY2026–27 Semester 1 scheduled courses | 210 |
| Real timetable indexes used as templates | 2,108 |
| Provenance sources | 48 |

All 23 public curricula remain `PARTIAL`. Stage 3 therefore performs
`SCENARIO_BOUNDED_SIMULATION` audits and retains limitations; it never upgrades
the source snapshot into a complete official curriculum determination.

## 2. Data classification boundary

Each generated fact belongs to one of four classes:

| Class | Meaning in Stage 3 |
| --- | --- |
| Verified real | A source-backed programme, curriculum, requirement, course, index template, calendar event, or public policy section from Stage 2 |
| Derived | A deterministic result calculated from verified records, such as selected study-plan rows or AU reconciliation |
| Simulated | Fictional student state, future period, operational state, approval, event, or prototype-only rule |
| Unknown | A public rule or personal fact that the collected sources cannot establish |

An invented policy is valid only as a `PrototypePolicy`. Its body begins with
the exact first line below, its `origin` is `SIMULATED_POLICY`, and it declares
explicit academic-year or admission-cohort applicability:

```text
SIMULATED POLICY FOR PROTOTYPE
```

Prototype policies are stored inside the generation manifest so their IDs and
versions are frozen with the dataset. They must not be cited as verified NTU
policy.

## 3. Stage 3 package

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

`transaction_results.json` contains one `TransactionScript` per case, not a
flat list of unrelated transaction responses. `scenarios.json` is evaluator
data and is intentionally outside the agent-facing simulated-data directory.

## 4. Exact population

| Record type | Required count |
| --- | ---: |
| Simulation scopes | 17 |
| Offering-state baselines | 2,108 |
| Synthetic students | 240 |
| Scenario-bounded degree audits | 240 |
| Current registrations | 240 |
| Exception cases | 140 |
| Approvals | 60 |
| Transaction scripts | 140 |
| Scenarios | 140 |

The approval distribution is exactly 24 `APPROVED`, 24 `REJECTED`, and 12
`PENDING`. Every student has exactly one audit and one registration. Every case
has exactly one transaction script and one scenario. The 140 case students are
unique, so no student carries two evaluation cases.

## 5. Curriculum scopes and time model

The 17 student-producing configurations are AISC, BCE, BCG, CE, CE-DANA,
CE-ENT, CE-SUST, CEEC, CSC mainstream, CSC with Business, CSC-ENT, CSC-ITP,
CSC-SUST, CSEC, DSAI, DSAI-SUST, and MACS.

The six thin configurations below remain searchable in Stage 2 but do not
receive invented student histories or positive complete-audit scenarios:

```text
ACDA, BACF, BTECH-COMP, CE-BUS, CE-ITP, ECDS
```

The source layers describe different periods, so generated records distinguish
them explicitly:

```text
admission cohort and curriculum rules: AY2025–26
catalogue and timetable template:      AY2026–27 Semester 1
abstract simulation period:            period.terminal.s1
four-year terminal scope:              AY2028–29 Semester 1
five-year terminal scope:              AY2029–30 Semester 1
```

There is one shared baseline `OfferingState` per real index. It carries the
abstract `simulation_period_id`, not a curriculum scope. Each
`SimulationScope` maps that abstract period to its concrete counterfactual
academic year. This avoids either duplicating 2,108 states 17 times or falsely
claiming that a verified AY2026–27 class is a future offering.

## 6. Student allocation and profiles

The four mainstream configurations have 21 students each. The other 13
detailed configurations have 12 each:

```text
4 × 21 + 13 × 12 = 240
```

Every 12-student configuration receives three students in each terminal
profile. The four 21-student configurations rotate the extra student:

| Configuration | Requirement outstanding | Index/timetable/workload constrained | Prerequisite/evidence dependent | No verified resolution |
| --- | ---: | ---: | ---: | ---: |
| AISC | 6 | 5 | 5 | 5 |
| CE | 5 | 6 | 5 | 5 |
| CSC mainstream | 5 | 5 | 6 | 5 |
| DSAI | 5 | 5 | 5 | 6 |
| Each remaining detailed configuration | 3 | 3 | 3 | 3 |
| **Total per profile** | **60** | **60** | **60** | **60** |

The 140 scenario students are selected from those profiles as follows:

| Profile | Scenario use | Used | Background-only |
| --- | --- | ---: | ---: |
| Requirement outstanding | S1: 20; S3: 10 | 30 | 30 |
| Index/timetable/workload constrained | S4: 20; S7: 20 | 40 | 20 |
| Prerequisite/evidence dependent | S2: 20; S5: 20 | 40 | 20 |
| No verified resolution | S3: 10; S6: 20 | 30 | 30 |

## 7. File contracts

### `generation_manifest.json`

One object freezes:

- generator version, global seed, and fixed generation timestamp;
- coverage-contract ID and SHA-256 digests of the real inputs;
- the abstract simulation-period rule;
- every permitted source-rule ID;
- inline prototype policies and their exact version index; and
- the declared count of every generated dataset.

### `simulation_scope.json`

One record per eligible curriculum identifies the programme, cohort, terminal
study year, concrete simulation year, shared period, source template period,
permitted graduation paths and study-plan labels, accepted source gaps,
student count, assumptions, and generation metadata.

### `audit_assumptions.json`

Every non-official derivation or mapping is explicit. Assumptions are typed as
source-backed derivation, prototype mapping, temporal template, or operational
state. Each record identifies its scope, declared value, limitations,
supporting source rules, optional prototype policy, and the exact generated
records that cite it. The reverse dependency list must reconcile exactly.

### `offering_states.json`

For every real `(offering_id, index_id)` pair, Stage 3 stores one deterministic
baseline containing capacity, vacancies, waitlist count, operational status,
availability, version, template period, shared simulation period, and source
links. `available` is true only when the runtime status is `OPEN` and vacancies
are positive. An administratively `UNAVAILABLE` class can still retain a
positive vacancy count, so status is not inferred from capacity alone.

### `students.json`

Each anonymous `SIM-...` record identifies exactly one integrated curriculum
configuration, optional graduation path and study-plan label, terminal profile,
standing, fee state, completed attempts, exemptions, earned AUs, assumptions,
and provenance. A course attempt declares whether credit was earned; grades are
not parsed to guess credit.

The following invariant is enforced exactly:

```text
student.earned_aus
= unique EARNED completed-course AUs
+ non-duplicated exemption AUs
```

Every earned course is allocated to exactly one grounded curriculum
requirement. Category exemptions are split by requirement, cannot exceed that
requirement's earned allocation, and together reconcile to the same total; the
generator does not hide a whole degree's credit inside one category.

`terminal_profile`, generation seed, and generator version are evaluator and
reproducibility metadata. Agent code receives `ObservableStudent`, which
retains the administrative facts and provenance but omits those labels.

### `degree_audits.json`

Each result is explicitly `SCENARIO_BOUNDED_SIMULATION`. Requirement progress
can be `SATISFIED`, `PARTIALLY_SATISFIED`, `OUTSTANDING`, or `INDETERMINATE`;
the overall result can be `READY`, `NOT_READY`, or `INDETERMINATE`. Unknown
requirement totals and decisive source gaps therefore cannot collapse into a
Boolean pass/fail.

The audit records its selected curriculum/path, requirement evidence,
assumptions, limitations, total earned AUs, and known required total. Audit and
student AU totals must match exactly. Requirement earned AUs sum to the audit
total, known requirement targets sum to the selected graduation total, and the
completed-course/exemption allocation must reproduce every requirement ledger.

### `current_registrations.json`

Each registration identifies its future simulation scope and time, real
template period, registration phase, workload ceiling, registered items,
missing required courses, and assumptions. Every item owns its course,
offering, index, offering-state ID, observed state version, AU value, and
eligibility state. Timetable meetings remain attributed to their item rather
than being stored as an unowned flattened list.

The zero-AU course `HW0001` remains zero AU. The registration contract permits
it, and including it does not increase the workload total.

### `exception_cases.json`

Cases contain only observable administrative facts: student, audit,
registration, scenario time, problem, goal, requested action, evidence,
documents, applicable public-policy sections, explicit assumptions, case
state, and typed intake readiness. `submission_ready` is either `true`,
`false`, or neutral (`null`); `unresolved_questions` is a unique list of the
specific intake fields still needed. Cross-field validation requires an
incomplete submission to name at least one question and forbids questions for
a complete or neutral submission. Cases contain no expected decision, future
event, valid path, or hidden transaction script.

### `approvals.json`

Approvals identify the case, scope, role, request, documents, status, decision
basis, basis rules, observable state, timestamps, and version. A routed public
role can ground where to ask; the generated decision and turnaround remain
simulated. Pending decisions have no final reason or decision time. Approval
outcomes begin evaluator-hidden; their event mutation sets `observable=true`
and version 2 before any approved follow-up action can use them.

### `transaction_results.json`

Each script contains consecutive attempts. A transaction binds its action and
parameters to the case and records precondition state versions, an optional
typed event, result, observation, retryability, error code, typed mutations,
and time. Attempt times increase strictly. A failed nonterminal attempt must be
retryable, while an approved follow-up must occur after its decision event.
Versioned mutations increment exactly once, match the target entity type, use
an explicit mutable-field allowlist, and must produce a valid target model when
replayed. Stale-state and temporary failures are retryable and cannot overwrite
persistent state. Every successful registration action binds the offering-state
version it observed; approved follow-ups bind approval version 2.

### `scenarios.json`

Each family contains exactly four development cases, one polished demo, and 15
evaluation cases:

```text
7 × (4 development + 1 demo + 15 evaluation) = 140
```

Scenario IDs use `Sx-D01` through `Sx-D04`, `Sx-M01`, and `Sx-E01` through
`Sx-E15`. Each scenario links the exact student, scope, curriculum, audit,
registration, case, offering states, and transaction script. Its hidden ground
truth stores valid initial and final paths, invalid paths, expected outcome,
and whether a human is required. Path action parameters resolve back to the
scenario's linked course, curriculum/path, approval, or offering state.

## 8. Scenario families

| Family | Grounded purpose |
| --- | --- |
| S1 | During Add/Drop, reject a concrete timetable-conflicting preferred index and use a prerequisite-safe, conflict-free index for the same required course |
| S2 | Use a prerequisite-bearing course, simulated foreign-course evidence, and the narrow pending-exchange-credit route without inventing a general waiver |
| S3 | Resolve cohort/version conflicts and preserve indeterminate source anomalies |
| S4 | Detect a concrete timetable conflict, request simulated approval, and use a conflict-free follow-up index only after approval becomes observable |
| S5 | Use one published integrated, non-primary, or overlay programme/pathway configuration with a selected graduation path and explicit prototype mappings; ordinary base CSC FYP/coursework alternatives are excluded |
| S6 | Use observable intake readiness to distinguish a missing submission declaration from a controlled final-class withdrawal when no verified route remains |
| S7 | During Add/Drop, detect a persistent, transient, or stale-state failure, re-query versions, and retry the still-feasible original index or a different feasible index as the event permits |

The prerequisite evaluator supports exact course codes, `AND`, `OR`, `&`,
parentheses, and `Year N standing`, with AND precedence and three-valued logic.
Unsupported non-empty text, corequisite annotations, or programme annotations
produce `UNKNOWN` unless an independent OR branch passes. It never uses
dynamic evaluation.

Grounded regression fixtures include:

```text
SC4002  SC2001 OR MH1403 OR IE2108
SC2005  SC1006 & SC1007
SC2001  MH1812 & SC1007 OR SC1007 & SC1124
SC3060  Year 2 standing
SC2207  corequisite annotation retained as UNKNOWN
SC4010  programme annotation retained as UNKNOWN
```

## 9. Controlled events

Stage 3 retains exactly these event types:

```text
VACANCY_BECOMES_ZERO
CLASS_BECOMES_UNAVAILABLE
APPROVAL_GRANTED
APPROVAL_REJECTED
APPROVAL_PENDING
TEMPORARY_TRANSACTION_FAILURE
STATE_CHANGED_BEFORE_COMMIT
REQUIRED_INFORMATION_MISSING
```

Every event is cross-checked against its target type, expected version,
transaction result, observation, retryability, and mutation. For example, a
vacancy event changes a positive vacancy to zero, increments the state version,
makes the case retryable only after refreshing or selecting a different state,
and yields `MODULE_FULL`; a temporary failure is retryable and has no persistent
mutation. `STATE_CHANGED_BEFORE_COMMIT` advances the target to version 2 and
makes an expected-version-1 action stale; after refreshing, the unchanged
eligibility constraints can still permit that index. A temporary failure also
leaves the original index feasible, so evaluator ground truth accepts either a
fresh original retry or the pre-verified alternative.

## 10. Agent/evaluator visibility boundary

The agent can observe only linked student, audit, registration, case, public
rules, current offering-state snapshots, and approvals that have become
observable. The evaluator alone owns transaction scripts, injected future
events, scenario family/split/ID, terminal profile, valid and invalid paths,
and expected outcomes. Observable case, document, evidence, approval, and
context identifiers are opaque and do not encode an `S1`–`S7` family or a
development/demo/evaluation split.

The S6 intake distinction is an ordinary `ExceptionCase` fact, not an oracle
lookup. During generation, `(family, position)` deterministically produces
`submission_ready` and `unresolved_questions` before any transaction event,
expected outcome, resolution path, or execution contract is constructed. The
20 S6 cases split evenly between incomplete intake (`false` plus
`submission_declaration`) and complete intake (`true` plus no questions); all
120 non-S6 cases retain the neutral `null`/empty defaults.

`Scenario.to_agent_context()` returns a defensive copy and recursively rejects
evaluator-only keys, even when they are nested inside lists or dictionaries.
It replaces the evaluator scenario ID with an opaque `context_id`; repository
student access similarly returns `ObservableStudent`. This prevents a scenario
from passing a schema check while leaking the answer through identifiers,
profile labels, or arbitrary `initial_state` data.

The context contract is exact: `initial_state_refs` must equal the linked
student, audit, registration, case, and offering-state IDs—no unrelated global
record can be added. `observed_state_versions` must cover exactly those linked
offering states at their baseline versions, and `request_time` must agree with
both the case and current-registration snapshot.

## 11. Determinism and rebuild

The generator uses:

```text
global seed:       42017
generator version: stage3.5.0
entity seed:       first eight bytes of SHA-256("42017|type|stable-id")
JSON ordering:     sorted records and keys
timestamps:        fixed timezone-aware values
encoding/newline:  UTF-8 with LF and a final newline
```

It does not use Python's randomized `hash()`, the wall clock, or an unseeded
random source. Generation validates the complete in-memory bundle before each
output file is replaced through a temporary file. The replacement is safe per
file, but it is not a whole-directory transaction. `--check` rebuilds the
bundle in memory and compares serialized bytes without modifying the checked-in
dataset.

From the repository root:

```powershell
.venv\Scripts\python.exe scripts\build_simulated_data.py
.venv\Scripts\python.exe scripts\build_simulated_data.py --check
.venv\Scripts\python.exe -m pytest
```

## 12. Readiness gate and limitations

The completed Stage 3 package passes a reload and cross-file validation that
proves:

- all frozen real hashes and manifest counts match;
- the 17/2,108/240/140/60 allocations are exact;
- every ID and source/assumption reference resolves;
- every student has one consistent scope, audit, and registration;
- student, audit, requirement, exemption, registration, and course AUs
  reconcile, including zero-AU records;
- every course/offering/index/state/version and attributed meeting agrees with
  the real template;
- path and study-plan alternatives are never summed together;
- approvals, events, results, observations, retries, and mutations are
  coherent;
- S1/S4/S7 prerequisite, exclusion, timetable, workload, path-state, and
  state-version predicates hold against the grounded records;
- S2 courses carry prerequisites, S5 students select published graduation
  paths, and S6 observable intake readiness agrees with its independently
  generated case variant and declared event;
- every scenario split and family count matches the contract;
- generated outputs are byte-identical across repeated runs; and
- agent context contains no evaluator-only information.

The Stage 3 package cannot establish authenticated Degree Audit results,
personal STARS registration slots, real future capacity, reserved quotas,
eligibility, general late-registration or substitution rules, or undocumented
approval chains. Those boundaries are deliberate evaluation features, not
missing values to guess.
