# Stage 4 — Deterministic Runtime and Tools

## 1. Status and purpose

Stage 4 is complete as the executable, deterministic environment between the
frozen Stage 3 package and the future LangGraph control plane.

It provides:

- strict request, response, provenance, observation, receipt, verifier, goal,
  and execution-contract models;
- one isolated mutable runtime session per scenario;
- the four tool domains frozen in the solution architecture;
- atomic and idempotent simulated write execution;
- explicit optimistic state-version checks and approval gates;
- durable action receipts with derived postconditions;
- deterministic goal evaluation against current runtime state; and
- one evaluator-only execution contract for each of the 140 Stage 3 scenarios.

Stage 4 is deliberately pure Python. It does not contain LangGraph nodes, an
LLM, checkpoint persistence, long-term memory, graph traces, or a UI. Those are
later-stage consumers of this boundary, not hidden features of the runtime.

## 2. Runtime boundary

The central safety rule is that agent-visible state and evaluator-only control
state are different objects:

```text
Frozen Stage 3 package
        │
        ▼
ScenarioRuntimeFactory
        │
        ├── Stage4Tools ─────────────── agent / future control plane
        │      │
        │      ├── Academic & Student
        │      ├── Policy & Exception
        │      ├── Course & Scheduling
        │      └── Action & Transaction
        │
        └── EvaluatorHandle ─────────── tests and evaluator only
               │
               └── ScenarioController
                      └── hidden transaction script and future event
```

`ScenarioRuntimeFactory.build(scenario_id)` constructs a fresh
`ScenarioRuntime`. Only `ScenarioRuntime.tools` is safe to pass into agent or
control-plane code. `ScenarioRuntime.evaluator` exposes test diagnostics and
must remain outside that boundary.

### `RuntimeSession`

`RuntimeSession` owns a defensive working copy of exactly one scenario's
observable student, audit, registration, case, offering states, and any
approval that has become observable. It does not contain scenario family,
split, terminal profile, ground truth, the transaction script, or a future
event.

Every public read returns a defensive copy. Separate factory builds therefore
cannot mutate one another or the frozen repositories. A re-entrant lock guards
session state, receipt storage, idempotency records, and the monotonically
increasing session revision.

### `ScenarioController`

`ScenarioController` is evaluator-only. It owns a private copy of one Stage 3
transaction script and its cursor. It accepts only the action and parameters of
the next scripted step and advances the cursor only after the supplied
copy-on-write callback succeeds. A mismatch, failed preflight, or exception
does not consume the step.

The controller is injected into `ActionEngine`; it is never returned through a
tool response or attached to `Stage4Tools`.

## 3. Typed tool contract

All tool calls use strict Pydantic request and response models.

### Call context

`ToolCallContext` carries:

- `session_id` and `case_id` for isolation;
- a unique `request_id`;
- a timezone-aware `requested_at` value;
- an `idempotency_key` for write calls; and
- zero or more typed `VersionExpectation` records.

Read and write tools reject a request whose session or case does not match the
active runtime. Action tools additionally require an idempotency key.

### Response envelope

`ToolResponse` normalizes every tool result with:

- `SUCCESS`, `FAILURE`, or `PENDING` status;
- structured JSON data;
- zero or more `ToolProvenance` records;
- a stable `ToolErrorCode` and retryability flag on failure;
- normalized observations for write attempts; and
- current entity versions where versioned state was read or changed.

Provenance must contain at least one source, rule, or derived-from identifier.
Real public records retain their source origin and completeness. Simulated
records are explicitly labelled as derived, and prototype policies are not
presented as official NTU rules.

### Action receipts

Every consumed action step produces an `ActionReceipt`. The receipt records the
request and transaction identity, action, normalized result and observation,
mutation IDs, resulting entity versions, postconditions, commit status,
retryability, session revision, and whether the result was an idempotent replay.

A successful approval request is always `intermediate=true` and
`goal_effect=false`. Transaction success alone is not sufficient evidence that
the student's goal was achieved. A final goal effect requires derived,
satisfied postconditions, and `Stage4Tools.evaluate_goal(...)` independently
checks explicit `GoalPredicate` values against current session state.

## 4. Four tool domains and exact APIs

### Academic & Student

Service: `AcademicStudentTools`

```text
get_student_record(StudentRecordRequest)
get_current_registration(CurrentRegistrationRequest)
get_curriculum(CurriculumRequest)
run_degree_audit(DegreeAuditRequest)
```

