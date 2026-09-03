import { memo, useState, type MouseEvent as ReactMouseEvent } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import {
  AlertTriangle,
  Check,
  Circle,
  CircleDot,
  Clock3,
  LoaderCircle,
  MessageCircleQuestion,
  ShieldCheck,
  UserCheck,
  UserCog,
} from 'lucide-react';
import { ProvenanceBadge } from '@/components/common/ProvenanceBadge';
import type { DetailItem, NodeExecutionDetail, RunSnapshot } from '@/lib/runtime-api';
import '@/lib/resize-observer-frame-scheduler';
import {
  GRAPH_EDGES,
  INITIAL_GRAPH_NODES,
  NODE_SUMMARIES,
  type AgentNodeData,
  type GraphEdgeData,
  type NodeStatus,
  type NodeSummary,
} from './workspace-data';
import '@xyflow/react/dist/style.css';

type AgentGraphCanvasProps = {
  onApprovalDecision: (status: 'PENDING' | 'APPROVED' | 'REJECTED', decisionReason?: string) => void | Promise<void>;
  onClarificationSubmit: (answers: Record<string, string | boolean>) => void | Promise<void>;
  onSelectNode: (nodeId: string, attempt?: number) => void;
  runSnapshot: RunSnapshot | null;
  selectedNodeAttempt: number | null;
  selectedNodeId: string;
};

type CanvasInspectorNodeData = {
  selectedNode: NodeSummary;
  selectedNodeId: string;
  selectedNodeAttempt: number | null;
  detail: NodeExecutionDetail | null;
  visits: NodeExecutionDetail[];
  isLatestVisit: boolean;
  pause: RunSnapshot['pause'];
  onSelectVisit: (nodeId: string, attempt: number) => void;
  onApprovalDecision: (status: 'PENDING' | 'APPROVED' | 'REJECTED', decisionReason?: string) => void | Promise<void>;
  onClarificationSubmit: (answers: Record<string, string | boolean>) => void | Promise<void>;
} & Record<string, unknown>;

const statusLabels: Record<NodeStatus, string> = {
  idle: 'Not visited',
  completed: 'Completed',
  running: 'Running',
  waiting: 'Waiting',
  failed: 'Failed',
  skipped: 'Skipped',
};

const handleLayout: Record<string, { position: Position; style?: { left?: string; top?: string } }> = {
  top: { position: Position.Top },
  'top-left': { position: Position.Top, style: { left: '28%' } },
  'top-right': { position: Position.Top, style: { left: '72%' } },
  left: { position: Position.Left },
  'left-top': { position: Position.Left, style: { top: '28%' } },
  'left-bottom': { position: Position.Left, style: { top: '72%' } },
  right: { position: Position.Right },
  'right-top': { position: Position.Right, style: { top: '28%' } },
  'right-bottom': { position: Position.Right, style: { top: '72%' } },
  bottom: { position: Position.Bottom },
  'bottom-left': { position: Position.Bottom, style: { left: '28%' } },
  'bottom-right': { position: Position.Bottom, style: { left: '72%' } },
};

function StatusIcon({ status }: { status: NodeStatus }) {
  const props = { 'aria-hidden': true, size: 10 } as const;
  if (status === 'completed') return <Check {...props} />;
  if (status === 'running') return <LoaderCircle {...props} />;
  if (status === 'waiting') return <Clock3 {...props} />;
  if (status === 'failed') return <AlertTriangle {...props} />;
  if (status === 'skipped') return <Circle {...props} />;
  return <CircleDot {...props} />;
}

