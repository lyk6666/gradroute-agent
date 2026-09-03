import { Check, Circle, Clock3, LoaderCircle, MousePointerClick } from 'lucide-react';
import type { RunSnapshot } from '@/lib/runtime-api';
import { NODE_SUMMARIES, type NodeStatus } from './workspace-data';

type ExecutionTimelineProps = {
  onSelectNode: (nodeId: string, attempt: number) => void;
  runSnapshot: RunSnapshot | null;
  selectedNodeAttempt: number | null;
  selectedNodeId: string;
};

function TimelineStatus({ status }: { status: NodeStatus }) {
  if (status === 'completed') return <Check aria-hidden="true" size={11} />;
  if (status === 'running') return <LoaderCircle aria-hidden="true" size={11} />;
  if (status === 'waiting') return <Clock3 aria-hidden="true" size={11} />;
  return <Circle aria-hidden="true" size={9} />;
}

export function ExecutionTimeline({ onSelectNode, runSnapshot, selectedNodeAttempt, selectedNodeId }: ExecutionTimelineProps) {
  const events = runSnapshot?.timeline.map((event) => ({
    nodeId: event.node_id,
    attempt: event.attempt,
    label: event.label,
    status: event.status,
    time: new Date(event.occurred_at).toLocaleTimeString('en-SG', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }),
    key: `${event.sequence}-${event.node_id}`,
  })) ?? [];
  if (runSnapshot?.current_node && runSnapshot.node_statuses[runSnapshot.current_node] === 'running') {
    const current = NODE_SUMMARIES[runSnapshot.current_node];
    events.push({
      nodeId: runSnapshot.current_node,
      attempt: runSnapshot.node_details[runSnapshot.current_node]?.attempt ?? 1,
      label: current?.label ?? runSnapshot.current_node,
      status: 'running',
      time: 'Now',
      key: `current-${runSnapshot.latest_event_sequence}`,
    });
  }

  return (
    <section aria-label="Execution timeline" className="workspace-panel timeline-panel" data-demo-target="execution-timeline">
      <div className="timeline-scroll" aria-label="Execution events">
        {events.length ? events.map((event) => {
          const node = NODE_SUMMARIES[event.nodeId];
          if (!node) return null;
          const Icon = node.icon;
          const selected = selectedNodeId === event.nodeId
            && (selectedNodeAttempt === null
              ? event.attempt === runSnapshot?.node_details[event.nodeId]?.attempt
              : selectedNodeAttempt === event.attempt);
          return (
            <button
              aria-label={`${event.label}, visit ${event.attempt}, ${event.status}`}
              className={`timeline-event status-${event.status}${selected ? ' is-selected' : ''}`}
              key={event.key}
              onClick={() => onSelectNode(event.nodeId, event.attempt)}
              type="button"
            >
              <span className="timeline-node-icon"><Icon aria-hidden="true" size={14} /><i><TimelineStatus status={event.status} /></i></span>
              <strong>{event.label}</strong>
              {((runSnapshot?.node_history[event.nodeId]?.length ?? 0) > 1) ? <em>Visit {event.attempt}</em> : null}
              <small>{event.time}</small>
            </button>
          );
        }) : <div className="timeline-empty">Start a grounded run to populate the human-readable trace.</div>}
      </div>
      <div className="timeline-hint"><MousePointerClick aria-hidden="true" size={12} /> {runSnapshot ? `${runSnapshot.thread_memory.trace_events} validated transitions · select an event to inspect its node.` : 'The timeline shows observed runtime events only.'}</div>
    </section>
  );
}
