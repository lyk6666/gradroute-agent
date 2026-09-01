# 02 — Solution Architecture

## Status and objective

This is the frozen high-level architecture for the current prototype. Stage 5
implements it as a controlled, checkpointed LangGraph workflow over the Stage
4 deterministic tool boundary. Stage 6 uses the existing typed decision seam
for grounded Bedrock reasoning without weakening these routes or gates.

```text
UNDERSTAND
→ RETRIEVE RELEVANT EXPERIENCE
→ PLAN
→ ROUTE
→ INVESTIGATE
→ BUILD RESOLUTION
→ VERIFY
→ ACT
→ OBSERVE
→ VERIFY OUTCOME
→ COMPLETE OR REPLAN
```

Core loop:

```text
PLAN → ACT → OBSERVE → VERIFY → ADAPT → REPLAN
```

The graph is deliberately bounded. Specialists return structured evidence;
they do not converse freely or execute writes. Deterministic tools and
verifiers remain responsible for academic, policy, state-version, and action
safety.

## 1. Normative graph

```text
Student / Case
      ↓
Intake + Context
      ↓
Memory Retriever ← Long-Term Memory (advisory experience only)
      ↓
Planner ←──────────────────────────────────────────────────────────┐
      ↓                                                            │
Supervisor / Router                                                │
  ├─ academic need ─→ Degree Audit Agent                           │
  ├─ policy need   ─→ Policy Agent                                 │
  └─ course need   ─→ Course Agent                                 │
                 ↓                                                  │
         Resolution Builder                                        │
                 ↓                                                  │
       Verifier [PRE_ACTION]                                        │
       ├─ REPLAN ──────────────────────────────────────────────────┤
       ├─ CLARIFY → Clarification                                   │
       │              ├─ small change → Verifier [PRE_ACTION]       │
       │              └─ material change ──────────────────────────┤
       ├─ ESCALATE → Human / Admin Review → Final Response          │
       └─ VALID → Action Gate                                       │
                        ├─ no approval → Transaction                 │
                        └─ approval required → Human Approval       │
                                                   ├─ approved → Transaction
                                                   ├─ rejected ────┤
                                                   └─ pending → checkpoint / pause
                                      Transaction                   │
                                           ↓                        │
                                      Observation                   │
                                           ↓                        │
                                  Verifier [POST_ACTION]            │
                                      ├─ continue/failure ──────────┘
                                      └─ DONE ─┬→ Final Response
                                               └→ Memory Updater
                                                     ↓
                                              Long-Term Memory
```

The edge table in this document is normative if a visual diagram is
ambiguous. In particular, `no approval` goes directly to `Transaction`;
`Human / Admin Review` is never a substitute for approval and is reached only
through an explicit `ESCALATE`, `NO_SAFE_ROUTE`, or loop-limit decision.

## 2. Source-of-truth rule

Maintain this separation throughout the graph:

```text
OFFICIAL OR CURRENT INFORMATION
    → grounded data and current tools

PAST AGENT EXPERIENCE
    → long-term memory
```

Long-term memory may suggest a strategy, such as checking an equivalent course
before considering a waiver. It must never assert a current prerequisite,
curriculum rule, offering, vacancy, policy, or approval requirement. Every such
claim must be refreshed through the appropriate tool and retain provenance.

If memory conflicts with a current tool result, the current grounded result
wins and the conflict is recorded.

## 3. Entry, retrieval, and planning

### `intake_context`

Responsibilities:

- interpret the student's goal without exposing evaluator labels;
- resolve the opaque student and case context;
- identify programme, curriculum, cohort, and scenario period;
- load the initial academic and registration snapshots; and
- classify the problem only enough to support retrieval and planning.

### `memory_retriever`

Runs after intake and before planning. It retrieves compact reusable experience:

- similar case types;
- successful resolution and recovery patterns;
- recurring failure patterns; and
- useful policy-navigation strategies.

Its output is advisory, provenance-labelled, and bounded in size. Retrieval
must be safe when the store is empty, and correctness must never depend on a
memory match.

### `planner`

Creates or revises a mutable plan. It determines what is outstanding, what
evidence is missing, which constraints must be checked, whether a supported
exception route exists, and whether human involvement may be needed. Every
material replan returns here and increments a loop counter.

## 4. Routing and specialist investigation

### `supervisor_router`

Selects the required subset of specialists for the current plan step:

```text
academic requirement needed → degree_audit_agent
rule or exception needed     → policy_agent
course feasibility needed    → course_agent
```

It must not call every specialist by default. When more than one domain is
needed, the selected specialists may run in parallel and join at the Resolution
Builder; their outputs remain independently attributable.

### `degree_audit_agent`

Uses Academic & Student tools to inspect the observable student record,
selected curriculum/path, and scenario-bounded audit; determine outstanding
requirements; and evaluate whether a candidate contributes to graduation.

### `policy_agent`

Uses Policy & Exception tools to retrieve a current policy route, distinguish a
verified route from an unknown or simulated rule, determine required evidence,
and identify whether approval or administrative escalation is appropriate.

### `course_agent`

Uses Course & Scheduling tools to find grounded candidates and check course
details, prerequisites, exclusions, semester templates, timetable, workload,
availability, and observed state versions.

All specialist outputs are structured evidence written to working state.

## 5. Resolution construction and pre-action verification

### `resolution_builder`

Combines specialist evidence into ranked candidate paths. Each candidate
records:

- proposed steps and target records;
- supporting rule and source IDs;
- required documents or approval;
- observed state versions;
- rejected alternatives and rejection reasons; and
- unresolved assumptions or unknowns.

The builder proposes paths; it cannot declare them valid.

### `verifier` in `PRE_ACTION` phase

Independently checks:

- curriculum and selected graduation-path consistency;
- prerequisite, exclusion, timetable, workload, and availability constraints;
- policy applicability and evidence completeness;
- approval requirements and observability;
- target and state-version freshness; and
- whether unknown information requires clarification or escalation.

It returns exactly one structured decision:

```text
VALID
REPLAN
CLARIFY
ESCALATE
```

`VALID` means a candidate may reach the Action Gate; it does not mean the
student's goal is complete.

## 6. Clarification and escalation

### `clarification`

Requests only information that can materially affect the decision. The update
is classified after it is received:

```text
small change    → PRE_ACTION verifier
material change → Planner
```

A material change alters the goal, curriculum/path, requested action, evidence
basis, or a constraint on which the plan depends. The classification must be a
typed result recorded in working state.

### `human_admin_review`

Handles `ESCALATE`: the system cannot safely or legitimately resolve the case
with the available rules or authority. It produces a bounded handoff and final
response rather than fabricating a resolution.

Administrative review is not approval. Approval means the proposed action is
valid but needs permission; escalation means the autonomous system lacks a
verified resolution or authority.

## 7. Action, approval, transaction, and observation

### `action_gate`

Accepts only a `VALID` candidate. It checks action risk, approval requirement,
approval observability, state versions, and idempotency key.

```text
no approval required → transaction
approval required    → human_approval
```

### `human_approval`

Owns the `request_approval` tool call, persists the request, and returns one of:

```text
APPROVED → transaction
REJECTED → planner
PENDING  → persist checkpoint and pause
```

Pending state, requested documents, and resumption data live in thread memory.

### `transaction`

Executes typed simulated writes through Action & Transaction tools:

- submit registration;
- submit prerequisite waiver; or
- submit another exception request.

The transaction runtime owns version checks and state mutation. The LLM cannot
write directly or assume success.

### `observation`

Normalizes tool results into the existing Stage 3 observation contract, such
as:

```text
TRANSACTION_SUCCESS
MODULE_FULL
CLASS_UNAVAILABLE
APPROVAL_REJECTED
APPROVAL_PENDING
STALE_STATE
TEMPORARY_FAILURE
REQUIRED_INFORMATION_MISSING
```

A raw `STATE_CHANGED` condition is represented by the established
`STALE_STATE` observation. Observation updates working state before any further
reasoning.

## 8. Post-action verification and completion

The same `verifier` is invoked again with `verification_phase=POST_ACTION`.
This second invocation checks the resulting world state and the student's
actual goal. A successful API response alone is insufficient.

```text
DONE             → Final Response + Memory Updater
CONTINUE/FAILURE → Planner
```

The post-action verifier must detect partial success, stale plans, changed
availability, rejected or pending approval, and transactions that succeeded
without satisfying the target requirement.

### `final_response`

Explains the verified result, evidence, actions taken, remaining unknowns, and
any human handoff. It must not expose evaluator-only paths or hidden events.

### `memory_updater`

Runs only after a verified `DONE` outcome. It writes compact reusable
experience, including case type, successful or failed strategy, recovery path,
and verified outcome.