function AgentFlowNode({ data }: NodeProps<Node<AgentNodeData>>) {
  const Icon = data.icon;
  const visitCount = Number(data.visitCount ?? 0);
  return (
    <div className={`agent-flow-node status-${data.status}`} title={`${data.label}: ${statusLabels[data.status]}`}>
      <span className="agent-node-icon"><Icon aria-hidden="true" size={14} /></span>
      <span className="agent-node-copy"><strong>{data.label}</strong><small><StatusIcon status={data.status} /> {statusLabels[data.status]}</small></span>
      {visitCount > 1 ? <span className="node-visit-count" title={`${visitCount} recorded visits`}>{visitCount}×</span> : null}
    </div>
  );
}

type CanvasPoint = { x: number; y: number };
type RouteAxis = 'horizontal' | 'vertical';

const AXIS_EPSILON = 0.01;

function routeAxis(position: Position): RouteAxis {
  return position === Position.Left || position === Position.Right ? 'horizontal' : 'vertical';
}

function samePoint(first: CanvasPoint, second: CanvasPoint) {
  return Math.abs(first.x - second.x) <= AXIS_EPSILON && Math.abs(first.y - second.y) <= AXIS_EPSILON;
}

function aligned(first: CanvasPoint, second: CanvasPoint) {
  return Math.abs(first.x - second.x) <= AXIS_EPSILON || Math.abs(first.y - second.y) <= AXIS_EPSILON;
}

function appendPoint(points: CanvasPoint[], point: CanvasPoint) {
  const previous = points.at(-1);
  if (!previous || !samePoint(previous, point)) points.push(point);
}

function appendOrthogonalSegment(points: CanvasPoint[], target: CanvasPoint, firstAxis: RouteAxis) {
  const source = points.at(-1)!;
  if (!aligned(source, target)) {
    appendPoint(points, firstAxis === 'horizontal'
      ? { x: target.x, y: source.y }
      : { x: source.x, y: target.y });
  }
  appendPoint(points, target);
}

function orthogonalRoutePoints(
  source: CanvasPoint,
  waypoints: CanvasPoint[],
  target: CanvasPoint,
  sourcePosition: Position,
  targetPosition: Position,
): CanvasPoint[] {
  const points = [source];
  const sourceAxis = routeAxis(sourcePosition);
  const targetAxis = routeAxis(targetPosition);

  if (waypoints.length === 0 && !aligned(source, target)) {
    if (sourceAxis === targetAxis) {
      if (sourceAxis === 'horizontal') {
        const middleX = (source.x + target.x) / 2;
        appendPoint(points, { x: middleX, y: source.y });
        appendPoint(points, { x: middleX, y: target.y });
      } else {
        const middleY = (source.y + target.y) / 2;
        appendPoint(points, { x: source.x, y: middleY });
        appendPoint(points, { x: target.x, y: middleY });
      }
    } else {
      appendPoint(points, sourceAxis === 'horizontal'
        ? { x: target.x, y: source.y }
        : { x: source.x, y: target.y });
    }
    appendPoint(points, target);
    return points;
  }

  waypoints.forEach((waypoint, index) => {
    const previous = points.at(-1)!;
    const beforePrevious = points.at(-2);
    let firstAxis = sourceAxis;
    if (index > 0 && beforePrevious) {
      const previousAxis: RouteAxis = Math.abs(beforePrevious.y - previous.y) <= AXIS_EPSILON
        ? 'horizontal'
        : 'vertical';
      firstAxis = previousAxis === 'horizontal' ? 'vertical' : 'horizontal';
    }
    appendOrthogonalSegment(points, waypoint, firstAxis);
  });

  const beforeTarget = points.at(-1)!;
  if (!aligned(beforeTarget, target)) {
    appendPoint(points, targetAxis === 'horizontal'
      ? { x: beforeTarget.x, y: target.y }
      : { x: target.x, y: beforeTarget.y });
  }
  appendPoint(points, target);
  return points;
}

