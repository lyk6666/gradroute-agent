# Stage 8 — UI Development

## 1. Purpose and status

Stage 8 turns the completed Stage 4–7 runtime and evaluation evidence into a
clear demonstration interface. The design is based on `main_page_reference.png`
and `UI_IMPLEMENTATION_GUIDE.md`, while the repository's frozen graph, safety
contracts, provenance boundaries, and evaluator isolation remain normative.

Current status: **UI-2 complete; UI-3 awaiting approval.**

The UI is a Team AIGO research prototype grounded in public NTU CCDS sources.
It must not be represented as an official NTU service.

## 2. Product pages

| Page | Purpose | Main surfaces |
| --- | --- | --- |
| Main | Execute and understand one exception case | Case rail, frozen agent graph, node/case inspector, timeline, human checkpoints, final response |
| Data | Inspect the data used by the agent | Domain navigation, read-only table, search/filters, relationships, provenance and developer JSON |
| Evaluation | Inspect Stage 7 quality evidence | Overview metrics, scenario-family performance, run explorer, run inspector and failure diagnostics |

Ground truth is permitted only on Evaluation/Developer surfaces. The Main page
receives agent-observable case context and never imports evaluator contracts.

## 3. Visual and interaction contract

The shared visual system uses:

- a dark charcoal/navy top bar;
- a light-grey application background;
- white rounded panels with cool-grey borders and restrained shadows;
- blue primary actions;
- green completed, amber waiting, red failed, purple replan/memory, and grey
  pending/skipped statuses;
- consistent `REAL NTU/CCDS`, `SIMULATED`, `DERIVED`, and
  `SCENARIO-INJECTED` provenance badges; and
- desktop-first layouts with collapsing rails/drawers on narrower screens.

Status always includes a text label. Keyboard focus, semantic controls,
reduced-motion preferences, readable contrast, and non-colour status cues are
part of the base contract rather than a final cosmetic pass.

## 4. Frontend boundary

The frontend lives in `frontend/` and uses React, TypeScript, Vinext, Vite, and
the Sites Vite integration. UI code must consume stable application API and
event schemas, not LangGraph-internal Python objects.

The planned live boundary is:

```text
Python runtime / evaluator
        ↓ stable API schemas
case, scenario, data and evaluation endpoints
        ↓ SSE run-event stream
frontend server state + isolated live-run state + local view state
```

Server state, live graph state, and local UI state remain separate. A displayed
approval string cannot open the action gate; authoritative status must still be
read through the backend runtime. The same rule applies to clarification resume,
checkpoint identity, state versions, transaction receipts, and verified-only
memory writes.

## 5. Delivery plan and progress

### UI-1 — Foundation — complete

- scaffolded the frontend project under `frontend/`;
- established metadata, shared application shell, top navigation, footer and
  responsive page container;
- added Main, Data, and Evaluation routes;
- implemented reusable card, button, status, provenance and inspector
  primitives;
- encoded visual tokens and accessibility foundations;
- added a bounded product-specific Main-page preview without pretending that
  graph or backend integration is already available;
- added build, lint and type-check verification; and
- updated the generated dependency set to patched compatible releases, with
  the final production and development dependency audit reporting zero known
  vulnerabilities.

### UI-2 — Main Page static workspace — complete

- replaced the foundation placeholder with a full-screen five-region workspace:
  input, graph, processed inspector, timeline, and final response;
- added Scenario and Manual Input modes, with grounded CCDS programme choices,
  required academic-snapshot fields, Demo/Evaluation scenario selection, and
  Normal or Step-by-step run selection;
- represented the complete frozen control plane with distinguishable current,
  selected, completed, skipped, waiting, and unvisited states;
- kept the Student/Case marker outside the control-step count and represented
  Pre-action Verifier and Post-action Verifier as separate visual nodes;
- represented clarification, bounded replanning, approval rejection, pending
  approval checkpoint/resume, no-safe-route escalation, transaction-domain
  handoff, observation, verified completion, and verified-only memory update;
- added selectable node cards with purpose, status, processed input/output/state
  summaries and related-tool summaries;
- added an in-canvas human interaction area for clarification, simulated
  approval and administrative handoff, with backend-dependent controls disabled;
- added a processed-only inspector for working state, tools, thread memory,
  long-term advisory memory and provenance; no raw JSON or evaluator ground truth
  is exposed on Main;
- added a selectable horizontal execution timeline and a truthful pending final
  response preview; and
- implemented desktop five-region sizing plus stacked tablet/mobile layouts.

### UI-3 — Main Page runtime integration — pending

- stable backend facade and SSE run events;
- live node/edge and timeline updates;
- selected-node tool/state/memory inspection;
- clarification and approval checkpoint/resume dialogs;
- final response, copy and export behavior.

### UI-4 — Data explorer — pending

- academic, operational and case-operation domains;
- search, filters, sorting and pagination;
- relationships, record details and provenance inspection;
- developer-only JSON view.

### UI-5 — Evaluation evidence — pending

- Stage 7 overview metrics and scenario-family performance;
- 315-run search/filter table and run inspector;
- consistency summary, failure categories and zero-failure state;
- evaluator-only visibility controls.

### UI-6 — Hardening and delivery — pending

- loading, error and empty states;
- responsive and keyboard/accessibility audit;
- reduced motion and performance checks;
- component, integration and end-to-end smoke tests;
- Demo/Developer mode review; and
- production packaging and final delivery.

## 6. Progress log

### 1 September 2026 — UI-1

The frontend foundation was created from scratch. The shared shell follows the
approved visual reference, navigation resolves all three product routes, and
the first Main route communicates the real product and safety boundaries. No
runtime API, graph interaction, approval action, or evaluator-ground-truth
exposure was added in this stage.

### 1 September 2026 — UI-2

The Main route now implements the approved static workspace and the corrected
`Intake Guard (3)` topology. It supports local UI selection and inspection but
does not claim that a case has executed. Manual cases, run controls,
clarification, approval decisions, checkpoint resume, transactions, and final
response export remain disabled until UI-3 connects the stable backend facade
and event stream. The Main surface shows processed summaries only and continues
to hide evaluator-only ground truth. A subsequent UI-2 density refinement
removed the five decorative panel title/subtitle bands, retained only compact
operational context such as the graph legend, and enlarged content typography
across intake, graph, inspector, timeline, and response surfaces.

## 7. Acceptance record

- [x] Shared dark-header/light-workspace shell
- [x] Main, Data and Evaluation navigation
- [x] Reusable visual primitives
- [x] Explicit provenance vocabulary
- [x] Truthful prototype and connectivity labels
- [x] Responsive foundation without page-level overflow by design
- [x] Visible keyboard focus and reduced-motion support
- [x] Production build, lint, type check and dependency audit
- [x] Five-region full-screen Main workspace
- [x] Scenario and entirely-new Manual Input composition
- [x] Selectable complete graph with two verifier phases
- [x] Distinct current and selected node states
- [x] Node details and human checkpoint preview inside the canvas
- [x] Selected-node tool highlighting and processed memory summaries
- [x] Horizontal human-readable timeline and pending final-response preview
- [x] Responsive desktop, tablet and mobile composition
- [x] Header-free content panels with larger working typography
- [ ] Runtime/API integration — UI-3
- [ ] Complete data explorer — UI-4
- [ ] Complete evaluation explorer — UI-5
- [ ] End-to-end and production delivery gate — UI-6