The student, registration, and audit are scenario-bounded observable copies.
The curriculum comes from the real-data repository. The returned degree audit
is the frozen deterministic audit and retains its declared assumptions and
limitations; it is not an authenticated NTU Degree Audit.

### Policy & Exception

Service: `PolicyExceptionTools`

```text
search_policy(PolicySearchRequest)
check_exception_eligibility(CasePolicyRequest)
get_approval_requirement(CasePolicyRequest)
get_required_documents(CasePolicyRequest)
```

Policy search is deterministic and scoped by academic year and admission
cohort. It can return current real policy sections and explicitly labelled
prototype policies. Eligibility is conservative: a declared review route does
not predict approval, and an ungrounded route remains `UNKNOWN`.

Approval requirement metadata may be visible before its outcome. Status,
decision reason, and decision time appear only after the approval has become
observable in the session.

### Course & Scheduling

Service: `CourseSchedulingTools`

```text
search_courses(CourseSearchRequest)
get_course_details(CourseDetailsRequest)
check_prerequisite(StudentCourseCheckRequest)
check_exclusion(StudentCourseCheckRequest)
get_semester_offerings(SemesterOfferingsRequest)
check_timetable(TimetableCheckRequest)
check_workload(WorkloadCheckRequest)
check_availability(AvailabilityCheckRequest)
```

Course details and offering templates come from grounded real data. Student
history, registration, and live availability are isolated simulated facts.
Prerequisite and timetable checks remain conservative when their source data
is incomplete. Availability returns the current simulated state version and
can reject an explicitly stale expected version.

### Action & Transaction

Service: `ActionTransactionTools`

```text
request_approval(ApprovalRequest)
submit_registration(RegistrationSubmissionRequest)
submit_waiver(WaiverSubmissionRequest)
submit_exception(ExceptionSubmissionRequest)
get_transaction_status(TransactionStatusRequest)
```

These adapters expose only `ActionEngine`; they do not expose the hidden
controller or script. `get_transaction_status` returns the same durable receipt
created by the original action attempt.

## 5. Transaction guarantees

### Atomic copy-on-write

For each accepted write attempt, `ActionEngine`:

1. validates session/case identity and the idempotency key;
2. enforces the approval gate;
3. matches the hidden next step;
4. copies all mutable session state;
5. validates explicit state-version preconditions;
6. applies only allowed mutations to the copy;
7. derives action-specific durable postconditions;
8. creates a normalized observation and receipt; and
9. commits the candidate state, receipt, idempotency record, and next session
   revision together.

Preflight rejection leaves session state, receipts, the idempotency index, and
the hidden script cursor unchanged. Controlled failure events may deliberately
commit their declared state change and failure receipt; this is how a vacancy
change or stale-state event becomes an observable fact for replanning.

Only the declared mutable offering and approval fields can be changed by a
script event. Registration commits additionally update the registered course,
timetable, workload, missing-course list, selected offering vacancy/version,
and case state as one session commit.

### Explicit versions

Writes carry `VersionExpectation` values for every required mutable target.
The target type, caller-observed version, scripted precondition, and current
runtime version must agree. Otherwise the action returns a normalized stale or
invalid-request error without a partial commit.

### Idempotency

An action idempotency key is bound to a fingerprint of its case, action,
parameters, and expected versions.

- Repeating the same key and fingerprint returns the original receipt with
  `replayed=true` and does not execute again.
- Reusing the key with a different fingerprint returns
  `IDEMPOTENCY_CONFLICT`.
- Concurrent duplicate calls are serialized and commit once.

### Approval gate

Approval and administrative escalation remain distinct.

- `request_approval` is valid only for the declared approval route.
- A later protected write must supply that approval ID.
- A hidden or pending approval blocks the protected write.
- A rejected approval blocks execution and requires replanning.
- Only an observable approved decision opens the gate.

Human/admin review is not an approval tool and is not implemented as a Stage 4
workflow. Its routing belongs to the Stage 5 graph.

### Observations and postconditions

Stage 3 transaction codes are converted into stable `ToolStatus`,
`ToolErrorCode`, and `ToolObservation` values, including success, module full,
class unavailable, prerequisite failure, approval pending/rejected, stale
state, temporary failure, and required information missing.

Successful registration, waiver, and exception actions derive postconditions
from the resulting state. Goal evaluation reads those durable effects instead
of trusting a success message or the hidden ground truth.

## 6. Evaluator-only execution contracts

