import type { ReactNode } from 'react';
import {
  ArrowRight,
  BrainCircuit,
  ChevronDown,
  CircleAlert,
  CircleCheck,
  Database,
  Info,
  ListTree,
  MessageSquareText,
  ShieldCheck,
  Wrench,
} from 'lucide-react';
import { ProvenanceBadge } from '@/components/common/ProvenanceBadge';
import type { RunSnapshot } from '@/lib/runtime-api';
import { NODE_SUMMARIES } from './workspace-data';

type MetaInspectorProps = { runSnapshot: RunSnapshot | null; selectedNodeId: string };

const toolCatalog = [
  { name: 'Student Record', group: 'Academic', status: 'Available' },
  { name: 'Degree Audit', group: 'Academic', status: 'Available' },
  { name: 'Curriculum Lookup', group: 'Academic', status: 'Available' },
  { name: 'Policy Search', group: 'Policy', status: 'Available' },
  { name: 'Exception Eligibility', group: 'Policy', status: 'Available' },
  { name: 'Approval Requirement', group: 'Policy', status: 'Ready' },
  { name: 'Required Documents', group: 'Policy', status: 'Available' },
  { name: 'Course Search', group: 'Course', status: 'Available' },
  { name: 'Prerequisite Check', group: 'Course', status: 'Available' },
  { name: 'Timetable Check', group: 'Course', status: 'Available' },
  { name: 'Workload Check', group: 'Course', status: 'Available' },
  { name: 'Availability', group: 'Course', status: 'Available' },
  { name: 'Request Approval', group: 'Action', status: 'Not called' },
  { name: 'Approval Status', group: 'Action', status: 'Not called' },
  { name: 'Submit Registration', group: 'Action', status: 'Not called' },
  { name: 'Submit Exception / Waiver', group: 'Action', status: 'Not called' },
  { name: 'Transaction Status', group: 'Action', status: 'Not called' },
  { name: 'Experience Memory Search', group: 'Memory', status: 'Available' },
  { name: 'Experience Memory Write', group: 'Memory', status: 'Locked' },
];

function relevanceLabel(relevance: number | null) {
  if (relevance === null) return 'Past pattern';
  if (relevance >= 0.75) return 'Highly relevant';
  if (relevance >= 0.45) return 'Possibly relevant';
  return 'Reference only';
}

