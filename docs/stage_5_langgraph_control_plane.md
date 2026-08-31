# Stage 5 — LangGraph Control Plane

## 1. Status and purpose

Stage 5 implements the frozen orchestration architecture over the Stage 4
runtime. It adds a typed, checkpointed LangGraph control plane while preserving
the central safety boundary: graph nodes may use only `Stage4Tools`, never the
evaluator handle, hidden transaction script, injected future event, scenario
family, expected outcome, or ground truth.

The implementation is deliberately deterministic. `GroundedDecisionProvider`
selects specialists and makes conservative pre-action decisions from typed
intake plus current tool evidence. Stage 6 can replace that reasoning port with
grounded LLM specialists without changing the graph topology, transaction
runtime, checkpoint contract, or evaluator boundary.

Stage 5 provides:

- one compiled graph bound to one isolated Stage 4 case session;
- strict Pydantic contracts stored as JSON-safe LangGraph state;
- all frozen nodes, conditional edges, verifier phases, and human routes;
- checkpointed clarification and pending-approval interrupts;
- deterministic loop budgets and safe administrative handoff;
- advisory, deidentified experience-memory ports with a verified-completion
  write gate; and
- a strict evaluator-only loader for external graph-trace comparison.

It does not add an LLM, embeddings, vector retrieval, authenticated NTU
systems, a durable production checkpointer, or a UI.

## 2. Runtime boundary

The composition boundary is:

```text
ScenarioRuntimeFactory.build(scenario_id)
        │
        ├── Stage4Tools ─────────────── Stage5ControlPlane.build(...)
        │                                    │
        │                                    ├── LangGraph nodes
        │                                    ├── DecisionProvider
        │                                    ├── ExperienceMemoryStore
        │                                    └── Checkpointer
        │
        └── EvaluatorHandle ─────────── evaluator/tests only
                                             │
                                             └── execution-contract comparison
```

Only `ScenarioRuntime.tools` is passed to `Stage5ControlPlane`. The control
plane closure can read the observable `ScenarioContext`, invoke the four Stage
4 tool domains, and call current-state goal evaluation. It has no reference to
`ScenarioRuntime.evaluator` or `ScenarioController`.

This keeps all academic, policy, course, availability, approval, and write
effects behind the typed Stage 4 environment boundary. Graph nodes do not read
repositories or simulation JSON directly and do not infer hidden script steps
by probing writes.

## 3. Exact graph topology

The compiled graph registers these 18 nodes:

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

`verifier` is one registered node invoked with either `PRE_ACTION` or
`POST_ACTION`; it is not duplicated into two implementations. Specialists are
selected as a subset and executed in a deterministic queue before joining at
`resolution_builder`. Stage 5 uses sequential specialist execution so trace
ordering and evidence attribution are stable; the architecture still permits a
future parallel implementation behind the same join contract.

The implemented flow is:

```text
START
  → intake_context
  → memory_retriever
  → planner
  → supervisor_router
      → selected specialist(s), in queue order
  → resolution_builder
  → verifier [PRE_ACTION]
      ├─ VALID    → action_gate
      ├─ REPLAN   → planner
      ├─ CLARIFY  → clarification interrupt
      │                ├─ SMALL_CHANGE    → verifier [PRE_ACTION]
      │                └─ MATERIAL_CHANGE → planner
      └─ ESCALATE → human_admin_review → final_response → END

action_gate
  ├─ NO_APPROVAL      → transaction
  └─ APPROVAL_REQUIRED → human_approval
                            ├─ APPROVED → transaction
                            ├─ REJECTED → planner
                            └─ PENDING  → pause_checkpoint interrupt
                                             └─ APPROVAL_OBSERVED
                                                  → human_approval

transaction
  → observation
  → verifier [POST_ACTION]
      ├─ CONTINUE_FAILURE → planner
      └─ DONE ─────────────┬→ final_response → END
                            └→ memory_updater → END
```

Additional safe edges route a planner, verifier, clarification, action gate,
approval, or transaction that reaches a domain limit to
`human_admin_review`. A rejected approval therefore never jumps directly to an
administrative handoff: it first returns to `planner`, which records that no
safe route remains before escalating.

