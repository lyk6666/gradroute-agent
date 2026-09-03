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
export type ManualCaseDraft = {
  profile: ScenarioPreview;
  requestText: string;
  notes: string;
};

type InputPanelProps = {
  canAdvance: boolean;
  demoScenarios: ScenarioPreview[];
  evaluationScenarios: ScenarioPreview[];
  intakeMode: IntakeMode;
  manualCase: ManualCaseDraft;
  onAdvance: () => void;
  onIntakeModeChange: (mode: IntakeMode) => void;
  onManualCaseChange: (draft: ManualCaseDraft) => void;
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

function ManualInputForm({
  draft,
  profiles,
  onChange,
}: {
  draft: ManualCaseDraft;
  profiles: ScenarioPreview[];
  onChange: (draft: ManualCaseDraft) => void;
}) {
  const caseTypes = Array.from(new Set(profiles.map((item) => item.caseType)));
  const programmes = Array.from(new Set(profiles.map((item) => item.programme))).sort();
  const selectProfile = (profile: ScenarioPreview) => onChange({
    profile,
    requestText: profile.request,
    notes: draft.notes,
  });

  return (
    <div className="intake-scroll-content">
      <div className="form-grid">
        <label className="form-field form-field-wide">
          <FieldLabel>Anonymous student ID</FieldLabel>
          <span className="select-shell">
            <select
              aria-label="Anonymous student ID"
              onChange={(event) => {
                const profile = profiles.find((item) => item.id === event.target.value);
                if (profile) selectProfile(profile);
              }}
              value={draft.profile.id}
            >
              {profiles.map((item) => <option key={item.id} value={item.id}>{item.studentId} · {item.caseType.replaceAll('_', ' ')}</option>)}
            </select>
            <ChevronDown aria-hidden="true" size={13} />
          </span>
        </label>

        <label className="form-field form-field-wide">
          <FieldLabel>Programme</FieldLabel>
          <span className="select-shell">
            <select
              aria-label="Programme"
              onChange={(event) => {
                const profile = profiles.find((item) => item.programme === event.target.value && item.caseType === draft.profile.caseType)
                  ?? profiles.find((item) => item.programme === event.target.value);
                if (profile) selectProfile(profile);
              }}
              value={draft.profile.programme}
            >
              {programmes.map((code) => {
                const name = PROGRAMMES.find(([item]) => item === code)?.[1] ?? code;
                return <option key={code} value={code}>{code} · {name}</option>;
              })}
            </select>
            <ChevronDown aria-hidden="true" size={13} />
          </span>
        </label>

        <label className="form-field">
          <FieldLabel>Cohort</FieldLabel>
          <span className="select-shell"><select aria-label="Cohort" value={draft.profile.cohort} onChange={() => undefined}><option>{draft.profile.cohort}</option></select><ChevronDown aria-hidden="true" size={13} /></span>
        </label>

        <label className="form-field">
          <FieldLabel>Study year</FieldLabel>
          <span className="select-shell"><select aria-label="Study year" value={draft.profile.studyYear} onChange={() => undefined}><option>{draft.profile.studyYear}</option></select><ChevronDown aria-hidden="true" size={13} /></span>
        </label>

        <label className="form-field form-field-wide">
          <FieldLabel>Request type</FieldLabel>
          <span className="select-shell">
            <select
              aria-label="Request type"
              onChange={(event) => {
                const profile = profiles.find((item) => item.caseType === event.target.value && item.programme === draft.profile.programme)
                  ?? profiles.find((item) => item.caseType === event.target.value);
                if (profile) selectProfile(profile);
              }}
              value={draft.profile.caseType}
            >
              {caseTypes.map((value) => {
                const label = REQUEST_TYPES.find(([item]) => item === value)?.[1] ?? value.replaceAll('_', ' ');
                return <option key={value} value={value}>{label}</option>;
              })}
            </select>
            <ChevronDown aria-hidden="true" size={13} />
          </span>
        </label>

        <label className="form-field form-field-wide">
          <FieldLabel>Request</FieldLabel>
          <textarea onChange={(event) => onChange({ ...draft, requestText: event.target.value })} value={draft.requestText} rows={3} />
        </label>

        <label className="form-field form-field-wide">
          <FieldLabel optional>Notes</FieldLabel>
          <textarea onChange={(event) => onChange({ ...draft, notes: event.target.value })} placeholder="Add context that may help the agent ask better questions." value={draft.notes} rows={2} />
        </label>
      </div>

      <details className="academic-snapshot">
        <summary><BookOpenCheck size={14} /> Academic snapshot <span>Required to execute a new case</span></summary>
        <div className="snapshot-fields">
          <label><FieldLabel>Earned AUs</FieldLabel><input readOnly value={draft.profile.earnedAus} /></label>
          <label><FieldLabel>Profile source</FieldLabel><input readOnly value={draft.profile.id} /></label>
          <label className="form-field-wide"><FieldLabel>Completed courses</FieldLabel><textarea readOnly rows={2} value={draft.profile.completedCourses.join(', ') || 'No explicit completion records'} /></label>
          <label className="form-field-wide"><FieldLabel>Current registration</FieldLabel><textarea readOnly rows={2} value={draft.profile.registeredCourses.join(', ') || 'No current registered courses'} /></label>
          <label className="form-field-wide"><FieldLabel optional>Supporting documents</FieldLabel><textarea readOnly rows={2} value={draft.profile.supportingDocuments.join(', ') || 'None declared'} /></label>
        </div>
      </details>

      <div className="intake-boundary-note">
        <UserRoundPlus aria-hidden="true" size={15} />
        <span>This creates a new request over the selected validated synthetic academic profile. Academic and operational facts remain simulated and are rechecked by the same agent graph.</span>
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
        {scenarioSplit === 'demo' && scenario.expectedResponse ? (
          <div className="scenario-preview-section expected-response-preview">
            <span className="preview-label">Expected response</span>
            <p>{scenario.expectedResponse}</p>
          </div>
        ) : null}
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
  const manualInvalid = props.manualCase.requestText.trim().length < 12;
  const startDisabled = props.runtimeStatus !== 'operational' || activeRun || (props.intakeMode === 'manual' && manualInvalid);
  const stepAction = props.runMode === 'step' && props.runStatus === 'running';
  const buttonLabel = stepAction
    ? (props.canAdvance ? 'Run next graph step' : 'Executing current step…')
    : props.runStatus === 'waiting'
      ? 'Respond in the canvas'
      : props.intakeMode === 'manual' && manualInvalid
        ? 'Enter a complete request'
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

      {props.intakeMode === 'scenario' ? (
        <ScenarioForm {...props} />
      ) : (
        <ManualInputForm
          draft={props.manualCase}
          onChange={props.onManualCaseChange}
          profiles={[...props.demoScenarios, ...props.evaluationScenarios]}
        />
      )}

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
