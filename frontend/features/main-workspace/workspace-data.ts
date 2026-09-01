import type { Edge, Node } from '@xyflow/react';
import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  BadgeCheck,
  BookOpen,
  ClipboardCheck,
  ClipboardClock,
  CreditCard,
  Database,
  FileInput,
  GraduationCap,
  LockKeyhole,
  MessageCircleQuestion,
  Network,
  RefreshCw,
  Route,
  Send,
  ShieldCheck,
  Sparkles,
  UserCheck,
  UserCog,
  UserRound,
} from 'lucide-react';

export type NodeStatus = 'idle' | 'completed' | 'running' | 'waiting' | 'failed' | 'skipped';

export type NodeSummary = {
  id: string;
  label: string;
  purpose: string;
  status: NodeStatus;
  input: string;
  output: string;
  stateChange: string;
  tools: string[];
  icon: LucideIcon;
};

export type AgentNodeData = NodeSummary & Record<string, unknown>;

export type ScenarioPreview = {
  id: string;
  family: string;
  title: string;
  challenge: string;
  caseType: string;
  studentId: string;
  programme: string;
  cohort: string;
  studyYear: string;
  request: string;
};

export const PROGRAMMES = [
  ['ACDA', 'Accountancy and Data Science & AI'],
  ['AISC', 'Artificial Intelligence and Society'],
  ['BACF', 'Applied Computing in Finance'],
  ['BCE', 'Computer Engineering and Business'],
  ['BCG', 'Computer Science and Business'],
  ['BTECH-COMP', 'Bachelor of Technology in Computing'],
  ['CE', 'Computer Engineering'],
  ['CE-BUS', 'Computer Engineering with Second Major in Business'],
  ['CE-DANA', 'Computer Engineering with Second Major in Data Analytics'],
  ['CE-ENT', 'Computer Engineering with Second Major in Entrepreneurship'],
  ['CE-ITP', 'Computer Engineering with International Trading'],
  ['CE-SUST', 'Computer Engineering with Second Major in Sustainability'],
  ['CEEC', 'Computer Engineering and Economics'],
  ['CSC', 'Computer Science'],
  ['CSC-BUS', 'Computer Science with Second Major in Business'],
  ['CSC-ENT', 'Computer Science with Second Major in Entrepreneurship'],
  ['CSC-ITP', 'Computer Science with International Trading'],
  ['CSC-SUST', 'Computer Science with Second Major in Sustainability'],
  ['CSEC', 'Computer Science and Economics'],
  ['DSAI', 'Data Science and Artificial Intelligence'],
  ['DSAI-SUST', 'Data Science & AI with Sustainability'],
  ['ECDS', 'Economics and Data Science'],
  ['MACS', 'Mathematical and Computer Sciences'],
] as const;

export const REQUEST_TYPES = [
  ['REGISTRATION_AFTER_DEADLINE', 'Registration after deadline'],
  ['PREREQUISITE_WAIVER', 'Prerequisite evidence or waiver'],
  ['GRADUATION_REQUIREMENT', 'Graduation requirement'],
  ['TIMETABLE_CONFLICT', 'Timetable or workload conflict'],
  ['CROSS_PROGRAMME', 'Integrated or cross-programme path'],
  ['COURSE_UNAVAILABLE', 'Required course unavailable'],
] as const;

const familyDetails: Record<string, Pick<ScenarioPreview, 'title' | 'challenge'>> = {
  S1: {
    title: 'Same-course registration recovery',
    challenge: 'Recover a valid registration path for the same required course.',
  },
  S2: {
    title: 'Prerequisite evidence route',
    challenge: 'Use bounded evidence and approval without inventing a general waiver.',
  },
  S3: {
    title: 'Versioned multi-source reasoning',
    challenge: 'Apply the correct cohort and curriculum version after clarification.',
  },
  S4: {
    title: 'Constraint-heavy index planning',
    challenge: 'Resolve timetable, workload, availability and approval constraints together.',
  },
  S5: {
    title: 'Integrated programme reasoning',
    challenge: 'Use compatible programme-path evidence without mixing curricula.',
  },
  S6: {
    title: 'No valid declared path',
    challenge: 'Clarify or escalate safely rather than fabricate a resolution.',
  },
  S7: {
    title: 'Dynamic registration recovery',
    challenge: 'Observe a failed transaction, replan and verify the recovered result.',
  },
};

