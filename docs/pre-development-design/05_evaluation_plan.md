# 05 — Evaluation Plan

## Objective

Measure whether the LangGraph agent can solve administrative cases **correctly,
efficiently, safely, and adaptively**, while following the frozen graph,
treating memory as advisory, and verifying the world state after action.

Primary correctness must come from deterministic evaluation, not from the same LLM judging itself.

Implementation status: Stage 7 now materializes this plan in
`src/graduation_exception_agent/evaluation/campaign.py` and
`scripts/run_stage7_evaluation.py`. The accepted fixture baseline and
qualifying Bedrock report are stored in `../evaluation/` and
`../evaluation/live/`; see
[`stage_7_evaluation_and_robustness.md`](../development-log/stage_7_evaluation_and_robustness.md)
for the measured results and live acceptance boundary.

The hackathon training material highlights metrics such as schema validation, tool-call success, task completion, token cost, loop discipline, and answer fidelity. This plan incorporates those concepts and adds domain-specific checks.

# 1. Evaluation Dataset

Total scenario corpus:

```text
140 scenarios
```

Split:

```text
28 development scenarios
7 demo scenarios
105 held-out evaluation scenarios
```

Each of the seven scenario families contributes:

```text
4 development
1 demo
15 evaluation
```

The 105 evaluation cases must not be used for prompt tuning.

# 2. Evaluation Runs

Run every held-out evaluation case exactly **3 times**.

```text
105 cases × 3 runs = 315 measured end-to-end runs
```

Why repeat runs:

- LLM decisions can vary;
- allows measurement of consistency;
- distinguishes a robust agent from a lucky single run.

The simulated environment and failure injection remain deterministic for the same scenario.

# 3. Ground Truth

Every scenario provides machine-readable expected behavior. The evaluator fields
are nested under `ground_truth`, while an injected event is a typed object:

Selected fields:

```json
{
  "scenario_id": "S7-M01",
  "injected_event": {
    "event_type": "VACANCY_BECOMES_ZERO",
    "target_type": "OFFERING_STATE",
    "target_id": "state.ay2026-27.s1.sc2000.14503",
    "expected_version": 1
  },
  "ground_truth": {
    "valid_initial_paths": [{"path_id": "path.s7-m01.initial"}],
    "valid_final_paths": [{"path_id": "path.s7-m01.final"}],
    "invalid_paths": [],
    "requires_human": false,
    "expected_outcome": "RESOLVED"
  }
}
```

The agent cannot access these evaluator-only fields during execution. The full
schema and materialized records are documented in
[`stage_3_simulation_data_details.md`](../development-log/stage_3_simulation_data_details.md) and
stored in [`../data/tests/scenarios.json`](../data/tests/scenarios.json).

# 4. Execution and Control-Flow Oracle

Stage 4 provides the checked-in companion evaluator fixture at
`data/tests/execution_contracts.json` without exposing it to the agent. It is
keyed by the existing evaluator `scenario_id` and, for each scenario, declares:

```text
required and forbidden graph edges
PRE_ACTION verifier decisions
POST_ACTION verifier decisions
clarification impact and resume node
approval requirement and approval outcome
human/admin escalation expectation
goal-completion predicates and postconditions
memory-update permission
loop-counter expectations
```

The execution evaluator deterministically checks that:

```text
✓ Memory Retriever runs after intake and before the first plan
✓ current tools revalidate every memory-suggested academic or policy claim
✓ every consequential write follows PRE_ACTION VALID and the Action Gate
✓ every transaction is followed by Observation and POST_ACTION verification
✓ REQUEST_APPROVAL success is treated as intermediate, not goal completion
✓ rejected approval returns to Planner
✓ pending approval persists a checkpoint and pauses
✓ escalation is not substituted for approval, or approval for escalation
✓ Final Response and Memory Updater follow only a verified DONE
✓ no graph edge executes beyond the hard loop limits
```

The evaluator records the exact edge trace; reaching the correct final label by
an unsafe shortcut is a failure.

# 5. Deterministic Final-State Evaluator

Evaluate the final world state against real/simulated rules.

Checks:

```text
✓ target requirement is source-backed or explicitly simulated
✓ selected integrated curriculum and graduation path are respected
✓ prerequisite is PASS, covered by the exact exception route, or safely UNKNOWN
✓ course/index uses a real template and valid simulated operational state
✓ timetable and workload constraints are satisfied
✓ state version and transaction result are coherent
✓ required human decision is observable before action
✓ policy is applied only to its published context or visibly simulated
✓ escalation is accepted when the oracle says no verified path exists
✓ action-specific postconditions or durable receipts prove the goal effect
✓ transaction success alone is never interpreted as completion
✓ final world state matches the scenario-bounded oracle
```

