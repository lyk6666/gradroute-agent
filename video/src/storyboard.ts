export const FPS = 30;
export const OUTPUT_WIDTH = 3840;
export const OUTPUT_HEIGHT = 2160;

export type FrameQuery = {
  scenarioId?: string;
  nodeId?: string;
  attempt?: number;
  phase?: string;
};

export type DirectedShot = {
  id: string;
  seconds: number;
  frameId?: string;
  query?: FrameQuery;
  caption: string;
  focus?: 'captured' | 'full';
  accent?: 'blue' | 'green' | 'amber' | 'red' | 'purple';
  approvalClick?: boolean;
};

export type StoryScene = {
  id: string;
  chapter: string;
  audioFile: string;
  shots: DirectedShot[];
};

export const STORYBOARD: StoryScene[] = [
  {
    id: 'opening',
    chapter: 'A connected exception problem',
    audioFile: 'audio/opening.mp3',
    shots: [
      {
        id: 'opening-workspace',
        seconds: 16,
        frameId: 'tour-main-full',
        caption: 'A late registration issue connects academic records, programme rules, availability, policy, and human authority.',
        focus: 'full',
        accent: 'blue',
      },
    ],
  },
  {
    id: 'main-page',
    chapter: 'Main Page · transparent case execution',
    audioFile: 'audio/main-page.mp3',
    shots: [
      {id: 'main-input', seconds: 6, frameId: 'tour-main-input', caption: 'Start from a prepared scenario or validated manual case.', accent: 'blue'},
      {id: 'main-graph', seconds: 7, frameId: 'tour-main-graph', caption: 'Follow planning, evidence checks, verification, decisions, action, and recovery.', accent: 'blue'},
      {id: 'main-inspector', seconds: 6, frameId: 'tour-main-inspector', caption: 'Read the current situation, material history, and advisory lessons in plain language.', accent: 'purple'},
      {id: 'main-timeline', seconds: 5, frameId: 'tour-main-lower', caption: 'Inspect a human-readable execution timeline.', accent: 'green'},
      {id: 'main-response', seconds: 6, frameId: 'tour-main-lower', caption: 'Release a reasoned response only after the outcome is verified.', accent: 'green'},
    ],
  },
  {
    id: 'data-page',
    chapter: 'Data Page · visible grounding boundaries',
    audioFile: 'audio/data-page.mp3',
    shots: [
      {id: 'data-sources', seconds: 9, frameId: 'tour-data-full', caption: 'Public NTU and CCDS materials ground academic, course, calendar, and policy rules.', accent: 'green'},
      {id: 'data-records', seconds: 12, frameId: 'tour-data-table', caption: 'Simulated student and operational records remain clearly labelled and traceable.', accent: 'amber'},
    ],
  },
  {
    id: 'evaluation-page',
    chapter: 'Evaluation Page · inspectable evidence',
    audioFile: 'audio/evaluation-page.mp3',
    shots: [
      {id: 'evaluation-overview', seconds: 8, frameId: 'tour-evaluation-full', caption: 'Compare observed runs with explicit academic, policy, operational, and safety expectations.', accent: 'purple'},
      {id: 'evaluation-metrics', seconds: 7, frameId: 'tour-evaluation-metrics', caption: 'Keep completion, consistency, violations, reasoning quality, and latency separate.', accent: 'purple'},
    ],
  },
  {
    id: 'scenarios',
    chapter: 'Seven grounded simulation scenarios',
    audioFile: 'audio/scenarios.mp3',
    shots: [
      {id: 'scenario-s1', seconds: 2.6, frameId: 'scenario-1', caption: 'S1 · Recover the same required course after the normal deadline.'},
      {id: 'scenario-s2', seconds: 2.6, frameId: 'scenario-2', caption: 'S2 · Build a prerequisite-evidence route with human approval.', accent: 'amber'},
      {id: 'scenario-s3', seconds: 2.6, frameId: 'scenario-3', caption: 'S3 · Check whether a final-year overload request is supportable.'},
      {id: 'scenario-s4', seconds: 2.6, frameId: 'scenario-4', caption: 'S4 · Resolve a timetable conflict without breaking degree requirements.'},
      {id: 'scenario-s5', seconds: 2.6, frameId: 'scenario-5', caption: 'S5 · Identify missing evidence before an exception is submitted.'},
      {id: 'scenario-s6', seconds: 2.6, frameId: 'scenario-6', caption: 'S6 · Clarify safely when no valid declared path is yet available.', accent: 'red'},
      {id: 'scenario-s7', seconds: 2.4, frameId: 'scenario-7', caption: 'S7 · Recover when availability changes during execution.', accent: 'blue'},
    ],
  },
  {
    id: 's7-recovery',
    chapter: 'S7 · dynamic registration recovery',
    audioFile: 'audio/s7-recovery.mp3',
    shots: [
      {id: 's7-ready', seconds: 4, frameId: 's7-m01-ready', caption: 'The selected student and registration request establish the observable goal.', focus: 'full'},
      {id: 's7-planner-1', seconds: 5, query: {scenarioId: 'S7-M01', nodeId: 'planner', attempt: 1}, caption: 'The first plan identifies a feasible-looking registration route.'},
      {id: 's7-course-1', seconds: 5, query: {scenarioId: 'S7-M01', nodeId: 'course_agent', attempt: 1}, caption: 'Course feasibility is checked against the current offering and student constraints.'},
      {id: 's7-precheck', seconds: 4, query: {scenarioId: 'S7-M01', nodeId: 'pre_action_verifier', attempt: 1}, caption: 'Pre-action verification bounds the exact transaction that may be attempted.', accent: 'blue'},
      {id: 's7-full', seconds: 7, query: {scenarioId: 'S7-M01', nodeId: 'transaction', attempt: 1}, caption: 'The transaction reports that the selected class is already full.', accent: 'red'},
      {id: 's7-observe', seconds: 5, query: {scenarioId: 'S7-M01', nodeId: 'observation', attempt: 1}, caption: 'The failed result becomes new observable evidence instead of being hidden.', accent: 'red'},
      {id: 's7-postcheck-1', seconds: 4, query: {scenarioId: 'S7-M01', nodeId: 'post_action_verifier', attempt: 1}, caption: 'The goal is still unsatisfied, so completion is refused.', accent: 'red'},
      {id: 's7-replan', seconds: 5, query: {scenarioId: 'S7-M01', nodeId: 'planner', attempt: 2}, caption: 'The planner creates a second route using the latest availability.', accent: 'purple'},
      {id: 's7-course-2', seconds: 4, query: {scenarioId: 'S7-M01', nodeId: 'course_agent', attempt: 2}, caption: 'A replacement index is rechecked against prerequisite, timetable, workload, and vacancy constraints.'},
      {id: 's7-success', seconds: 5, query: {scenarioId: 'S7-M01', nodeId: 'transaction', attempt: 2}, caption: 'The revised, independently verified transaction succeeds.', accent: 'green'},
      {id: 's7-postcheck-2', seconds: 4, query: {scenarioId: 'S7-M01', nodeId: 'post_action_verifier'}, caption: 'Post-action verification confirms the required course is now registered.', accent: 'green'},
      {id: 's7-final', seconds: 6, frameId: 's7-m01-final-response', caption: 'The final response explains the result, supporting checks, and reason for replanning.', accent: 'green'},
    ],
  },
  {
    id: 's2-approval',
    chapter: 'S2 · evidence-led human approval',
    audioFile: 'audio/s2-approval.mp3',
    shots: [
      {id: 's2-ready', seconds: 4, frameId: 's2-m01-ready', caption: 'The request concerns a missing prerequisite for a graduation-relevant course.', focus: 'full'},
      {id: 's2-audit', seconds: 5, query: {scenarioId: 'S2-M01', nodeId: 'degree_audit_agent', attempt: 1}, caption: 'Degree-audit evidence establishes what remains outstanding.'},
      {id: 's2-policy', seconds: 6, query: {scenarioId: 'S2-M01', nodeId: 'policy_agent', attempt: 1}, caption: 'The policy route identifies eligibility, required evidence, and the approving role.'},
      {id: 's2-course', seconds: 5, query: {scenarioId: 'S2-M01', nodeId: 'course_agent', attempt: 1}, caption: 'Course checks expose the prerequisite and confirm the remaining feasibility conditions.'},
      {id: 's2-precheck', seconds: 5, query: {scenarioId: 'S2-M01', nodeId: 'pre_action_verifier', attempt: 1}, caption: 'The verifier concludes that review is possible, but autonomous execution is not.', accent: 'amber'},
      {id: 's2-decision', seconds: 6, frameId: 's2-m01-approval-decision', caption: 'The simulated reviewer sees the exact request, policy basis, evidence, and consequence before deciding.', accent: 'amber'},
      {id: 's2-action', seconds: 4, frameId: 's2-m01-approval-action', caption: 'The designated role approves explicitly; the agent cannot approve its own request.', accent: 'amber', approvalClick: true},
      {id: 's2-transaction', seconds: 5, query: {scenarioId: 'S2-M01', nodeId: 'transaction', attempt: 1}, caption: 'Only the authorised action is released to the transaction boundary.', accent: 'green'},
      {id: 's2-postcheck', seconds: 4, query: {scenarioId: 'S2-M01', nodeId: 'post_action_verifier', attempt: 1}, caption: 'The system verifies the observed result independently of the approval.', accent: 'green'},
      {id: 's2-final', seconds: 6, frameId: 's2-m01-final-response', caption: 'The response records why the route was valid, who approved it, and what happened.', accent: 'green'},
    ],
  },
  {
    id: 'closing',
    chapter: 'Evidence, not a scripted claim',
    audioFile: 'audio/closing.mp3',
    shots: [
      {id: 'closing-proof', seconds: 10, frameId: 'proof-evaluation', caption: 'Each execution remains inspectable against its expected outcome.', focus: 'full', accent: 'purple'},
      {id: 'closing-metrics', seconds: 10, frameId: 'proof-metrics', caption: 'S7 demonstrates recovery. S2 demonstrates governed intervention.', accent: 'green'},
    ],
  },
];

export const TOTAL_FRAMES = STORYBOARD.reduce(
  (total, scene) => total + scene.shots.reduce((sceneTotal, shot) => sceneTotal + Math.round(shot.seconds * FPS), 0),
  0,
);
