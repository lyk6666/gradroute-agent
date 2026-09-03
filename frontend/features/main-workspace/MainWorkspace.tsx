'use client';

import { useEffect, useRef, useState } from 'react';
import { AppShell } from '@/components/shell/AppShell';
import {
  advanceRun,
  checkRuntime,
  loadScenarios,
  resumeClarification,
  startManualRun,
  startRun,
  submitApprovalDecision,
  subscribeToRun,
  type ApiStatus,
  type RunSnapshot,
} from '@/lib/runtime-api';
import { AgentGraphCanvas } from './AgentGraphCanvas';
import { ExecutionTimeline } from './ExecutionTimeline';
import { FinalResponsePanel } from './FinalResponsePanel';
import {
  InputPanel,
  type IntakeMode,
  type ManualCaseDraft,
  type RunMode,
  type ScenarioSplit,
} from './InputPanel';
import { MetaInspector } from './MetaInspector';
import { DEMO_SCENARIOS, EVALUATION_SCENARIOS, type ScenarioPreview } from './workspace-data';

export function MainWorkspace() {
  const [runtimeStatus, setRuntimeStatus] = useState<ApiStatus>('checking');
  const [intakeMode, setIntakeMode] = useState<IntakeMode>('scenario');
  const [runMode, setRunMode] = useState<RunMode>('normal');
  const [scenarioSplit, setScenarioSplit] = useState<ScenarioSplit>('demo');
  const [scenario, setScenario] = useState<ScenarioPreview>(DEMO_SCENARIOS[6]);
  const [manualCase, setManualCase] = useState<ManualCaseDraft>({
    profile: DEMO_SCENARIOS[0],
    requestText: DEMO_SCENARIOS[0].request,
    notes: '',
  });
  const [demoScenarios, setDemoScenarios] = useState<ScenarioPreview[]>(DEMO_SCENARIOS);
  const [evaluationScenarios, setEvaluationScenarios] = useState<ScenarioPreview[]>(EVALUATION_SCENARIOS);
  const [selectedNodeId, setSelectedNodeId] = useState('student_case');
  const [runSnapshot, setRunSnapshot] = useState<RunSnapshot | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const streamRef = useRef<EventSource | null>(null);
  const snapshotRef = useRef<RunSnapshot | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([checkRuntime(), loadScenarios()])
      .then(([, items]) => {
        if (!active) return;
        const demos = items.filter((item) => item.id.includes('-M'));
        const evaluations = items.filter((item) => item.id.includes('-E'));
        setDemoScenarios(demos);
        setEvaluationScenarios(evaluations);
        setScenario(demos.find((item) => item.id === 'S7-M01') ?? demos[0]);
        const firstManual = demos.find((item) => item.id === 'S1-M01') ?? demos[0];
        if (firstManual) setManualCase({ profile: firstManual, requestText: firstManual.request, notes: '' });
        setRuntimeStatus('operational');
      })
      .catch((error: unknown) => {
        if (!active) return;
        setRuntimeStatus('offline');
        setRunError(error instanceof Error ? error.message : 'The runtime API is unavailable.');
      });
    return () => {
      active = false;
      streamRef.current?.close();
    };
  }, []);

  function applySnapshot(snapshot: RunSnapshot) {
    snapshotRef.current = snapshot;
    setRunSnapshot(snapshot);
  }

  function connectToRun(snapshot: RunSnapshot) {
    streamRef.current?.close();
    const source = subscribeToRun(
      snapshot.run_id,
      snapshot.latest_event_sequence,
      (event) => {
        applySnapshot(event.snapshot);
        if (event.node_id) setSelectedNodeId(event.node_id);
        if (['completed', 'failed'].includes(event.snapshot.status)) {
          source.close();
        }
      },
      () => {
        const latest = snapshotRef.current;
        if (latest && !['completed', 'failed'].includes(latest.status)) {
          setRunError('The live event stream disconnected. The persisted run can be inspected safely.');
        }
      },
    );
    streamRef.current = source;
  }

  async function handleStart() {
    setRunError(null);
    setSelectedNodeId('intake_context');
    try {
      const snapshot = intakeMode === 'scenario'
        ? await startRun(scenario.id, runMode)
        : await startManualRun({
          profile_scenario_id: manualCase.profile.id,
          student_id: manualCase.profile.studentId,
          programme: manualCase.profile.programme,
          cohort: manualCase.profile.cohort,
          study_year: Number(manualCase.profile.studyYear),
          problem_type: manualCase.profile.caseType,
          request_text: manualCase.requestText,
          notes: manualCase.notes.trim() || null,
        }, runMode);
      applySnapshot(snapshot);
      connectToRun(snapshot);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : 'The run could not be started.');
    }
  }

  async function handleAdvance() {
    if (!runSnapshot) return;
    setRunError(null);
    try {
      applySnapshot(await advanceRun(runSnapshot.run_id));
    } catch (error) {
      setRunError(error instanceof Error ? error.message : 'The next step could not be released.');
    }
  }

  async function handleClarification(answers: Record<string, string | boolean>) {
    if (!runSnapshot) return;
    setRunError(null);
    try {
      const snapshot = await resumeClarification(runSnapshot.run_id, answers);
      applySnapshot(snapshot);
      connectToRun(snapshot);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : 'The clarification could not be submitted.');
    }
  }

  async function handleApprovalDecision(status: 'PENDING' | 'APPROVED' | 'REJECTED', decisionReason?: string) {
    if (!runSnapshot) return;
    setRunError(null);
    try {
      const snapshot = await submitApprovalDecision(runSnapshot.run_id, status, decisionReason);
      applySnapshot(snapshot);
      connectToRun(snapshot);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : 'The approval decision could not be recorded.');
    }
  }

  function changeScenarioSplit(split: ScenarioSplit) {
    setScenarioSplit(split);
    setScenario(split === 'demo' ? demoScenarios[0] : evaluationScenarios[0]);
  }

  return (
    <AppShell activeSection="main" systemStatus={runtimeStatus} workspace>
      <h1 className="sr-only">Graduation exception case execution workspace</h1>
      <div className="main-dashboard-grid" aria-label="Case execution workspace">
        <InputPanel
          canAdvance={runSnapshot?.can_advance ?? false}
          demoScenarios={demoScenarios}
          evaluationScenarios={evaluationScenarios}
          intakeMode={intakeMode}
          manualCase={manualCase}
          onAdvance={handleAdvance}
          onIntakeModeChange={setIntakeMode}
          onManualCaseChange={setManualCase}
          onRunModeChange={setRunMode}
          onScenarioChange={setScenario}
          onScenarioSplitChange={changeScenarioSplit}
          onStart={handleStart}
          runError={runError}
          runMode={runMode}
          runStatus={runSnapshot?.status ?? 'idle'}
          runtimeStatus={runtimeStatus}
          scenario={scenario}
          scenarioSplit={scenarioSplit}
        />
        <AgentGraphCanvas
          onApprovalDecision={handleApprovalDecision}
          onClarificationSubmit={handleClarification}
          onSelectNode={setSelectedNodeId}
          runSnapshot={runSnapshot}
          selectedNodeId={selectedNodeId}
        />
        <MetaInspector runSnapshot={runSnapshot} selectedNodeId={selectedNodeId} />
        <ExecutionTimeline onSelectNode={setSelectedNodeId} runSnapshot={runSnapshot} selectedNodeId={selectedNodeId} />
        <FinalResponsePanel runSnapshot={runSnapshot} scenario={intakeMode === 'manual' ? manualCase.profile : scenario} />
      </div>
    </AppShell>
  );
}