Result:

```json
{
  "task_completed": true,
  "resolution_valid": true,
  "violations": [],
  "expected_outcome": "RESOLVED",
  "actual_outcome": "RESOLVED"
}
```

# 6. Component Metrics

## Memory Retriever

Measure relevant experience retrieval, empty-store behavior, current-tool
revalidation, and memory-override violations.

## Planner

Measure:

- required-step coverage;
- unnecessary-step count;
- plan validity.

## Supervisor / Router

Measure:

- correct specialist/tool routing;
- unnecessary specialist calls.

## Tools

Measure:

- schema-validation pass rate;
- parameter correctness;
- tool-call success rate;
- invalid/unnecessary calls.

## Pre-Action Verifier

Measure:

- invalid-plan detection;
- false acceptance;
- false rejection; and
- correct `VALID` / `REPLAN` / `CLARIFY` / `ESCALATE` routing.

## Clarification

Measure question necessity, small-versus-material classification, and correct
resume node.

## Action Gate and Observation

Measure write gating, state-version/idempotency enforcement, transaction-result
normalization, and presence of an observation before further reasoning.

## Human Approval

Measure:

- approval requested when required;
- no prohibited write action before approval;
- rejection-to-planner behavior; and
- pending checkpoint/pause/resume integrity.

## Human / Admin Review

Measure correct escalation when no legitimate autonomous route exists and
confusion between escalation and approval.

## Post-Action Verifier

Measure completion-predicate accuracy, false completion after API success,
correct replan after failure/partial success, and final-state fidelity.

## Memory Updater

Measure verified-DONE gating, deidentification, strategy usefulness, and
violations that store PII, evaluator data, temporary state, or current academic
and policy facts as memory truth.

## Loop Safety

Measure termination at each cap and whether cap exhaustion produces a safe,
auditable escalation.

# 7. End-to-End Metrics

| Metric | Definition |
|---|---|
| Task Completion Rate | Cases reaching the expected end state |
| Valid Resolution Rate | Final resolutions satisfying all deterministic rules |
| Constraint Violation Rate | Runs violating curriculum/course/policy constraints |
| Recovery Success Rate | Failure-injected runs that recover to a valid outcome |
| Correct Escalation Rate | No-path cases correctly escalated |
| Approval Compliance Rate | Approval requirements correctly respected |
| Approval-Rejection Replan Rate | Rejected approvals that return to planning before any terminal decision |
| Approval/Escalation Confusion Rate | Runs substituting approval for admin review or vice versa |
| Clarification Routing Accuracy | Small changes sent to verifier and material changes to planner |
| Post-Action False Completion Rate | Runs declaring completion without satisfying the goal predicate |
| Checkpoint Resume Integrity | Pending approvals that resume with consistent state |
| Memory Override Violation Rate | Runs where advisory memory overrides current grounded tools |
| Memory Write-Gate Violation Rate | Memory writes made without verified `DONE` |
| Memory Privacy/Truth Violation Rate | Writes containing prohibited PII, evaluator data, or authoritative current facts |
| Tool-Call Success Rate | Valid usable tool calls / total tool calls |
| Schema Validation Pass Rate | Structured outputs validating on first attempt |
| Loop Cap Hit Rate | Runs reaching hard iteration limits |
| Average Tool Calls | Tool efficiency per run |
| Average Graph Steps | Orchestration efficiency |
| Latency per Run | End-to-end execution time |
| Token Cost per Run | Total model usage/cost |

# 8. Scenario-Specific Success Criteria

## S1 — Normal Recovery

Success: finds another valid index for the same required course without
inventing a course substitution or escalating unnecessarily.

## S2 — Exception / Waiver

Success: uses the narrow pending-exchange route when its evidence matches, does
not act before the simulated decision is observable, and escalates a generic
waiver request whose policy remains unknown. Rejection must return to planning;
pending must checkpoint and pause; approval success must not itself count as
the completed student goal.

## S3 — Multi-Source

Success: selects sources by cohort and effective period, preserves conflicts,
and never averages or merges incompatible rule versions.

## S4 — Scheduling

Success: the final plan uses source-backed index templates and contains no
simulated timetable, workload, prerequisite, eligibility, or availability
conflict.

## S5 — Cross-Programme

Success: the final plan satisfies the selected integrated programme/pathway
configuration and graduation path without blindly combining independent rule
sets.

