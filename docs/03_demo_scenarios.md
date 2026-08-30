# 03 — Demo Scenarios

## Purpose

Use seven scenario families to demonstrate different agentic capabilities. Each family has development, demo, and hidden evaluation cases.

## Scenario 1 — Normal Recovery Path

**Example:** Final-year CS student is missing a graduation requirement; the preferred course is unavailable/full.

Agent should:

```text
audit requirement
→ search alternatives
→ check constraints
→ choose valid path
→ verify
→ act
```

Tests planning, degree audit, course search, and constraint checking.

## Scenario 2 — Prerequisite / Exception Path

**Example:** CE student needs a course but does not satisfy a prerequisite.

Agent should:

```text
detect prerequisite issue
→ retrieve policy
→ determine exception eligibility
→ request approval if required
→ resume after decision
```

Tests policy reasoning, evidence gathering, human-in-the-loop, and checkpoint/resume.

## Scenario 3 — Multi-Source Programme Reasoning

**Example:** DSAI student requires reasoning across multiple curriculum/rule sources.

Agent should:

```text
assemble relevant rules
→ perform degree audit
→ reconcile requirements
→ build valid plan
```

Tests multi-source retrieval, orchestration, and evidence consistency.

## Scenario 4 — Constraint-Heavy Scheduling

**Example:** AISC student has several outstanding requirements, but candidate courses create timetable/workload conflicts.

Agent should:

```text
generate candidate schedules
→ detect conflicts
→ reject invalid combinations
→ find a feasible plan
```

Tests multi-constraint planning, timetable reasoning, and workload reasoning.

## Scenario 5 — Cross-Programme Complexity

**Example:** Synthetic second-major/double-degree case with interacting requirements.

Agent should:

```text
load both rule sets
→ identify shared/non-shared requirements
→ evaluate alternatives
→ produce a plan valid for both
```

Tests complex degree audit, cross-rule reasoning, and plan verification.

## Scenario 6 — No Valid Path

Every legitimate candidate fails.

Correct behavior:

```text
investigate valid alternatives
→ verify none work
→ do not invent an exception
→ explain blockers
→ escalate safely
```

Tests refusal to hallucinate, correct escalation, and evidence-based explanation.

## Scenario 7 — Dynamic Failure / Main Live Demo

The agent initially finds a valid course:

```text
capacity = 1
```

Immediately before execution, the simulator injects:

```text
capacity = 0
```

Transaction returns:

```text
MODULE_FULL
```

Expected behavior:

```text
observe failure
→ update state
→ invalidate old plan
→ replan
→ find another valid route
→ verify
→ continue
```

Tests observation, failure recovery, replanning, and state consistency.

This should be the main live demonstration because it visibly distinguishes an agent from a static workflow.

# Scenario Allocation

Exactly **140 total scenarios**:

```text
7 families × 20 cases per family = 140
```

Per family:

```text
4 development cases
1 polished demo case
15 evaluation cases
```

Overall:

```text
Development: 28
Demo:         7
Evaluation: 105
Total:       140
```

The 105 evaluation cases should be kept separate from prompt tuning.