const demoRecords = [
  ['S1-M01', 'SIM-AISC-005', 'AISC', '4', 'REGISTRATION_AFTER_DEADLINE', 'CC0015'],
  ['S2-M01', 'SIM-AISC-016', 'AISC', '4', 'PREREQUISITE_WAIVER', 'SC4002'],
  ['S3-M01', 'SIM-DSAI-001', 'DSAI', '4', 'GRADUATION_REQUIREMENT', 'MH1805'],
  ['S4-M01', 'SIM-AISC-011', 'AISC', '4', 'TIMETABLE_CONFLICT', 'CC0001'],
  ['S5-M01', 'SIM-CEEC-008', 'CEEC', '5', 'CROSS_PROGRAMME', 'SC1004'],
  ['S6-M01', 'SIM-CEENT-010', 'CE-ENT', '4', 'COURSE_UNAVAILABLE', 'CC0001'],
  ['S7-M01', 'SIM-CE-010', 'CE', '4', 'REGISTRATION_AFTER_DEADLINE', 'ML0004'],
] as const;

const evaluationRecords = [
  ['S1-E01', 'SIM-AISC-006', 'AISC', '4', 'REGISTRATION_AFTER_DEADLINE', 'SC2304'],
  ['S2-E01', 'SIM-BCE-007', 'BCE', '4', 'PREREQUISITE_WAIVER', 'SC2001'],
  ['S3-E01', 'SIM-BCE-010', 'BCE', '4', 'GRADUATION_REQUIREMENT', 'MH1812'],
  ['S4-E01', 'SIM-BCE-004', 'BCE', '4', 'TIMETABLE_CONFLICT', 'CC0003'],
  ['S5-E01', 'SIM-CEEC-009', 'CEEC', '5', 'CROSS_PROGRAMME', 'SC1007'],
  ['S6-E01', 'SIM-CEENT-011', 'CE-ENT', '4', 'COURSE_UNAVAILABLE', 'SC1006'],
  ['S7-E01', 'SIM-CE-011', 'CE', '4', 'REGISTRATION_AFTER_DEADLINE', 'CC0006'],
] as const;

function makeScenario(record: (typeof demoRecords)[number] | (typeof evaluationRecords)[number]): ScenarioPreview {
  const [id, studentId, programme, studyYear, caseType, course] = record;
  const family = id.slice(0, 2);
  return {
    id,
    family,
    ...familyDetails[family],
    caseType,
    studentId,
    programme,
    cohort: 'AY2025-26',
    studyYear,
    request: `Terminal-stage registration or graduation exception concerning ${course} after normal registration.`,
  };
}

export const DEMO_SCENARIOS = demoRecords.map(makeScenario);
export const EVALUATION_SCENARIOS = evaluationRecords.map(makeScenario);

