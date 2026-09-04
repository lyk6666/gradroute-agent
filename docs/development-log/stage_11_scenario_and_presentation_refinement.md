# Stage 11 — Scenario and Presentation Refinement

## Outcome

Stage 11 removes the repeated case template that previously made different
demo and evaluation records appear to ask the same question. The scenario
generator, runtime summaries, node inspector, memory panels, and final response
now describe the actual student situation while keeping evaluator answers and
internal coordination identifiers out of the agent-facing surface.

Completion status: implemented and validated for the local hackathon
prototype. The deterministic simulation generator is now `stage3.5.0`.

## Scenario contract

Each of the 140 generated cases now has its own observable:

- student request, based on programme, cohort, study year, earned AUs, current
  registration, target course, documents, and declared programme path where
  relevant;
- goal, stating what a successful or safely bounded result means for that case;
- requested action, stating the exact registration, waiver, exception,
  clarification, or escalation being sought;
- approval request and decision explanation where approval applies;
- transaction messages that name the material course, class, failure, or
  follow-up result; and
- resolution-path rationale tailored to the scenario family.

The requests contain only facts available at intake. They never reveal a future
approval decision, injected failure, retry result, or evaluator outcome.

## Expected-response boundary

`ScenarioGroundTruth.expected_response` records the complete acceptable result
for every scenario. It describes the expected course or class outcome, required
approval behavior, safe clarification or escalation, and post-action
verification.

This field is evaluator-owned:

- `Scenario.to_agent_context()` does not expose it;
- the API returns it only for the seven polished demo scenarios;
- the 105 evaluation summaries return `expected_response: null`; and
- runtime planning and action selection never read it.

This lets a presenter explain what each demo is intended to prove without
leaking the answer key into held-out evaluation.

## Runtime presentation

The deterministic control plane now emits meaningful, case-specific plan
purposes, plan rationales, specialist evidence summaries, candidate rationales,
transaction observations, and verified memory patterns. These facts are the
source material for both the interface and optional Bedrock narration.

Every visited node receives a short fallback explanation even if Bedrock is
unavailable. With Bedrock enabled, the narrator is given a node-specific
communication goal and a compact material-event history. It is instructed to
explain one useful input, finding, state change, and action rather than repeat
the full request or describe raw schemas and counters.

The Main workspace now:

- starts with the Student / Case node selected instead of implying that every
  case begins at Human Approval;
- labels node prose as “What came in”, “What this step found”, and “What
  changed”;
- keeps exact recorded facts available in a collapsed audit section;
- makes no-action human panels compact;
- shows at most three relevant advisory memory patterns; and
- presents friendly course, class, programme-path, approval, transaction, and
  next-step details without primary-display runtime IDs.

## Final-response behavior

Completed responses now identify the actual course and class where relevant,
state whether approval was required and observed, explain transaction success
without exposing an internal receipt ID, and give action-specific next steps.
Dynamic recovery explicitly states that the first attempt failed and live state
was refreshed before the verified alternative was used.

Clarification and administrative handoff remain safe terminal or pause
boundaries. The UI does not turn a candidate into a claimed resolution before
post-action verification.

## Modification history

- Added varied family-specific scenario input, goals, actions, approvals,
  transactions, path rationales, and expected responses to the deterministic
  generator.
- Added demo-only expected-response delivery and evaluation-answer hiding to
  the API and frontend contract.
- Replaced generic planner, evidence, candidate, and successful-memory wording
  with current-case facts.
- Added case-specific deterministic narration fallback and refined Bedrock
  narration inputs.
- Simplified the selected-node, human-action, working-state, thread-memory,
  long-term-memory, and final-response presentation.
- Added Stage 11 acceptance coverage for scenario diversity, evaluator
  isolation, and removal of legacy presentation templates.

## Validation

The stage is accepted when:

- generated files are byte-current under `scripts/build_simulated_data.py
  --check`;
- all demo requests and expected responses are distinct and meaningful;
- evaluation scenario summaries do not expose expected responses;
- legacy “Terminal-stage registration…” and count-only Stage 4 evidence copy no
  longer appears in runtime presentation;
- backend tests pass; and
- frontend typecheck, lint, tests, and production build pass.

