import { useState } from 'react';
import { CheckCircle2, Clock3, Copy, Download, FileCheck2, ShieldCheck } from 'lucide-react';
import { ProvenanceBadge } from '@/components/common/ProvenanceBadge';
import { exportResolution, type RunSnapshot } from '@/lib/runtime-api';
import type { ScenarioPreview } from './workspace-data';

export function FinalResponsePanel({ runSnapshot, scenario }: { runSnapshot: RunSnapshot | null; scenario: ScenarioPreview }) {
  const [copied, setCopied] = useState(false);
  const response = runSnapshot?.final_response;
  const approvalClass = response?.approval_state === 'REJECTED'
    ? 'is-failed'
    : response && !['PENDING', 'REQUIRED'].includes(response.approval_state)
      ? 'is-complete'
      : 'is-waiting';

  async function copyResponse() {
    if (!response) return;
    await navigator.clipboard.writeText(response.message);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <section aria-label="Final response" className="workspace-panel response-panel">
      <div className="response-content">
        <div className="response-checks" aria-label="Resolution checks">
          <span className={response?.academic_verified ? 'is-complete' : 'is-waiting'}>{response?.academic_verified ? <CheckCircle2 size={13} /> : <Clock3 size={13} />}Academic path</span>
          <span className={response?.policy_verified ? 'is-complete' : 'is-waiting'}>{response?.policy_verified ? <ShieldCheck size={13} /> : <Clock3 size={13} />}Policy path</span>
          <span className={approvalClass}><Clock3 size={13} />{response?.approval_state.replaceAll('_', ' ') ?? 'Approval'}</span>
        </div>
        <div className="response-summary">
          <span>Preview for {scenario.id}</span>
          <strong>{response ? response.status.replaceAll('_', ' ') : runSnapshot?.status === 'failed' ? 'Run failed safely' : 'A bounded exception path is awaiting verification.'}</strong>
          <p>{response?.message ?? runSnapshot?.error ?? 'The final student-facing resolution appears only after the applicable verification, approval, transaction and observation gates.'}</p>
        </div>
        <div className="response-provenance"><FileCheck2 aria-hidden="true" size={13} /><span>Ground truth remains hidden from this surface.</span><ProvenanceBadge kind="derived" /></div>
      </div>

      <footer className="response-actions">
        <button disabled={!response} onClick={copyResponse} type="button"><Copy size={13} /> {copied ? 'Copied' : 'Copy'}</button>
        <button className="is-primary" disabled={!response || !runSnapshot} onClick={() => runSnapshot && exportResolution(runSnapshot)} type="button">Export resolution <Download size={13} /></button>
      </footer>
    </section>
  );
}