const summaries: NodeSummary[] = [
  {
    id: 'student_case', label: 'Student / Case', icon: UserRound, status: 'completed',
    purpose: 'Represent the observable intake source before graph execution.',
    input: 'Selected synthetic case and anonymous student profile.',
    output: 'A start request ready for typed intake construction.',
    stateChange: 'No graph state yet; this marker is not counted as a control step.', tools: [],
  },
  {
    id: 'intake_context', label: 'Intake + Context', icon: FileInput, status: 'completed',
    purpose: 'Validate case/session identity and construct agent-safe context.',
    input: 'Case ID, student ID, programme, cohort and request.',
    output: 'Typed observable intake with goal predicates.',
    stateChange: 'Intake context and start request persisted.', tools: ['Exception Eligibility'],
  },
  {
    id: 'memory_retriever', label: 'Memory Retriever', icon: Database, status: 'completed',
    purpose: 'Retrieve deidentified advisory patterns relevant to the current case.',
    input: 'Observable case type and goal only.',
    output: 'Ranked advisory patterns; current tools remain authoritative.',
    stateChange: 'Advisory memories added without changing academic facts.', tools: ['Experience Memory Search'],
  },
  {
    id: 'planner', label: 'Planner', icon: Sparkles, status: 'completed',
    purpose: 'Create or revise a bounded resolution plan.',
    input: 'Intake, advisory patterns, verified evidence and prior failures.',
    output: 'Plan and required specialist domains.',
    stateChange: 'Plan history and specialist request updated.', tools: [],
  },
  {
    id: 'supervisor_router', label: 'Supervisor / Router', icon: Network, status: 'completed',
    purpose: 'Route only to the specialist evidence domains the plan requires.',
    input: 'Current plan and completed specialist evidence.',
    output: 'Next specialist or Resolution Builder route.',
    stateChange: 'Pending specialist queue advanced.', tools: [],
  },
  {
    id: 'degree_audit_agent', label: 'Degree Audit Agent', icon: GraduationCap, status: 'skipped',
    purpose: 'Check earned credit and outstanding curriculum requirements.',
    input: 'Anonymous student, curriculum version and audit identifiers.',
    output: 'Grounded degree requirement evidence.',
    stateChange: 'Academic evidence appended when selected.', tools: ['Student Record', 'Curriculum Lookup', 'Degree Audit'],
  },
  {
    id: 'policy_agent', label: 'Policy Agent', icon: ShieldCheck, status: 'completed',
    purpose: 'Find applicable rules, exception eligibility, documents and approval roles.',
    input: 'Case type, requested action and grounded source identifiers.',
    output: 'Policy path, evidence requirements and approval basis.',
    stateChange: 'Policy evidence appended with provenance.', tools: ['Policy Search', 'Exception Eligibility', 'Approval Requirement', 'Required Documents'],
  },
  {
    id: 'course_agent', label: 'Course Agent', icon: BookOpen, status: 'skipped',
    purpose: 'Evaluate prerequisites, exclusions, schedule, workload and availability.',
    input: 'Candidate courses, registrations and live simulated offerings.',
    output: 'Feasible course/index alternatives and constraint evidence.',
    stateChange: 'Course feasibility evidence appended when selected.', tools: ['Course Search', 'Prerequisite Check', 'Timetable Check', 'Workload Check', 'Availability'],
  },
  {
    id: 'resolution_builder', label: 'Resolution Builder', icon: Route, status: 'completed',
    purpose: 'Combine compatible evidence into a candidate resolution.',
    input: 'Current plan plus completed specialist evidence.',
    output: 'Approval-bound or direct action candidate.',
    stateChange: 'Action candidate created for independent verification.', tools: [],
  },
  {
    id: 'clarification', label: 'Clarification', icon: MessageCircleQuestion, status: 'idle',
    purpose: 'Request missing facts and route small or material changes correctly.',
    input: 'Missing fields, question and impact classification.',
    output: 'Validated answers with a verifier or planner resume target.',
    stateChange: 'Clarification pause and response persisted.', tools: [],
  },
  {
    id: 'pre_action_verifier', label: 'Pre-action Verifier', icon: BadgeCheck, status: 'running',
    purpose: 'Fail closed on academic, policy, document, provenance and version gaps.',
    input: 'Candidate resolution and complete evidence set.',
    output: 'Valid, replan, clarify or escalate decision.',
    stateChange: 'Verification history records PRE_ACTION phase.', tools: [],
  },
  {
    id: 'action_gate', label: 'Action Gate', icon: LockKeyhole, status: 'idle',
    purpose: 'Allow writes only after a valid pre-action decision and correct approval route.',
    input: 'Verified candidate and approval requirement.',
    output: 'Transaction, Human Approval or Human/Admin Review route.',
    stateChange: 'Selected protected-action route recorded.', tools: ['Approval Requirement'],
  },
  {
    id: 'human_approval', label: 'Human Approval', icon: UserCheck, status: 'idle',
    purpose: 'Request, observe and validate an approval decision without self-approval.',
    input: 'Approval-bound action, evidence, approver role and version.',
    output: 'Approved, rejected or pending authoritative status.',
    stateChange: 'Approval request/response and intermediate receipt persisted.', tools: ['Request Approval', 'Approval Status'],
  },
  {
    id: 'pause_checkpoint', label: 'Approval Wait', icon: ClipboardClock, status: 'idle',
    purpose: 'Persist a pending approval checkpoint and resume safely.',
    input: 'Approval ID, expected version and pending status.',
    output: 'Validated wake-up routed back to Human Approval.',
    stateChange: 'Thread paused without replaying approval or transaction writes.', tools: [],
  },
  {
    id: 'human_admin_review', label: 'Human / Admin Review', icon: UserCog, status: 'idle',
    purpose: 'Prepare an evidence-backed handoff when no safe autonomous path remains.',
    input: 'Blockers, attempted plans, evidence and required role.',
    output: 'Administrative handoff and recommended next step.',
    stateChange: 'Admin handoff recorded separately from approval.', tools: [],
  },
  {
    id: 'transaction', label: 'Transaction', icon: CreditCard, status: 'idle',
    purpose: 'Execute exactly one typed, idempotent final write.',
    input: 'Verified action candidate and current state version.',
    output: 'Durable action receipt or normalized failure.',
    stateChange: 'Action receipt appended without duplicate replay.', tools: ['Submit Registration', 'Submit Exception / Waiver', 'Transaction Status'],
  },
  {
    id: 'observation', label: 'Observation', icon: Activity, status: 'idle',
    purpose: 'Normalize the authoritative result of the attempted action.',
    input: 'Transaction receipt and current simulated world state.',
    output: 'Observed success, dynamic failure or administrative boundary.',
    stateChange: 'Observation bound to the candidate receipt.', tools: ['Transaction Status'],
  },
  {
    id: 'post_action_verifier', label: 'Post-action Verifier', icon: ClipboardCheck, status: 'idle',
    purpose: 'Confirm the durable goal is complete after action.',
    input: 'Observation, receipts and declared goal predicates.',
    output: 'Done or continue/failure decision.',
    stateChange: 'Verification history records POST_ACTION phase.', tools: [],
  },
  {
    id: 'final_response', label: 'Final Response', icon: Send, status: 'idle',
    purpose: 'Present a verified resolution, safe failure or administrative handoff.',
    input: 'Goal evaluation, evidence and final route.',
    output: 'Human-readable outcome and next actions.',
    stateChange: 'Terminal outcome persisted.', tools: [],
  },
  {
    id: 'memory_updater', label: 'Memory Updater', icon: RefreshCw, status: 'idle',
    purpose: 'Write a deidentified pattern only after verified completion.',
    input: 'Verified DONE, final receipt and privacy-safe summary.',
    output: 'Advisory memory write result.',
    stateChange: 'Memory update completed only when permitted.', tools: ['Experience Memory Write'],
  },
];