## 4. Node responsibilities and routes

| Node | Implemented responsibility | Normal next route |
| --- | --- | --- |
| `intake_context` | Validate intake/session identity and ground the caller's problem type against the observable case record | `memory_retriever` |
| `memory_retriever` | Retrieve at most five advisory patterns by observable case type and goal | `planner` |
| `planner` | Create/version a bounded plan, select required domains, and account for replans/retries | `supervisor_router` or safe admin review |
| `supervisor_router` | Dispatch the first required specialist | selected specialist |
| `degree_audit_agent` | Read the scenario-bounded audit and grounded curriculum | next specialist or builder |
| `policy_agent` | Read eligibility, approval requirement, and required documents | next specialist or builder |
| `course_agent` | Read details, prerequisites, exclusions, offerings, workload, timetable, and availability | next specialist or builder |
| `resolution_builder` | Build one typed action candidate from current evidence and observed versions | `verifier` in `PRE_ACTION` |
| `verifier` | Fail closed on missing/incomplete evidence, eligibility, documents, provenance, or versions before action; evaluate receipt-bound durable goals after action | phase-dependent conditional edge |
| `clarification` | Pause for typed answers, validate clarification identity/impact, and classify the resume route | pre-action verifier or planner |
| `action_gate` | Require `PRE_ACTION/VALID`, then separate approval-required from direct action | approval or transaction |
| `human_approval` | Read the current requirement, submit an idempotent approval request once, and re-read observable status | transaction, planner, or checkpoint |
| `pause_checkpoint` | Interrupt a pending thread and validate the approval/version wake-up payload | `human_approval` |
| `transaction` | Execute exactly one typed final write through Stage 4 Action & Transaction tools | `observation` |
| `observation` | Normalize the receipt or error into the Stage 4 observation contract | `verifier` in `POST_ACTION` |
| `human_admin_review` | Build a bounded CCDS administration handoff with evidence and attempted plans | `final_response` |
| `memory_updater` | Write only a deidentified pattern from verified `DONE` plus final receipts | `END` |
| `final_response` | Produce a typed verified-completion or administrative-handoff outcome | `END` |

The post-action verifier uses `Stage4Tools.evaluate_goal(...)`. A successful
request, an approval receipt, or a transaction success message cannot by itself
produce `DONE`; the candidate's durable current-state predicates must all be
satisfied. Exception and waiver predicates are bound to the single final
receipt carrying that candidate's action and idempotency key, so separate
receipts cannot jointly create a false completion.

## 5. Typed working state

`WorkflowState` is a `TypedDict`. Pydantic models validate every structured
value at node boundaries, and nodes store `model_dump(mode="json")` values so
the checkpointer does not depend on Python-object pickling.

The main state groups are:

| Group | Fields |
| --- | --- |
| Identity and intake | schema, thread/session/case IDs, start request, typed intake, agent-safe scenario context |
| Planning | current plan, plan history, specialist selection and queue |
| Evidence | specialist evidence and current Stage 4 tool responses |
| Resolution | action candidate, expected versions, goal predicates, idempotency key |
| Verification | phase, current decision, decision history, goal evaluation |
| Human interaction | clarification pause/response, approval pause/response, current approval requirement, admin handoff |
| Execution | action receipts, normalized observation, attempted offering IDs |
| Safety and audit | loop caps/counters, route, run status, errors, canonical trace |
| Completion and memory | final outcome and memory-write result |

Trace, specialist-evidence, receipt, and error fields use identity-aware reducers
so checkpoint replay cannot duplicate an already persisted item. `TraceEvent`
stores a monotonically numbered source, outcome, destination, optional verifier
phase, and canonical `SOURCE:OUTCOME->DESTINATION` key for external assertions.

Strict intake rejects extra evaluator fields. In particular, expected outcome,
scenario family, transaction scripts, injected events, and ground truth are not
valid `IntakeContext` fields.

## 6. Checkpointing, interrupts, and resume

The project depends on:

```text
langgraph>=1.2.10,<1.3
```

