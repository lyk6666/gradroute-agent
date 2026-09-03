# Stage 14 — Node Visit History

## Purpose

Stage 14 preserves and presents every visit to a workflow node. Replanning,
rechecking policy, retrying a transaction, or returning from a human checkpoint
must create a new visit record instead of replacing the earlier explanation.
This lets a student, reviewer, or judge understand how the case changed over time.

The latest node record remains available through the existing API field for
backward compatibility. An additional ordered history is the authoritative source
for visit-by-visit inspection.

## Experience design

- A graph node shows a compact visit count after it has been reached more than
  once.
- Clicking a graph node opens its latest visit.
- Clicking an execution-timeline event opens the exact visit represented by that
  event.
- The in-canvas detail panel separates visits into clearly labelled sections such
  as `Visit 1 · Initial pass` and `Visit 2 · Replan`.
- Each section shows the explanation, status, time, and optional evidence record
  captured for that visit. The selected visit is visually distinct.
- Human clarification, approval, and review controls belong only to the latest
  active visit. Earlier visits remain readable but cannot submit a new decision.
- Later planner and specialist visits retain their own case-specific narration so
  the reason for a revised plan or repeated check is not lost.

## Data contract

1. `node_details` continues to expose the latest record for each node.
2. `node_history` exposes an ordered list of immutable attempt records per node.
3. Every timeline event includes its node attempt number.
4. A narration update replaces only the matching attempt in `node_history`; it
   must not rewrite another visit.
5. The narration request receives a concise prior-visit summary when one exists,
   allowing the wording to explain what changed without exposing internal state.

## Implementation and test plan

1. Add visit history and timeline-attempt fields to the backend and frontend API
   models.
2. Record, complete, pause, and narrate the matching visit atomically while
   retaining the latest-record compatibility view.
3. Add exact-visit selection to the main workspace, graph, detail panel, human
   interaction area, and timeline.
4. Add compact visit-count and visit-section styling without reducing graph
   clarity.
5. Add regression tests using the dynamic-recovery scenario to prove that two
   planner visits remain distinct and that timeline events point to the correct
   visits.
6. Run focused and complete backend checks plus frontend type, lint, and build
   checks.

## Acceptance criteria

- A revisited node exposes all attempts in chronological order.
- Earlier narration and evidence remain unchanged after later visits.
- The latest compatibility record matches the final history entry.
- A timeline selection opens the intended node attempt, not merely the latest one.
- Human action buttons cannot act from a historical visit.
- Single-visit nodes retain the compact existing experience.
- Existing backend and frontend behavior remains compatible.

## Progress

- **Status:** complete for the local hackathon prototype.
- Stage scope, compatibility boundary, interaction design, and acceptance criteria
  recorded before implementation.
- Added an ordered `node_history` to every run snapshot while preserving
  `node_details` as the latest-visit compatibility view.
- Added the attempt number to each timeline event and recorded the initial,
  running, completed, and human-checkpoint visits against the matching attempt.
- Narration updates now replace only their own visit record. The optional LLM
  receives the previous visit's safe summary and is instructed to explain the
  material change without merging or overwriting the visits.
- Graph nodes now show a compact count when they have multiple visits. A graph
  click opens the latest visit; a timeline click opens the exact historical visit.
- The in-canvas inspector displays multiple visits as distinct sections, with the
  latest visit first, a case-appropriate label such as `Initial pass`, `Replan`,
  `Evidence recheck`, or `Retry`, its status and time, and the visit-specific
  explanation and evidence record.
- Historical clarification and approval visits are explicitly read-only. Human
  controls remain available only on the latest active visit.
- Replaced the late `ResizeObserver` error-event filter with stable React Flow
  node dimensions and frame-scheduled, coalesced resize measurements. This keeps
  graph geometry current without allowing Chromium's benign delivery notice to
  open the development error overlay.
- Removed the development-only React Flow attribution warning by retaining the
  library's standard attribution, and standardized Main-workspace event times to
  a compact English 24-hour display.
- Replaced content-derived React keys in repeated findings, evidence, final-response
  facts, data tokens, and evaluation transition lists with position-qualified keys.
  Repeated but valid sentences no longer trigger duplicate-key warnings or risk a
  missing list item.
- Added four Stage 14 regression tests covering retained planner explanations,
  exact timeline attempts, latest-view compatibility, and historical-action UI
  safeguards.

## Validation results

- Dynamic S7 recovery confirms two distinct planner visits: the first retains its
  initial plan and the second explains the replan.
- Stage 14 focused suite: **4 passed**.
- Complete backend suite: **630 passed, 2 opt-in live tests skipped**.
- Frontend TypeScript check: **passed**.
- Frontend lint: **passed**.
- Frontend production build: **passed** for `/`, `/data`, and `/evaluation`.
- Fresh-load browser regression: **0 errors or warnings**; repeated approval
  visits correctly keep historical decisions read-only and the latest visit actionable.
- Source-diff whitespace check: **passed**; only the repository's existing CRLF
  conversion notices were reported.