function roundedOrthogonalPath(points: CanvasPoint[], cornerRadius = 8): string {
  if (points.length < 2) return '';
  const compact = points.filter((point, index) => {
    const previous = points[index - 1];
    return !previous || !samePoint(previous, point);
  }).filter((point, index, allPoints) => {
    if (index === 0 || index === allPoints.length - 1) return true;
    const previous = allPoints[index - 1];
    const next = allPoints[index + 1];
    return !(
      (Math.abs(previous.x - point.x) <= AXIS_EPSILON && Math.abs(point.x - next.x) <= AXIS_EPSILON)
      || (Math.abs(previous.y - point.y) <= AXIS_EPSILON && Math.abs(point.y - next.y) <= AXIS_EPSILON)
    );
  });
  if (compact.length < 2) return '';

  let path = `M ${compact[0].x} ${compact[0].y}`;
  for (let index = 1; index < compact.length - 1; index += 1) {
    const previous = compact[index - 1];
    const corner = compact[index];
    const next = compact[index + 1];
    const incomingLength = Math.abs(corner.x - previous.x) + Math.abs(corner.y - previous.y);
    const outgoingLength = Math.abs(next.x - corner.x) + Math.abs(next.y - corner.y);
    const radius = Math.min(cornerRadius, incomingLength / 2, outgoingLength / 2);
    const before = {
      x: corner.x + Math.sign(previous.x - corner.x) * radius,
      y: corner.y + Math.sign(previous.y - corner.y) * radius,
    };
    const after = {
      x: corner.x + Math.sign(next.x - corner.x) * radius,
      y: corner.y + Math.sign(next.y - corner.y) * radius,
    };
    path += ` L ${before.x} ${before.y} Q ${corner.x} ${corner.y} ${after.x} ${after.y}`;
  }
  const last = compact.at(-1)!;
  return `${path} L ${last.x} ${last.y}`;
}

const graphNodeById = new Map(INITIAL_GRAPH_NODES.map((node) => [node.id, node]));
const emptyFlowEdges: Edge[] = [];
const graphRouteKinds = ['conditional', 'completed', 'active', 'replan', 'danger', 'success', 'waiting'] as const;
const graphRouteColors: Record<(typeof graphRouteKinds)[number], string> = {
  conditional: '#94a3b8',
  completed: '#059669',
  active: '#2563eb',
  replan: '#7c3aed',
  danger: '#dc2626',
  success: '#059669',
  waiting: '#d97706',
};

function fixedHandlePoint(nodeId: string, handleId: string): CanvasPoint {
  const node = graphNodeById.get(nodeId);
  if (!node) return { x: 0, y: 0 };
  const width = Number(node.width ?? 188);
  const height = Number(node.height ?? 58);
  const position = handleLayout[handleId]?.position ?? Position.Bottom;
  const horizontalRatio = handleId.endsWith('-left') ? 0.28 : handleId.endsWith('-right') ? 0.72 : 0.5;
  const verticalRatio = handleId.endsWith('-top') ? 0.28 : handleId.endsWith('-bottom') ? 0.72 : 0.5;
  if (position === Position.Top) return { x: node.position.x + width * horizontalRatio, y: node.position.y };
  if (position === Position.Bottom) return { x: node.position.x + width * horizontalRatio, y: node.position.y + height };
  if (position === Position.Left) return { x: node.position.x, y: node.position.y + height * verticalRatio };
  return { x: node.position.x + width, y: node.position.y + height * verticalRatio };
}

function renderedEdgeKind(edge: (typeof GRAPH_EDGES)[number]) {
  const match = edge.className?.match(/edge-(conditional|completed|active|replan|danger|success|waiting)/);
  return (match?.[1] ?? edge.data?.kind ?? 'conditional') as (typeof graphRouteKinds)[number];
}