`Stage5ControlPlane.build(...)` compiles the graph with an injected checkpointer
or a default `langgraph.checkpoint.memory.InMemorySaver`. Every invocation uses
the typed intake's public `thread_id`. Its private saver key is namespaced by
session, case, runtime-instance UUID, and public thread. Independent runtime
instances may therefore safely reuse a case and public thread label in one
shared saver. Because a `Stage4Tools` session is mutable, its `RuntimeSession`
also grants one exclusive lease to exactly one control-plane facade and one
public thread. Repeated `start(...)`, a second thread on the same facade, and a
second facade over the same runtime all fail closed. The public methods are:

```text
create_intake(...)  build strict observable intake
start(intake)       invoke a new checkpointed thread
resume(...)         invoke Command(resume=...) on the same thread
state(thread_id)    inspect the current state snapshot
history(thread_id)  inspect checkpoint history
```

`InMemorySaver` is appropriate for deterministic tests and a local hackathon
demo, but it is process-local and not a production durability guarantee. A
database-backed checkpointer can be injected without changing graph nodes, but
that alone does not provide cross-process recovery: durable Stage 4 state and
an explicit runtime/checkpoint ownership-adoption protocol are also required.

### Clarification pause

`clarification` calls `interrupt(...)` with a typed `ClarificationPause`. On
resume it requires the matching clarification ID, a meaningful answer for
every requested field, the already verified small/material impact, and a
timezone-aware response time. The facade validates the payload before sending
`Command(resume=...)`, so an invalid client response cannot consume or poison
the persisted interrupt.
The readiness field `submission_declaration` is stricter: its answer must be
the literal Boolean `true`; `false`, `0`, missing, or blank answers leave the
checkpoint untouched and resumable. Other requested fields use the general
meaningfulness check.
Small updates mark the submission ready and return to pre-action verification;
material updates clear the missing question and return to planning.

The impact is not accepted as a new routing judgement from the caller. It must
match the impact already recorded by the verifier before the pause.

Stage 5 proves the checkpoint and routing contract; its deterministic provider
does not interpret free-form clarification answers as new academic truth.
Stage 6 must ground and validate any material answer before changing a goal,
curriculum/path selection, or Stage 4 fact.

### Pending approval pause

`human_approval` owns the Stage 4 `request_approval` call. It stores the
intermediate receipt before routing a pending result to `pause_checkpoint`, so
the interrupt occurs in a separate node after the side effect is checkpointed.
On resume, the payload must match the approval ID and checkpoint version. The
graph then returns to `human_approval`, which re-reads the authoritative current
status through the Stage 4 policy tool; the resume payload does not grant
approval.

This structure prevents a resumed node from replaying the approval request and
prevents a client-provided `APPROVED` string from opening the transaction gate.

### Current pending-approval limitation

The frozen Stage 3 pending cases contain an initial `PENDING` decision but no
later external approval-status event. Stage 4 likewise exposes no agent-facing
operation that can mutate an approval after that point. Consequently Stage 5
can prove persistence, wake-up validation, authoritative re-check, and safe
re-pause, but it cannot locally convert those pending fixtures to `APPROVED` or
`REJECTED`.

A real integration or a future evaluator fixture must first update the external
approval source and version. Only then may `resume(...)` wake the graph and the
Stage 4 policy read authorize the corresponding approved/rejected route. The
control plane intentionally does not simulate that authority from the resume
payload.

## 7. Approval is not administrative review

The implementation keeps the two human routes structurally separate:

```text
Approval
  candidate is valid, but permission is required
  → human_approval
  → approved / rejected / pending

Administrative review
  no safe autonomous route or authority remains
  → human_admin_review
  → evidence-bounded handoff and final response
```

`human_admin_review` never grants an approval or performs a protected write.
`human_approval` never invents a route when approval is rejected. Rejection is
recorded as `HUMAN_APPROVAL:REJECTED->PLANNER`; only the subsequent planner
decision may produce `PLANNER:NO_SAFE_ROUTE->HUMAN_ADMIN_REVIEW`.

## 8. Loop budgets and the control-step definition

