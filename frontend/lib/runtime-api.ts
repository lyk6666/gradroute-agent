import type { NodeStatus, ScenarioPreview } from '@/features/main-workspace/workspace-data';

export type ApiStatus = 'checking' | 'operational' | 'offline';
export type RunStatus = 'queued' | 'running' | 'waiting' | 'completed' | 'failed';

export type TimelineItem = {
  sequence: number;
  node_id: string;
  label: string;
  status: NodeStatus;
  occurred_at: string;
};

export type ToolSummary = {
  key: string;
  name: string;
  group: string;
  status: string;
  summary: string;
  provenance_count: number;
};

export type PauseSummary = {
  kind: 'clarification' | 'approval';
  title: string;
  message: string;
  fields: string[];
  impact: string | null;
};

export type FinalResponseSummary = {
  status: string;
  message: string;
  evidence_ids: string[];
  academic_verified: boolean;
  policy_verified: boolean;
  approval_state: string;
  completed_at: string | null;
};

export type RunSnapshot = {
  api_version: '1.0';
  run_id: string;
  scenario_id: string;
  thread_id: string;
  mode: 'normal' | 'step';
  status: RunStatus;
  can_advance: boolean;
  current_node: string | null;
  node_statuses: Record<string, NodeStatus>;
  traversed_edges: string[];
  timeline: TimelineItem[];
  working_state: {
    current_step: string;
    plan: string;
    route: string;
    replans: number;
    max_replans: number;
    tool_retries: number;
    max_tool_retries: number;
    total_steps: number;
    max_total_steps: number;
    status: string;
    candidate_resolution: string;
  };
  tools: ToolSummary[];
  long_term_memory: Array<{
    label: string;
    summary: string;
    relevance: number | null;
    advisory_only: boolean;
  }>;
  thread_memory: {
    trace_events: number;
    clarifications: number;
    checkpoints: number;
    pause_state: string;
    latest_checkpoint: string;
  };
  pause: PauseSummary | null;
  final_response: FinalResponseSummary | null;
  error: string | null;
  latest_event_sequence: number;
};

type ApiScenario = {
  scenario_id: string;
  family: string;
  split: 'demo' | 'evaluation';
  title: string;
  challenge: string;
  case_type: string;
  student_id: string;
  programme: string;
  cohort: string;
  study_year: number;
  request_text: string;
};

type RunEvent = {
  sequence: number;
  event_type: string;
  occurred_at: string;
  run_id: string;
  node_id: string | null;
  message: string;
  snapshot: RunSnapshot;
};

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Runtime request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export async function checkRuntime(): Promise<{ execution_mode: string }> {
  return request('/api/v1/health');
}

export async function loadScenarios(): Promise<ScenarioPreview[]> {
  const scenarios = await request<ApiScenario[]>('/api/v1/scenarios');
  return scenarios.map((item) => ({
    id: item.scenario_id,
    family: item.family,
    title: item.title,
    challenge: item.challenge,
    caseType: item.case_type,
    studentId: item.student_id,
    programme: item.programme,
    cohort: item.cohort,
    studyYear: String(item.study_year),
    request: item.request_text,
  }));
}

export async function startRun(scenarioId: string, mode: 'normal' | 'step'): Promise<RunSnapshot> {
  const response = await request<{ snapshot: RunSnapshot }>('/api/v1/runs', {
    method: 'POST',
    body: JSON.stringify({ scenario_id: scenarioId, mode }),
  });
  return response.snapshot;
}

export async function advanceRun(runId: string): Promise<RunSnapshot> {
  return request(`/api/v1/runs/${runId}/advance`, { method: 'POST' });
}

export async function resumeClarification(
  runId: string,
  answers: Record<string, string | boolean>,
): Promise<RunSnapshot> {
  return request(`/api/v1/runs/${runId}/resume`, {
    method: 'POST',
    body: JSON.stringify({ kind: 'clarification', answers }),
  });
}

export async function recheckApproval(runId: string): Promise<RunSnapshot> {
  return request(`/api/v1/runs/${runId}/resume`, {
    method: 'POST',
    body: JSON.stringify({ kind: 'approval', status: 'PENDING' }),
  });
}

export function subscribeToRun(
  runId: string,
  after: number,
  onEvent: (event: RunEvent) => void,
  onError: () => void,
): EventSource {
  const source = new EventSource(`${API_BASE}/api/v1/runs/${runId}/events?after=${after}`);
  source.onmessage = (message) => onEvent(JSON.parse(message.data) as RunEvent);
  source.onerror = onError;
  return source;
}

export function exportResolution(snapshot: RunSnapshot): void {
  if (!snapshot.final_response) return;
  const payload = [
    `Scenario: ${snapshot.scenario_id}`,
    `Run: ${snapshot.run_id}`,
    `Status: ${snapshot.final_response.status}`,
    '',
    snapshot.final_response.message,
    '',
    `Evidence: ${snapshot.final_response.evidence_ids.join(', ') || 'None recorded'}`,
    `Completed: ${snapshot.final_response.completed_at ?? 'Not recorded'}`,
  ].join('\n');
  const url = URL.createObjectURL(new Blob([payload], { type: 'text/plain;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${snapshot.scenario_id}-${snapshot.run_id}-resolution.txt`;
  anchor.click();
  URL.revokeObjectURL(url);
}