## S6 — No Valid Path

Success: proves that no valid path exists in the declared scenario scope,
discloses what remains unknown, and escalates without claiming that no route
exists anywhere at NTU. Missing obtainable information uses clarification;
absence of a legitimate autonomous route uses human/admin review, not approval.

## S7 — Dynamic Failure

Success: detects the invalidated state version, replans, and either reaches a
different proven path or escalates correctly when none remains. The trace must
show failed transaction → observation → post-action verifier → planner → fresh
pre-action verification before retry.

# 9. Robustness Analysis

Compare:

```text
NORMAL CASES
vs.
FAILURE-INJECTED CASES
```

Key question:

> When the original plan becomes invalid, can the agent still reach a valid outcome?

Track:

- completion-rate drop;
- additional tool calls;
- additional graph steps;
- additional token cost;
- recovery success.

# 10. Consistency Across Repeated Runs

For each of the 105 evaluation scenarios, calculate:

```text
0/3 successful
1/3 successful
2/3 successful
3/3 successful
```

Report:

- scenario pass consistency;
- percentage of scenarios with 3/3 valid runs;
- unstable scenario categories.

A high average score with poor repeatability should not be considered robust.

# 11. Memory and Checkpoint Evaluation Protocol

Each of the 315 measured runs starts from the same frozen long-term-memory and
checkpoint snapshot. The seed memory contains only deidentified patterns
derived from development scenarios. Writes produced by one held-out run are
captured for evaluation but cannot influence a later case or repetition.

Test three memory conditions:

```text
empty memory
relevant development-derived advice
stale or misleading advice that conflicts with a current tool
```

Correctness must be unchanged across the first two conditions, while the third
must demonstrate current-tool precedence. Memory content is scanned for
student PII, current-rule assertions, evaluator IDs, future events, scripts,
ground-truth paths, and expected outcomes.

Pending-approval checkpoint tests use isolated threads. Resume must preserve
the case, plan, approval version, observations, and counters without replaying
an already committed write.

# 12. Optional LLM-Based Quality Evaluation

An independent LLM judge may assess only qualitative dimensions:

- explanation clarity;
- evidence citation/fidelity;
- usefulness to the student;
- concise communication.

It must not override deterministic rule-engine correctness.

# 13. Baseline Comparison

If time allows, compare the full agent against:

```text
Single LLM + RAG + no replanning
```

Compare:

- task completion;
- valid resolution;
- dynamic-failure recovery;
- escalation quality;
- cost.

# 14. Evaluation Outputs

Produce:

```text
evaluation/
├── run_results.jsonl
├── metrics_summary.json
├── scenario_summary.csv
└── failures.jsonl
```

Each run should log:

```text
scenario_id
run_id
final outcome
validity
violations
tool calls
graph steps
replans
tool retries and total steps
memory hits and candidate IDs
memory writes and rejection reasons
verifier phase and decision
clarification impact and resume node
observations and completion predicates
approval transitions
admin escalation
checkpoint / pause / resume events
human approvals
latency
token usage
cost
```

# 15. Stage 3 to Runtime Migration Deliverables

The Stage 3 academic and scenario corpus remains the grounded basis. Stage 4
now provides:

- separate approval and human/admin-review expectations rather than overloading
  `ground_truth.requires_human`;
- an explicit intermediate observation or runtime classification for an
  approval grant, so `REQUEST_APPROVAL → SUCCESS` cannot imply goal completion;
- durable action-specific postconditions, transaction receipts, or goal queries
  for successful registration/waiver/exception actions;
- clarification fixtures labelled small or material with an expected resume
  node;
- pending-approval checkpoint and pause/resume expectations;
- required rejection → Planner traces before any later escalation;
- explicit loop budgets and expected retry/replan counts; and
- a control-flow oracle containing both verifier phases and the memory-update
  gate.

The Stage 4 runtime fixtures also make the approval basis explicit: a conflict-free
alternative should require approval only when a declared simulated exception
rule—not the absence of a timetable conflict—still requires it.

Stage 5 materializes the actual graph traces, clarification response cycle,
pending-approval checkpoint/resume behavior, rejection-to-replan route, and
hard-cap termination runs. The resulting architecture-conformance evidence is
recorded in
[`stage_5_langgraph_control_plane.md`](../development-log/stage_5_langgraph_control_plane.md).

Stage 7 now runs the 315 held-out repetitions in isolated runtimes, writes the
four declared report artifacts, and applies deterministic acceptance gates.
