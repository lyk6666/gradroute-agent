# 04 — Simulation Design

## Goal

Create a medium-scale, reproducible simulated NTU/CCDS administrative environment while keeping **academic rules and published course data grounded in real sources**.

The simulator does not invent the academic world. It creates fictional students and controlled administrative events inside that world.

# 1. Exact Scale

## Real Academic Scope

Use real data for:

- 4 primary CCDS undergraduate programmes;
- 4 selected cohorts / academic-year rule sets per programme;
- official curriculum structures;
- official course metadata;
- prerequisites/exclusions;
- official semester offerings and timetable/index data where accessible;
- public registration/exception/approval guidance.

Real source size is determined by what is officially published and therefore is **not artificially capped**.

## Simulated Population

Generate exactly:

```text
240 synthetic students
```

Distribution:

```text
60 Computer Science
60 Computer Engineering
60 Data Science & Artificial Intelligence
60 Artificial Intelligence & Society
```

Each programme should contain:

```text
15 students × 4 study/cohort profiles = 60
```

Student histories should vary in:

- completed courses;
- grades;
- earned AUs;
- outstanding requirements;
- exemptions;
- current workload.

## Derived Academic State

Generate exactly:

```text
240 degree audits
240 current registration states
```

Degree audits must be calculated from:

```text
real curriculum + synthetic student history
```

Registration states must be internally consistent with real course metadata, real semester offerings, and synthetic student history.

## Administrative Cases

Generate exactly:

```text
140 exception/problem cases
```

Allocation:

```text
20 × Scenario 1
20 × Scenario 2
20 × Scenario 3
20 × Scenario 4
20 × Scenario 5
20 × Scenario 6
20 × Scenario 7
```

Each case has exactly one corresponding scenario definition and transaction script.

## Human Approval Data

Generate exactly:

```text
60 approval records
```

Use:

```text
24 approved
24 rejected
12 pending
```

Only cases that logically require approval should reference these records.

## Transaction Scripts

Generate exactly:

```text
140 transaction-result scripts
```

A script may contain more than one sequential outcome, for example:

```text
1. registration attempt → MODULE_FULL
2. alternative attempt → SUCCESS
```

This enables deterministic recovery tests.

# 2. Rule Categories

## Real / Grounded Rules

Use real sourced information for:

### Curriculum rules
- required/core courses;
- AU/category requirements;
- programme requirements;
- graduation completeness.

### Course rules
- prerequisites;
- exclusions;
- programme/category applicability;
- semester offering.

### Timetable rules
- real class/index times where available;
- conflict detection performed deterministically.

### Registration / exception rules
Use official public guidance when available.

If a needed hackathon rule is unavailable, create an explicitly labeled prototype rule:

```text
SIMULATED POLICY FOR PROTOTYPE
```

Never silently represent simulated policy as NTU policy.

# 3. Controlled Dynamic Events

Implement exactly **8 event types**:

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

Events should be deterministic per scenario.

They are used to force replanning, clarification, retry, human approval, and safe escalation.

# 4. Generation Order

Never generate JSON files independently.

Use this dependency pipeline:

```text
REAL DATA
curricula + courses + offerings + policies
        ↓
240 synthetic students
        ↓
240 deterministic degree audits
        ↓
240 registration states
        ↓
140 administrative cases
        ↓
60 approval records
        ↓
140 transaction scripts
        ↓
140 scenario definitions
```

This ensures consistency.

# 5. Generation Strategy

Use seeded deterministic generation.

Each generated entity should include:

```text
generator_version
seed
source_rule_ids
```

Example:

```json
{
  "student_id": "SIM-CS-042",
  "generator_version": "1.0",
  "seed": 42017,
  "source_rule_ids": ["ccds_cs_curriculum_ay2026"]
}
```

A failed evaluation case must be exactly reproducible.

# 6. Scenario Construction Rules

Every scenario must guarantee that the expected result is knowable before the agent runs.

Pattern:

```text
Select student
→ compute outstanding requirement
→ enumerate valid candidate paths with rule engine
→ manipulate operational state if needed
→ define expected valid/invalid paths
→ define event injection
→ save scenario
```

Do not generate a case until the deterministic rule engine can prove its expected outcome.

# 7. Simulator Interface

Expose environment state only through tools.

Recommended interface:

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

The LangGraph agent must not directly read hidden scenario ground truth.

# 8. Hidden Ground Truth

The simulator may internally know:

- valid paths;
- invalid paths;
- future injected events;
- expected final outcome.

The agent must not.

This separation prevents evaluation leakage.
