# CCDS Agentic AI Implementation Documents

This package contains the current implementation specification for the NTU CCDS-grounded administrative exception-resolution prototype.

Files:

1. `01_data_design.md` — real vs simulated data contracts and structure
2. `02_solution_architecture.md` — LangGraph architecture, memory, tools, loops
3. `03_demo_scenarios.md` — seven scenario families and dataset split
4. `04_simulation_design.md` — exact medium-scale simulation design
5. `05_evaluation_plan.md` — 315-run evaluation methodology and metrics

Recommended implementation order:

```text
01 Data Design
    ↓
04 Simulation Design
    ↓
Deterministic Rule Engine + Tools
    ↓
02 Solution Architecture
    ↓
03 Demo Scenarios
    ↓
05 Evaluation Plan
```

Key principle:

> Real NTU/CCDS rules + synthetic student/operational state + controlled failures → agent execution → deterministic evaluation.
