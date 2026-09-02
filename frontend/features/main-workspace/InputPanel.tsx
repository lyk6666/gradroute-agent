import type { ReactNode } from 'react';
import {
  BookOpenCheck,
  ChevronDown,
  CirclePlay,
  FilePlus2,
  FlaskConical,
  ListChecks,
  UserRoundPlus,
} from 'lucide-react';
import { ProvenanceBadge } from '@/components/common/ProvenanceBadge';
import {
  PROGRAMMES,
  REQUEST_TYPES,
  type ScenarioPreview,
} from './workspace-data';

export type IntakeMode = 'scenario' | 'manual';
export type ScenarioSplit = 'demo' | 'evaluation';
export type RunMode = 'normal' | 'step';

type InputPanelProps = {
  canAdvance: boolean;
  demoScenarios: ScenarioPreview[];
  evaluationScenarios: ScenarioPreview[];
  intakeMode: IntakeMode;
  onAdvance: () => void;
  onIntakeModeChange: (mode: IntakeMode) => void;
  onRunModeChange: (mode: RunMode) => void;
  onScenarioChange: (scenario: ScenarioPreview) => void;
  onStart: () => void;
  runError: string | null;
  runMode: RunMode;
  runStatus: 'idle' | 'queued' | 'running' | 'waiting' | 'completed' | 'failed';
  runtimeStatus: 'checking' | 'operational' | 'offline';
  scenario: ScenarioPreview;
  scenarioSplit: ScenarioSplit;
  onScenarioSplitChange: (split: ScenarioSplit) => void;
};

function FieldLabel({ children, optional }: { children: ReactNode; optional?: boolean }) {
  return (
    <span className="form-label">
      {children}
      {optional ? <small>Optional</small> : null}
    </span>
  );
}

