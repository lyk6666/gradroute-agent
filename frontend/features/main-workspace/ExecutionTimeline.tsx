import { Check, Circle, Clock3, LoaderCircle, MousePointerClick } from 'lucide-react';
import { NODE_SUMMARIES, TIMELINE_EVENTS, type NodeStatus } from './workspace-data';

type ExecutionTimelineProps = {
  onSelectNode: (nodeId: string) => void;
  selectedNodeId: string;
};

function TimelineStatus({ status }: { status: NodeStatus }) {
  if (status === 'completed') return <Check aria-hidden="true" size={11} />;
  if (status === 'running') return <LoaderCircle aria-hidden="true" size={11} />;
  if (status === 'waiting') return <Clock3 aria-hidden="true" size={11} />;
  return <Circle aria-hidden="true" size={9} />;
}

export function ExecutionTimeline({ onSelectNode, selectedNodeId }: ExecutionTimelineProps) {
  return (
    <section aria-label="Execution timeline" className="workspace-panel timeline-panel">
      <div className="timeline-scroll" aria-label="Execution events">
        {TIMELINE_EVENTS.map((event) => {
          const node = NODE_SUMMARIES[event.nodeId];
          const Icon = node.icon;
          const selected = selectedNodeId === event.nodeId;
          return (
            <button
              aria-label={`${event.label}, ${event.status}`}
              className={`timeline-event status-${event.status}${selected ? ' is-selected' : ''}`}
              key={event.nodeId}
              onClick={() => onSelectNode(event.nodeId)}
              type="button"
            >
              <span className="timeline-node-icon"><Icon aria-hidden="true" size={14} /><i><TimelineStatus status={event.status} /></i></span>
              <strong>{event.label}</strong>
              <small>{event.time}</small>
            </button>
          );
        })}
      </div>
      <div className="timeline-hint"><MousePointerClick aria-hidden="true" size={12} /> Select an event to inspect its graph node.</div>
    </section>
  );
}