export const NODE_SUMMARIES = Object.fromEntries(summaries.map((item) => [item.id, item]));

const nodePositions: Record<string, { x: number; y: number }> = {
  student_case: { x: 0, y: 0 }, intake_context: { x: 220, y: 0 }, memory_retriever: { x: 450, y: 0 }, planner: { x: 680, y: 0 },
  supervisor_router: { x: 680, y: 95 }, degree_audit_agent: { x: 390, y: 190 }, policy_agent: { x: 680, y: 190 }, course_agent: { x: 970, y: 190 },
  resolution_builder: { x: 680, y: 285 }, clarification: { x: 970, y: 285 }, pre_action_verifier: { x: 680, y: 380 },
  human_admin_review: { x: 390, y: 475 }, action_gate: { x: 680, y: 475 }, human_approval: { x: 970, y: 475 }, pause_checkpoint: { x: 1165, y: 565 },
  observation: { x: 390, y: 580 }, transaction: { x: 680, y: 580 }, post_action_verifier: { x: 390, y: 685 },
  final_response: { x: 680, y: 685 }, memory_updater: { x: 970, y: 685 },
};

export const INITIAL_GRAPH_NODES: Node<AgentNodeData>[] = summaries.map((summary) => ({
  id: summary.id,
  type: 'agentNode',
  position: nodePositions[summary.id],
  data: summary,
  selected: summary.id === 'human_approval',
  draggable: false,
}));

type EdgeKind = 'completed' | 'active' | 'conditional' | 'replan' | 'success' | 'danger' | 'waiting';

function edge(
  id: string,
  source: string,
  target: string,
  label?: string,
  kind: EdgeKind = 'conditional',
  handles: [string, string] = ['bottom', 'top'],
): Edge {
  return {
    id,
    source,
    target,
    label,
    sourceHandle: handles[0],
    targetHandle: handles[1],
    type: 'smoothstep',
    className: `flow-edge edge-${kind}`,
    animated: kind === 'active',
    labelBgPadding: [4, 2],
    labelBgBorderRadius: 4,
    labelStyle: { fontSize: 8, fontWeight: 700, fill: '#475569' },
    labelBgStyle: { fill: '#ffffff', fillOpacity: 0.92 },
  };
}