It must not store:

- current policy or academic facts as memory truth;
- unverified reasoning;
- rejected candidates as successful patterns;
- transient tool output as permanent fact;
- evaluator-only labels or ground truth; or
- unnecessary student PII.

## 9. Three memory layers

### Working state

Typed LangGraph state for one execution:

```text
student / case and goal
retrieved advisory memories
plan and routing decisions
degree audit and relevant policies
candidate courses and resolutions
tool results and observations
clarification state
approval and transaction state
verification phase and decision
errors and loop counters
final verified outcome
```

### Thread memory

LangGraph checkpoint state for:

- conversation and clarification responses;
- previous attempts and observations;
- pending approval;
- pause/resume; and
- deterministic recovery after interruption.

### Long-term memory

A separate experience store containing reusable patterns and recovery
strategies. Every item has a schema version, provenance to a verified run,
sensitivity classification, and invalidation metadata. It is not an academic
or policy database.

## 10. Tool architecture

Tools are grouped into four domains.

### Academic & Student

```text
get_student_record
get_current_registration
get_curriculum
run_degree_audit
```

### Policy & Exception

```text
search_policy
check_exception_eligibility
get_approval_requirement
get_required_documents
```

### Course & Scheduling

```text
search_courses
get_course_details
check_prerequisite
check_exclusion
get_semester_offerings
check_timetable
check_workload
check_availability
```

### Action & Transaction

```text
request_approval
submit_registration
submit_waiver
submit_exception
get_transaction_status
```

All tools use typed inputs and compact outputs. Academic, policy, and course
results include provenance and completeness. Availability and write tools bind
the observed version. Action tools require an idempotency key and never expose
the hidden transaction script.

## 11. Required nodes and conditional edges

The implemented graph contains exactly 18 registered nodes:

```text
intake_context
memory_retriever
planner
supervisor_router
degree_audit_agent
policy_agent
course_agent
resolution_builder
verifier
clarification
action_gate
human_approval
pause_checkpoint
human_admin_review
transaction
observation
memory_updater
final_response
```

Normative edges:

| Source | Outcome | Destination |
| --- | --- | --- |
| Intake | context ready | Memory Retriever |
| Memory Retriever | advisory context ready or empty | Planner |
| Planner | plan ready | Supervisor / Router |
| Planner | no safe route | Human / Admin Review |
| Supervisor | academic / policy / course needs | Required specialist subset, then join |
| Resolution Builder | candidates built | Verifier `PRE_ACTION` |
| Verifier `PRE_ACTION` | `VALID` | Action Gate |
| Verifier `PRE_ACTION` | `REPLAN` | Planner |
| Verifier `PRE_ACTION` | `CLARIFY` | Clarification |
| Verifier `PRE_ACTION` | `ESCALATE` | Human / Admin Review |
| Clarification | small change | Verifier `PRE_ACTION` |
| Clarification | material change | Planner |
| Action Gate | no approval | Transaction |
| Action Gate | approval needed | Human Approval |
| Human Approval | approved | Transaction |
| Human Approval | rejected | Planner |
| Human Approval | pending | Pause Checkpoint |
| Pause Checkpoint | approval observed after resume | Human Approval |
| Transaction | result | Observation |
| Observation | normalized | Verifier `POST_ACTION` |
| Verifier `POST_ACTION` | done | Final Response and Memory Updater |
| Verifier `POST_ACTION` | continue / failure | Planner |
| Human / Admin Review | handoff prepared | Final Response |
| Bounded control node | next step would exceed a loop cap | Human / Admin Review |

## 12. Loop and execution safety

Hard limits are enforced in code and state:

```text
MAX_REPLANS = 4
MAX_TOOL_RETRIES = 2
MAX_TOTAL_STEPS = 20
```

Reaching a cap produces a safe escalation with an audit trail. LLM judgement
cannot override caps, approval gates, tool schemas, state versions, source
completeness, or evaluator visibility boundaries.

## 13. Implementation sequence

The frozen architecture is implemented incrementally:

```text
Stage 4  deterministic tools + isolated transaction runtime (complete)
Stage 5  typed LangGraph state, nodes, edges, checkpointing, and memory ports (complete)
Stage 6  grounded LLM reasoning + ranked advisory-memory retrieval (complete)
Stage 7  scenario runner, deterministic and live evaluation, and robustness hardening (complete)
Stage 8  user-facing demo integration and delivery hardening
```

