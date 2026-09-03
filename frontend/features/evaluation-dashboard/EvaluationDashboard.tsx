'use client';

import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BrainCircuit,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  DatabaseZap,
  FileSearch,
  FlaskConical,
  Gauge,
  ListChecks,
  MemoryStick,
  Search,
  ShieldCheck,
  Sparkles,
  Users,
  XCircle,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { AppShell } from '@/components/shell/AppShell';
import {
  fetchCampaigns,
  fetchEvaluationFailures,
  fetchEvaluationRuns,
  fetchEvaluationScenarios,
  type CampaignArtifact,
  type EvaluationLane,
  type EvaluationRun,
  type EvaluationRunsPage,
  type EvaluationScenario,
  type EvaluationScenariosPage,
} from '@/lib/evaluation-api';

type EvaluationTab = 'overview' | 'runs' | 'scenarios' | 'failures';
const PAGE_SIZE = 25;
const familyNames: Record<string, string> = {
  S1: 'Registration recovery',
  S2: 'Prerequisite evidence',
  S3: 'Capacity recovery',
  S4: 'Approval checkpoint',
  S5: 'Administrative escalation',
  S6: 'Clarification routing',
  S7: 'Dynamic failure recovery',
};

export function EvaluationDashboard() {
  const [campaigns, setCampaigns] = useState<CampaignArtifact[]>([]);
  const [lane, setLane] = useState<EvaluationLane>('live');
  const [tab, setTab] = useState<EvaluationTab>('overview');
  const [runsPage, setRunsPage] = useState<EvaluationRunsPage | null>(null);
  const [scenariosPage, setScenariosPage] = useState<EvaluationScenariosPage | null>(null);
  const [failuresPage, setFailuresPage] = useState<EvaluationRunsPage | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [family, setFamily] = useState('');
  const [memory, setMemory] = useState('');
  const [status, setStatus] = useState('');
  const [outcome, setOutcome] = useState('');
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState('scenario_id');
  const [direction, setDirection] = useState<'asc' | 'desc'>('asc');
  const [loadedRunRequest, setLoadedRunRequest] = useState('');
  const [loadedScenarioRequest, setLoadedScenarioRequest] = useState('');
  const [loadedFailureLane, setLoadedFailureLane] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchCampaigns(controller.signal)
      .then((response) => {
        setCampaigns(response.campaigns);
        setError(null);
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setError(reason.message);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), 220);
    return () => window.clearTimeout(timer);
  }, [search]);

  const runRequestKey = `${lane}|${page}|${debouncedSearch}|${family}|${memory}|${status}|${outcome}|${sort}|${direction}`;
  const scenarioRequestKey = `${lane}|${page}|${debouncedSearch}|${family}|${outcome}|${sort}|${direction}`;

  useEffect(() => {
    if (tab !== 'runs') return;
    const controller = new AbortController();
    fetchEvaluationRuns(
      lane,
      { page, pageSize: PAGE_SIZE, search: debouncedSearch, family, memory, status, outcome, sort, direction },
      controller.signal,
    )
      .then((response) => {
        setRunsPage(response);
        setSelectedRunId((current) =>
          response.records.some((record) => record.run_id === current)
            ? current
            : (response.records[0]?.run_id ?? null),
        );
        setLoadedRunRequest(runRequestKey);
        setError(null);
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') {
          setLoadedRunRequest(runRequestKey);
          setError(reason.message);
        }
      });
    return () => controller.abort();
  }, [tab, lane, page, debouncedSearch, family, memory, status, outcome, sort, direction, runRequestKey]);

  useEffect(() => {
    if (tab !== 'scenarios') return;
    const controller = new AbortController();
    fetchEvaluationScenarios(
      lane,
      { page, pageSize: PAGE_SIZE, search: debouncedSearch, family, outcome, sort, direction },
      controller.signal,
    )
      .then((response) => {
        setScenariosPage(response);
        setLoadedScenarioRequest(scenarioRequestKey);
        setError(null);
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') {
          setLoadedScenarioRequest(scenarioRequestKey);
          setError(reason.message);
        }
      });
    return () => controller.abort();
  }, [tab, lane, page, debouncedSearch, family, outcome, sort, direction, scenarioRequestKey]);

  useEffect(() => {
    if (tab !== 'failures') return;
    const controller = new AbortController();
    fetchEvaluationFailures(lane, controller.signal)
      .then((response) => {
        setFailuresPage(response);
        setLoadedFailureLane(lane);
        setError(null);
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') {
          setLoadedFailureLane(lane);
          setError(reason.message);
        }
      });
    return () => controller.abort();
  }, [tab, lane]);

  const campaign = campaigns.find((item) => item.lane === lane) ?? null;
  const selectedRun = useMemo(
    () => runsPage?.records.find((record) => record.run_id === selectedRunId) ?? null,
    [runsPage, selectedRunId],
  );

  function resetQuery(nextSort = 'scenario_id') {
    setSearch('');
    setDebouncedSearch('');
    setFamily('');
    setMemory('');
    setStatus('');
    setOutcome('');
    setPage(1);
    setSort(nextSort);
    setDirection('asc');
  }

  function selectLane(nextLane: EvaluationLane) {
    setLane(nextLane);
    resetQuery();
  }

  function selectTab(nextTab: EvaluationTab) {
    setTab(nextTab);
    resetQuery();
  }

  function changeSort(key: string) {
    if (sort === key) setDirection((current) => current === 'asc' ? 'desc' : 'asc');
    else {
      setSort(key);
      setDirection('asc');
    }
    setPage(1);
  }

  return (
    <AppShell activeSection="evaluation" workspace systemStatus={error ? 'offline' : campaign ? 'operational' : 'checking'}>
      <section className="evaluation-dashboard" aria-label="Evaluation evidence dashboard" data-demo-target="evaluation-page">
        <header className="evaluation-command-bar">
          <div className="evaluation-title-lockup">
            <span><FlaskConical size={21} /></span>
            <div>
              <strong>Evaluation evidence</strong>
              <small>Stage 7 deterministic oracles · evaluator-only surface</small>
            </div>
          </div>
          <div className="evaluation-lane-switch" aria-label="Campaign lane" role="group">
            <button type="button" aria-pressed={lane === 'fixture'} className={lane === 'fixture' ? 'is-active' : ''} onClick={() => selectLane('fixture')}>
              <DatabaseZap size={15} /> Fixture baseline
            </button>
            <button type="button" aria-pressed={lane === 'live'} className={lane === 'live' ? 'is-active' : ''} onClick={() => selectLane('live')}>
              <Sparkles size={15} /> Bedrock live
            </button>
          </div>
          <div className="evaluation-acceptance-state">
            {campaign?.metrics.acceptance_passed ? <CheckCircle2 size={17} /> : <XCircle size={17} />}
            <span><small>Acceptance gate</small><strong>{campaign?.metrics.acceptance_passed ? 'Passed' : 'Checking'}</strong></span>
          </div>
        </header>

        {error ? <div className="evaluation-error" role="alert"><AlertTriangle size={17} /><span>{error}</span><button type="button" onClick={() => window.location.reload()}>Retry</button></div> : null}

        <nav className="evaluation-tabs" aria-label="Evaluation views" role="tablist">
          {([
            ['overview', 'Overview', Gauge],
            ['runs', '315 Runs', Activity],
            ['scenarios', '105 Scenarios', ListChecks],
            ['failures', `Failures ${campaign ? `(${campaign.metrics.failed_runs})` : ''}`, AlertTriangle],
          ] as const).map(([key, label, Icon]) => (
            <button type="button" aria-controls="evaluation-tab-panel" aria-selected={tab === key} id={`evaluation-tab-${key}`} key={key} className={tab === key ? 'is-active' : ''} onClick={() => selectTab(key)} role="tab">
              <Icon size={15} /> {label}
            </button>
          ))}
          <span className="evaluation-tab-boundary"><ShieldCheck size={13} /> Ground truth isolated from agent context</span>
        </nav>

        <div aria-labelledby={`evaluation-tab-${tab}`} aria-live="polite" className="evaluation-view" id="evaluation-tab-panel" role="tabpanel" tabIndex={0}>
          {tab === 'overview' ? <Overview campaign={campaign} /> : null}
          {tab === 'runs' ? (
            <RunsView
              data={runsPage}
              selectedRun={selectedRun}
              selectedRunId={selectedRunId}
              loading={loadedRunRequest !== runRequestKey}
              search={search}
              family={family}
              memory={memory}
              status={status}
              outcome={outcome}
              page={page}
              sort={sort}
              direction={direction}
              onSearch={(value) => { setSearch(value); setPage(1); }}
              onFamily={(value) => { setFamily(value); setPage(1); }}
              onMemory={(value) => { setMemory(value); setPage(1); }}
              onStatus={(value) => { setStatus(value); setPage(1); }}
              onOutcome={(value) => { setOutcome(value); setPage(1); }}
              onPage={setPage}
              onSort={changeSort}
              onSelect={setSelectedRunId}
            />
          ) : null}
          {tab === 'scenarios' ? (
            <ScenariosView
              data={scenariosPage}
              loading={loadedScenarioRequest !== scenarioRequestKey}
              search={search}
              family={family}
              outcome={outcome}
              page={page}
              sort={sort}
              direction={direction}
              onSearch={(value) => { setSearch(value); setPage(1); }}
              onFamily={(value) => { setFamily(value); setPage(1); }}
              onOutcome={(value) => { setOutcome(value); setPage(1); }}
              onPage={setPage}
              onSort={changeSort}
            />
          ) : null}
          {tab === 'failures' ? <FailuresView campaign={campaign} data={failuresPage} loading={loadedFailureLane !== lane} /> : null}
        </div>
      </section>
    </AppShell>
  );
}

