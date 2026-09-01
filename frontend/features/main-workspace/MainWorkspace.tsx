'use client';

import { useState } from 'react';
import { AppShell } from '@/components/shell/AppShell';
import { AgentGraphCanvas } from './AgentGraphCanvas';
import { ExecutionTimeline } from './ExecutionTimeline';
import { FinalResponsePanel } from './FinalResponsePanel';
import {
  InputPanel,
  type IntakeMode,
  type RunMode,
  type ScenarioSplit,
} from './InputPanel';
import { MetaInspector } from './MetaInspector';
import { DEMO_SCENARIOS, EVALUATION_SCENARIOS, type ScenarioPreview } from './workspace-data';

export function MainWorkspace() {
  const [intakeMode, setIntakeMode] = useState<IntakeMode>('scenario');
  const [runMode, setRunMode] = useState<RunMode>('normal');
  const [scenarioSplit, setScenarioSplit] = useState<ScenarioSplit>('demo');
  const [scenario, setScenario] = useState<ScenarioPreview>(DEMO_SCENARIOS[6]);
  const [selectedNodeId, setSelectedNodeId] = useState('human_approval');

  function changeScenarioSplit(split: ScenarioSplit) {
    setScenarioSplit(split);
    setScenario(split === 'demo' ? DEMO_SCENARIOS[0] : EVALUATION_SCENARIOS[0]);
  }

  return (
    <AppShell activeSection="main" workspace>
      <h1 className="sr-only">Graduation exception case execution workspace</h1>
      <div className="main-dashboard-grid" aria-label="Case execution workspace">
        <InputPanel
          intakeMode={intakeMode}
          onIntakeModeChange={setIntakeMode}
          onRunModeChange={setRunMode}
          onScenarioChange={setScenario}
          onScenarioSplitChange={changeScenarioSplit}
          runMode={runMode}
          scenario={scenario}
          scenarioSplit={scenarioSplit}
        />
        <AgentGraphCanvas onSelectNode={setSelectedNodeId} selectedNodeId={selectedNodeId} />
        <MetaInspector selectedNodeId={selectedNodeId} />
        <ExecutionTimeline onSelectNode={setSelectedNodeId} selectedNodeId={selectedNodeId} />
        <FinalResponsePanel scenario={scenario} />
      </div>
    </AppShell>
  );
}
