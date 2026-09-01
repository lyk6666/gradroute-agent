import { AppShell } from '@/components/shell/AppShell';
import { Button } from '@/components/common/Button';
import { Card } from '@/components/common/Card';
import { ProvenanceBadge } from '@/components/common/ProvenanceBadge';
import { StatusChip } from '@/components/common/StatusChip';
import { InspectorPanel, InspectorSection } from '@/components/inspector/InspectorPanel';

const demoCases = [
  {
    id: 'S7-E01',
    label: 'Dynamic registration recovery',
    programme: 'CCDS · Evaluation case',
    status: 'ready' as const,
  },
  {
    id: 'S2-E01',
    label: 'Prerequisite evidence route',
    programme: 'CCDS · Evaluation case',
    status: 'waiting' as const,
  },
  {
    id: 'S6-E01',
    label: 'No valid declared path',
    programme: 'CCDS · Evaluation case',
    status: 'escalated' as const,
  },
];

const workflow = ['Intake', 'Plan', 'Route', 'Verify', 'Act', 'Observe'];

export default function MainPage() {
  return (
    <AppShell activeSection="main">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Stage 8 · UI-1 foundation</p>
          <h1>Case execution workspace</h1>
          <p>
            A transparent control surface for grounded exception resolution.
            Live execution arrives in UI-3.
          </p>
        </div>
        <div className="heading-actions">
          <StatusChip tone="success">Foundation ready</StatusChip>
          <Button disabled>New Case</Button>
        </div>
      </div>

      <div className="workspace-grid">
        <Card as="aside" className="case-rail" title="Demo cases" eyebrow="Scenario split">
          <div className="case-list">
            {demoCases.map((item, index) => (
              <button
                className={`case-item${index === 0 ? ' is-selected' : ''}`}
                key={item.id}
                type="button"
              >
                <span className="case-avatar" aria-hidden="true">
                  {item.id.slice(0, 2)}
                </span>
                <span className="case-copy">
                  <strong>{item.label}</strong>
                  <span>{item.id} · {item.programme}</span>
                  <StatusChip tone={item.status} compact>
                    {item.status === 'ready'
                      ? 'Ready'
                      : item.status === 'waiting'
                        ? 'Awaiting approval'
                        : 'Escalated'}
                  </StatusChip>
                </span>
              </button>
            ))}
          </div>
          <Button variant="secondary" fullWidth disabled>
            View all cases
          </Button>
        </Card>

        <Card
          className="foundation-canvas"
          title="Agent workspace foundation"
          eyebrow="Plan → Act → Observe → Verify → Replan"
          action={<StatusChip tone="active">UI-1</StatusChip>}
        >
          <div className="foundation-message">
            <span className="foundation-mark" aria-hidden="true">✦</span>
            <div>
              <p className="eyebrow">Shared shell established</p>
              <h2>Built around the frozen control plane</h2>
              <p>
                The interactive graph will occupy this primary canvas in UI-2.
                It will expose real node, edge, verifier, approval, and checkpoint
                states without leaking evaluator-only ground truth.
              </p>
            </div>
          </div>

          <ol className="workflow-strip" aria-label="Agent workflow stages">
            {workflow.map((step, index) => (
              <li key={step}>
                <span>{index + 1}</span>
                <strong>{step}</strong>
              </li>
            ))}
          </ol>

          <div className="boundary-grid">
            <div>
              <span className="boundary-icon" aria-hidden="true">G</span>
              <strong>Grounded decisions</strong>
              <p>Current academic, course, policy and registration tools remain authoritative.</p>
            </div>
            <div>
              <span className="boundary-icon" aria-hidden="true">H</span>
              <strong>Human checkpoints</strong>
              <p>Clarification, approval and administrative escalation stay visibly separate.</p>
            </div>
            <div>
              <span className="boundary-icon" aria-hidden="true">V</span>
              <strong>Verified completion</strong>
              <p>Final outcomes appear only after post-action verification.</p>
            </div>
          </div>

          <div className="provenance-row" aria-label="Supported provenance classes">
            <span>Visible provenance:</span>
            <ProvenanceBadge kind="real" />
            <ProvenanceBadge kind="simulated" />
            <ProvenanceBadge kind="derived" />
            <ProvenanceBadge kind="injected" />
          </div>
        </Card>

        <InspectorPanel title="Foundation inspector" subtitle="UI-1 contract">
          <InspectorSection title="Current scope">
            <dl className="inspector-list">
              <div><dt>Route</dt><dd>Main</dd></div>
              <div><dt>Mode</dt><dd>Demo</dd></div>
              <div><dt>Backend</dt><dd>Not connected</dd></div>
              <div><dt>Ground truth</dt><dd>Hidden</dd></div>
            </dl>
          </InspectorSection>
          <InspectorSection title="Delivery status">
            <ul className="check-list">
              <li className="is-done">Application shell</li>
              <li className="is-done">Three-page routing</li>
              <li className="is-done">Visual tokens</li>
              <li>Interactive graph · UI-2</li>
              <li>Live execution · UI-3</li>
            </ul>
          </InspectorSection>
          <InspectorSection title="Prototype boundary">
            <p className="inspector-note">
              Team AIGO research prototype grounded in public NTU CCDS sources.
              It is not an official NTU service.
            </p>
          </InspectorSection>
        </InspectorPanel>
      </div>
    </AppShell>
  );
}
