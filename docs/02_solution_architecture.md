# 02 — Solution Architecture

## Objective

Build a LangGraph-based agent that can:

> understand a student's administrative problem → plan → investigate → propose a resolution → verify it → act safely → observe the result → replan when necessary.

The architecture is intentionally **controlled**, not an unrestricted multi-agent conversation.

## High-Level Flow

```text
Student / Case
      ↓
Intake + Context
      ↓
Planner
      ↓
Supervisor / Router
  ↙       ↓       ↘
Degree   Policy   Course
Audit    Agent    Agent
  ↘       ↓       ↙
 Resolution Builder
        ↓
     Verifier
  ↙       ↓       ↘
Clarify  Replan   Valid
   │       │        ↓
Student    └────→ Planner
   ↓             Action Gate
Update State       /    \
   │             Auto   Human Approval
   └→ Planner             /      \
                     Approved   Rejected
                        ↓          │
                   Transaction     │
                        ↓          │
                   Observation     │
                        ↓          │
                     Verifier ←────┘
                     /      \
                 Complete   Replan
                    ↓         ↓
              Final Response Planner
```

Core loop:

```text
PLAN → ACT → OBSERVE → VERIFY → ADAPT → REPLAN
```

## Main Components

### Intake + Context

Creates the initial case state:

- student/profile reference;
- programme and cohort;
- request/goal;
- current registration context;
- relevant academic status.

### Planner

Creates a mutable task plan.

Example:

```text
1. determine the missing graduation requirement
2. find feasible courses
3. check prerequisites
4. check timetable/availability
5. inspect exception policy if needed
6. propose the safest valid path
```

### Supervisor / Router

Selects only the specialist(s) required for the current step.

It should not always call every specialist.

### Degree Audit Agent

Answers questions such as:

- what remains outstanding?
- does a candidate satisfy the curriculum?
- is the student on a valid graduation path?

Primary tools:

- student record;
- curriculum;
- degree-audit engine.

### Policy Agent

Determines:

- which policy applies;
- whether an exception/waiver path exists;
- what evidence or approval is required.

Primary tools:

- policy retrieval/RAG;
- approval rules.

### Course Agent

Checks:

- candidate courses;
- prerequisites;
- semester offering;
- timetable;
- availability/capacity snapshot;
- alternatives.

### Resolution Builder

Combines specialist outputs into ranked candidate resolutions.

Each candidate should carry evidence and constraints.

### Verifier

Independent decision point.

Checks:

- curriculum validity;
- prerequisite validity;
- offering/timetable constraints;
- policy compliance;
- approvals;
- goal completion.

Outputs:

```text
VALID
REPLAN
CLARIFY
ESCALATE
```

After a transaction, the verifier also checks whether the user's actual goal is complete.

### Clarification

Used when necessary information is missing.

Prototype rule:

```text
Clarify → Student Response → Update State → Planner
```

### Action Gate

Separates reasoning from execution.

```text
read-only / low-risk action → automatic
write / high-impact action → human approval when required
```

### Human Approval

Supports:

- approved → continue;
- rejected → update state and replan;
- pending → checkpoint and pause.

### Transaction

Simulated actions such as:

- submit registration;
- submit waiver;
- submit exception;
- request approval.

### Observation

Normalizes action/tool outcomes into state.

Example:

```text
MODULE_FULL
APPROVAL_REJECTED
TRANSACTION_SUCCESS
STALE_STATE
TEMPORARY_FAILURE
```

Failures return to planning rather than automatically ending the case.

# Memory Architecture

## Working Memory — LangGraph State

Shared mutable state for one run:

```text
student
request
degree audit
current plan
candidate courses
candidate resolutions
relevant policies
tool results
approval status
transaction status
observations
errors
loop counters
final resolution
```

All core nodes read/write this state.

## Thread Memory — Checkpointer

Persists execution across turns:

- conversation;
- clarifications;
- checkpoints;
- human-approval pause/resume;
- previous attempts.

## Long-Term Memory — Optional

Store only non-sensitive reusable patterns:

- case type;
- successful strategy;
- recurring failure;
- useful policy path.

Do not depend on long-term memory for core correctness.

# Tool Layer

Recommended tools:

```text
get_student_record()
run_degree_audit()
search_courses()
check_prerequisite()
check_timetable()
check_availability()
search_policy()
check_exception_eligibility()
request_approval()
submit_registration()
submit_exception()
```

Design principle:

```text
Agent = decides WHAT to do
Tool = interacts with the environment
Verifier = decides WHETHER the result is valid
```

# Implementation Guardrails

- typed graph state;
- structured tool inputs/outputs;
- compact tool responses;
- hard loop limits;
- deterministic rule checks for final validity;
- human approval for consequential write actions;
- explicit source provenance;
- checkpoint support for interrupted runs.

Suggested limits:

```text
MAX_REPLANS = 4
MAX_TOOL_RETRIES = 2
MAX_TOTAL_STEPS = 20
```
