import type { ReactNode } from 'react';
import {
  BrainCircuit,
  ChevronDown,
  CircleCheck,
  Clock3,
  Database,
  History,
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
  { name: 'Policy Search', group: 'Policy', status: 'Completed' },
  { name: 'Exception Eligibility', group: 'Policy', status: 'Completed' },
  { name: 'Approval Requirement', group: 'Policy', status: 'Ready' },
  { name: 'Required Documents', group: 'Policy', status: 'Completed' },
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
  { name: 'Experience Memory Search', group: 'Memory', status: 'Completed' },
  { name: 'Experience Memory Write', group: 'Memory', status: 'Locked' },
];

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
  const selectedTools = new Set(selected.tools);
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
          <div><strong>Inspector follows selected node</strong><span>{selected.tools.length ? `${selected.tools.length} related tool${selected.tools.length > 1 ? 's' : ''} highlighted below.` : 'This orchestration node uses no external tool.'}</span></div>
        </section>

        <InspectorSection icon={ListTree} open title="Working state">
          <dl className="processed-state-list">
            <div><dt>Current step</dt><dd>{working?.current_step ?? 'Not started'}</dd></div>
            <div><dt>Plan</dt><dd>{working?.plan ?? 'No plan yet'}</dd></div>
            <div><dt>Route</dt><dd>{working?.route ?? 'Awaiting intake'}</dd></div>
            <div><dt>Replans</dt><dd>{working ? `${working.replans} of ${working.max_replans}` : '0 of 4'}</dd></div>
            <div><dt>Tool retries</dt><dd>{working ? `${working.tool_retries} of ${working.max_tool_retries}` : '0 of 2'}</dd></div>
            <div><dt>Status</dt><dd><span className="inline-status is-running"><Clock3 size={10} /> {working?.status ?? 'Idle'}</span></dd></div>
          </dl>
          <div className="processed-summary-box"><strong>Candidate resolution</strong><p>{working?.candidate_resolution ?? 'A processed candidate summary will appear after evidence collection.'}</p></div>
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

        <InspectorSection icon={MessageSquareText} title="Thread memory">
          <dl className="processed-state-list">
            <div><dt>Trace events</dt><dd>{thread?.trace_events ?? 0}</dd></div>
            <div><dt>Clarifications</dt><dd>{thread?.clarifications ?? 0}</dd></div>
            <div><dt>Checkpoints</dt><dd>{thread?.checkpoints ?? 0}</dd></div>
            <div><dt>Pause state</dt><dd>{thread?.pause_state ?? 'None'}</dd></div>
          </dl>
          <ol className="memory-summary-list">
            <li><History size={11} /><span><strong>Latest checkpoint</strong><small>{thread?.latest_checkpoint ?? 'No runtime checkpoint observed yet.'}</small></span></li>
            <li><ShieldCheck size={11} /><span><strong>Resume protection</strong><small>Approval ID and state version required after a human pause.</small></span></li>
          </ol>
        </InspectorSection>

        <InspectorSection icon={Database} title="Long-term memory">
          {runSnapshot?.long_term_memory.length ? runSnapshot.long_term_memory.map((memory) => (
            <div className="memory-pattern-card" key={`${memory.label}-${memory.summary}`}>
              <header><BrainCircuit size={13} /><strong>{memory.label.replaceAll('_', ' ')}</strong><span>{memory.relevance === null ? 'Advisory' : `${Math.round(memory.relevance * 100)}% relevance`}</span></header>
              <p>{memory.summary}</p>
            </div>
          )) : <div className="memory-pattern-card"><header><BrainCircuit size={13} /><strong>No matching pattern yet</strong><span>Advisory</span></header><p>Verified deidentified patterns may appear after a prior successful run.</p></div>}
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
