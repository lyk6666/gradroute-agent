import type { ReactNode } from 'react';
import {
  ArrowRight,
  BrainCircuit,
  ChevronDown,
  CircleAlert,
  Database,
  Info,
  ListTree,
  ShieldCheck,
} from 'lucide-react';
import { ProvenanceBadge } from '@/components/common/ProvenanceBadge';
import type { RunSnapshot } from '@/lib/runtime-api';
import { NODE_SUMMARIES } from './workspace-data';

type MetaInspectorProps = { runSnapshot: RunSnapshot | null; selectedNodeId: string };

function relevanceLabel(relevance: number | null) {
  if (relevance === null) return 'Past lesson';
  if (relevance >= 0.75) return 'Strong match';
  if (relevance >= 0.45) return 'Possible match';
  return 'Reference only';
}

function InspectorSection({ children, icon: Icon, open = false, title }: {
  children: ReactNode;
  icon: typeof BrainCircuit;
  open?: boolean;
  title: string;
}) {
  return (
    <details className="meta-accordion" open={open}>
      <summary><Icon aria-hidden="true" size={14} /><span>{title}</span><ChevronDown aria-hidden="true" size={13} /></summary>
      <div className="meta-accordion-content">{children}</div>
    </details>
  );
}

export function MetaInspector({ runSnapshot, selectedNodeId }: MetaInspectorProps) {
  const selected = NODE_SUMMARIES[selectedNodeId] ?? NODE_SUMMARIES.pre_action_verifier;
  const working = runSnapshot?.working_state;
  const thread = runSnapshot?.thread_memory;

  return (
    <aside aria-label="Case state and memory" className="workspace-panel meta-panel">
      <div className="meta-scroll-content">
        <section className="selected-node-callout">
          <Info aria-hidden="true" size={14} />
          <div><strong>Viewing {selected.label}</strong><span>Case progress and relevant memory are summarised below.</span></div>
        </section>

        <InspectorSection icon={ListTree} open title="Case overview">
          <div className="natural-language-summary"><p>{working?.narrative ?? 'The case is ready to begin from the student’s request.'}</p></div>
          {working?.narrative_known.length ? (
            <div className="case-briefing-block"><strong>Important findings</strong><ul>{working.narrative_known.slice(0, 3).map((fact) => <li key={fact}>{fact}</li>)}</ul></div>
          ) : null}
          {working?.narrative_next ? <div className="case-next-step"><ArrowRight size={14} /><span><strong>Next</strong>{working.narrative_next}</span></div> : null}
          {working?.narrative_attention ? <div className="case-attention"><CircleAlert size={14} /><span><strong>Needs attention</strong>{working.narrative_attention}</span></div> : null}
          {thread?.narrative_highlights.length ? <div className="case-briefing-block case-history-block"><strong>Recent case developments</strong><ol className="case-history-list">{thread.narrative_highlights.slice(-4).map((item, index) => <li key={`${index}-${item}`}><span>{index + 1}</span><p>{item}</p></li>)}</ol></div> : null}
          <details className="meta-recorded-facts">
            <summary>Technical run and checkpoint details</summary>
            <div className="meta-recorded-content">
              <dl className="processed-state-list">
                <div><dt>Current step</dt><dd>{working?.current_step ?? 'Not started'}</dd></div>
                <div><dt>Status</dt><dd>{working?.status ?? 'Idle'}</dd></div>
                <div><dt>Plan</dt><dd>{working?.plan ?? 'No plan yet'}</dd></div>
                <div><dt>Route</dt><dd>{working?.route.replaceAll('_', ' ') ?? 'Awaiting intake'}</dd></div>
                <div><dt>Replans</dt><dd>{working ? `${working.replans} of ${working.max_replans}` : '0 of 4'}</dd></div>
                <div><dt>Clarifications</dt><dd>{thread?.clarifications ?? 0}</dd></div>
                <div><dt>Checkpoints</dt><dd>{thread?.checkpoints ?? 0}</dd></div>
                <div><dt>Waiting for</dt><dd>{thread?.pause_state ?? 'Nothing'}</dd></div>
              </dl>
              {working?.candidate_resolution ? <div className="processed-summary-box"><strong>Proposed resolution</strong><p>{working.candidate_resolution}</p></div> : null}
              {working?.outstanding_items.length ? <div className="inspector-alert"><strong>Outstanding</strong><p>{working.outstanding_items.join(' · ')}</p></div> : null}
              {working?.errors.length ? <div className="inspector-alert is-error"><strong>Observed problems</strong>{working.errors.map((item) => <p key={item}>{item}</p>)}</div> : null}
              {thread?.events.length ? <ol className="thread-event-list">{thread.events.slice(-6).map((event) => <li key={`${event.sequence}-${event.label}`}><div><strong>{event.label}</strong><small>{event.status} · {new Date(event.occurred_at).toLocaleTimeString()}</small></div></li>)}</ol> : null}
            </div>
          </details>
        </InspectorSection>

        <InspectorSection icon={Database} open={['memory_retriever', 'memory_updater'].includes(selectedNodeId)} title="Relevant past lessons">
          {runSnapshot?.long_term_memory.length ? runSnapshot.long_term_memory.slice(0, 2).map((memory) => (
            <article className="memory-pattern-card" key={memory.memory_id}>
              <header><BrainCircuit size={13} /><strong>{memory.label.replaceAll('_', ' ')}</strong><span>{relevanceLabel(memory.relevance)}</span></header>
              <p>{memory.narrative ?? memory.summary}</p>
              <p className="memory-applicability"><strong>Useful when:</strong> {memory.applicability}</p>
              <small className="advisory-memory-note">Past experience only; current case evidence still decides.</small>
            </article>
          )) : <div className="memory-pattern-card"><header><BrainCircuit size={13} /><strong>No similar case used</strong><span>Advisory</span></header><p>The decision relies on the current case evidence.</p></div>}
        </InspectorSection>

        <InspectorSection icon={ShieldCheck} title="Information sources">
          <div className="inspector-provenance-row"><ProvenanceBadge kind="real" /><span>Academic and public policy information</span></div>
          <div className="inspector-provenance-row"><ProvenanceBadge kind="simulated" /><span>Student, offering, approval and transaction state</span></div>
          <div className="inspector-provenance-row"><ProvenanceBadge kind="derived" /><span>Case checks and resolution reasoning</span></div>
        </InspectorSection>
      </div>
    </aside>
  );
}