The domain limits are unchanged:

```text
MAX_REPLANS = 4
MAX_TOOL_RETRIES = 2
MAX_TOTAL_STEPS = 20
```

`total_steps` is a domain control-step count, not a count of every LangGraph
node or every trace event. One control step is charged when entering:

```text
planner
verifier (either phase)
clarification (after a response resumes it)
action_gate
human_approval
transaction
human_admin_review
```

Pure intake, retrieval, routing, specialist reads, resolution assembly,
observation normalization, checkpoint waiting, final response, and memory
fan-out do not consume a domain control step.

The first planner entry is not a replan. A later planner entry increments
`replans`; if it follows a retryable observation it also increments
`tool_retries`. A prospective increment is checked before it is committed. If
it would exceed a cap, the counters remain at their allowed maximum and the
graph records the cap reason before routing to safe administrative review.

LangGraph's configured recursion limit is a framework backstop only. It does
not replace these smaller, explicit, auditable domain limits.

## 9. Advisory experience memory

Stage 5 defines `ExperienceMemoryReader`, `ExperienceMemoryWriter`, and
`ExperienceMemoryStore` protocols plus two deterministic implementations:

- `NullExperienceMemory`, the safe default, returns no matches and records that
  writes are disabled; and
- `InMemoryExperienceMemory`, a thread-safe local/test store with deterministic
  bounded filtering and idempotent record IDs.

Retrieval occurs after intake and before planning. It is bounded to five active
records for the current observable case type and goal. Retrieved content is
advice only; every academic, policy, offering, version, and approval claim is
re-checked through Stage 4 tools.

Read and write outages are isolated as typed workflow errors. Retrieval falls
back to current Stage 4 evidence, and a failed write cannot hide or roll back an
already verified final response. Privacy validation covers prose and every
identifier-bearing field, with only the exact deidentified Stage 4 receipt
grammar allowed through the receipt-reference gate.

The write gate requires a `POST_ACTION/DONE` verifier decision, a complete goal
evaluation, and at least one final transaction receipt. Approval-request
receipts are excluded from the proof set. Records are schema-versioned,
deidentified, invalidatable, and bounded. Validation rejects student IDs,
contact patterns, evaluator vocabulary, hidden-event references, and text that
purports to preserve current academic, policy, capacity, or availability facts.

`memory_updater` is reachable only on the verified `DONE` fan-out. It is never
reachable from clarification, pending approval, rejection, failure, or an
administrative handoff.

## 10. Evaluator isolation and trace contracts

`evaluation/execution_contracts.py` loads
`data/tests/execution_contracts.json` into strict evaluator-only Pydantic
models. By default it verifies the SHA-256 hashes of the three frozen source
artifacts before returning a package.

The loader validates route consistency, clarification resume rules,
approval/admin separation, checkpoint expectations, loop budgets, terminal
goal semantics, and memory permission. It is not imported by graph nodes and
its records are never placed in `WorkflowState`.

Tests may compare the graph's canonical trace with a contract outside the
agent boundary:

```text
Stage 5 graph trace ──┐
                     ├── evaluator assertion
hidden contract ─────┘
```

The contract may judge what happened; it may not tell the planner what to do.

## 11. S6 observable-intake boundary

The Stage 3 S6 family has two distinct cases: a missing simulated declaration
that should request a small clarification, and a controlled withdrawal/no-path
case that should end in administrative review. Reading the execution contract
or transaction script to choose between them would leak the answer. Generator
`stage3.4.0` instead persists the distinction as two typed, agent-observable
`ExceptionCase` fields:

```text
submission_ready: bool | None
unresolved_questions: list[str]
```

The simulation generator derives these fields directly from the S6
family/position variant before constructing its transaction script, event,
expected outcome, or execution contract. Missing-declaration variants store
`false` plus `submission_declaration`; conclusive variants store `true` plus an
empty list. Non-S6 cases use `null` plus an empty list.

