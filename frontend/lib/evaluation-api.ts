export type EvaluationLane = 'fixture' | 'live';

export type CohortMetrics = {
  run_count: number;
  passed_runs: number;
  pass_rate: number;
  average_graph_steps: number;
  average_tool_calls: number;
  average_latency_ms: number;
};

export type CampaignMetrics = {
  campaign_id: string;
  runner_version: string;
  evaluation_mode: 'fixture' | 'bedrock';
  model_id: string | null;
  scenario_count: number;
  repetitions_per_scenario: number;
  run_count: number;
  passed_runs: number;
  failed_runs: number;
  task_completion_rate: number;
  valid_resolution_rate: number;
  constraint_violation_rate: number;
  recovery_success_rate: number;
  correct_escalation_rate: number;
  approval_compliance_rate: number;
  clarification_routing_accuracy: number;
  checkpoint_resume_integrity: number;
  memory_override_violation_rate: number;
  memory_write_gate_violation_rate: number;
  post_action_false_completion_rate: number;
  tool_call_success_rate: number;
  schema_validation_pass_rate: number | null;
  loop_cap_hit_rate: number;
  scenarios_passing_3_of_3: number;
  scenario_consistency_rate: number;
  average_tool_calls: number;
  average_graph_steps: number;
  average_latency_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  reasoning_calls: number;
  reasoning_successes: number;
  reasoning_fallbacks: number;
  estimated_cost_usd: number | null;
  acceptance_passed: boolean;
  acceptance_failures: string[];
  violation_counts: Record<string, number>;
  by_family: Record<string, CohortMetrics>;
  by_memory_condition: Record<string, CohortMetrics>;
};

export type CampaignArtifact = {
  lane: EvaluationLane;
  updated_at: string;
  metrics: CampaignMetrics;
};

export type EvaluationRun = {
  campaign_id: string;
  runner_version: string;
  scenario_id: string;
  run_id: string;
  repetition: number;
  memory_condition: 'empty' | 'relevant' | 'misleading';
  evaluation_mode: 'fixture' | 'bedrock';
  model_id: string | null;
  family: string;
  expected_outcome: string;
  actual_outcome: string;
  task_completed: boolean;
  resolution_valid: boolean;
  passed: boolean;
  violations: Array<{ code: string; message: string }>;
  required_transitions_missing: string[];
  forbidden_transitions_observed: string[];
  trace: string[];
  verifier_pre_action: string[];
  verifier_post_action: string[];
  observed_tool_calls: number;
  successful_tool_calls: number;
  graph_steps: number;
  replans: number;
  tool_retries: number;
  total_steps: number;
  memory_hits: number;
  memory_candidate_ids: string[];
  memory_write_attempted: boolean;
  memory_write_completed: boolean;
  approval_transitions: string[];
  admin_escalation: boolean;
  clarification_impact: string | null;
  clarification_resume_target: string | null;
  checkpoint_paused: boolean;
  checkpoint_resumed: boolean;
  reasoning_calls: number;
  reasoning_successes: number;
  reasoning_fallbacks: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
  latency_ms: number;
  result_signature: string;
  error_type: string | null;
};

export type EvaluationFilters = {
  families: string[];
  memory_conditions: string[];
  statuses: string[];
  outcomes: string[];
};

export type EvaluationRunsPage = {
  api_version: '1.0';
  lane: EvaluationLane;
  page: number;
  page_size: number;
  total: number;
  records: EvaluationRun[];
  filters: EvaluationFilters;
};

export type EvaluationScenario = {
  scenario_id: string;
  family: string;
  expected_outcome: string;
  passed_runs: number;
  consistency: string;
  empty_passed: boolean;
  relevant_passed: boolean;
  misleading_passed: boolean;
  average_tool_calls: number;
  average_graph_steps: number;
  average_latency_ms: number;
  total_tokens: number;
  violation_codes: string[];
};

export type EvaluationScenariosPage = {
  api_version: '1.0';
  lane: EvaluationLane;
  page: number;
  page_size: number;
  total: number;
  records: EvaluationScenario[];
  filters: EvaluationFilters;
};

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Evaluation request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export function fetchCampaigns(signal?: AbortSignal) {
  return get<{ api_version: '1.0'; campaigns: CampaignArtifact[] }>('/api/v1/evaluation/campaigns', signal);
}

export function fetchEvaluationRuns(
  lane: EvaluationLane,
  query: {
    page: number;
    pageSize: number;
    search: string;
    family: string;
    memory: string;
    status: string;
    outcome: string;
    sort: string;
    direction: 'asc' | 'desc';
  },
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({
    lane,
    page: String(query.page),
    page_size: String(query.pageSize),
    search: query.search,
    family: query.family,
    memory: query.memory,
    status: query.status,
    outcome: query.outcome,
    sort: query.sort,
    direction: query.direction,
  });
  return get<EvaluationRunsPage>(`/api/v1/evaluation/runs?${params}`, signal);
}

export function fetchEvaluationScenarios(
  lane: EvaluationLane,
  query: {
    page: number;
    pageSize: number;
    search: string;
    family: string;
    outcome: string;
    sort: string;
    direction: 'asc' | 'desc';
  },
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({
    lane,
    page: String(query.page),
    page_size: String(query.pageSize),
    search: query.search,
    family: query.family,
    outcome: query.outcome,
    sort: query.sort,
    direction: query.direction,
  });
  return get<EvaluationScenariosPage>(`/api/v1/evaluation/scenarios?${params}`, signal);
}

export function fetchEvaluationFailures(lane: EvaluationLane, signal?: AbortSignal) {
  return get<EvaluationRunsPage>(`/api/v1/evaluation/failures?lane=${lane}&page_size=100`, signal);
}