export const GRAPH_EDGES: Edge[] = [
  edge('e-student-intake', 'student_case', 'intake_context', undefined, 'completed', ['right', 'left']),
  edge('e-intake-memory', 'intake_context', 'memory_retriever', undefined, 'completed', ['right', 'left']),
  edge('e-memory-planner', 'memory_retriever', 'planner', undefined, 'completed', ['right', 'left']),
  edge('e-planner-router', 'planner', 'supervisor_router', undefined, 'completed'),
  edge('e-planner-admin', 'planner', 'human_admin_review', 'No safe route', 'conditional', ['left', 'top']),
  edge('e-router-audit', 'supervisor_router', 'degree_audit_agent', 'Academic', 'conditional'),
  edge('e-router-policy', 'supervisor_router', 'policy_agent', 'Policy', 'completed'),
  edge('e-router-course', 'supervisor_router', 'course_agent', 'Course', 'conditional'),
  edge('e-audit-policy', 'degree_audit_agent', 'policy_agent', 'Next specialist', 'conditional', ['right', 'left']),
  edge('e-policy-course', 'policy_agent', 'course_agent', 'Next specialist', 'conditional', ['right', 'left']),
  edge('e-audit-builder', 'degree_audit_agent', 'resolution_builder', undefined, 'conditional'),
  edge('e-policy-builder', 'policy_agent', 'resolution_builder', undefined, 'completed'),
  edge('e-course-builder', 'course_agent', 'resolution_builder', undefined, 'conditional'),
  edge('e-builder-pre', 'resolution_builder', 'pre_action_verifier', undefined, 'active'),
  edge('e-pre-action', 'pre_action_verifier', 'action_gate', 'Valid', 'conditional'),
  edge('e-pre-planner', 'pre_action_verifier', 'planner', 'Replan', 'replan', ['right', 'right']),
  edge('e-pre-clarify', 'pre_action_verifier', 'clarification', 'Clarify', 'waiting', ['right', 'left']),
  edge('e-pre-admin', 'pre_action_verifier', 'human_admin_review', 'Escalate', 'danger', ['left', 'right']),
  edge('e-clarify-pre', 'clarification', 'pre_action_verifier', 'Small change', 'waiting', ['bottom', 'right']),
  edge('e-clarify-planner', 'clarification', 'planner', 'Material change', 'replan', ['right', 'right']),
  edge('e-gate-transaction', 'action_gate', 'transaction', 'No approval', 'conditional'),
  edge('e-gate-approval', 'action_gate', 'human_approval', 'Approval required', 'waiting', ['right', 'top']),
  edge('e-gate-admin', 'action_gate', 'human_admin_review', 'Blocked', 'danger', ['left', 'right']),
  edge('e-approval-transaction', 'human_approval', 'transaction', 'Approved', 'success', ['bottom', 'right']),
  edge('e-approval-planner', 'human_approval', 'planner', 'Rejected', 'danger', ['right', 'right']),
  edge('e-approval-pause', 'human_approval', 'pause_checkpoint', 'Pending', 'waiting', ['right', 'left']),
  edge('e-pause-approval', 'pause_checkpoint', 'human_approval', 'Resume', 'waiting', ['top', 'right']),
  edge('e-transaction-observation', 'transaction', 'observation', undefined, 'conditional', ['left', 'right']),
  edge('e-transaction-admin', 'transaction', 'human_admin_review', 'Domain limit', 'danger', ['left', 'bottom']),
  edge('e-observation-post', 'observation', 'post_action_verifier', undefined, 'conditional'),
  edge('e-post-planner', 'post_action_verifier', 'planner', 'Continue / failure', 'replan', ['right', 'right']),
  edge('e-post-final', 'post_action_verifier', 'final_response', 'Done', 'success', ['right', 'left']),
  edge('e-post-memory', 'post_action_verifier', 'memory_updater', 'Verified DONE', 'success', ['bottom', 'bottom']),
  edge('e-admin-final', 'human_admin_review', 'final_response', 'Handoff', 'conditional', ['bottom', 'left']),
];

export const TIMELINE_EVENTS = [
  { nodeId: 'intake_context', label: 'Intake validated', time: '09:41:02', status: 'completed' as NodeStatus },
  { nodeId: 'memory_retriever', label: 'Memory retrieved', time: '09:41:03', status: 'completed' as NodeStatus },
  { nodeId: 'planner', label: 'Plan created', time: '09:41:04', status: 'completed' as NodeStatus },
  { nodeId: 'supervisor_router', label: 'Policy route selected', time: '09:41:05', status: 'completed' as NodeStatus },
  { nodeId: 'policy_agent', label: 'Policy evidence found', time: '09:41:07', status: 'completed' as NodeStatus },
  { nodeId: 'resolution_builder', label: 'Candidate assembled', time: '09:41:09', status: 'completed' as NodeStatus },
  { nodeId: 'pre_action_verifier', label: 'Verifying candidate', time: '09:41:10', status: 'running' as NodeStatus },
  { nodeId: 'action_gate', label: 'Action gate', time: '—', status: 'idle' as NodeStatus },
  { nodeId: 'human_approval', label: 'Simulated approval', time: '—', status: 'idle' as NodeStatus },
  { nodeId: 'transaction', label: 'Transaction', time: '—', status: 'idle' as NodeStatus },
  { nodeId: 'post_action_verifier', label: 'Outcome verification', time: '—', status: 'idle' as NodeStatus },
  { nodeId: 'final_response', label: 'Final response', time: '—', status: 'idle' as NodeStatus },
];