function InspectorSection({
  children,
  icon: Icon,
  open = false,
  title,
}: {
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
  const liveNodeDetail = runSnapshot?.node_details[selectedNodeId];
  const selectedTools = new Set(liveNodeDetail?.tool_names.length ? liveNodeDetail.tool_names : selected.tools);
  const liveTools = new Map(runSnapshot?.tools.map((tool) => [tool.name, tool]) ?? []);
  const displayedTools = toolCatalog.map((tool) => ({ ...tool, ...liveTools.get(tool.name) }));
  for (const tool of runSnapshot?.tools ?? []) {
    if (!displayedTools.some((item) => item.name === tool.name)) displayedTools.push(tool);
  }
  const working = runSnapshot?.working_state;
  const thread = runSnapshot?.thread_memory;

  return (
    <aside aria-label="Tools and memory inspector" className="workspace-panel meta-panel">
      <div className="meta-scroll-content">
        <section className="selected-node-callout">
          <Info aria-hidden="true" size={14} />
          <div><strong>Inspector follows selected node</strong><span>{selectedTools.size ? `${selectedTools.size} observed or related tool${selectedTools.size > 1 ? 's' : ''} highlighted below.` : 'This orchestration node uses no external tool.'}</span></div>
        </section>

        <InspectorSection icon={ListTree} open title="Working state">
          <div className="natural-language-summary"><strong>What is happening</strong><p>{working?.narrative ?? 'A plain-language progress explanation will appear as the case runs.'}</p></div>
          {working?.narrative_known.length ? (
            <div className="case-briefing-block"><strong>What we know</strong><ul>{working.narrative_known.map((fact) => <li key={fact}>{fact}</li>)}</ul></div>
          ) : null}
          {working?.narrative_next ? <div className="case-next-step"><ArrowRight size={14} /><span><strong>Next</strong>{working.narrative_next}</span></div> : null}
          {working?.narrative_attention ? <div className="case-attention"><CircleAlert size={14} /><span><strong>Needs attention</strong>{working.narrative_attention}</span></div> : null}
          <details className="meta-recorded-facts">
            <summary>View run details</summary>
            <div className="meta-recorded-content">
              <dl className="processed-state-list">
                <div><dt>Current step</dt><dd>{working?.current_step ?? 'Not started'}</dd></div>
                <div><dt>Plan</dt><dd>{working?.plan ?? 'No plan yet'}</dd></div>
                <div><dt>Route</dt><dd>{working?.route ?? 'Awaiting intake'}</dd></div>
                <div><dt>Replans</dt><dd>{working ? `${working.replans} of ${working.max_replans}` : '0 of 4'}</dd></div>
                <div><dt>Tool retries</dt><dd>{working ? `${working.tool_retries} of ${working.max_tool_retries}` : '0 of 2'}</dd></div>
                <div><dt>Status</dt><dd>{working?.status ?? 'Idle'}</dd></div>
              </dl>
              <div className="processed-summary-box"><strong>Candidate resolution</strong><p>{working?.candidate_resolution ?? 'No candidate assembled yet.'}</p></div>
              {working?.plan_rationale ? <div className="processed-summary-box"><strong>Plan rationale</strong><p>{working.plan_rationale}</p></div> : null}
              {working?.plan_steps.length ? (
                <ol className="inspector-plan-list">
                  {working.plan_steps.map((step) => (
                    <li key={`${step.ordinal}-${step.purpose}`}><span>{step.ordinal}</span><div><strong>{step.specialist?.replaceAll('_', ' ') ?? 'Control step'}</strong><p>{step.purpose}</p></div><b>{step.status}</b></li>
                  ))}
                </ol>
              ) : null}
              {working?.evidence.length ? (
                <div className="inspector-evidence-list">
                  {working.evidence.map((item) => (
                    <article key={`${item.specialist}-${item.summary}`}>
                      <header><strong>{item.specialist.replaceAll('_', ' ')}</strong><span>{item.completeness_known ? 'Complete' : 'Incomplete'}</span></header>
                      <p>{item.summary}</p><small>{item.source_ids.length} source(s) · {item.rule_ids.length} rule(s)</small>
                    </article>
                  ))}
                </div>
              ) : null}
              {working?.action ? <div className="processed-summary-box"><strong>Action record · {working.action.replaceAll('_', ' ')}</strong>{working.action_parameters.map((item) => <p key={item.label}><b>{item.label}:</b> {item.value}</p>)}</div> : null}
              {working?.reasoning.length ? <div className="reasoning-call-list">{working.reasoning.map((item, index) => <article key={`${item.task}-${index}`}><header><strong>{item.task.replaceAll('_', ' ')}</strong><span>{item.status}</span></header><p>{item.model_id ?? 'Deterministic safety gate'}</p><small>{item.input_tokens + item.output_tokens} tokens · {item.applied ? 'Applied' : 'Safety result retained'}</small></article>)}</div> : null}
              {working?.outstanding_items.length ? <div className="inspector-alert"><strong>Outstanding</strong><p>{working.outstanding_items.join(' · ')}</p></div> : null}
              {working?.errors.length ? <div className="inspector-alert is-error"><strong>Observed errors</strong>{working.errors.map((item) => <p key={item}>{item}</p>)}</div> : null}
            </div>
          </details>
        </InspectorSection>

        <InspectorSection icon={Wrench} open title="Tools">
          <div className="tool-summary-list">
            {displayedTools.map((tool) => (
              <div className={selectedTools.has(tool.name) ? 'is-highlighted' : ''} key={tool.name}>
                <span className="tool-state-icon">{['Completed', 'Success'].includes(tool.status) ? <CircleCheck size={11} /> : <Wrench size={11} />}</span>
                <span><strong>{tool.name}</strong><small>{tool.group} · {tool.status}{'provenance_count' in tool ? ` · ${tool.provenance_count} source group(s)` : ''}</small></span>
                {selectedTools.has(tool.name) ? <b>Selected node</b> : null}
              </div>
            ))}
          </div>
        </InspectorSection>

        <InspectorSection icon={MessageSquareText} open={['clarification', 'human_approval', 'human_admin_review', 'approval_wait'].includes(selectedNodeId)} title="Thread memory">
          <div className="natural-language-summary"><strong>What this case remembers</strong><p>{thread?.narrative ?? 'The case history will be explained here after the first step runs.'}</p></div>
          {thread?.narrative_highlights.length ? <ol className="case-history-list">{thread.narrative_highlights.map((item, index) => <li key={`${index}-${item}`}><span>{index + 1}</span><p>{item}</p></li>)}</ol> : null}
          <details className="meta-recorded-facts">
            <summary>View checkpoint details</summary>
            <div className="meta-recorded-content">
              <dl className="processed-state-list">
                <div><dt>Trace events</dt><dd>{thread?.trace_events ?? 0}</dd></div>
                <div><dt>Clarifications</dt><dd>{thread?.clarifications ?? 0}</dd></div>
                <div><dt>Checkpoints</dt><dd>{thread?.checkpoints ?? 0}</dd></div>
                <div><dt>Pause state</dt><dd>{thread?.pause_state ?? 'None'}</dd></div>
                <div><dt>Latest checkpoint</dt><dd>{thread?.latest_checkpoint ?? 'None recorded'}</dd></div>
              </dl>
              {thread?.events.length ? <ol className="thread-event-list">{thread.events.map((event) => <li key={`${event.sequence}-${event.label}`}><span>{event.sequence}</span><div><strong>{event.label}</strong><small>{event.status} · {new Date(event.occurred_at).toLocaleTimeString()}</small></div></li>)}</ol> : null}
              {thread?.clarification_details.length ? <div className="thread-detail-box"><strong>Clarification record</strong>{thread.clarification_details.map((item) => <p key={item.label}><b>{item.label}:</b> {item.value}</p>)}</div> : null}
              {thread?.approval_details.length ? <div className="thread-detail-box"><strong>Approval record</strong>{thread.approval_details.map((item) => <p key={item.label}><b>{item.label}:</b> {item.value}</p>)}</div> : null}
            </div>
          </details>
        </InspectorSection>

        <InspectorSection icon={Database} open={['memory_retriever', 'memory_updater'].includes(selectedNodeId)} title="Long-term memory">
          {runSnapshot?.long_term_memory.length ? runSnapshot.long_term_memory.map((memory) => (
            <div className="memory-pattern-card" key={memory.memory_id}>
              <header><BrainCircuit size={13} /><strong>{memory.label.replaceAll('_', ' ')}</strong><span>{relevanceLabel(memory.relevance)}</span></header>
              <p>{memory.narrative ?? memory.summary}</p>
              <small className="advisory-memory-note">Past experience only · current evidence still decides this case</small>
              <details className="meta-recorded-facts">
                <summary>View memory record</summary>
                <div className="meta-recorded-content">
                  <dl className="memory-detail-list">
                    <div><dt>Summary</dt><dd>{memory.summary}</dd></div>
                    <div><dt>Applies when</dt><dd>{memory.applicability}</dd></div>
                    <div><dt>Pattern ID</dt><dd>{memory.memory_id}</dd></div>
                    {memory.verified_at ? <div><dt>Verified</dt><dd>{new Date(memory.verified_at).toLocaleString()}</dd></div> : null}
                  </dl>
                  {memory.recovery_steps.length ? <ol className="memory-step-list">{memory.recovery_steps.map((step) => <li key={step}>{step}</li>)}</ol> : null}
                  {memory.failed_patterns.length ? <p className="memory-warning"><strong>Avoid:</strong> {memory.failed_patterns.join(' · ')}</p> : null}
                  {memory.tags.length ? <div className="memory-tags">{memory.tags.map((tag) => <span key={tag}>{tag.replaceAll('_', ' ')}</span>)}</div> : null}
                </div>
              </details>
            </div>
          )) : <div className="memory-pattern-card"><header><BrainCircuit size={13} /><strong>No similar past case used</strong><span>Advisory</span></header><p>The agent is relying on current academic, course and policy evidence for this case.</p></div>}
        </InspectorSection>

        <InspectorSection icon={ShieldCheck} title="Provenance">
          <div className="inspector-provenance-row"><ProvenanceBadge kind="real" /><span>Academic and public policy rules</span></div>
          <div className="inspector-provenance-row"><ProvenanceBadge kind="simulated" /><span>Student, offering and approval state</span></div>
          <div className="inspector-provenance-row"><ProvenanceBadge kind="derived" /><span>Audit and candidate summaries</span></div>
          <div className="inspector-provenance-row"><ProvenanceBadge kind="injected" /><span>Controlled scenario event</span></div>
        </InspectorSection>
      </div>
    </aside>
  );
}