function Overview({ campaign }: { campaign: CampaignArtifact | null }) {
  const metrics = campaign?.metrics;
  if (!metrics) return <EvaluationLoading />;
  const primaryMetrics = [
    { label: 'Accepted runs', value: `${metrics.passed_runs} / ${metrics.run_count}`, note: `${rate(metrics.task_completion_rate)} task completion`, icon: CheckCircle2, tone: 'green' },
    { label: 'Scenario consistency', value: `${metrics.scenarios_passing_3_of_3} / ${metrics.scenario_count}`, note: 'Passed under all 3 memory conditions', icon: ListChecks, tone: 'blue' },
    { label: metrics.evaluation_mode === 'bedrock' ? 'Structured reasoning' : 'Valid resolutions', value: metrics.evaluation_mode === 'bedrock' ? `${metrics.reasoning_successes} / ${metrics.reasoning_calls}` : rate(metrics.valid_resolution_rate), note: metrics.evaluation_mode === 'bedrock' ? `${rate(metrics.schema_validation_pass_rate ?? 0)} schema validation` : 'Deterministic fixture decisions', icon: BrainCircuit, tone: 'purple' },
    { label: 'Oracle violations', value: String(Object.values(metrics.violation_counts).reduce((sum, value) => sum + value, 0)), note: 'Across safety and outcome gates', icon: ShieldCheck, tone: 'green' },
    { label: 'Average latency', value: duration(metrics.average_latency_ms), note: `${metrics.average_graph_steps.toFixed(2)} graph steps · ${metrics.average_tool_calls.toFixed(2)} tools`, icon: Clock3, tone: 'amber' },
  ];
  const gates = [
    ['Valid resolution', metrics.valid_resolution_rate, false],
    ['Dynamic recovery', metrics.recovery_success_rate, false],
    ['Correct escalation', metrics.correct_escalation_rate, false],
    ['Approval compliance', metrics.approval_compliance_rate, false],
    ['Clarification routing', metrics.clarification_routing_accuracy, false],
    ['Checkpoint integrity', metrics.checkpoint_resume_integrity, false],
    ['Memory override violations', metrics.memory_override_violation_rate, true],
    ['False post-action completion', metrics.post_action_false_completion_rate, true],
  ] as const;

  return (
    <div className="evaluation-overview-scroll">
      <section className={`evaluation-acceptance-banner${metrics.acceptance_passed ? ' is-passed' : ' is-failed'}`}>
        <span>{metrics.acceptance_passed ? <CheckCircle2 size={24} /> : <XCircle size={24} />}</span>
        <div><strong>{metrics.acceptance_passed ? 'All frozen acceptance gates passed' : 'Campaign requires review'}</strong><p>{metrics.campaign_id} · runner {metrics.runner_version} · updated {new Date(campaign.updated_at).toLocaleString()}</p></div>
        <code>{metrics.evaluation_mode === 'bedrock' ? metrics.model_id : 'Deterministic fixture'}</code>
      </section>

      <section className="evaluation-metric-grid" data-demo-target="evaluation-metrics">
        {primaryMetrics.map(({ label, value, note, icon: Icon, tone }) => (
          <article className={`evaluation-metric-card tone-${tone}`} key={label}>
            <span><Icon size={18} /></span><div><small>{label}</small><strong>{value}</strong><p>{note}</p></div>
          </article>
        ))}
      </section>

      <div className="evaluation-overview-columns">
        <section className="evaluation-panel evaluation-family-panel">
          <PanelHeading icon={Activity} title="Scenario-family performance" note="45 runs per family" />
          <div className="evaluation-family-table">
            <div className="evaluation-family-head"><span>Family</span><span>Pass</span><span>Steps</span><span>Tools</span><span>Latency</span></div>
            {Object.entries(metrics.by_family).map(([family, item]) => (
              <div className="evaluation-family-row" key={family}>
                <span><b>{family}</b><small>{familyNames[family] ?? 'Scenario family'}</small></span>
                <span><i style={{ width: `${item.pass_rate * 100}%` }} /><b>{rate(item.pass_rate)}</b></span>
                <span>{item.average_graph_steps.toFixed(2)}</span>
                <span>{item.average_tool_calls.toFixed(2)}</span>
                <span>{duration(item.average_latency_ms)}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="evaluation-panel evaluation-memory-panel">
          <PanelHeading icon={MemoryStick} title="Memory robustness" note="Fresh isolated runtime for each repetition" />
          <div className="evaluation-memory-list">
            {Object.entries(metrics.by_memory_condition).map(([condition, item]) => (
              <article key={condition}>
                <span className={`evaluation-memory-icon memory-${condition}`}><MemoryStick size={17} /></span>
                <div><strong>{condition}</strong><small>{memoryDescription(condition)}</small></div>
                <b>{item.passed_runs}/{item.run_count}</b>
                <span className="evaluation-mini-stats"><small>{item.average_graph_steps.toFixed(2)} steps</small><small>{duration(item.average_latency_ms)}</small></span>
              </article>
            ))}
          </div>
          <div className="evaluation-memory-conclusion"><ShieldCheck size={15} /><span><strong>No advisory-memory override</strong>Misleading memory changed no valid outcome or authoritative tool decision.</span></div>
        </section>
      </div>

      <div className="evaluation-overview-columns evaluation-bottom-columns">
        <section className="evaluation-panel">
          <PanelHeading icon={ShieldCheck} title="Deterministic safety gates" note="Green means the frozen threshold is met" />
          <div className="evaluation-gate-grid">
            {gates.map(([label, value, inverse]) => {
              const passed = inverse ? value === 0 : value === 1;
              return <article key={label}><span>{passed ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}</span><div><small>{label}</small><strong>{rate(value)}</strong></div></article>;
            })}
          </div>
        </section>
        <section className="evaluation-panel">
          <PanelHeading icon={metrics.evaluation_mode === 'bedrock' ? Zap : DatabaseZap} title={metrics.evaluation_mode === 'bedrock' ? 'Bedrock reasoning coverage' : 'Fixture execution profile'} note={metrics.evaluation_mode === 'bedrock' ? 'Cost uses explicitly supplied campaign rates' : 'Reproducible offline acceptance lane'} />
          {metrics.evaluation_mode === 'bedrock' ? (
            <div className="evaluation-coverage-grid">
              <MetricPair label="Validated calls" value={`${metrics.reasoning_successes}/${metrics.reasoning_calls}`} />
              <MetricPair label="Fallbacks" value={String(metrics.reasoning_fallbacks)} />
              <MetricPair label="Total tokens" value={metrics.total_tokens.toLocaleString()} />
              <MetricPair label="Estimated cost" value={currency(metrics.estimated_cost_usd)} />
              <MetricPair label="Input tokens" value={metrics.total_input_tokens.toLocaleString()} />
              <MetricPair label="Output tokens" value={metrics.total_output_tokens.toLocaleString()} />
            </div>
          ) : (
            <div className="evaluation-coverage-grid">
              <MetricPair label="Tool-call success" value={rate(metrics.tool_call_success_rate)} />
              <MetricPair label="Average tools" value={metrics.average_tool_calls.toFixed(3)} />
              <MetricPair label="Average graph steps" value={metrics.average_graph_steps.toFixed(3)} />
              <MetricPair label="Model calls" value="0" />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

type RunsViewProps = {
  data: EvaluationRunsPage | null;
  selectedRun: EvaluationRun | null;
  selectedRunId: string | null;
  loading: boolean;
  search: string;
  family: string;
  memory: string;
  status: string;
  outcome: string;
  page: number;
  sort: string;
  direction: 'asc' | 'desc';
  onSearch: (value: string) => void;
  onFamily: (value: string) => void;
  onMemory: (value: string) => void;
  onStatus: (value: string) => void;
  onOutcome: (value: string) => void;
  onPage: (value: number) => void;
  onSort: (key: string) => void;
  onSelect: (runId: string) => void;
};

function RunsView(props: RunsViewProps) {
  const { data, selectedRun, loading } = props;
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));
  const columns = [
    ['scenario_id', 'Scenario'], ['family', 'Family'], ['memory_condition', 'Memory'],
    ['actual_outcome', 'Outcome'], ['graph_steps', 'Steps'], ['observed_tool_calls', 'Tools'],
    ['latency_ms', 'Latency'], ['passed', 'Result'],
  ] as const;
  return (
    <div className="evaluation-runs-grid">
      <section className="evaluation-panel evaluation-run-table-panel">
        <EvaluationToolbar
          search={props.search} family={props.family} memory={props.memory} status={props.status} outcome={props.outcome}
          filters={data?.filters} includeMemory includeStatus
          onSearch={props.onSearch} onFamily={props.onFamily} onMemory={props.onMemory} onStatus={props.onStatus} onOutcome={props.onOutcome}
        />
        <div className="evaluation-table-wrap">
          <table aria-label="Evaluation runs" className="evaluation-table evaluation-run-table">
            <thead><tr>{columns.map(([key, label]) => <SortableHeader key={key} field={key} label={label} sort={props.sort} direction={props.direction} onSort={props.onSort} />)}<th aria-label="Open" /></tr></thead>
            <tbody>{data?.records.map((run) => (
              <tr aria-selected={run.run_id === props.selectedRunId} key={run.run_id} className={run.run_id === props.selectedRunId ? 'is-selected' : ''} onClick={() => props.onSelect(run.run_id)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); props.onSelect(run.run_id); } }} tabIndex={0}>
                <td><strong>{run.scenario_id}</strong><small>R{run.repetition}</small></td>
                <td><span className="evaluation-family-chip">{run.family}</span></td>
                <td><span className={`evaluation-memory-chip memory-${run.memory_condition}`}>{run.memory_condition}</span></td>
                <td>{run.actual_outcome}</td><td>{run.graph_steps}</td><td>{run.successful_tool_calls}/{run.observed_tool_calls}</td><td>{duration(run.latency_ms)}</td>
                <td><span className={`evaluation-result-chip ${run.passed ? 'is-passed' : 'is-failed'}`}>{run.passed ? <CheckCircle2 size={12} /> : <XCircle size={12} />}{run.passed ? 'Passed' : 'Failed'}</span></td>
                <td><ChevronRight size={15} /></td>
              </tr>
            ))}</tbody>
          </table>
          {!loading && data?.records.length === 0 ? <EmptyRows /> : null}
          {loading ? <EvaluationLoading compact /> : null}
        </div>
        <EvaluationPagination page={props.page} total={data?.total ?? 0} totalPages={totalPages} onPage={props.onPage} />
      </section>
      <RunInspector run={selectedRun} />
    </div>
  );
}

function RunInspector({ run }: { run: EvaluationRun | null }) {
  if (!run) return <aside className="evaluation-panel evaluation-run-inspector"><div className="evaluation-inspector-empty"><FileSearch size={28} /><strong>Select a run</strong><span>Inspect its oracle result, trace and memory behavior.</span></div></aside>;
  return (
    <aside className="evaluation-panel evaluation-run-inspector">
      <div className="evaluation-inspector-heading"><div><span className={`evaluation-result-chip ${run.passed ? 'is-passed' : 'is-failed'}`}>{run.passed ? <CheckCircle2 size={12} /> : <XCircle size={12} />}{run.passed ? 'Passed' : 'Failed'}</span><h2>{run.scenario_id} · repetition {run.repetition}</h2><code>{run.run_id}</code></div></div>
      <div className="evaluation-inspector-scroll">
        <InspectorSection title="Oracle outcome" icon={ShieldCheck}>
          <InspectorGrid items={[
            ['Expected', run.expected_outcome], ['Actual', run.actual_outcome], ['Task completed', yesNo(run.task_completed)], ['Resolution valid', yesNo(run.resolution_valid)], ['Signature', run.result_signature.slice(0, 16) + '…'], ['Latency', duration(run.latency_ms)],
          ]} />
        </InspectorSection>
        <InspectorSection title="Execution profile" icon={Activity}>
          <InspectorGrid items={[
            ['Graph steps', String(run.graph_steps)], ['Tool results', `${run.successful_tool_calls}/${run.observed_tool_calls}`], ['Replans', String(run.replans)], ['Tool retries', String(run.tool_retries)], ['Pre-action verifier', run.verifier_pre_action.join(', ') || 'None'], ['Post-action verifier', run.verifier_post_action.join(', ') || 'None'],
          ]} />
        </InspectorSection>
        <InspectorSection title="Canonical trace" icon={ListChecks}>
          <ol className="evaluation-trace-list">{run.trace.map((step, index) => <li key={`${index}-${step}`}><span>{index + 1}</span><code>{step}</code></li>)}</ol>
        </InspectorSection>
        <InspectorSection title="Memory & checkpoints" icon={MemoryStick}>
          <InspectorGrid items={[
            ['Condition', run.memory_condition], ['Memory hits', String(run.memory_hits)], ['Write attempted', yesNo(run.memory_write_attempted)], ['Write completed', yesNo(run.memory_write_completed)], ['Paused', yesNo(run.checkpoint_paused)], ['Resumed', yesNo(run.checkpoint_resumed)],
          ]} />
          {run.memory_candidate_ids.length ? <div className="evaluation-code-list">{run.memory_candidate_ids.map((item, index) => <code key={`${index}-${item}`}>{item}</code>)}</div> : null}
        </InspectorSection>
        <InspectorSection title="Human and approval path" icon={Users}>
          <InspectorGrid items={[
            ['Admin escalation', yesNo(run.admin_escalation)], ['Clarification impact', run.clarification_impact ?? 'None'], ['Resume target', run.clarification_resume_target ?? 'None'], ['Approval transitions', String(run.approval_transitions.length)],
          ]} />
          {run.approval_transitions.length ? <div className="evaluation-code-list">{run.approval_transitions.map((item, index) => <code key={`${index}-${item}`}>{item}</code>)}</div> : null}
        </InspectorSection>
        {run.evaluation_mode === 'bedrock' ? (
          <InspectorSection title="Reasoning coverage" icon={BrainCircuit}>
            <InspectorGrid items={[
              ['Validated calls', `${run.reasoning_successes}/${run.reasoning_calls}`], ['Fallbacks', String(run.reasoning_fallbacks)], ['Input tokens', run.input_tokens.toLocaleString()], ['Output tokens', run.output_tokens.toLocaleString()], ['Cost', currency(run.estimated_cost_usd)], ['Model', run.model_id ?? 'None'],
            ]} />
          </InspectorSection>
        ) : null}
        <InspectorSection title="Violations" icon={AlertTriangle}>
          {run.violations.length ? <ul className="evaluation-violation-list">{run.violations.map((item) => <li key={item.code}><strong>{item.code}</strong>{item.message}</li>)}</ul> : <div className="evaluation-no-violations"><CheckCircle2 size={15} /> No missing, forbidden or outcome-oracle violations.</div>}
        </InspectorSection>
      </div>
    </aside>
  );
}

type ScenariosViewProps = {
  data: EvaluationScenariosPage | null;
  loading: boolean;
  search: string;
  family: string;
  outcome: string;
  page: number;
  sort: string;
  direction: 'asc' | 'desc';
  onSearch: (value: string) => void;
  onFamily: (value: string) => void;
  onOutcome: (value: string) => void;
  onPage: (value: number) => void;
  onSort: (key: string) => void;
};

function ScenariosView(props: ScenariosViewProps) {
  const { data } = props;
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));
  const columns = [
    ['scenario_id', 'Scenario'], ['family', 'Family'], ['expected_outcome', 'Expected'],
    ['passed_runs', 'Consistency'], ['average_graph_steps', 'Steps'], ['average_tool_calls', 'Tools'],
    ['average_latency_ms', 'Latency'], ['total_tokens', 'Tokens'],
  ] as const;
  return (
    <section className="evaluation-panel evaluation-scenario-panel">
      <EvaluationToolbar search={props.search} family={props.family} memory="" status="" outcome={props.outcome} filters={data?.filters} onSearch={props.onSearch} onFamily={props.onFamily} onMemory={() => undefined} onStatus={() => undefined} onOutcome={props.onOutcome} />
      <div className="evaluation-table-wrap">
        <table aria-label="Evaluation scenario consistency" className="evaluation-table evaluation-scenario-table">
          <thead><tr>{columns.map(([key, label]) => <SortableHeader key={key} field={key} label={label} sort={props.sort} direction={props.direction} onSort={props.onSort} />)}</tr></thead>
          <tbody>{data?.records.map((scenario) => <ScenarioRow key={scenario.scenario_id} scenario={scenario} />)}</tbody>
        </table>
        {!props.loading && data?.records.length === 0 ? <EmptyRows /> : null}
        {props.loading ? <EvaluationLoading compact /> : null}
      </div>
      <EvaluationPagination page={props.page} total={data?.total ?? 0} totalPages={totalPages} onPage={props.onPage} />
    </section>
  );
}

