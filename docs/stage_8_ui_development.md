# Stage 8 — UI Development

## 1. Purpose and status

Stage 8 turns the completed Stage 4–7 runtime and evaluation evidence into a
clear demonstration interface. The design is based on `main_page_reference.png`
and `UI_IMPLEMENTATION_GUIDE.md`, while the repository's frozen graph, safety
contracts, provenance boundaries, and evaluator isolation remain normative.

Current status: **UI-3 complete; UI-4 is next.**

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
- assigned every branch and return path an explicit orthogonal route, dedicated
  corridor and independently positioned label so edges remain visually distinct;
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

### UI-3 — Main Page runtime integration — complete

- added a versioned FastAPI facade over an isolated Stage 4/5 runtime per run;
- projected all 7 demo and 105 held-out evaluation scenarios without exposing
  ground truth, expected outcomes, injected scripts, or raw LangGraph state;
- added replayable SSE events and processed snapshots for live node, edge,
  timeline, tool, working-state, thread-memory and long-term-memory updates;
- preserved two visual verifier phases while keeping the single frozen backend
  verifier implementation;
- implemented normal and true step-by-step execution, where the graph generator
  waits between nodes until the user releases the next step;
- implemented persisted clarification resume with required-field validation and
  approval re-check through the authoritative simulated approval state;
- enabled verified final-response copy and text export; and
- added API, projection, execution, step-mode, checkpoint and leakage tests.

UI-3 deliberately executes only records already validated in the frozen Stage 3
scenario package. Manual Input remains a guarded composition surface until a
separate simulation builder can create a mutually consistent student, degree
audit, registration, offering and exception record; the interface does not
pretend that arbitrary text has entered the authoritative runtime.

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
across intake, graph, inspector, timeline, and response surfaces. The node-detail
and human-interaction surfaces were then consolidated into one embedded canvas
inspector that pans and zooms with the architecture. Graph branches use
separated connection ports and offset return lanes so conditional, approval,
clarification, and replanning edges do not share the same visible track. The
scenario preview grid now constrains provenance badges to their intrinsic size
and preserves content-sized rows, while the timeline row is intentionally
shorter to return vertical space to the execution canvas.

The final graph-legibility pass replaced automatic edge placement with rounded
orthogonal routes, reserved three independent right-side replan/rejection lanes
and two left-side recovery lanes, and moved the approval wait/resume loop below
its approval node. Edge labels use opaque semantic pills and explicit positions
rather than path midpoints. Desktop checks at 1920×1080 and 1440×900 found no
label-to-label or label-to-node collisions, no unrelated edge-to-node crossings,
no independent edge intersections and no clipped route labels. At compact
desktop widths the processed inspector moves below the graph so the architecture
retains a readable canvas width.

A follow-up routing correction keeps Degree Audit, Policy and Course as
independent Supervisor/Router branches rather than implying a fixed specialist
sequence. Runtime specialist transitions highlight the corresponding Supervisor
branch, all replan/rejection paths now enter Planner horizontally with inward
arrowheads, and the administrative Handoff uses a separate neutral corridor
from the red transaction-domain escalation path.

### 1 September 2026 — UI-3

The Main workspace now runs the real checkpointed control plane through a
stable API instead of replaying static frontend samples. The backend exposes
processed UI summaries only, supports event replay after reconnect, and keeps
each mutable case runtime bound to one run/thread. Graph nodes and traversed
edges update from actual LangGraph events; the timeline records repeated nodes
for replans and dynamic recovery rather than forcing a fixed sequence. The
right inspector follows real tool calls and memory summaries. Clarification
answers resume the matching persisted interrupt, while pending approval can
only be re-checked against the authoritative scenario state—the agent and UI
cannot self-approve. Final student-facing output appears only after the runtime
produces its terminal outcome.

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
- [x] Embedded pannable canvas inspector and separated edge-routing lanes
- [x] Collision-audited orthogonal routes and explicit edge-label placement
- [x] Runtime/API integration — UI-3
- [ ] Complete data explorer — UI-4
- [ ] Complete evaluation explorer — UI-5
- [ ] End-to-end and production delivery gate — UI-6