`data/tests/execution_contracts.json` contains 140 deterministic Stage 4
contracts, exactly one for each Stage 3 scenario. The package is generated with
`generator_version: stage4.0.0`, is marked `evaluator_only`, and binds itself to
the source scenario, transaction, and approval files with SHA-256 hashes.

Each contract records the expected:

- pre- and post-action verifier decisions;
- required and forbidden control-flow edges;
- clarification impact and resume destination;
- approval versus human/admin-review route;
- action-specific goal predicate and expected satisfaction;
- verifier/observation transitions needed around each write;
- memory-update permission after verified completion; and
- replan, retry, and total-step budgets.

These graph-related values are contracts for Stage 5. Stage 4 does **not**
execute LangGraph, emit graph traces, persist checkpoints, pause a thread, or
resume a pending approval. In particular, `checkpoint_required` in an
execution contract required Stage 5 to implement and prove that behavior; it is
not a claim that Stage 4 already has checkpoint storage.

The contract builder treats the Stage 3 artifacts as immutable inputs and does
not reinterpret academic facts or transaction outcomes.

## 7. File map

```text
data/tests/
└── execution_contracts.json

scripts/
└── build_execution_contracts.py

src/graduation_exception_agent/
├── models/
│   ├── tooling.py             # tool, provenance, observation, and receipt models
│   └── runtime.py             # goal, verifier, loop, and evaluator-contract models
├── runtime/
│   ├── controller.py          # evaluator-only hidden script cursor
│   ├── execution.py           # atomic/idempotent action engine
│   ├── factory.py             # isolated runtime and four-domain tool factory
│   └── session.py             # agent-safe mutable case session
└── tools/
    ├── academic.py            # Academic & Student
    ├── policy.py              # Policy & Exception
    ├── course.py              # Course & Scheduling
    ├── actions.py             # Action & Transaction
    └── common.py              # shared envelopes and provenance helpers

tests/
├── test_stage4_models.py
├── test_stage4_runtime.py
└── test_execution_contracts.py
```

## 8. Completion gate and verification

The completed Stage 4 package establishes that:

- the 140 execution contracts cover the 140 Stage 3 scenarios exactly once;
- their source hashes and generated bytes are current and deterministic;
- every Stage 3 transaction script replays through a fresh Stage 4 runtime;
- all four read-tool domains return typed, grounded responses;
- agent-facing objects do not expose the scenario controller or oracle;
- separate sessions and the frozen repositories remain isolated;
- stale preflight failures roll back without consuming a hidden step;
- action idempotency, conflicting key reuse, and concurrent duplicates behave
  deterministically;
- approval gating and outcome visibility are enforced;
- transaction status returns a durable receipt; and
- final goal completion depends on current-state postconditions rather than a
  successful request or approval alone.

The focused Stage 4 suite currently passes 172 tests.

From the repository root:

```powershell
.venv\Scripts\python.exe scripts\build_execution_contracts.py --check
.venv\Scripts\python.exe -m pytest -q tests\test_stage4_models.py tests\test_execution_contracts.py tests\test_stage4_runtime.py
```

Run the entire project suite before committing:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

To rebuild the evaluator contracts after an intentional change to their frozen
inputs or mapping logic:

```powershell
.venv\Scripts\python.exe scripts\build_execution_contracts.py
.venv\Scripts\python.exe scripts\build_execution_contracts.py --check
```

## 9. Boundaries and limitations

Stage 4 does not provide:

- LangGraph state, nodes, conditional edges, or execution traces;
- planner, router, specialist, resolution-builder, or verifier LLM behavior;
- thread/checkpoint persistence or actual pending-approval pause/resume;
- working-, thread-, or long-term-memory implementations;
- a vector or embedding-based policy RAG system;
- a UI or operational deployment;
- authenticated NTU student, Degree Audit, registration, approval, or capacity
  integrations; or
- real administrative transactions.

The runtime is an in-memory deterministic simulator. Its write results are
controlled by evaluator scripts so the future agent can be tested against
repeatable failures and state changes. Public-data limitations recorded in the
Stage 2 and Stage 3 documents still apply.

## 10. Stage 5 handoff (completed)

Stage 5 now uses `Stage4Tools` as the graph's only environment boundary. It
adds typed LangGraph working state, the frozen nodes and conditional edges,
pre- and post-action verifier routing, loop-budget enforcement, checkpointed
thread memory, pending-approval pause/resume, clarification routing, separate
human/admin escalation, and graph traces checked against all 140 execution
contracts. See
[`stage_5_langgraph_control_plane.md`](stage_5_langgraph_control_plane.md).
