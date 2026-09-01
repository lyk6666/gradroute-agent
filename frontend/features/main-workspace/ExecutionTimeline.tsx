import { Check, Circle, Clock3, LoaderCircle, MousePointerClick } from 'lucide-react';
import type { RunSnapshot } from '@/lib/runtime-api';
import { NODE_SUMMARIES, type NodeStatus } from './workspace-data';

type ExecutionTimelineProps = {
  onSelectNode: (nodeId: string) => void;
  runSnapshot: RunSnapshot | null;
  selectedNodeId: string;
};

function TimelineStatus({ status }: { status: NodeStatus }) {
  if (status === 'completed') return <Check aria-hidden="true" size={11} />;
  if (status === 'running') return <LoaderCircle aria-hidden="true" size={11} />;
  if (status === 'waiting') return <Clock3 aria-hidden="true" size={11} />;
  return <Circle aria-hidden="true" size={9} />;
}

export function ExecutionTimeline({ onSelectNode, runSnapshot, selectedNodeId }: ExecutionTimelineProps) {
  const events = runSnapshot?.timeline.map((event) => ({
    nodeId: event.node_id,
    label: event.label,
    status: event.status,
    time: new Date(event.occurred_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    key: `${event.sequence}-${event.node_id}`,
  })) ?? [];
  if (runSnapshot?.current_node && runSnapshot.node_statuses[runSnapshot.current_node] === 'running') {
    const current = NODE_SUMMARIES[runSnapshot.current_node];
    events.push({
      nodeId: runSnapshot.current_node,
      label: current?.label ?? runSnapshot.current_node,
      status: 'running',
      time: 'Now',
      key: `current-${runSnapshot.latest_event_sequence}`,
    });
  }

  return (
    <section aria-label="Execution timeline" className="workspace-panel timeline-panel">
      <div className="timeline-scroll" aria-label="Execution events">
        {events.length ? events.map((event) => {
          const node = NODE_SUMMARIES[event.nodeId];
          if (!node) return null;
          const Icon = node.icon;
          const selected = selectedNodeId === event.nodeId;
          return (
            <button
              aria-label={`${event.label}, ${event.status}`}
              className={`timeline-event status-${event.status}${selected ? ' is-selected' : ''}`}
              key={event.key}
              onClick={() => onSelectNode(event.nodeId)}
              type="button"
            >
              <span className="timeline-node-icon"><Icon aria-hidden="true" size={14} /><i><TimelineStatus status={event.status} /></i></span>
              <strong>{event.label}</strong>
              <small>{event.time}</small>
            </button>
          );
        }) : <div className="timeline-empty">Start a grounded run to populate the human-readable trace.</div>}
      </div>
      <div className="timeline-hint"><MousePointerClick aria-hidden="true" size={12} /> {runSnapshot ? `${runSnapshot.thread_memory.trace_events} validated transitions · select an event to inspect its node.` : 'The timeline shows observed runtime events only.'}</div>
    </section>
  );
}
