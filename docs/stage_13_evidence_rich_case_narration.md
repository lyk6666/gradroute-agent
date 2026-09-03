# Stage 13 — Evidence-Rich Case Narration

## Purpose

Stage 13 makes each visible explanation specific enough for a student, reviewer,
or judge to understand why the system reached its current position. The interface
will stay concise, but it will refer to the material case facts: the student's
programme and academic position, the relevant course and prerequisite, represented
class availability and timetable constraints, applicable public or simulated
policy basis, submitted documents, approval role, and observed transaction result.

This is a presentation-layer refinement. Deterministic tools, safety rules,
approval boundaries, evaluator ground truth, and transaction authority remain
unchanged.

## Experience design

### Node-specific explanations

Every graph node receives its own communication brief rather than a shared generic
template. A visited node presents one smooth case explanation of roughly 60–110
words when the evidence supports that length. The wording answers the questions a
person would naturally ask at that step.

- Intake introduces the student, request, relevant registration context, and the
  facts accepted into the case.
- Memory retrieval explains any comparable past lesson and why current evidence
  still controls the decision.
- Planning explains the ordered checks and, on later attempts, what changed and why
  a new plan is necessary.
- Degree audit explains earned progress, the outstanding requirement, and the
  academic significance of the target course.
- Policy analysis identifies the represented rule or simulated exception basis,
  eligibility, required documents, and approval role without presenting a
  prototype rule as official NTU policy.
- Course analysis explains prerequisites, exclusions, semester offering,
  availability, timetable fit, and workload using the actual represented course
  and class details.
- Resolution, verification, action, observation, and final-response nodes explain
  the exact proposed action, the checks that support it, the observed result, and
  whether the student's goal is now true.
- Clarification, approval, and administrative review explain precisely what a
  person must decide, the evidence relevant to that decision, and what happens
  after each possible response.

The main explanation avoids internal context IDs, trace vocabulary, tool names,
schema terms, counters, and hidden expected answers. Exact recorded values and
provenance remain available in the collapsed evidence-and-audit view.

### Human actions

A human prompt must be evidence-rich rather than merely saying that permission or
information is required. Where applicable it will identify:

- the student's programme, year, academic progress, and outstanding requirement;
- the target course and represented prerequisite or exclusion finding;
- the feasible class index, capacity, timetable, and workload finding;
- the policy or simulated exception basis and the source/rule provenance;
- the required and supplied supporting documents;
- the exact action awaiting authorisation and the named approving role; and
- the consequence of approve, reject, pending, clarification, or handoff.

The display must explicitly disclose when the approval route comes from simulated
prototype policy rather than a public NTU rule. Approval only authorises the
already-verified proposal; it does not itself prove that registration or graduation
has succeeded.

### Unified case overview

The right panel merges `Current situation` and `Case history` into one open
`Case overview`. It contains:

1. a natural paragraph describing the current position;
2. the most important case-specific findings;
3. the immediate next decision or action;
4. a warning only when genuine attention is required; and
5. up to four recent material events in chronological order.

Technical plan, route, checkpoint, and event records remain in a single collapsed
details area. Relevant past lessons and information sources remain separate,
compact sections.

## Grounding and narration contract

The optional Bedrock narrator receives only presentation-safe observed facts plus
the selected node's communication brief. It may improve organisation and wording,
but it cannot add a rule, infer an unrecorded prerequisite, choose an action, grant
approval, or change execution state. Deterministic case-specific fallback text is
always available when narration is disabled or unavailable.

Narration quality will be judged against these requirements:

- **specificity:** names the relevant student situation, course, constraint, rule
  basis, document, class, or decision when those facts are known;
- **grounding:** every substantive statement can be traced to the visible run
  record and provenance remains accurate;
- **node fit:** the explanation answers the questions appropriate to that node;
- **loop awareness:** a replanned node explains what changed from the earlier
  attempt;
- **actionability:** human prompts state who decides what, why, and what follows;
- **readability:** natural language, limited repetition, and no implementation
  jargon; and
- **safety:** no evaluator answer leakage and no unsupported policy or success
  claim.

## Implementation plan

1. Enrich the presentation-safe narration payload with programme, academic,
   prerequisite, offering, policy, document, approval, and loop context already
   observed by the run.
2. Replace broad node goals with node-specific narration briefs and strengthen the
   deterministic fallbacks for every graph role.
3. Build detailed clarification, approval, and administrative-review explanations
   from the same observed evidence, with explicit provenance limitations.
4. Merge current situation and case history in the metadata panel while preserving
   compact expandable audit records.
5. Add regression tests for specificity, provenance, node fit, loop awareness,
   human authority, and the merged interface structure.
6. Run backend and frontend checks.
7. Execute all seven demo scenarios with real Bedrock narration, provide required
   simulated human responses, inspect representative node/action/memory/final
   outputs, refine any weak wording, and record the results below.

## Acceptance criteria

