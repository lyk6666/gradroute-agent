# Stage 8 — UI Development

## 1. Purpose and status

Stage 8 turns the completed Stage 4–7 runtime and evaluation evidence into a
clear demonstration interface. The design is based on `main_page_reference.png`
and `UI_IMPLEMENTATION_GUIDE.md`, while the repository's frozen graph, safety
contracts, provenance boundaries, and evaluator isolation remain normative.

Current status: **UI-1 complete; UI-2 awaiting approval.**

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

### UI-2 — Main Page static workspace — pending approval

- cases/demo-scenario rail;
- complete frozen graph with collision-free nodes and typed edge styles;
- case/node inspector shell;
- execution timeline and final-response composition;
- target desktop and responsive layouts.

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

## 7. UI-1 acceptance record

- [x] Shared dark-header/light-workspace shell
- [x] Main, Data and Evaluation navigation
- [x] Reusable visual primitives
- [x] Explicit provenance vocabulary
- [x] Truthful prototype and connectivity labels
- [x] Responsive foundation without page-level overflow by design
- [x] Visible keyboard focus and reduced-motion support
- [x] Production build, lint, type check and dependency audit
- [ ] Interactive graph — UI-2
- [ ] Runtime/API integration — UI-3
- [ ] Complete data explorer — UI-4
- [ ] Complete evaluation explorer — UI-5
- [ ] End-to-end and production delivery gate — UI-6
