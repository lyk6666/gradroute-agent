import { AppShell } from '@/components/shell/AppShell';
import { Card } from '@/components/common/Card';
import { StatusChip } from '@/components/common/StatusChip';

const metrics = [
  ['315 / 315', 'Accepted runs'],
  ['105 / 105', 'Scenarios passing 3/3'],
  ['720 / 720', 'Structured live calls'],
  ['0', 'Oracle violations'],
];

export default function EvaluationPage() {
  return (
    <AppShell activeSection="evaluation">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Stage 8 · UI-5 destination</p>
          <h1>Evaluation evidence</h1>
          <p>Measured Stage 7 outcomes, run traces and failure diagnostics.</p>
        </div>
        <StatusChip tone="success">Stage 7 accepted</StatusChip>
      </div>

      <div className="metric-grid">
        {metrics.map(([value, label]) => (
          <Card key={label} className="metric-card">
            <strong>{value}</strong>
            <span>{label}</span>
          </Card>
        ))}
      </div>

      <Card className="route-placeholder" title="Planned UI-5 surface" eyebrow="Evaluation contract">
        <div className="tab-preview" aria-label="Planned evaluation sections">
          <span className="is-active">Overview</span>
          <span>Runs</span>
          <span>Failures</span>
        </div>
        <p>
          The accepted fixture and Bedrock reports will drive this page. Evaluator-only ground
          truth will remain restricted to this evaluation surface and Developer Mode.
        </p>
      </Card>
    </AppShell>
  );
}