- Node explanations materially differ by graph role and current case.
- Known prerequisites, offerings, documents, policies, and approval facts appear
  where relevant instead of being replaced by generic language.
- Later planner/verifier attempts explain the event that caused replanning.
- Every human checkpoint states the concrete decision basis and downstream effect.
- Simulated policy is clearly labelled as prototype evidence, not official NTU
  policy.
- `Case overview` replaces separate `Current situation` and `Case history`
  sections without losing recent material events.
- All seven demo workflows can be completed or safely handed off with real LLM
  narration, and their displayed outcome matches the represented run evidence.
- Automated backend and frontend checks pass.

## Progress

- **Status:** complete for the local hackathon prototype.
- Stage scope, presentation contract, safety boundary, seven-demo validation plan,
  and acceptance criteria recorded before code changes.
- Added structured, node-specific communication briefs covering every graph role,
  including distinct questions for intake, planning, academic audit, policy,
  course feasibility, verification, human interaction, transaction, final outcome,
  and memory.
- Added a presentation-safe case-evidence projection containing only observed
  student, academic, prerequisite, exclusion, class, timetable, workload, policy,
  document, approval, action, observation, and replan facts.
- Replaced short generic fallbacks with evidence-rich, case-specific explanations.
  The deterministic wording is assembled from current case facts and differs by
  node, course, programme, approval route, and loop attempt.
- Approval explanations now identify the actual course, AU position when relevant,
  prerequisite result, feasible represented class, document set, policy reference,
  approving role, and consequence of each decision. Simulated approval routes state
  that they are not general official NTU rules.
- Clarification explanations now connect the missing answer to the actual student,
  course, known audit position, affected route, and no-action safety boundary.
- Added an optional natural-language human-decision summary while retaining the
  authoritative structured reason and evidence underneath it.
- Combined the right-panel `Current situation` and `Case history` sections into one
  open `Case overview`, with the current explanation, important findings, next
  action, genuine attention item, and up to four recent developments. Technical run
  and checkpoint records share one collapsed details section.
- Prevented the memory-update node from replacing a completed case overview with a
  memory-management message. Completed cases continue to show the verified outcome
  and next step.
- Added a model-output quality guard. Placeholder field names, copied prompt
  instructions, cross-node text, missing case/course facts, and evidence-poor role
  summaries are retried and then replaced by the grounded fallback. Partial
  secondary fields are normalized without accepting a missing primary explanation.
- Added a reusable seven-demo live review script and a machine-readable review
  artifact at `evaluation/stage13_demo_narration_review.json`.
- Added five Stage 13 acceptance tests for public-policy approval detail, simulated
  policy disclosure, replan awareness, the unified overview, and reasoned terminal
  output.
- Stabilized the React Flow viewport so the graph cannot feed its measured size
  back into the dashboard layout. The UI now filters only the browser's two benign
  `ResizeObserver` delivery notifications while leaving genuine script errors
  visible in development.

## Seven-demo validation results

The configured Amazon Bedrock model `amazon.nova-micro-v1:0` was invoked through the
project's `ccds-sandbox` SSO profile. The review did not expose demo expected answers
to the runtime; those remained post-run comparison material only.

| Demo | Observed boundary | Display review |
| --- | --- | --- |
| S1 — same-course recovery | Verified completion | Pass |
| S2 — prerequisite evidence route | Human approval, then verified completion | Pass |
| S3 — versioned multi-source reasoning | Verified completion | Pass |
| S4 — constraint-heavy index planning | Human approval, then verified completion | Pass |
| S5 — integrated programme reasoning | Human approval, then verified completion | Pass |
| S6 — no valid declared path | Safely waiting for the student's declaration | Pass |
| S7 — dynamic registration recovery | Failed first attempt, replan, verified completion | Pass |

Across the seven workflows, the narrator was called for every executed node. The
quality driver made 198 bounded calls, including retries, for 110 displayed node
records. Seventy-six model narrations passed the role and grounding guard; 34 records
used the evidence-rich deterministic fallback after incomplete, placeholder,
cross-node, or unavailable model responses. This is an intentional safety result:
live language improves presentation when it is usable, but cannot displace a more
specific grounded explanation.

The final artifact reports **7/7 passed**. Each accepted display named the target
course, matched the selected node's purpose, ended at a safe terminal or human
boundary, contained no expected-answer or internal-state leakage, and retained the
case-specific final or clarification reason.

## Automated validation

- Stage 10, 12, and 13 focused narration/presentation tests: **12 passed, 1 opt-in
  live test skipped** before the explicit seven-demo live campaign.
- Frontend TypeScript, lint, and production-build checks: **passed**.
- Complete backend regression suite: **626 passed, 2 opt-in live tests skipped**.
  The skipped tests are separate single-request Stage 6/10 checks; the explicit
  seven-demo Bedrock campaign above ran successfully.
- Frontend TypeScript check: **passed**.
- Frontend lint: **passed**.
- Frontend production build: **passed** for `/`, `/data`, and `/evaluation`.
