# Stage 10 — Natural-Language Runtime Narration

Status: **complete for the local hackathon-prototype boundary**.

Stage 10 turns the Main workspace from a processed system record into a
human-readable case explanation. Each explanation is produced from the current
run after a graph step executes. It is not selected from a fixed set of node or
scenario sentences.

## User experience

For every visited node, the canvas explains:

- what information the step received and why it mattered;
- what the step actually found or decided;
- what changed in the case state; and
- whether an action, clarification, approval or handoff is required.

The metadata panel also gives a compact case briefing: what is happening, the
few facts that matter now, the immediate next step and any genuine blocker or
human decision. Thread memory is shown as a short chronological case history.
Long-term memory explains why a past case may be relevant while clearly marking
it as advisory. The final-response panel presents a case-specific explanation
of the verified outcome and next step. Exact recorded fields remain available
under optional detail controls. Unvisited nodes no longer show generic expected
inputs and outputs.

## Grounding and safety boundary

The narrator receives presentation-safe data only: processed input, output and
state records, observed tools, evidence references, the current plan and
progress, thread checkpoints, advisory memory summaries and the already-built
final response. Evaluator ground truth, transaction scripts and controlled
future events are not included.

Narration is a display layer. It cannot select specialists, change the plan,
approve a request, submit a transaction, alter memory or change the final
outcome. Academic, course, policy, approval and transaction records remain
authoritative.

Model-produced memory explanations are accepted only for memory IDs that were
actually retrieved. Any invented memory reference is discarded. A malformed or
unavailable model response does not stop the run. The primary view says that
the plain-language explanation is temporarily unavailable, while exact
processed facts remain inspectable under the optional record disclosure. Raw
context identifiers and traces are never substituted into the main narrative.

## Runtime behaviour

One bounded structured Bedrock request is made after each executed graph step.
The same request refreshes that node's four explanations together with the
working-state and memory summaries. This avoids repeated model calls whenever a
browser asks for a snapshot.

Narration is enabled when `UI_NARRATION_ENABLED` is true and a
`BEDROCK_MODEL_ID` is configured. It is independent of the control-plane mode:

- fixture mode can keep deterministic case decisions while using Bedrock only
  for natural-language presentation; and
- Bedrock mode uses grounded model reasoning at the existing bounded decision
  points and Bedrock narration for the interface.

## Modification history

### Stage 10.1 — Narration contract

- Added a structured narration task covering node input, output, state, action,
  working state, thread memory, retrieved memories and the final response.
- Added typed narration fields to the runtime API without replacing the exact
  Stage 9 records.
- Added prompt-injection resistance by treating all supplied record text as
  evidence rather than instructions.

### Stage 10.2 — Runtime integration

- Generated narration only after a node has an observed runtime record.
- Cached narration in the isolated run record so normal snapshot and event
  requests do not trigger extra model calls.
- Kept narration failures outside the execution path so a provider outage cannot
  fail or change a case.
- Filtered all model-produced long-term-memory explanations against retrieved
  memory IDs.

### Stage 10.3 — Interface integration

- Made natural explanations the primary Input, Output, State and Action content
  in the in-canvas inspector.
- Moved technical recorded fields into optional disclosure sections.
- Added plain-language Working State and Thread Memory summaries.
- Applied model-generated explanations to retrieved memory cards and the final
  response.
- Replaced unvisited-node templates with a neutral not-yet-run message.

### Stage 10.4 — Validation

- Added context-aware narration tests that confirm different node records produce
  different explanations.
- Added outage tests confirming that the graph still completes with recorded
  facts available.
- Added an opt-in live Bedrock narration test.
- The configured Amazon Bedrock model passed the live structured narration check.
- Full backend regression result: **613 passed, 2 opt-in Bedrock tests skipped**.
- Frontend TypeScript, ESLint and production-build checks: **passed**.

### Stage 10.5 — Natural-language case and memory briefing

- Added a concise semantic case profile to each narration request so the model
  can explain the student, programme, study year, current registration and
  request without leading with internal context or curriculum identifiers.
- Expanded Working State into **What is happening**, **What we know**, **Next**
  and **Needs attention**. The last section appears only for a real blocker or
  human decision.
- Expanded Thread Memory into a short chronological history of the current case
  and moved event counters, timestamps, pause records and approval records under
  **View checkpoint details**.
- Reframed Long-Term Memory as relevant past experience rather than a score.
  Pattern IDs, percentages, recovery records and tags now sit under
  **View memory record**, and every card states that current evidence still
  decides the case.
- Kept exact node and action records under **View recorded facts** while making
  run-specific model narration the primary content.
- Prevented an intermediate narration call from creating a final response and
  continued to reject memory explanations for IDs that were not retrieved.
- Revalidated the final package: **613 backend tests passed**, the two opt-in
  live tests were skipped in the full offline suite, frontend type checking,
  lint and production build passed, and the focused live Amazon Bedrock
  narration test passed after SSO renewal.

## Completion criteria

Stage 10 is complete when every visited node can display run-specific natural
language, working and memory explanations evolve with the run, the final answer
uses the observed outcome, invented memory references cannot enter the UI, and
narration failure cannot affect execution. Working, thread and long-term memory
must also be readable without exposing counters or internal IDs as the primary
content. These criteria are satisfied.
