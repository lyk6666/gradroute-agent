import { useState } from 'react';
import { Copy, Download, FileCheck2 } from 'lucide-react';
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
  const approvalLabel = response?.approval_state.replaceAll('_', ' ') ?? 'Not checked';
  const academicLabel = response?.academic_verified ? 'Verified' : response ? 'Pending' : 'Not checked';
  const policyLabel = response?.policy_verified ? 'Verified' : response ? 'Pending' : 'Not checked';

  async function copyResponse() {
    if (!response) return;
    const text = [
      response.headline,
      response.narrative ?? response.message,
      response.reasoning_heading,
      ...response.validity_reasons.map((item) => `- ${item}`),
      `Request: ${response.request_summary}`,
      `Approval: ${response.approval_summary}`,
      `Transaction: ${response.transaction_summary}`,
      'Next steps:',
      ...response.next_steps.map((item) => `- ${item}`),
      `Evidence: ${response.evidence_ids.join(', ') || 'None recorded'}`,
    ].join('\n\n');
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <section aria-label="Final response" className="workspace-panel response-panel">
      <div className="response-content">
        <div className="response-summary">
          <span>{runSnapshot ? `Run ${runSnapshot.scenario_id}` : `Preview for ${scenario.id}`}</span>
          <strong>{response?.headline ?? (runSnapshot?.status === 'failed' ? 'Run failed safely' : 'A bounded exception path is awaiting verification.')}</strong>
          <p>{response?.narrative ?? response?.message ?? runSnapshot?.error ?? 'The final case explanation will appear after the required checks and actions are complete.'}</p>
        </div>
        {response ? (
          <div className="response-detail-sections">
            <section><strong>Request</strong><p>{response.request_summary}</p></section>
            <section><strong>Verified resolution</strong><p>{response.resolution_summary}</p></section>
            <section className="response-reasoning"><strong>{response.reasoning_heading}</strong><ul>{response.validity_reasons.map((item) => <li key={item}>{item}</li>)}</ul></section>
            {response.action ? <section><strong>Action · {response.action.replaceAll('_', ' ')}</strong>{response.action_parameters.map((item) => <p key={item.label}><b>{item.label}:</b> {item.value}</p>)}</section> : null}
            <section><strong>Approval</strong><p>{response.approval_summary}</p></section>
            <section><strong>Transaction</strong><p>{response.transaction_summary}</p></section>
            {response.academic_basis.length ? <section><strong>Academic and course basis</strong>{response.academic_basis.map((item) => <p key={item}>{item}</p>)}</section> : null}
            {response.policy_basis.length ? <section><strong>Policy basis</strong>{response.policy_basis.map((item) => <p key={item}>{item}</p>)}</section> : null}
            <section><strong>Next steps</strong><ol>{response.next_steps.map((item) => <li key={item}>{item}</li>)}</ol></section>
            <details><summary>Evidence and limitations</summary><p>{response.evidence_ids.join(' · ') || 'No evidence identifiers recorded.'}</p>{response.limitations.map((item) => <p key={item}>{item}</p>)}</details>
          </div>
        ) : null}
        <div className="response-provenance"><FileCheck2 aria-hidden="true" size={13} /><span>Ground truth remains hidden from this surface.</span><ProvenanceBadge kind="derived" /></div>
        <div className="response-checks" aria-label="Resolution checks">
          <span aria-label={`Academic status: ${academicLabel}`} className={response?.academic_verified ? 'is-complete' : 'is-waiting'}>Academic</span>
          <span aria-label={`Policy status: ${policyLabel}`} className={response?.policy_verified ? 'is-complete' : 'is-waiting'}>Policy</span>
          <span aria-label={`Approval status: ${approvalLabel}`} className={approvalClass}>Approval</span>
        </div>
      </div>

      <footer className="response-actions">
        <button aria-live="polite" disabled={!response} onClick={copyResponse} type="button"><Copy size={13} /> {copied ? 'Copied' : 'Copy'}</button>
        <button className="is-primary" disabled={!response || !runSnapshot} onClick={() => runSnapshot && exportResolution(runSnapshot)} type="button">Export resolution <Download size={13} /></button>
      </footer>
    </section>
  );
}