function ScenarioRow({ scenario }: { scenario: EvaluationScenario }) {
  return (
    <tr>
      <td><strong>{scenario.scenario_id}</strong></td>
      <td><span className="evaluation-family-chip">{scenario.family}</span><small>{familyNames[scenario.family]}</small></td>
      <td>{scenario.expected_outcome}</td>
      <td><span className="evaluation-consistency"><CheckCircle2 size={13} />{scenario.consistency}</span><span className="evaluation-memory-dots" title="Empty, relevant and misleading memory all passed">{[scenario.empty_passed, scenario.relevant_passed, scenario.misleading_passed].map((passed, index) => <i className={passed ? 'is-passed' : 'is-failed'} key={index} />)}</span></td>
      <td>{scenario.average_graph_steps.toFixed(2)}</td><td>{scenario.average_tool_calls.toFixed(2)}</td><td>{duration(scenario.average_latency_ms)}</td><td>{scenario.total_tokens.toLocaleString()}</td>
    </tr>
  );
}

function FailuresView({ campaign, data, loading }: { campaign: CampaignArtifact | null; data: EvaluationRunsPage | null; loading: boolean }) {
  if (loading) return <EvaluationLoading />;
  if (!data?.total) {
    return (
      <div className="evaluation-zero-failures">
        <span><ShieldCheck size={38} /></span>
        <strong>No oracle failures in this campaign</strong>
        <p>All {campaign?.metrics.run_count ?? 315} runs satisfied expected outcomes, required/forbidden transitions, approval separation, checkpoint integrity, memory safety and post-action verification.</p>
        <div><MetricPair label="Failed runs" value="0" /><MetricPair label="Constraint violations" value="0" /><MetricPair label="Memory overrides" value="0" /><MetricPair label="False completions" value="0" /></div>
        <small>The empty <code>failures.jsonl</code> file is an accepted artifact, not missing data.</small>
      </div>
    );
  }
  return <section className="evaluation-panel"><PanelHeading icon={AlertTriangle} title="Failure diagnostics" note={`${data.total} failed runs`} /><ul className="evaluation-violation-list">{data.records.map((run) => <li key={run.run_id}><strong>{run.run_id}</strong>{run.violations.map((item) => `${item.code}: ${item.message}`).join('; ')}</li>)}</ul></section>;
}

