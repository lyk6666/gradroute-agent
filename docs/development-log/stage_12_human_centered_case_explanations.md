# Stage 12 — Human-Centred Case Explanations and Review

## Purpose

Stage 12 makes the execution workspace easier to understand without weakening
the grounded control plane. The primary surface should explain the student's
case, the material decision, and any human responsibility. Internal tool names,
raw identifiers, counters, and state payloads remain available only as optional
audit detail.

## Agreed experience

### Node monitoring

The selected-node card will no longer repeat the fixed `What came in`, `What
this step found`, and `What changed` template. Each visited node instead shows
one concise, case-specific explanation and, only when useful, a short next
decision. The node title, execution status, and selected/current graph styling
remain visible.

Unvisited nodes explain their role in one sentence. Advanced evidence, versions,
and recorded fields remain collapsed under `Evidence and audit details`. Tool
names are removed from the ordinary node, action, and memory presentation.

### Human interaction

Clarification must show:

- the exact question;
- why the answer is needed;
- what decision depends on it; and
- whether the answer returns to verification or requires replanning.

Approval must show:

- the exact proposed action;
- why approval is required;
- the applicable policy or simulated approval basis;
- the evidence supplied;
- the named approving role; and
- `Approve`, `Reject`, and `Leave pending` controls.

The agent cannot approve its own proposal. Interactive demo and evaluation runs
must pause at an approval checkpoint. Automated evaluation continues to use its
isolated evaluator-controlled human actor so the 315-run campaign remains
repeatable.

Administrative review must explain why automation stopped, what was already
checked, what remains unknown, the recommended CCDS role, and the handoff that
the reviewer is acknowledging. Approval and administrative review remain
different concepts: approval authorises an otherwise valid action, while review
handles a case for which the system lacks a safe route or authority.

### Working and thread memory

Working state will be limited to a short current-situation summary, the next
step, and an attention item when one exists. Technical plan versions, counters,
raw evidence, and model diagnostics remain in collapsed audit details.

Thread memory will show only a small chronological set of material case events,
such as the request being understood, a decisive finding, a clarification, an
approval, a failed attempt, or a recovery. It will not present internal trace
sequence numbers as primary content.

### Long-term memory

At most two relevant, deidentified lessons will be shown. Each lesson explains
the useful strategy and when it applies. Long-term memory remains advisory and
cannot establish current curriculum, policy, offering, vacancy, or approval
facts.

### Final response

Every final response will contain a dedicated `Why this is valid` explanation.
It will connect the outcome to the actual case evidence, including as applicable:

- the outstanding academic requirement;
- course, prerequisite, exclusion, timetable, workload, and availability checks;
- the applicable exception or registration policy;
- supporting-document completeness;
- the approval requirement and observed decision; and
- post-action confirmation that the student's goal is now true.

The final response will distinguish the outcome, its reasoning, the action and
verification result, the student's next step, and prototype limitations. A
candidate, approval request, or successful transaction response alone must
never be presented as a completed result.

## Implementation plan

1. Extend the UI-safe API contract with concise node explanations, decision
   context, final-response reasoning, and human-interaction context.
2. Produce deterministic case-specific fallbacks for every node and allow the
   optional Bedrock narrator to improve wording without changing decisions.
3. Simplify the selected-node, working-state, thread-memory, and long-term-memory
   panels; keep audit material collapsed.
4. Add interactive approval decisions and administrative-handoff acknowledgement
   without leaking evaluator ground truth into the agent context.
5. Update copy/export output so the reasoning is retained outside the screen.
6. Add API, orchestration, and presentation tests for every human gate and the
   concise information boundary.
7. Run backend tests plus frontend typecheck, lint, tests, and production build.

## Acceptance criteria

- No ordinary node panel uses the three repeated `What...` headings or lists
  tool names.
- Every visited node has a concise, case-specific explanation.
- Clarification explains why the requested information matters.
- Approval-bound interactive runs pause for a user decision and cannot transact
  before approval.
- Rejection returns to planning; pending remains safely checkpointed; approval
  permits only the already-verified action.
- Administrative review explains the handoff and requires user acknowledgement
  on the interactive surface.
- Working state and memory remain concise, natural, and privacy-safe.
- Final responses include a case-specific `Why this is valid` section and retain
  that reasoning when copied or exported.
- Evaluation ground truth and hidden future events remain absent from agent and
  UI runtime context.
- All required automated checks pass.

## Progress

- **Status:** complete for the local hackathon prototype.
- Replaced the three repeated node sections with one concise, case-specific
  explanation and a collapsed evidence/audit view.
- Removed the ordinary tool catalogue and node tool list from the Main
  workspace. Tool traces remain in backend audit state and continue to support
  deterministic evaluation.
- Simplified the right panel to current situation, up to four material case
  events, at most two relevant past lessons, and provenance.
- Added explicit clarification reasons and explained whether the answer returns
  to verification or planning.
- Added a host-only interactive approval boundary. Demo and evaluation cases
  launched from the Main workspace now pause with the proposed action, reason,
  basis, evidence, approver, and `Approve`, `Reject`, or `Leave pending`
  controls. The agent never receives this authority.
- Approval changes only the isolated UI runtime: pending remains checkpointed,
  approval permits the already-verified action, and rejection returns to
  planning. The frozen scenario package and automated evaluator actor are not
  modified.
- Added an explicit administrative-handoff acknowledgement on the interactive
  surface.
- Added `Why this is valid`, `Why human review is required`, or `Why the case
  stopped here` reasoning to final responses and retained it in copy/export
  output.
- Prevented optional LLM narration from naming internal tools in user-facing
  prose.

## Validation results

- Stage 12 focused acceptance tests: **5 passed**.
- Complete backend regression suite: **621 passed, 2 opt-in Bedrock tests
  skipped**.
- Frontend TypeScript check: **passed**.
- Frontend lint: **passed**.
- Frontend production build: **passed** for `/`, `/data`, and `/evaluation`.

The skipped checks intentionally require `RUN_BEDROCK_LIVE_TESTS=1` and would
spend live model requests. Existing accepted Stage 6 and Stage 7 live campaign
evidence remains unchanged because Stage 12 does not alter the automated
evaluation lane.
