# Stage 9 — Runtime Transparency and Manual Intake

Status: **complete for the local hackathon-prototype boundary**.

Stage 9 removes the remaining static-preview behaviour from the Main workspace.
The backend now projects processed execution evidence for each visited graph node,
the metadata panel exposes useful runtime content rather than counters alone, the
final response is assembled from the verified case state, and Manual Input starts
a real run through the same Stage 5/6 graph used by catalogue scenarios.

## Scope and design boundary

This remains a research and competition prototype. Manual cases are new requests
created over a selected, validated synthetic academic profile. The user may edit
the request and optional context, while the student's programme, cohort, study
year, earned AUs, course history, current registration, supporting-document
inventory and operational environment remain tied to the selected simulated
profile. This prevents an incomplete form from creating an internally
inconsistent degree audit or registration state.

No evaluator ground truth, transaction script, hidden event or future approval
result is exposed through the Stage 9 API or UI.

## Modification history

### Stage 9.1 — Runtime-detail contract

- Added a typed `node_details` map to every run snapshot.
- Captured the latest execution attempt for each visited node, including:
  - processed input fields;
  - processed output fields;
  - persisted state changes;
  - observed tool names;
  - evidence and source identifiers;
  - bounded Bedrock/fallback reasoning metadata where applicable;
  - start and completion timestamps.
- Kept unvisited-node descriptions as clearly labelled expected behaviour rather
  than presenting them as observed results.

### Stage 9.2 — Adaptive canvas inspector and action surface

- Replaced static Input, Output and State sentences with the selected node's
  runtime record after execution.
- Added scenario-specific tool, reasoning, attempt and evidence summaries.
- Made the lower canvas area adaptive for candidate construction, verification,
  action gating, transactions, observation, final response and memory update.
- Retained interactive clarification and approval checkpoint controls.
- Replaced fixed approval examples with the observed approval data for the run.

### Stage 9.3 — Expanded metadata and memory

- Expanded Working State with plan rationale, ordered plan steps, accumulated
  specialist evidence, action parameters, outstanding items, errors and reasoning
  call outcomes.
- Expanded Thread Memory with a chronological checkpoint history plus processed
  clarification and approval records.
- Expanded Long-Term Memory with pattern ID, applicability, recovery steps,
  failure patterns, tags, relevance and verification time.
- Deduplicated retrieved long-term-memory patterns by memory ID.
- Kept memory advisory-only; it cannot replace current academic, course, policy,
  approval or transaction evidence.

### Stage 9.4 — Detailed final response

- Replaced the generic UI outcome with a structured final response derived from
  the final outcome, action candidate, evidence, approval state, transaction
  receipt, observation and goal evaluation.
- Added a case-specific headline, request summary, verified resolution, action
  parameters, academic/course basis, policy basis, approval result, transaction
  result, next steps, evidence identifiers and prototype limitations.
- Updated Copy and Export so they include the detailed verified resolution rather
  than only the short message.

### Stage 9.5 — Connected manual mode

- Added `POST /api/v1/runs/manual`.
- Added a profile-backed manual form with student, programme and request-type
  selectors populated from the validated scenario catalogue.
- Added read-only previews of earned AUs, completed courses, current registration
  and supporting documents.
- Validated that all submitted identity and academic-profile fields match the
  selected synthetic profile before execution.
- Assigned each accepted manual run a distinct `MANUAL-*` identifier.
- Preserved the manually entered request and notes in the intake, node detail and
  final response.
- Supported both normal and step-by-step execution modes.

### Stage 9.6 — Validation

- Added `tests/test_stage9_runtime_transparency.py` for node-detail projection,
  expanded state, detailed final response, accepted manual execution and rejected
  profile mismatches.
- Full backend result: **611 passed, 1 opt-in Bedrock test skipped**.
- Frontend TypeScript check: **passed**.
- Frontend ESLint check: **passed**.
- Frontend production build: **passed** for `/`, `/data` and `/evaluation`.

## API additions

The run snapshot adds these presentation-safe structures:

- `node_details`;
- detailed `working_state.plan_steps`, `working_state.evidence`, action,
  outstanding-item, error and reasoning fields;
- `thread_memory.events`, clarification details and approval details;
- expanded long-term-memory summaries;
- an expanded structured `final_response`.

Scenario summaries now include the academic-profile preview required by Manual
Input: earned AUs, completed courses, registered courses and declared supporting
documents.

## Completion criteria

Stage 9 is complete when:

- a selected visited node shows observed input, output and state rather than
  template-only copy;
- action-related nodes show their actual decisions and results;
- metadata sections expose processed runtime content;
- the final response differs according to the actual case route and receipt;
- a valid manual request can execute through the same graph in normal or step
  mode;
- mismatched or incomplete manual profiles fail before graph execution; and
- all local automated delivery gates pass.

These criteria are satisfied. Institutional authentication, live NTU student
systems, durable multi-user storage and production deployment remain outside the
hackathon boundary.