Stage 4 deliberately precedes orchestration so graph behavior can be tested
against trustworthy tools. Stage 5 then freezes those safety and control-flow
contracts before Stage 6 adds probabilistic reasoning. UI work remains outside
this architecture update and is not required before the runtime and evaluation
gates pass.

## 14. Implemented Stage 6/7 boundary and Stage 8 handoff

Stage 5 implements the architecture without changing the grounded Stage 3
academic corpus. It adds:

- `memory_retriever` before `planner` and a verified-only `memory_updater` on
  the post-action `DONE` fan-out;
- JSON-safe typed working state plus checkpoint and advisory-memory contracts;
- one verifier node used in explicit `PRE_ACTION` and `POST_ACTION` phases;
- fail-closed policy, document, provenance, evidence-set, and version checks
  before the action gate, plus candidate-receipt binding after action;
- separate approval, pending checkpoint, and administrative-review routes;
- typed small/material clarification interrupts and resume routing;
- an exclusive one-facade/one-thread lease per mutable Stage 4 runtime, with
  session/case/runtime-instance/public-thread-namespaced saver keys;
- deterministic loop counters and safe cap escalation; and
- canonical trace events for evaluator-side comparison.

Implemented areas are:

```text
src/graduation_exception_agent/tools/          Stage 4 environment boundary
src/graduation_exception_agent/runtime/        isolated transaction runtime
src/graduation_exception_agent/orchestration/  Stage 5 nodes and graph
src/graduation_exception_agent/memory/         advisory memory ports
src/graduation_exception_agent/evaluation/     evaluator contracts and Stage 7 campaign
```

LangGraph is now an explicit Stage 5 dependency. The earlier Stage 4 import
guard has been superseded by dependency, model, topology, route, interrupt,
memory, and isolation tests. The control plane defaults to an in-memory
checkpointer for deterministic tests and local demonstration; production
durability requires a persistent checkpointer, durable Stage 4 state, and an
explicit cross-process checkpoint ownership/adoption design.

The Stage 4/5 interface decisions are resolved as follows:

- `human_approval` alone consumes the scripted `REQUEST_APPROVAL` step and
  records it as an intermediate, non-goal receipt;
- final writes expose durable action-specific postconditions for the
  post-action verifier;
- `STALE_STATE` remains the normalized form of the reference diagram's
  `STATE_CHANGED` example;
- rejected approval records `rejected → Planner` before any later admin route;
- clarification impact is typed before the interrupt and controls its resume
  destination; and
- pending approval uses an explicit `pause_checkpoint` node and resumes through
  `human_approval`, which re-reads current status rather than trusting the wake-up
  payload.

The evaluator-only execution-contract package remains outside the graph and
provides approval/admin, clarification, checkpoint, loop, goal, and memory
expectations without becoming planner input. `create_intake` derives the S6
missing-declaration distinction from the agent-safe observable case
(`submission_ready` and `unresolved_questions`) and the first node rechecks it;
caller-supplied values are exact assertions, never a substitute for that read
or an inference from the hidden expected outcome. Completing
`submission_declaration` requires literal Boolean `true`.

Pending Stage 3 approvals have no later external status-change fixture. The
implemented control plane can persist, resume, re-check, and safely re-pause
those threads, but it cannot manufacture an approved or rejected decision from
a resume payload. A real approval source or later evaluator fixture must update
the authoritative state first.

Stage 6 now implements grounded Bedrock reasoning for the existing
specialist-selection/pre-action decision provider plus deterministic
exact-and-related advisory retrieval. Forced structured output, allowlisted
prompt projections, deterministic safety dominance, and bounded checkpoint
audit prevent the model from broadening an unsafe route. The offline suite and
the opt-in two-request Bedrock integration gate pass. Stage 7 now implements
the 315-run trace, robustness, and regression campaign with isolated memory
conditions and deterministic acceptance gates. Both the fixture and qualifying
Bedrock campaigns pass 315/315 runs and all 105 scenarios at 3/3 consistency;
the live campaign also validates 720/720 structured reasoning calls without
fallback. Neither stage may bypass current tools,
approval/version gates, loop caps, checkpoint identity, or verified-only memory
writes. See
[`stage_5_langgraph_control_plane.md`](stage_5_langgraph_control_plane.md) for
the control-plane record and
[`stage_6_grounded_llm_reasoning.md`](stage_6_grounded_llm_reasoning.md) for the
reasoning boundary and live gate.