function ManualInputForm() {
  return (
    <div className="intake-scroll-content">
      <div className="form-grid">
        <label className="form-field form-field-wide">
          <FieldLabel>Anonymous student ID</FieldLabel>
          <input defaultValue="SIM-NEW-001" aria-label="Anonymous student ID" />
        </label>

        <label className="form-field form-field-wide">
          <FieldLabel>Programme</FieldLabel>
          <span className="select-shell">
            <select defaultValue="CE:Computer Engineering" aria-label="Programme">
              {PROGRAMMES.map(([code, name]) => (
                <option key={`${code}-${name}`} value={`${code}:${name}`}>{code} · {name}</option>
              ))}
            </select>
            <ChevronDown aria-hidden="true" size={13} />
          </span>
        </label>

        <label className="form-field">
          <FieldLabel>Cohort</FieldLabel>
          <span className="select-shell"><select defaultValue="AY2025-26"><option>AY2025-26</option></select><ChevronDown aria-hidden="true" size={13} /></span>
        </label>

        <label className="form-field">
          <FieldLabel>Study year</FieldLabel>
          <span className="select-shell"><select defaultValue="4"><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select><ChevronDown aria-hidden="true" size={13} /></span>
        </label>

        <label className="form-field form-field-wide">
          <FieldLabel>Request type</FieldLabel>
          <span className="select-shell">
            <select defaultValue="REGISTRATION_AFTER_DEADLINE">
              {REQUEST_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <ChevronDown aria-hidden="true" size={13} />
          </span>
        </label>

        <label className="form-field form-field-wide">
          <FieldLabel>Request</FieldLabel>
          <textarea defaultValue="I discovered a required course registration issue after normal registration closed." rows={3} />
        </label>

        <label className="form-field form-field-wide">
          <FieldLabel optional>Notes</FieldLabel>
          <textarea placeholder="Add context that may help the agent ask better questions." rows={2} />
        </label>
      </div>

      <details className="academic-snapshot">
        <summary><BookOpenCheck size={14} /> Academic snapshot <span>Required to execute a new case</span></summary>
        <div className="snapshot-fields">
          <label><FieldLabel>Earned AUs</FieldLabel><input defaultValue="128" inputMode="decimal" /></label>
          <label><FieldLabel>Current semester</FieldLabel><select defaultValue="Semester 1"><option>Semester 1</option><option>Semester 2</option></select></label>
          <label className="form-field-wide"><FieldLabel>Completed courses</FieldLabel><input placeholder="Search and add course codes" /></label>
          <label className="form-field-wide"><FieldLabel>Current registration</FieldLabel><input placeholder="Search and add registered courses" /></label>
          <label className="form-field-wide"><FieldLabel optional>Supporting documents</FieldLabel><input placeholder="Document types or references" /></label>
        </div>
      </details>

      <div className="intake-boundary-note">
        <UserRoundPlus aria-hidden="true" size={15} />
        <span>New-case composition is retained as a guarded input surface. This UI-3 increment executes the frozen scenario package first; manual records will require an explicit validated simulation builder.</span>
      </div>
    </div>
  );
}

function ScenarioForm({
  scenario,
  scenarioSplit,
  demoScenarios,
  evaluationScenarios,
  onScenarioChange,
  onScenarioSplitChange,
}: Pick<InputPanelProps, 'scenario' | 'scenarioSplit' | 'demoScenarios' | 'evaluationScenarios' | 'onScenarioChange' | 'onScenarioSplitChange'>) {
  const options = scenarioSplit === 'demo' ? demoScenarios : evaluationScenarios;

  return (
    <div className="intake-scroll-content">
      <div className="split-selector" aria-label="Scenario set">
        <button aria-pressed={scenarioSplit === 'demo'} className={scenarioSplit === 'demo' ? 'is-active' : ''} onClick={() => onScenarioSplitChange('demo')} type="button">
          <CirclePlay size={13} /> Demo <span>{demoScenarios.length}</span>
        </button>
        <button aria-pressed={scenarioSplit === 'evaluation'} className={scenarioSplit === 'evaluation' ? 'is-active' : ''} onClick={() => onScenarioSplitChange('evaluation')} type="button">
          <FlaskConical size={13} /> Evaluation <span>{evaluationScenarios.length}</span>
        </button>
      </div>

      <label className="form-field scenario-picker">
        <FieldLabel>Scenario</FieldLabel>
        <span className="select-shell">
          <select
            aria-label="Scenario"
            onChange={(event) => {
              const selected = options.find((item) => item.id === event.target.value);
              if (selected) onScenarioChange(selected);
            }}
            value={scenario.id}
          >
            {options.map((item) => <option key={item.id} value={item.id}>{item.id} · {item.title}</option>)}
          </select>
          <ChevronDown aria-hidden="true" size={13} />
        </span>
      </label>

      <section className="scenario-preview-card" aria-label="Selected scenario preview">
        <header>
          <span className="scenario-family">{scenario.family}</span>
          <div><strong>{scenario.title}</strong><small>{scenario.id} · {scenario.caseType.replaceAll('_', ' ')}</small></div>
        </header>
        <div className="scenario-preview-section">
          <span className="preview-label">Expected challenge</span>
          <p>{scenario.challenge}</p>
        </div>
        <div className="scenario-preview-section">
          <span className="preview-label">Request</span>
          <p>{scenario.request}</p>
        </div>
      </section>

      <section className="student-preview-card" aria-label="Synthetic student information">
        <header><UserRoundPlus size={14} /><strong>Student information</strong><ProvenanceBadge kind="simulated" /></header>
        <dl>
          <div><dt>Anonymous ID</dt><dd>{scenario.studentId}</dd></div>
          <div><dt>Programme</dt><dd>{scenario.programme}</dd></div>
          <div><dt>Cohort</dt><dd>{scenario.cohort}</dd></div>
          <div><dt>Study year</dt><dd>Year {scenario.studyYear}</dd></div>
        </dl>
      </section>

      {scenarioSplit === 'evaluation' ? (
        <div className="evaluation-boundary-note"><ListChecks size={14} /><span>Representative UI-2 preview. All 105 held-out cases remain available to the UI-3 API, with ground truth hidden here.</span></div>
      ) : null}
    </div>
  );
}

export function InputPanel(props: InputPanelProps) {
  const activeRun = ['queued', 'running', 'waiting'].includes(props.runStatus);
  const startDisabled = props.runtimeStatus !== 'operational' || props.intakeMode !== 'scenario' || activeRun;
  const stepAction = props.runMode === 'step' && props.runStatus === 'running';
  const buttonLabel = stepAction
    ? (props.canAdvance ? 'Run next graph step' : 'Executing current step…')
    : props.runStatus === 'waiting'
      ? 'Respond in the canvas'
      : props.intakeMode === 'manual'
        ? 'Manual builder not connected'
        : props.runtimeStatus === 'offline'
          ? 'Runtime offline'
          : activeRun
            ? 'Run in progress…'
            : props.runStatus === 'completed'
              ? 'Start a new run'
              : 'Start grounded run';

  return (
    <aside aria-label="Case input" className="workspace-panel intake-panel">
      <div className="mode-tabs" aria-label="Input mode">
        <button aria-pressed={props.intakeMode === 'scenario'} className={props.intakeMode === 'scenario' ? 'is-active' : ''} onClick={() => props.onIntakeModeChange('scenario')} type="button">
          <FlaskConical size={13} /> Scenario
        </button>
        <button aria-pressed={props.intakeMode === 'manual'} className={props.intakeMode === 'manual' ? 'is-active' : ''} onClick={() => props.onIntakeModeChange('manual')} type="button">
          <FilePlus2 size={13} /> Manual input
        </button>
      </div>

      {props.intakeMode === 'scenario' ? <ScenarioForm {...props} /> : <ManualInputForm />}

      <footer className="run-setup-footer">
        <span className="form-label">Run mode</span>
        <div className="run-mode-selector" aria-label="Run mode">
          <button aria-pressed={props.runMode === 'normal'} className={props.runMode === 'normal' ? 'is-active' : ''} onClick={() => props.onRunModeChange('normal')} type="button">Normal run</button>
          <button aria-pressed={props.runMode === 'step'} className={props.runMode === 'step' ? 'is-active' : ''} onClick={() => props.onRunModeChange('step')} type="button">Step-by-step</button>
        </div>
        {props.runError ? <p className="run-error" role="alert">{props.runError}</p> : null}
        <button
          className="start-run-button"
          disabled={stepAction ? !props.canAdvance : startDisabled}
          onClick={stepAction ? props.onAdvance : props.onStart}
          type="button"
        >
          <CirclePlay size={15} /> {buttonLabel}
        </button>
      </footer>
    </aside>
  );
}