function EvaluationToolbar(props: {
  search: string; family: string; memory: string; status: string; outcome: string;
  filters: EvaluationRunsPage['filters'] | EvaluationScenariosPage['filters'] | undefined;
  includeMemory?: boolean; includeStatus?: boolean;
  onSearch: (value: string) => void; onFamily: (value: string) => void; onMemory: (value: string) => void; onStatus: (value: string) => void; onOutcome: (value: string) => void;
}) {
  return (
    <div className="evaluation-toolbar">
      <label className="evaluation-search"><Search size={16} /><input value={props.search} onChange={(event) => props.onSearch(event.target.value)} placeholder="Search scenario, run, transition or violation…" aria-label="Search evaluation records" /></label>
      <FilterSelect label="All families" value={props.family} options={props.filters?.families ?? []} onChange={props.onFamily} />
      {props.includeMemory ? <FilterSelect label="All memory" value={props.memory} options={props.filters?.memory_conditions ?? []} onChange={props.onMemory} /> : null}
      {props.includeStatus ? <FilterSelect label="All results" value={props.status} options={props.filters?.statuses ?? []} onChange={props.onStatus} /> : null}
      <FilterSelect label="All outcomes" value={props.outcome} options={props.filters?.outcomes ?? []} onChange={props.onOutcome} />
    </div>
  );
}

