# 03 — Demo Scenarios

## Purpose

Use seven scenario families to demonstrate planning, evidence use, safe
escalation, human involvement, and recovery from changing operational state.
Each family has development, polished-demo, and hidden-evaluation cases.

The cases are synthetic terminal-stage student situations. Academic facts come
from the Stage 2 NTU/CCDS snapshot; private student data, future scenario time,
live availability, eligibility, decisions, and transaction outcomes are
simulated. Nothing in a scenario is an official Degree Audit or a prediction of
a future NTU offering.

## Shared grounding contract

Every generated scenario records:

- the selected `curriculum_id` and, where applicable, `graduation_path_id`;
- the source rule IDs supporting the target requirement;
- the AY2026–27 Semester 1 course and index records used as operational
  templates;
- every explicit prototype assumption used to fill a public-data gap;
- which facts are verified, derived, simulated, or unknown; and
- hidden, evaluator-owned ground-truth resolution or escalation constructed by
  the deterministic builder and checked for cross-file coherence.

Scenario family, split, evaluator scenario ID, terminal-profile label, future
event, script, and expected answer stay outside agent context. Agent-facing
case and context identifiers are opaque rather than encoding the scenario
family or split.

The exact delivered populations and validation boundaries are recorded in
[`stage_3_simulation_data_details.md`](stage_3_simulation_data_details.md).

## Materialized demo inputs and expected responses

The Main workspace exposes the following seven polished demo inputs. Their
expected responses are visible for presentation and learning. The same field is
hidden for all evaluation cases and is never included in agent context.

### `S1-M01` — same-course registration recovery

Input: a Year 4 AISC student from AY2025–26 has 129 earned AUs, has `CC0001`
registered, and still needs `CC0015`. Preferred class `83501` conflicts with the
current timetable; the request asks for the same course, not a substitution.

Expected response: reject class `83501`, register conflict-free class `83506`
during Add/Drop without approval, and verify that `CC0015` appears in the final
registration.

### `S2-M01` — prerequisite evidence route

Input: a Year 4 AISC student from AY2025–26 has 128 earned AUs and needs
`SC4002`. Simulated exchange course `FX2001` was passed, but transfer credit is
pending; the transcript and requested-course, prerequisite-course, and foreign-
course mappings are attached.

Expected response: validate the narrow pending-transfer evidence route, observe
CCDS Undergraduate Office approval, submit the `SC4002` prerequisite waiver,
and verify the waiver result.

### `S3-M01` — versioned curriculum reasoning

Input: a Year 4 DSAI student from AY2025–26 has 127 earned AUs, a not-ready
audit, and `MH1805` affecting graduation clearance. The request asks which dated
curriculum rules apply before any exception is recommended.

Expected response: use the cohort-specific curriculum source, retain the source
limitation, submit only the supported graduation exception, and verify the
result.

### `S4-M01` — timetable and approval constraints

Input: a Year 4 AISC student from AY2025–26 has 129 earned AUs, has `CC0007`
registered, and still needs `CC0001`. Preferred class `26501` conflicts with the
current timetable.

Expected response: reject class `26501`, observe the required approval,
register conflict-free class `82001`, and verify the resulting timetable.

### `S5-M01` — integrated-programme path

Input: a Year 5 CEEC student from AY2025–26 has 171 earned AUs, follows the
`PA option: 10-WEEK Professional Attachment` path, and still needs `SC1004`.
The request explicitly forbids combining another CCDS curriculum.

Expected response: keep the decision within that PA path, observe approval,
submit the `SC1004` integrated-programme exception, and verify the result.

### `S6-M01` — clarification instead of invention

Input: a Year 4 CE-ENT student from AY2025–26 has 139 earned AUs and an
unresolved `CC0001` issue after normal registration. No verified public
exception route is evident, and the submission declaration is missing.

Expected response: ask for the declaration and take no registration or
exception action until it is supplied.

### `S7-M01` — live-state recovery

Input: a Year 4 CE student from AY2025–26 has 134 earned AUs and still needs
`ML0004`. Class `83008` initially appears feasible, and the student asks the
system to refresh current state if the attempt fails.