`create_intake` reads these values through the agent-safe case policy tool. It
derives them when the caller omits them and treats supplied S6 values as exact
assertions against the observable case. The `intake_context` node independently
re-reads and compares the case, so a forged typed intake cannot bypass the
guard. When the case declares that the S6 submission is incomplete, the
deterministic verifier requests `submission_declaration`; only a literal
Boolean `true` can complete that small clarification and return to pre-action
verification. When intake is complete, the graph continues normally and lets
current tools plus the transaction observation determine whether a route
remains.

The matrix's explicit values are redundant consistency assertions sourced from
the typed observable case; they are not the trust mechanism. It never derives
either field from `expected_outcome`, clarification expectations, a transaction
result, or a scenario ID. The execution contract remains exclusively on the
evaluator side.

## 12. File map and public entry point

```text
src/graduation_exception_agent/
├── models/orchestration.py          typed state, plans, candidates, pauses,
│                                    traces, outcomes, reducers, and loop caps
├── orchestration/
│   ├── decisions.py                 deterministic Stage 5 reasoning port
│   ├── nodes.py                     node implementations over Stage4Tools
│   └── graph.py                     topology, checkpointer, start/resume API
├── memory/
│   ├── ports.py                     advisory-memory contracts and privacy gate
│   └── in_memory.py                 null and in-memory implementations
└── evaluation/execution_contracts.py
                                     evaluator-only contract loader
```

The main construction path is:

```python
from graduation_exception_agent import ScenarioRuntimeFactory, Stage5ControlPlane

runtime = ScenarioRuntimeFactory.from_data_directory("data").build("S1-D01")
control_plane = Stage5ControlPlane.build(tools=runtime.tools)
```

Only `runtime.tools` crosses into the graph. `runtime.evaluator` remains with
the test or evaluation harness.

## 13. Completion gate

Stage 5 is complete only when verification establishes all of the following:

- all 18 registered nodes and every conditional destination match the frozen
  topology;
- the same verifier implementation handles both explicit phases;
- specialist routing is selective and evidence remains attributable;
- small clarification resumes at pre-action verification and material
  clarification resumes at planning;
- approval required/no-approval, approved/rejected/pending, and separate
  administrative-review routes are covered;
- pending approval interrupts persist state and resume without replaying the
  approval request;
- invalid clarification answers leave the original checkpoint resumable;
- one mutable Stage 4 session cannot be shared by multiple graph threads, and
  its exclusive facade/thread lease plus session/case/runtime/thread saver
  namespace prevent checkpoint collisions;
- post-action completion depends on current-state goal predicates;
- exception/waiver predicates bind to one candidate-specific final receipt;
- loop caps produce deterministic safe handoff;
- memory retrieval is advisory, backend failures are contained, privacy covers
  identifiers as well as prose, and writes occur only after verified `DONE`;
- graph state and agent-facing objects contain no evaluator-only contract data;
- execution-contract source hashes remain current; and
- the Stage 3 and Stage 4 suites remain green.

Verification commands:

```powershell
.venv\Scripts\python.exe scripts\build_simulated_data.py --check
.venv\Scripts\python.exe scripts\build_execution_contracts.py --check
.venv\Scripts\python.exe -m pytest -q
```

Full-suite result at Stage 5 handoff: `573` tests passed.

## 14. Boundaries and Stage 6 handoff

Stage 5 is the control plane, not the final reasoning system. Its deterministic
provider is intentionally conservative and replaceable. Stage 6 should add:

- grounded adapters for the existing typed specialist-selection and pre-action
  assessment decision seam;
- new typed ports before introducing LLM planning, specialist synthesis,
  resolution building, or post-action reasoning, while preserving the frozen
  topology and gates;
- policy/document retrieval that preserves source IDs, effective periods,
  completeness, and current-tool precedence;
- advisory experience retrieval/ranking beyond deterministic exact filters;
- structured-output validation, retry handling, and model failure containment;
- prompts that exclude evaluator-only fields and never let memory override a
  current tool result; and
- focused reasoning evaluations before the Stage 7 315-run scenario and
  robustness campaign.

Stage 6 must preserve the Stage 5 graph, checkpoint, approval, transaction,
loop, trace, and memory-write gates unless a separately reviewed architecture
change updates the normative contract.
