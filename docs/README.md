# CCDS Agentic AI Implementation Documents

This package contains the current implementation specification for the NTU CCDS-grounded administrative exception-resolution prototype.

Current status: Stage 14 is complete for the local hackathon-prototype boundary.
Its UI is backed by the Stage 7 frozen 315-run held-out evaluation over the
Stage 5/6 system. Both the deterministic fixture baseline and the
qualifying Amazon Bedrock campaign pass 315/315 with 105/105 scenarios at 3/3
consistency. The live campaign also validates all 720 structured reasoning
calls without fallback. Stage 8 UI-1 established the shared frontend shell,
three product routes, visual tokens, and reusable interface primitives. UI-2
now adds the approved five-region Main workspace, complete selectable graph,
manual/scenario intake composition, processed tool and memory inspector,
human-checkpoint previews, timeline, and final-response preview. UI-3 connects
that workspace to the live runtime, and UI-4 adds the comprehensive, read-only
grounded data explorer. UI-5 now provides the accepted fixture/Bedrock
evaluation dashboard. UI-6 completes accessibility, recovery, readiness,
performance and local delivery hardening for the Stage 8 research prototype.
Stage 9 replaces the remaining template-only Main-workspace details with
processed runtime input, output and state records; expands working, thread and
long-term memory; produces a detailed case-specific final response; and connects
validated Manual Input to the same graph used by scenario execution.
Stage 10 adds evidence-grounded Bedrock narration for every executed node and
for working, thread-memory, long-term-memory and final-response content. The
natural-language layer is generated from the current run rather than from UI
templates. Working State now reads as a concise case briefing, Thread Memory as
a chronological case history, and Long-Term Memory as clearly advisory past
experience; exact recorded facts remain inspectable and continue to control
every decision.
Stage 11 removes repeated scenario and evaluator wording at the data source,
adds demo-only expected-response previews, keeps evaluation answers hidden, and
aligns plans, node details, actions, memories, and final responses with each
case's actual course, constraints, evidence, approval, and observed outcome.
Stage 12 replaces repeated node templates with concise case-specific findings,
removes tool names from the ordinary presentation, adds reasoning-led final
responses, simplifies working/thread/long-term memory, and makes approval-bound
interactive runs pause for a real simulated human decision. Clarification and
administrative handoff now explain why human involvement is required.
Stage 13 adds a distinct communication brief for every graph role and grounds the
visible prose in the actual student, course, prerequisite, class, timetable,
workload, policy, document, approval, transaction, and replanning evidence. Human
prompts now present a decision-ready reason with explicit public-versus-simulated
policy provenance. The right panel combines progress and material history into a
single case overview. All seven demo workflows passed a real Bedrock narration
review; unsuitable model wording was rejected in favour of the case-specific safe
fallback.
Stage 14 preserves every visit to a repeated workflow node instead of replacing
the earlier record. Graph nodes show repeat counts, timeline events open their exact
visit, the in-canvas inspector separates initial checks from replans and rechecks,
and historical human checkpoints remain visible but read-only. The optional LLM is
also given the preceding visit summary so later explanations can state what changed.

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
- [`stage_8_ui_development.md`](stage_8_ui_development.md) — living UI plan,
  page and frontend boundaries, implementation checkpoints, progress log, and
  acceptance record
- [`stage_9_runtime_transparency_and_manual_intake.md`](stage_9_runtime_transparency_and_manual_intake.md)
  — adaptive node and action evidence, expanded runtime memory, detailed final
  responses, connected manual cases, validation and modification history
- [`stage_10_natural_language_runtime_narration.md`](stage_10_natural_language_runtime_narration.md)
  — case-specific Bedrock explanations for node input, output, state, action,
  working state, memory and final response, plus grounding and outage controls
- [`stage_11_scenario_and_presentation_refinement.md`](stage_11_scenario_and_presentation_refinement.md)
  — varied scenario inputs and evaluator expectations, concise case-specific
  runtime presentation, answer-key isolation, and modification history
- [`stage_12_human_centered_case_explanations.md`](stage_12_human_centered_case_explanations.md)
  — concise node monitoring, reasoning-led outcomes, simplified memory, and
  interactive clarification, approval, and administrative-review boundaries
- [`stage_13_evidence_rich_case_narration.md`](stage_13_evidence_rich_case_narration.md)
  — node-specific narration briefs, evidence-rich human decisions, unified case
  overview, model-output quality guard, and seven-demo live review
- [`stage_14_node_visit_history.md`](stage_14_node_visit_history.md)
  — ordered node-attempt history, exact timeline-to-visit inspection, repeat-count
  indicators, read-only historical decisions, and compatibility safeguards

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
Stage 8 — Demo/UI Delivery + Operational Hardening (complete)
    ↓
Stage 9 — Runtime Transparency + Manual Intake (complete)
    ↓
Stage 10 — Grounded Natural-Language Runtime Narration (complete)
    ↓
Stage 11 — Scenario + Evaluation + Presentation Refinement (complete)
    ↓
Stage 12 — Human-Centred Case Explanations + Review (complete)
    ↓
Stage 13 — Evidence-Rich Case Narration + Live Demo Review (complete)
    ↓
Stage 14 — Preserved Node Visit History + Exact Timeline Inspection (complete for local hackathon prototype)
```

Key principle:

> Real NTU/CCDS rules + synthetic student/operational state + controlled failures → agent execution → deterministic evaluation.

The architecture document's conditional-edge table is normative. Long-term
memory stores verified experience only and can never override current academic,
course, availability, or policy tools.