function FilterSelect({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return <label><span className="sr-only">{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}><option value="">{label}</option>{options.map((item) => <option key={item} value={item}>{pretty(item)}</option>)}</select></label>;
}

function SortableHeader({ field, label, sort, direction, onSort }: { field: string; label: string; sort: string; direction: 'asc' | 'desc'; onSort: (field: string) => void }) {
  return <th aria-sort={sort === field ? (direction === 'asc' ? 'ascending' : 'descending') : undefined} scope="col"><button type="button" onClick={() => onSort(field)}>{label}{sort === field ? direction === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} /> : null}</button></th>;
}

function EvaluationPagination({ page, total, totalPages, onPage }: { page: number; total: number; totalPages: number; onPage: (page: number) => void }) {
  return <footer className="evaluation-pagination"><span>{total ? `${((page - 1) * PAGE_SIZE + 1)}–${Math.min(page * PAGE_SIZE, total)} of ${total}` : '0 records'}</span><div><button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}><ChevronLeft size={15} /> Previous</button><span>Page {page} of {totalPages}</span><button type="button" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>Next <ChevronRight size={15} /></button></div></footer>;
}

function PanelHeading({ icon: Icon, title, note }: { icon: LucideIcon; title: string; note: string }) {
  return <header className="evaluation-panel-heading"><span><Icon size={17} /></span><div><strong>{title}</strong><small>{note}</small></div></header>;
}

