# CCDS Agentic AI Implementation Documents

This package contains the current implementation specification for the NTU CCDS-grounded administrative exception-resolution prototype.

Current status: Stage 7 implements the frozen 315-run held-out evaluation over
the Stage 5/6 system. Both the deterministic fixture baseline and the
qualifying Amazon Bedrock campaign pass 315/315 with 105/105 scenarios at 3/3
consistency. The live campaign also validates all 720 structured reasoning
calls without fallback.

Foundation specifications:

- [`01_data_design.md`](01_data_design.md) — real vs simulated data contracts and structure
- [`02_solution_architecture.md`](02_solution_architecture.md) — frozen LangGraph topology, memory semantics, tool domains, safety edges, and staged migration
- [`03_demo_scenarios.md`](03_demo_scenarios.md) — seven materialized scenario families plus their graph-trace expectations
- [`04_simulation_design.md`](04_simulation_design.md) — implemented medium-scale simulation design
- [`05_evaluation_plan.md`](05_evaluation_plan.md) — planned 315-run final-state, control-flow, memory, and robustness evaluation

Stage records:

- [`stage_1_contract_decisions.md`](stage_1_contract_decisions.md) — explicit resolutions for schema ambiguities
- [`stage_2_grounding_conventions.md`](stage_2_grounding_conventions.md) — grounding conventions plus the detailed
  real-data inventory, sources, coverage, limitations, and rebuild instructions
- [`stage_3_simulation_data_details.md`](stage_3_simulation_data_details.md) — deterministic simulation package,
  exact populations, temporal mapping, provenance boundaries, replay rules,
  and readiness checks
- [`stage_4_runtime_and_tools.md`](stage_4_runtime_and_tools.md) — typed four-domain tools, isolated runtime,
  atomic transaction guarantees, execution contracts, and the boundary now
  consumed by Stage 5
- [`stage_5_langgraph_control_plane.md`](stage_5_langgraph_control_plane.md) — typed state, exact graph topology,
  checkpointed interrupts, loop controls, advisory memory, evaluator isolation,
  limitations, and the Stage 6 handoff
- [`stage_6_grounded_llm_reasoning.md`](stage_6_grounded_llm_reasoning.md) —
  Bedrock Converse adapter, deterministic safety dominance, prompt projection,
  checkpoint audit, advisory-memory ranking, and live-test boundary
- [`stage_7_evaluation_and_robustness.md`](stage_7_evaluation_and_robustness.md)
  — isolated 315-run campaign, deterministic oracles, report artifacts,
  acceptance thresholds, fixture results, and live robustness boundary

Stage-specific documents use `stage_<number>_<topic>.md`. They do not receive
an additional sequence prefix such as `06_`, `07_`, or `08_`; the same rule
applies to later stages.

Recommended implementation order:

```text
Stage 3 Models + Data + Validation (complete)
    ↓
Architecture Alignment + Freeze (complete)
    ↓
Stage 4 — Deterministic Tools + Transaction Runtime (complete)
    ↓
Stage 5 — LangGraph Control Plane + Checkpoint/Memory Interfaces (complete)
    ↓
Stage 6 — Grounded LLM Reasoning + Ranked Advisory Memory (complete)
    ↓
Stage 7 — Scenario Trace Evaluation + Robustness Hardening (complete)
    ↓
Stage 8 — Demo/UI Delivery + Operational Hardening
```

Key principle:

> Real NTU/CCDS rules + synthetic student/operational state + controlled failures → agent execution → deterministic evaluation.

The architecture document's conditional-edge table is normative. Long-term
memory stores verified experience only and can never override current academic,
course, availability, or policy tools.
