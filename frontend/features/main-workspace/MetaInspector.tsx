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
import { NODE_SUMMARIES } from './workspace-data';

type MetaInspectorProps = { selectedNodeId: string };

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

export function MetaInspector({ selectedNodeId }: MetaInspectorProps) {
  const selected = NODE_SUMMARIES[selectedNodeId] ?? NODE_SUMMARIES.pre_action_verifier;
  const selectedTools = new Set(selected.tools);

  return (
    <aside aria-label="Tools and memory inspector" className="workspace-panel meta-panel">
      <div className="meta-scroll-content">
        <section className="selected-node-callout">
          <Info aria-hidden="true" size={14} />
          <div><strong>Inspector follows selected node</strong><span>{selected.tools.length ? `${selected.tools.length} related tool${selected.tools.length > 1 ? 's' : ''} highlighted below.` : 'This orchestration node uses no external tool.'}</span></div>
        </section>

        <InspectorSection icon={ListTree} open title="Working state">
          <dl className="processed-state-list">
            <div><dt>Current step</dt><dd>Pre-action Verifier</dd></div>
            <div><dt>Plan</dt><dd>1 candidate · step 6 of 11</dd></div>
            <div><dt>Route</dt><dd>Policy evidence path</dd></div>
            <div><dt>Replans</dt><dd>0 of 4</dd></div>
            <div><dt>Tool retries</dt><dd>0 of 2</dd></div>
            <div><dt>Status</dt><dd><span className="inline-status is-running"><Clock3 size={10} /> Verifying</span></dd></div>
          </dl>
          <div className="processed-summary-box"><strong>Candidate resolution</strong><p>Submit a bounded prerequisite exception supported by the documented evidence route and required approval.</p></div>
        </InspectorSection>

        <InspectorSection icon={Wrench} open title="Tools">
          <div className="tool-summary-list">
            {toolCatalog.map((tool) => (
              <div className={selectedTools.has(tool.name) ? 'is-highlighted' : ''} key={tool.name}>
                <span className="tool-state-icon">{tool.status === 'Completed' ? <CircleCheck size={11} /> : <Wrench size={11} />}</span>
                <span><strong>{tool.name}</strong><small>{tool.group} · {tool.status}</small></span>
                {selectedTools.has(tool.name) ? <b>Selected node</b> : null}
              </div>
            ))}
          </div>
        </InspectorSection>

        <InspectorSection icon={MessageSquareText} title="Thread memory">
          <dl className="processed-state-list">
            <div><dt>Messages</dt><dd>7 summarized</dd></div>
            <div><dt>Clarifications</dt><dd>0</dd></div>
            <div><dt>Checkpoints</dt><dd>6</dd></div>
            <div><dt>Pause state</dt><dd>None</dd></div>
          </dl>
          <ol className="memory-summary-list">
            <li><History size={11} /><span><strong>Latest checkpoint</strong><small>Candidate assembled; pre-action verification entered.</small></span></li>
            <li><ShieldCheck size={11} /><span><strong>Resume protection</strong><small>Approval ID and state version required after a human pause.</small></span></li>
          </ol>
        </InspectorSection>

        <InspectorSection icon={Database} title="Long-term memory">
          <div className="memory-pattern-card">
            <header><BrainCircuit size={13} /><strong>Bounded prerequisite evidence</strong><span>0.86 relevance</span></header>
            <p>Check current policy and evidence before considering any exception route. Advisory only.</p>
          </div>
          <div className="memory-pattern-card misleading">
            <header><BrainCircuit size={13} /><strong>Generic waiver shortcut</strong><span>Rejected</span></header>
            <p>Conflicts with current tools and cannot influence the selected candidate.</p>
          </div>
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