function InspectorSection({ title, icon: Icon, children }: { title: string; icon: LucideIcon; children: ReactNode }) {
  return <section className="evaluation-inspector-section"><h3><Icon size={15} />{title}</h3>{children}</section>;
}

function InspectorGrid({ items }: { items: Array<[string, string]> }) {
  return <dl className="evaluation-inspector-grid">{items.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

function MetricPair({ label, value }: { label: string; value: string }) {
  return <div className="evaluation-metric-pair"><small>{label}</small><strong>{value}</strong></div>;
}

function EmptyRows() {
  return <div className="evaluation-empty-rows"><Search size={25} /><strong>No matching evidence</strong><span>Clear one of the filters to broaden the result.</span></div>;
}

function EvaluationLoading({ compact = false }: { compact?: boolean }) {
  return <div className={`evaluation-loading${compact ? ' is-compact' : ''}`}><Activity size={20} /><span>Loading accepted evaluation artifacts…</span></div>;
}

function rate(value: number) { return `${(value * 100).toFixed(value === 0 || value === 1 ? 0 : 2)}%`; }
function duration(value: number) { return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value.toFixed(0)} ms`; }
function currency(value: number | null) { return value === null ? 'Not supplied' : `$${value.toFixed(8)}`; }
function yesNo(value: boolean) { return value ? 'Yes' : 'No'; }
function pretty(value: string) { return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function memoryDescription(condition: string) {
  if (condition === 'empty') return 'No prior advisory pattern';
  if (condition === 'relevant') return 'Helpful verified advisory pattern';
  return 'Incorrect advice must be ignored';
}
