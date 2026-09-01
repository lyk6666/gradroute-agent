import { CheckCircle2, Clock3, Copy, ExternalLink, FileCheck2, ShieldCheck } from 'lucide-react';
import { ProvenanceBadge } from '@/components/common/ProvenanceBadge';
import type { ScenarioPreview } from './workspace-data';

export function FinalResponsePanel({ scenario }: { scenario: ScenarioPreview }) {
  return (
    <section aria-label="Final response" className="workspace-panel response-panel">
      <div className="response-content">
        <div className="response-checks" aria-label="Resolution checks">
          <span className="is-complete"><CheckCircle2 size={13} />Academic path</span>
          <span className="is-complete"><ShieldCheck size={13} />Policy path</span>
          <span className="is-waiting"><Clock3 size={13} />Approval</span>
        </div>
        <div className="response-summary">
          <span>Preview for {scenario.id}</span>
          <strong>A bounded exception path is being verified.</strong>
          <p>The final student-facing resolution will appear only after pre-action verification, any required human approval, the transaction observation, and post-action verification.</p>
        </div>
        <div className="response-provenance"><FileCheck2 aria-hidden="true" size={13} /><span>Ground truth remains hidden from this surface.</span><ProvenanceBadge kind="derived" /></div>
      </div>

      <footer className="response-actions">
        <button disabled type="button"><Copy size={13} /> Copy</button>
        <button className="is-primary" disabled type="button">Open resolution <ExternalLink size={13} /></button>
      </footer>
    </section>
  );
}
