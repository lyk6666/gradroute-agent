import { AppShell } from '@/components/shell/AppShell';
import { Card } from '@/components/common/Card';
import { ProvenanceBadge } from '@/components/common/ProvenanceBadge';
import { StatusChip } from '@/components/common/StatusChip';

const domains = [
  ['Academic', 'Courses, curricula, policies and calendar'],
  ['Operational', 'Students, audits, registrations and offerings'],
  ['Case Operations', 'Cases, approvals, transactions and scenarios'],
];

export default function DataPage() {
  return (
    <AppShell activeSection="data">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Stage 8 · UI-4 destination</p>
          <h1>Grounded data explorer</h1>
          <p>Read-only inspection with explicit real, simulated, derived and injected provenance.</p>
        </div>
        <StatusChip tone="neutral">Foundation only</StatusChip>
      </div>

      <div className="route-foundation-grid">
        {domains.map(([title, description]) => (
          <Card key={title} title={title} eyebrow="Data domain">
            <p className="route-card-copy">{description}</p>
            <div className="provenance-row">
              {title === 'Academic' ? <ProvenanceBadge kind="real" /> : null}
              {title !== 'Academic' ? <ProvenanceBadge kind="simulated" /> : null}
              <ProvenanceBadge kind="derived" />
            </div>
          </Card>
        ))}
      </div>

      <Card className="route-placeholder" title="Planned UI-4 surface" eyebrow="Data contract">
        <div className="placeholder-columns" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <p>
          Domain navigation, searchable tables, relationship inspection and source provenance
          will be connected here after the Main workspace stages are approved.
        </p>
      </Card>
    </AppShell>
  );
}