const GraphRouteLayer = memo(function GraphRouteLayer({ edges }: { edges: typeof GRAPH_EDGES }) {
  return (
    <div aria-hidden="true" className="graph-route-overlay">
      <svg className="graph-route-svg" height="1040" width="1400">
        <defs>
          {graphRouteKinds.map((kind) => (
            <marker id={`graph-arrow-${kind}`} key={kind} markerHeight="8" markerUnits="userSpaceOnUse" markerWidth="8" orient="auto" refX="7" refY="4" viewBox="0 0 8 8">
              <path d="M 0 0 L 8 4 L 0 8 z" fill={graphRouteColors[kind]} />
            </marker>
          ))}
        </defs>
        {edges.map((edge) => {
          const route = edge.data as GraphEdgeData;
          const sourceHandle = edge.sourceHandle ?? 'bottom';
          const targetHandle = edge.targetHandle ?? 'top';
          const source = fixedHandlePoint(edge.source, sourceHandle);
          const target = fixedHandlePoint(edge.target, targetHandle);
          const points = orthogonalRoutePoints(
            source,
            route.waypoints,
            target,
            handleLayout[sourceHandle]?.position ?? Position.Bottom,
            handleLayout[targetHandle]?.position ?? Position.Top,
          );
          const kind = renderedEdgeKind(edge);
          return (
            <g className={edge.className} data-edge-id={edge.id} key={edge.id}>
              <path className="graph-route-hit-area" d={roundedOrthogonalPath(points)} />
              <path className="graph-route-path" d={roundedOrthogonalPath(points)} markerEnd={`url(#graph-arrow-${kind})`} />
            </g>
          );
        })}
      </svg>
      <div className="graph-route-label-layer">
        {edges.map((edge) => {
          if (!edge.label) return null;
          const route = edge.data as GraphEdgeData;
          const source = fixedHandlePoint(edge.source, edge.sourceHandle ?? 'bottom');
          const target = fixedHandlePoint(edge.target, edge.targetHandle ?? 'top');
          const labelPosition = route.labelPosition ?? { x: (source.x + target.x) / 2, y: (source.y + target.y) / 2 };
          return (
            <div className={`flow-edge-label label-${route.kind}`} data-edge-label={edge.id} key={edge.id} style={{ left: labelPosition.x, top: labelPosition.y }}>
              {String(edge.label)}
            </div>
          );
        })}
      </div>
    </div>
  );
});

function DetailRows({ items }: { items: DetailItem[] }) {
  return (
    <dl className="runtime-detail-list">
      {items.map((item, index) => (
        <div key={`${item.label}-${index}`}><dt>{item.label}</dt><dd>{item.value}</dd></div>
      ))}
    </dl>
  );
}

function visitLabel(nodeId: string, attempt: number) {
  if (attempt === 1) return 'Initial pass';
  if (nodeId === 'planner') return `Replan ${attempt - 1}`;
  if (['degree_audit_agent', 'policy_agent', 'course_agent'].includes(nodeId)) return `Evidence recheck ${attempt - 1}`;
  if (['pre_action_verifier', 'post_action_verifier'].includes(nodeId)) return `Verification pass ${attempt}`;
  if (nodeId === 'transaction') return `Retry ${attempt - 1}`;
  if (['clarification', 'human_approval', 'pause_checkpoint'].includes(nodeId)) return `Decision cycle ${attempt}`;
  return `Return ${attempt}`;
}