Expected response: observe that class `83008` becomes full, refresh the
offering state, register verified alternative class `83001`, and confirm that
the final registration goal is complete.

All curricula remain `PARTIAL`. Therefore the simulator may construct a
scenario-bounded audit, but it must never label that audit as an official or
complete NTU determination. General late-registration, prerequisite-waiver,
substitution, overload, and approval-chain rules remain unknown unless a
narrow public route applies or the rule begins with the exact banner:

```text
SIMULATED POLICY FOR PROTOTYPE
```

Such a rule must also use `origin=SIMULATED_POLICY` and declare explicit
academic-year or admission-cohort applicability.

## Shared execution contract

Every future demo run follows the frozen control flow:

```text
Intake + Context
→ Memory Retriever
→ Planner
→ selectively routed specialists
→ Resolution Builder
→ Verifier [PRE_ACTION]
→ Action Gate / Approval when required
→ Transaction
→ Observation
→ Verifier [POST_ACTION]
→ DONE or Planner
```

Retrieved experience is advisory only. It may suggest an investigation or
recovery strategy, but it cannot be cited as evidence for a curriculum,
prerequisite, offering, vacancy, or policy. Every memory-suggested path must be
revalidated through current tools.

The pre-action verifier returns `VALID`, `REPLAN`, `CLARIFY`, or `ESCALATE`.
The post-action verifier returns `DONE` or `CONTINUE_FAILURE` after inspecting
the resulting world state and goal predicate. `TRANSACTION_SUCCESS`, including
a successful approval request, is never sufficient by itself to prove that the
student's goal is complete.

Clarification with a small, non-material update returns to the pre-action
verifier; a material update returns to the planner. Human approval means a
valid action needs permission. Human/admin review means no safe autonomous
resolution or authority exists. Rejected approval returns to the planner;
pending approval checkpoints and pauses.

Long-term memory is updated only after verified `DONE`. It stores a
deidentified strategy and outcome, never current NTU facts, transient
availability, evaluator-only fields, or unnecessary student data. All runs
enforce `MAX_REPLANS=4`, `MAX_TOOL_RETRIES=2`, and `MAX_TOTAL_STEPS=20`.

## Scenario 1 — Same-Course Registration Recovery

**Grounded example:** A terminal-stage student is missing a typed study-plan
course such as `SC2001`. The real schedule snapshot exposes multiple indexes,
but the student's preferred index is unavailable in simulated live state.

Expected behavior:

```text
confirm the outstanding course from the selected curriculum
→ retrieve the real course and index templates
→ check prerequisites, exclusions, timetable, and simulated eligibility
→ reject the unavailable or conflicting index
→ select another valid index for the same course
→ pre-action verify and submit through the no-approval route
→ observe the result and post-action verify the registration goal
```

This family tests audit lookup, index search, timetable reasoning, and safe
registration. It must not turn an index problem into an unsupported course
substitution. The normal positive variant occurs after normal registration but
during the simulated Add/Drop window.

## Scenario 2 — Prerequisite Evidence and Bounded Exception

**Grounded demo route:** `SC4002` publishes the raw prerequisite expression
`SC2001 OR MH1403 OR IE2108`. A synthetic student completed a mapped foreign
course, but the exchange credit has not yet appeared in the simulated Degree
Audit.

The collected public route
`policy.exception.exchange.pending_transfer` requires an unofficial transcript
and mappings for the requested NTU course, the NTU prerequisite, and the
foreign course. It routes the case to the CCDS Undergraduate Office for
verification.

Expected behavior:

```text
detect the unmet prerequisite in observable state
→ preserve the published Boolean expression
→ identify the narrow pending-exchange route
→ check the required evidence and mappings
→ pre-action verify and request approval
→ approved: transact; rejected: replan; pending: checkpoint and pause
→ observe the follow-up action and verify the actual goal
```

The public source establishes the route and evidence, not a guaranteed
decision. Approval, rejection, or pending status is simulated. Generic
prerequisite-waiver variants for which no public process exists must end in
`ESCALATED` or `CLARIFICATION_REQUIRED`; the agent must not generalize the
exchange route. Rejection itself is not a direct escalation edge: the planner
must first assess whether another grounded route exists.

