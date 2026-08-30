# 05 — Evaluation Plan

## Objective

Measure whether the LangGraph agent can solve administrative cases **correctly, efficiently, safely, and adaptively**.

Primary correctness must come from deterministic evaluation, not from the same LLM judging itself.

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

Every scenario must provide machine-readable expected behavior.

Minimum fields:

```json
{
  "scenario_id": "S7-E08",
  "valid_initial_paths": ["PATH-A"],
  "valid_final_paths": ["PATH-C"],
  "invalid_paths": ["PATH-B"],
  "requires_human": false,
  "injected_event": "VACANCY_BECOMES_ZERO",
  "expected_outcome": "RESOLVED"
}
```

The agent cannot access these fields during execution.

# 4. Deterministic Final-State Evaluator

Evaluate the final world state against real/simulated rules.

Checks:

```text
✓ correct graduation requirement addressed
✓ curriculum/category requirement satisfied
✓ prerequisite valid or approved exception exists
✓ course is actually offered
✓ timetable constraints satisfied
✓ availability/transaction state valid
✓ required approval obtained
✓ policy/action path valid
✓ final transaction state consistent
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

# 5. Component Metrics

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

## Verifier

Measure:

- invalid-plan detection;
- false acceptance;
- false rejection.

## Human Approval

Measure:

- approval requested when required;
- no prohibited write action before approval;
- correct handling of rejection/pending states.

# 6. End-to-End Metrics

| Metric | Definition |
|---|---|
| Task Completion Rate | Cases reaching the expected end state |
| Valid Resolution Rate | Final resolutions satisfying all deterministic rules |
| Constraint Violation Rate | Runs violating curriculum/course/policy constraints |
| Recovery Success Rate | Failure-injected runs that recover to a valid outcome |
| Correct Escalation Rate | No-path cases correctly escalated |
| Approval Compliance Rate | Approval requirements correctly respected |
| Tool-Call Success Rate | Valid usable tool calls / total tool calls |
| Schema Validation Pass Rate | Structured outputs validating on first attempt |
| Loop Cap Hit Rate | Runs reaching hard iteration limits |
| Average Tool Calls | Tool efficiency per run |
| Average Graph Steps | Orchestration efficiency |
| Latency per Run | End-to-end execution time |
| Token Cost per Run | Total model usage/cost |

# 7. Scenario-Specific Success Criteria

## S1 — Normal Recovery

Success: finds a valid alternative without unnecessary escalation.

## S2 — Exception / Waiver

Success: uses the correct policy path, requests approval when required, and does not act before approval.

## S3 — Multi-Source

Success: uses all required rule sources and produces one consistent valid conclusion.

## S4 — Scheduling

Success: final plan contains no timetable/workload conflicts.

## S5 — Cross-Programme

Success: final plan satisfies both relevant rule sets.

## S6 — No Valid Path

Success: does not hallucinate a solution and escalates with correct blockers.

## S7 — Dynamic Failure

Success: detects the invalidated plan, updates state, replans, and reaches another valid outcome when one exists.

# 8. Robustness Analysis

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

# 9. Consistency Across Repeated Runs

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

# 10. Optional LLM-Based Quality Evaluation

An independent LLM judge may assess only qualitative dimensions:

- explanation clarity;
- evidence citation/fidelity;
- usefulness to the student;
- concise communication.

It must not override deterministic rule-engine correctness.

# 11. Baseline Comparison

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

# 12. Evaluation Outputs

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
human approvals
latency
token usage
cost
```