function visitTime(detail: NodeExecutionDetail) {
  const timestamp = detail.completed_at ?? detail.started_at;
  return timestamp
    ? new Date(timestamp).toLocaleTimeString('en-SG', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
    : 'Time unavailable';
}

function VisitEvidence({ detail }: { detail: NodeExecutionDetail }) {
  return (
    <details className="recorded-facts">
      <summary>Evidence and audit details</summary>
      <section className="runtime-detail-group"><h4>Input record</h4><DetailRows items={detail.input_items} /></section>
      <section className="runtime-detail-group"><h4>Output record</h4><DetailRows items={detail.output_items} /></section>
      <section className="runtime-detail-group"><h4>State record</h4><DetailRows items={detail.state_changes} /></section>
      {detail.reasoning ? <p>{detail.reasoning.safety_rule}</p> : null}
    </details>
  );
}

function NodeDetail({
  detail,
  node,
  onSelectVisit,
  visits,
}: {
  detail: NodeExecutionDetail | null;
  node: NodeSummary;
  onSelectVisit: (attempt: number) => void;
  visits: NodeExecutionDetail[];
}) {
  const Icon = node.icon;
  const selectedAttempt = detail?.attempt ?? null;
  const status = detail?.status ?? node.status;
  return (
    <section className="canvas-detail-card node-detail-card" aria-label={`${node.label} details`}>
      <header>
        <span className="detail-node-icon"><Icon size={15} /></span>
        <div><span className="panel-kicker">Selected node</span><h3>{node.label}</h3></div>
        <span className={`detail-status status-${status}`}><StatusIcon status={status} />{statusLabels[status]}</span>
      </header>
      {!detail ? <p className="node-purpose">{node.purpose} A case-specific result will appear when this step runs.</p> : null}
      {detail && visits.length <= 1 ? <><p className="node-purpose">{detail.narrative?.summary ?? node.purpose}</p><VisitEvidence detail={detail} /></> : null}
      {visits.length > 1 ? (
        <div className="node-visit-history" aria-label={`${visits.length} recorded visits`}>
          <div className="node-visit-history-heading"><strong>{visits.length} recorded visits</strong><span>Latest shown first</span></div>
          {[...visits].reverse().map((visit, index) => {
            const selected = visit.attempt === selectedAttempt;
            const latest = index === 0;
            return (
              <section className={`node-visit-section${selected ? ' is-selected' : ''}`} key={visit.attempt}>
                <button aria-pressed={selected} onClick={() => onSelectVisit(visit.attempt)} type="button">
                  <span><b>Visit {visit.attempt}</b><small>{visitLabel(node.id, visit.attempt)}</small></span>
                  <span className={`visit-status status-${visit.status}`}><StatusIcon status={visit.status} />{statusLabels[visit.status]}</span>
                  <time>{latest ? 'Latest · ' : ''}{visitTime(visit)}</time>
                </button>
                {selected ? <div className="node-visit-content"><p>{visit.narrative?.summary ?? node.purpose}</p><VisitEvidence detail={visit} /></div> : null}
              </section>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}

function HumanInteraction({
  onApprovalDecision,
  onClarificationSubmit,
  pause,
  detail,
  isLatestVisit,
  selectedNodeId,
}: {
  onApprovalDecision: (status: 'PENDING' | 'APPROVED' | 'REJECTED', decisionReason?: string) => void | Promise<void>;
  onClarificationSubmit: (answers: Record<string, string | boolean>) => void | Promise<void>;
  pause: RunSnapshot['pause'];
  detail: NodeExecutionDetail | null;
  isLatestVisit: boolean;
  selectedNodeId: string;
}) {
  const [answers, setAnswers] = useState<Record<string, string | boolean>>({});
  const [rejectionReason, setRejectionReason] = useState('');
  const [handoffAcknowledged, setHandoffAcknowledged] = useState(false);
  const actionNarrative = detail?.narrative?.action;

  if (selectedNodeId === 'clarification') {
    const active = pause?.kind === 'clarification' && isLatestVisit;
    const complete = active && pause.fields.every((field) => {
      const value = answers[field];
      return field === 'submission_declaration' ? value === true : Boolean(String(value ?? '').trim());
    });
    return (
      <section className="canvas-detail-card human-interaction-card">
        <header><MessageCircleQuestion size={15} /><div><span className="panel-kicker">Human interaction</span><h3>Clarification required</h3></div></header>
        <p className="interaction-question">{active ? pause.message : actionNarrative ?? 'No clarification is active for this step yet.'}</p>
        {!isLatestVisit ? <p className="historical-visit-note"><Clock3 size={12} /> This is a previous clarification visit. Its record is read-only.</p> : null}
        {active ? <div className="interaction-reason"><strong>Why this is needed</strong><p>{pause.narrative ?? pause.why_needed}</p>{pause.narrative ? <p>{pause.why_needed}</p> : null}<small>{pause.decision_depends_on}</small></div> : null}
        {active && pause.evidence_summary.length ? <details className="recorded-facts"><summary>Evidence already checked</summary><ul>{pause.evidence_summary.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul></details> : null}
        {active ? pause.fields.map((field) => (
          field === 'submission_declaration' ? (
            <label className="clarification-checkbox" key={field}>
              <input checked={answers[field] === true} onChange={(event) => setAnswers((current) => ({ ...current, [field]: event.target.checked }))} type="checkbox" />
              <span>I confirm the submission declaration.</span>
            </label>
          ) : (
            <label key={field}>
              <span>{field.replaceAll('_', ' ')}</span>
              <textarea onChange={(event) => setAnswers((current) => ({ ...current, [field]: event.target.value }))} placeholder="Provide the missing fact or evidence reference." rows={2} value={String(answers[field] ?? '')} />
            </label>
          )
        )) : null}
        <button disabled={!complete} onClick={() => onClarificationSubmit(answers)} type="button">Continue with this information</button>
      </section>
    );
  }

  if (selectedNodeId === 'human_approval' || selectedNodeId === 'pause_checkpoint') {
    const active = pause?.kind === 'approval' && isLatestVisit;
    return (
      <section className="canvas-detail-card human-interaction-card approval-preview-card">
        <header><UserCheck size={15} /><div><span className="panel-kicker">Human decision</span><h3>{active ? pause.approver_role : 'Approval decision'}</h3></div><span className="simulated-role">Simulated</span></header>
        <p className="interaction-question">{active ? pause.message : actionNarrative ?? 'Approval details will appear if the action gate selects this route.'}</p>
        {!isLatestVisit ? <p className="historical-visit-note"><Clock3 size={12} /> This earlier decision visit is preserved for review. Only the latest visit can accept a decision.</p> : null}
        {active ? <div className="approval-brief">
          <dl>
            <div><dt>Proposed action</dt><dd>{pause.requested_action}</dd></div>
            <div><dt>Approval basis</dt><dd>{pause.approval_basis}</dd></div>
          </dl>
          {pause.narrative ? <div className="decision-ready-summary"><strong>Decision summary</strong><p>{pause.narrative}</p></div> : null}
          <div className="interaction-reason"><strong>Why approval is required</strong><p>{pause.why_needed}</p><small>{pause.decision_depends_on}</small></div>
          {pause.evidence_summary.length ? <div className="approval-evidence"><strong>Evidence prepared</strong><ul>{pause.evidence_summary.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul></div> : null}
          <label><span>Reason required when rejecting</span><textarea onChange={(event) => setRejectionReason(event.target.value)} placeholder="Explain what is insufficient or why the request is rejected." rows={2} value={rejectionReason} /></label>
        </div> : null}
        <p><ShieldCheck size={12} /> The agent cannot make this decision for the approving role.</p>
        <div className="approval-buttons">
          <button disabled={!active} onClick={() => onApprovalDecision('APPROVED')} type="button">Approve</button>
          <button disabled={!active || !rejectionReason.trim()} onClick={() => onApprovalDecision('REJECTED', rejectionReason.trim())} type="button">Reject</button>
          <button disabled={!active} onClick={() => onApprovalDecision('PENDING')} type="button">Leave pending</button>
        </div>
      </section>
    );
  }

  if (selectedNodeId === 'human_admin_review') {
    return (
      <section className="canvas-detail-card human-interaction-card">
        <header><UserCog size={15} /><div><span className="panel-kicker">Human interaction</span><h3>Administrative handoff</h3></div></header>
        <p>{actionNarrative ?? (detail ? 'The plain-language handoff explanation is temporarily unavailable.' : 'No administrative handoff has been prepared yet.')}</p>
        {!isLatestVisit ? <p className="historical-visit-note"><Clock3 size={12} /> This previous handoff visit is preserved as a read-only record.</p> : null}
        {detail ? <details className="recorded-facts"><summary>Evidence and audit details</summary><DetailRows items={detail.state_changes.slice(0, 5)} /></details> : null}
        {detail ? <button aria-live="polite" disabled={!isLatestVisit} onClick={() => setHandoffAcknowledged(true)} type="button">{handoffAcknowledged ? 'Handoff acknowledged' : 'Acknowledge staff handoff'}</button> : null}
        <ProvenanceBadge kind="derived" />
      </section>
    );
  }

  if (['resolution_builder', 'pre_action_verifier', 'action_gate', 'transaction', 'observation', 'post_action_verifier', 'final_response', 'memory_updater'].includes(selectedNodeId)) {
    return (
      <section className="canvas-detail-card human-interaction-card runtime-action-card">
        <header><ShieldCheck size={15} /><div><span className="panel-kicker">Runtime action</span><h3>{detail ? 'Observed result' : 'Awaiting execution'}</h3></div></header>
        {detail ? (
          <>
            <p className="runtime-action-narrative">{actionNarrative ?? 'The plain-language action explanation is temporarily unavailable.'}</p>
            <details className="recorded-facts"><summary>Evidence and audit details</summary><DetailRows items={detail.output_items.slice(0, 5)} /><div className="action-state-divider"><span>Recorded state</span></div><DetailRows items={detail.state_changes.slice(0, 5)} /></details>
          </>
        ) : <p>The exact decision, result and state update will appear here when this node executes.</p>}
      </section>
    );
  }

  return (
    <section className="canvas-detail-card human-interaction-card interaction-empty is-compact">
      <header><UserCheck size={15} /><div><span className="panel-kicker">Human interaction</span><h3>No input needed</h3></div></header>
      <p>{actionNarrative ?? (detail ? 'This step can continue without a separate human decision.' : 'If this step later needs a person, the exact request will appear here.')}</p>
    </section>
  );
}

function CanvasInspectorNode({ data }: NodeProps<Node<CanvasInspectorNodeData>>) {
  return (
    <aside aria-label="Selected node and human interaction" className="canvas-embedded-inspector nodrag nowheel nopan">
      <NodeDetail
        detail={data.detail}
        node={data.selectedNode}
        onSelectVisit={(attempt) => data.onSelectVisit(data.selectedNodeId, attempt)}
        visits={data.visits}
      />
      <HumanInteraction
        key={`${data.selectedNodeId}-${data.detail?.attempt ?? 'none'}-${data.pause?.kind ?? 'none'}-${data.pause?.message ?? 'idle'}`}
        isLatestVisit={data.isLatestVisit}
        onApprovalDecision={data.onApprovalDecision}
        onClarificationSubmit={data.onClarificationSubmit}
        pause={data.pause}
        detail={data.detail}
        selectedNodeId={data.selectedNodeId}
      />
    </aside>
  );
}

const nodeTypes = {
  agentNode: AgentFlowNode,
  inspectorNode: CanvasInspectorNode,
};

export function AgentGraphCanvas({
  onApprovalDecision,
  onClarificationSubmit,
  onSelectNode,
  runSnapshot,
  selectedNodeAttempt,
  selectedNodeId,
}: AgentGraphCanvasProps) {
  const [graphViewport, setGraphViewport] = useState({ x: 0, y: 0, zoom: 1 });
  const statuses = runSnapshot?.node_statuses ?? {};
  const selectedBase = NODE_SUMMARIES[selectedNodeId] ?? NODE_SUMMARIES.pre_action_verifier;
  const selectedNode = { ...selectedBase, status: statuses[selectedNodeId] ?? 'idle' };
  const latestDetail = runSnapshot?.node_details[selectedNodeId] ?? null;
  const visits = runSnapshot?.node_history[selectedNodeId] ?? (latestDetail ? [latestDetail] : []);
  const selectedDetail = selectedNodeAttempt === null
    ? latestDetail
    : visits.find((visit) => visit.attempt === selectedNodeAttempt) ?? latestDetail;
  const latestAttempt = visits.at(-1)?.attempt ?? latestDetail?.attempt ?? null;
  const inspectorNode: Node<CanvasInspectorNodeData> = {
    id: 'canvas_inspector',
    type: 'inspectorNode',
    position: { x: 0, y: 130 },
    width: 330,
    height: 700,
    data: {
      selectedNode,
      selectedNodeId,
      selectedNodeAttempt,
      detail: selectedDetail,
      visits,
      isLatestVisit: selectedDetail === null || selectedDetail.attempt === latestAttempt,
      pause: runSnapshot?.pause ?? null,
      onSelectVisit: onSelectNode,
      onApprovalDecision,
      onClarificationSubmit,
    },
    draggable: false,
    handles: [],
    selectable: false,
    zIndex: 3,
  };
  const nodes: Node[] = [
    ...INITIAL_GRAPH_NODES.map((node) => ({
      ...node,
      data: {
        ...node.data,
        status: statuses[node.id] ?? 'idle',
        visitCount: runSnapshot?.node_history[node.id]?.length ?? (runSnapshot?.node_details[node.id] ? 1 : 0),
      },
      ariaLabel: `${node.data.label}, ${statusLabels[statuses[node.id] ?? 'idle']}`,
      selected: node.id === selectedNodeId,
    })),
    inspectorNode,
  ];
  return (
    <section aria-label="Agent execution graph" className="workspace-panel graph-panel">
      <div className="graph-toolbar" aria-label="Graph status legend" role="group">
        <div className="graph-legend">
          <span><i className="legend-running" />Current</span>
          <span><i className="legend-selected" />Selected</span>
          <span><i className="legend-completed" />Completed</span>
          <span><i className="legend-idle" />Not visited</span>
          <b aria-live="polite">{runSnapshot ? runSnapshot.status.replaceAll('_', ' ') : 'Awaiting run'}</b>
        </div>
      </div>

      <div className="agent-canvas-shell">
        <div
          className="graph-route-screen"
          style={{ transform: `translate(${graphViewport.x}px, ${graphViewport.y}px) scale(${graphViewport.zoom})` }}
        >
          <GraphRouteLayer edges={GRAPH_EDGES} />
        </div>
        <ReactFlow
          edges={emptyFlowEdges}
          edgesFocusable={false}
          elementsSelectable
          fitView
          fitViewOptions={{ padding: 0.075, maxZoom: 0.9 }}
          maxZoom={1.45}
          minZoom={0.34}
          nodeTypes={nodeTypes}
          nodes={nodes}
          nodesConnectable={false}
          nodesDraggable={false}
          nodesFocusable
          onInit={(instance) => setGraphViewport(instance.getViewport())}
          onMove={(_event, viewport) => setGraphViewport(viewport)}
          onNodeClick={(_event: ReactMouseEvent, node) => {
            if (node.type === 'agentNode') onSelectNode(node.id);
          }}
          onKeyDown={(event) => {
            if (event.key !== 'Enter' && event.key !== ' ') return;
            const nodeElement = (event.target as HTMLElement).closest<HTMLElement>('.react-flow__node[data-id]');
            const nodeId = nodeElement?.dataset.id;
            if (nodeId && nodeId !== 'canvas_inspector') onSelectNode(nodeId);
          }}
          panOnScroll
          zoomOnDoubleClick={false}
        >
          <Background color="#edf2f8" gap={24} size={1} variant={BackgroundVariant.Lines} />
          <Controls position="top-right" showInteractive={false} />
        </ReactFlow>
      </div>
    </section>
  );
}