## Scenario 3 — Versioned Multi-Source Reasoning

**Grounded example:** The dated AY2025–26 DSAI curriculum records 61 AU of
Programme Core and 19 AU of BDE, while the current unversioned overview records
60 and 20. Both total 131 AU.

Expected behavior:

```text
load the student's selected curriculum configuration
→ compare source version, cohort, and effective period
→ retain the conflict
→ use the dated cohort-specific source for that simulated cohort
→ explain the decision and its limitations
```

Memory must never settle this source conflict. If the cohort, selected path, or
other decisive context is missing, that is a material clarification and the
response returns to the planner.

Evaluation variants may use other preserved conflicts, including CE with Data
Analytics (136 versus legacy 156 AU), the CE with Sustainability 116-AU path
anomaly, DSAI with Sustainability (142 versus overview 141 AU), and the ACDA
172-versus-160 visible-category gap. The agent must never average conflicting
values or combine rules from different cohorts.

## Scenario 4 — Constraint-Heavy Index Planning

**Grounded example:** A terminal-stage student has several outstanding typed
plan courses. Candidate indexes use real AY2026–27 Semester 1 meeting patterns,
while current registration, individual workload ceiling, standing,
eligibility, capacity, and waitlist state are simulated.

Expected behavior:

```text
enumerate only source-backed course/index templates
→ apply conservative prerequisite and exclusion checks
→ detect meeting and workload conflicts
→ reject invalid combinations
→ return a feasible schedule or a bounded escalation
```

The generator chooses exact courses and indexes from grounded study-plan and
timetable records. The cross-file validator checks ownership, references,
versions, and event/result coherence. Public timetable appearance is never
treated as proof of personal eligibility or future availability.

## Scenario 5 — Integrated Programme or Pathway Reasoning

**Grounded example:** A BCG, BCE, CEEC, CSEC, CSC-with-Business, or
second-major student follows one published integrated curriculum
configuration, possibly with multiple graduation paths.

Expected behavior:

```text
load the integrated configuration
→ select the applicable graduation path
→ audit its source-backed components
→ apply declared simulated mappings only where public lists are incomplete
→ evaluate alternatives
→ verify one path-specific plan
```

This replaces the earlier assumption that the agent should independently load
and merge two complete rule sets. Public data already represents these cases as
integrated configurations, and shared-credit or double-counting decisions that
are not published remain explicit simulation assumptions. CE-BUS, CE-ITP, and
other configurations without detailed study-plan rows are not used for a
positive complete-audit demonstration. Ordinary base CSC FYP-versus-coursework
alternatives are also excluded from S5 because they are not cross-programme
configurations.

## Scenario 6 — No Valid Path in the Declared Scope

Every candidate that can be proved from the selected curriculum, collected
Semester 1 templates, and simulated live state fails because of prerequisites,
exclusions, clashes, availability, missing evidence, or unsupported policy.

Correct behavior:

```text
investigate all in-scope candidates
→ prove why each candidate fails or remains unknown
→ distinguish no path in scope from no path at NTU
→ disclose missing Semester 2, substitution, or late-registration rules
→ escalate or request clarification safely
```

Expected outcomes are normally `ESCALATED` or `CLARIFICATION_REQUIRED`. This
family must not convert missing public data into a negative university
decision. The six thin curriculum configurations remain in separate coverage
and routing tests rather than these student-backed scenarios.

Clarification is used when obtainable information may change the decision.
Human/admin review is used when the bounded system has no legitimate
autonomous route. Neither is represented as approval.

## Scenario 7 — Dynamic Failure / Main Live Demo

The agent initially finds a valid source-backed course/index template whose
simulated state is:

```text
version = 1
vacancies = 1
```

Immediately before execution, the simulator injects:

```text
VACANCY_BECOMES_ZERO
version = 2
vacancies = 0
```

The scripted transaction returns `MODULE_FULL`.

Expected behavior:

```text
observe the failed transaction and new state version
→ post-action verifier returns CONTINUE_FAILURE
→ invalidate the stale plan and return to the planner
→ re-query availability
→ replan to another proven index or route
→ pre-action verify and retry
→ observe and post-action verify DONE, or escalate if none remains
```

Capacity, vacancies, waitlist state, and the transaction are simulated over a
real catalogue/timetable template. This remains the main live demonstration
because it visibly distinguishes an adaptive agent from a static workflow.
Memory may retain the generic recovery strategy after verified completion, but
never the scenario's specific index, vacancy, event, or evaluator answer.

## Architecture coverage by family

| Family | Primary graph behavior |
| --- | --- |
| S1 | Selective audit/course routing, pre-action validation, direct transaction, and post-action completion check |
| S2 | Policy/evidence reasoning, approval grant/rejection/pending, checkpointing, and replan after rejection |
| S3 | Current-source precedence over memory plus material clarification for missing cohort/path facts |
| S4 | Multi-constraint resolution building, independent verification, and explicit approval only when the simulated exception route requires it |
| S5 | Integrated-path evidence across specialists without composing incompatible curricula |
| S6 | Small/material clarification versus human/admin escalation, never fabricated approval |
| S7 | Failed transaction observation, post-action replan, refreshed tools, second pre-action verification, and verified recovery |

## Scenario allocation

The materialized dataset contains exactly 140 scenarios:

```text
7 families × 20 cases per family = 140
```

Per family:

```text
4 development cases
1 polished demo case
15 hidden evaluation cases
```

Overall:

```text
Development: 28
Demo:         7
Evaluation: 105
Total:       140
```

The 105 evaluation cases remain separate from prompt tuning. Within each
family, include both resolvable and fail-closed variants where appropriate so
success is not synonymous with always taking an action.

## Scenario acceptance rules

A scenario is admitted only when the deterministic builder and cross-file
validator establish all of the following:

1. The student, curriculum, selected graduation path, case, transaction script,
   registration, and simulated offering states resolve across files.
2. The target requirement is backed by a typed study-plan row or by a visibly
   labelled prototype assumption.
3. Every positive course path has catalogue metadata and a usable timetable
   template. The 26 unresolved curriculum codes and nine courses without a
   conventional timetable are fail-closed unless missing information is the
   point of the case.
4. A non-empty raw prerequisite is never treated as no prerequisite merely
   because normalized fields are empty. Unsupported expressions produce
   `UNKNOWN`.
5. Policy routing is tied to the exact published context; a contact address is
   not silently promoted to final approver.
6. `valid_initial_paths`, `valid_final_paths`, and `invalid_paths` have disjoint
   IDs and their referenced records resolve before the scenario is saved.
7. The expected outcome is one of the existing contract values: `RESOLVED`,
   `ESCALATED`, `CLARIFICATION_REQUIRED`, `PENDING_APPROVAL`, or `FAILED`.
8. The Stage 4 execution fixture declares required and forbidden graph edges,
   both verifier decisions, the goal-completion predicate, and whether approval
   or human/admin review applies.
9. Clarification fixtures declare small versus material impact and the expected
   resume node; pending approval fixtures declare pause/resume behavior.
10. A scenario's loop budget remains within the global hard caps, and memory
    update is permitted only after verified `DONE`.

## Visibility boundary

The agent may receive only the observable student, audit, registration, case,
policy, catalogue, timetable-template, and current simulated-state data exposed
through tools. Future event injections, transaction scripts, valid/invalid path
sets, and expected outcomes remain evaluator-only ground truth through
`Scenario.to_agent_context()`. Retrieved or stored memory must also exclude
scenario IDs, family/split labels, future events, scripts, ground-truth paths,
expected outcomes, and unnecessary student-identifying data.

The Stage 3 corpus supplies academic and transaction scenarios. Stage 4 adds
the checked-in execution/control-flow fixture for verifier phases,
clarification routing, approval versus escalation, checkpoint expectations,
and goal postconditions. Stage 5 now executes and traces those graph behaviors;
see [`stage_5_langgraph_control_plane.md`](stage_5_langgraph_control_plane.md).
Neither later stage changes the grounded academic facts.
