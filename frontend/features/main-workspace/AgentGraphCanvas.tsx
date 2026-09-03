import { useState, type MouseEvent as ReactMouseEvent } from 'react';
import {
  BaseEdge,
  Background,
  BackgroundVariant,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type EdgeProps,
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
  onApprovalRecheck: () => void | Promise<void>;
  onClarificationSubmit: (answers: Record<string, string | boolean>) => void | Promise<void>;
  onSelectNode: (nodeId: string) => void;
  runSnapshot: RunSnapshot | null;
  selectedNodeId: string;
};

type CanvasInspectorNodeData = {
  selectedNode: NodeSummary;
  selectedNodeId: string;
  detail: NodeExecutionDetail | null;
  pause: RunSnapshot['pause'];
  onApprovalRecheck: () => void | Promise<void>;
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
  return (
    <div className={`agent-flow-node status-${data.status}`} title={`${data.label}: ${statusLabels[data.status]}`}>
      <Handle id="top" position={Position.Top} type="target" />
      <Handle id="top-left" position={Position.Top} style={{ left: '28%' }} type="target" />
      <Handle id="top-right" position={Position.Top} style={{ left: '72%' }} type="target" />
      <Handle id="left" position={Position.Left} type="target" />
      <Handle id="left-top" position={Position.Left} style={{ top: '28%' }} type="target" />
      <Handle id="left-bottom" position={Position.Left} style={{ top: '72%' }} type="target" />
      <Handle id="top" position={Position.Top} type="source" />
      <Handle id="top-left" position={Position.Top} style={{ left: '28%' }} type="source" />
      <Handle id="top-right" position={Position.Top} style={{ left: '72%' }} type="source" />
      <Handle id="left" position={Position.Left} type="source" />
      <Handle id="left-top" position={Position.Left} style={{ top: '28%' }} type="source" />
      <Handle id="left-bottom" position={Position.Left} style={{ top: '72%' }} type="source" />
      <span className="agent-node-icon"><Icon aria-hidden="true" size={14} /></span>
      <span className="agent-node-copy"><strong>{data.label}</strong><small><StatusIcon status={data.status} /> {statusLabels[data.status]}</small></span>
      <Handle id="right" position={Position.Right} type="source" />
      <Handle id="right-top" position={Position.Right} style={{ top: '28%' }} type="source" />
      <Handle id="right-bottom" position={Position.Right} style={{ top: '72%' }} type="source" />
      <Handle id="bottom" position={Position.Bottom} type="source" />
      <Handle id="bottom-left" position={Position.Bottom} style={{ left: '28%' }} type="source" />
      <Handle id="bottom-right" position={Position.Bottom} style={{ left: '72%' }} type="source" />
      <Handle id="right" position={Position.Right} type="target" />
      <Handle id="right-top" position={Position.Right} style={{ top: '28%' }} type="target" />
      <Handle id="right-bottom" position={Position.Right} style={{ top: '72%' }} type="target" />
      <Handle id="bottom" position={Position.Bottom} type="target" />
      <Handle id="bottom-left" position={Position.Bottom} style={{ left: '28%' }} type="target" />
      <Handle id="bottom-right" position={Position.Bottom} style={{ left: '72%' }} type="target" />
    </div>
  );
}

function roundedOrthogonalPath(points: Array<{ x: number; y: number }>): string {
  const compact = points.filter((point, index) => {
    const previous = points[index - 1];
    return !previous || previous.x !== point.x || previous.y !== point.y;
  });
  if (compact.length < 2) return '';
  let path = `M ${compact[0].x} ${compact[0].y}`;
  for (let index = 1; index < compact.length - 1; index += 1) {
    const previous = compact[index - 1];
    const current = compact[index];
    const next = compact[index + 1];
    const incoming = Math.hypot(current.x - previous.x, current.y - previous.y);
    const outgoing = Math.hypot(next.x - current.x, next.y - current.y);
    const radius = Math.min(9, incoming / 2, outgoing / 2);
    const before = {
      x: current.x - ((current.x - previous.x) / incoming) * radius,
      y: current.y - ((current.y - previous.y) / incoming) * radius,
    };
    const after = {
      x: current.x + ((next.x - current.x) / outgoing) * radius,
      y: current.y + ((next.y - current.y) / outgoing) * radius,
    };
    path += ` L ${before.x} ${before.y} Q ${current.x} ${current.y} ${after.x} ${after.y}`;
  }
  const last = compact.at(-1)!;
  path += ` L ${last.x} ${last.y}`;
  return path;
}

function RoutedFlowEdge({
  data,
  id,
  label,
  markerEnd,
  sourceX,
  sourceY,
  style,
  targetX,
  targetY,
}: EdgeProps) {
  const route = (data ?? { kind: 'conditional', waypoints: [] }) as GraphEdgeData;
  const points = [{ x: sourceX, y: sourceY }, ...route.waypoints, { x: targetX, y: targetY }];
  const path = roundedOrthogonalPath(points);
  const labelPosition = route.labelPosition ?? {
    x: (sourceX + targetX) / 2,
    y: (sourceY + targetY) / 2,
  };

  return (
    <>
      <BaseEdge id={id} markerEnd={markerEnd} path={path} style={style} />
      {label ? (
        <EdgeLabelRenderer>
          <div
            aria-hidden="true"
            className={`flow-edge-label label-${route.kind}`}
            style={{ transform: `translate(-50%, -50%) translate(${labelPosition.x}px, ${labelPosition.y}px)` }}
          >
            {String(label)}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

function DetailRows({ items }: { items: DetailItem[] }) {
  return (
    <dl className="runtime-detail-list">
      {items.map((item, index) => (
        <div key={`${item.label}-${index}`}><dt>{item.label}</dt><dd>{item.value}</dd></div>
      ))}
    </dl>
  );
}

function NodeDetail({ detail, node }: { detail: NodeExecutionDetail | null; node: NodeSummary }) {
  const Icon = node.icon;
  return (
    <section className="canvas-detail-card node-detail-card" aria-label={`${node.label} details`}>
      <header>
        <span className="detail-node-icon"><Icon size={15} /></span>
        <div><span className="panel-kicker">Selected node</span><h3>{node.label}</h3></div>
        <span className={`detail-status status-${node.status}`}><StatusIcon status={node.status} />{statusLabels[node.status]}</span>
      </header>
      <p className="node-purpose">{node.purpose}</p>
      {!detail ? <p className="node-narrative-pending">This step has not run yet. Its case-specific explanation will appear when the case reaches it.</p> : null}
      {detail?.narrative ? (
        <div className="runtime-narrative-list">
          <section className="runtime-narrative-block"><h4>What came in</h4><p>{detail.narrative.input}</p></section>
          <section className="runtime-narrative-block"><h4>What this step found</h4><p>{detail.narrative.output}</p></section>
          <section className="runtime-narrative-block"><h4>What changed</h4><p>{detail.narrative.state}</p></section>
        </div>
      ) : detail ? <p className="node-narrative-pending">The plain-language explanation is temporarily unavailable. The recorded facts remain available below.</p> : null}
      {detail ? (
        <details className="recorded-facts">
          <summary>View recorded facts</summary>
          <section className="runtime-detail-group"><h4>Input record</h4><DetailRows items={detail.input_items} /></section>
          <section className="runtime-detail-group"><h4>Output record</h4><DetailRows items={detail.output_items} /></section>
          <section className="runtime-detail-group"><h4>State record</h4><DetailRows items={detail.state_changes} /></section>
          {detail.reasoning ? <p>{detail.reasoning.safety_rule}</p> : null}
        </details>
      ) : null}
      <div className="node-tool-summary">
        <span>Tools</span>
        <strong>{detail?.tool_names.length ? detail.tool_names.join(' · ') : detail ? 'No external tool used' : 'Available after this step runs'}</strong>
      </div>
      {detail ? <p className="node-execution-meta">Attempt {detail.attempt} · {detail.evidence_ids.length} evidence reference(s)</p> : null}
    </section>
  );
}

function HumanInteraction({
  onApprovalRecheck,
  onClarificationSubmit,
  pause,
  detail,
  selectedNodeId,
}: {
  onApprovalRecheck: () => void | Promise<void>;
  onClarificationSubmit: (answers: Record<string, string | boolean>) => void | Promise<void>;
  pause: RunSnapshot['pause'];
  detail: NodeExecutionDetail | null;
  selectedNodeId: string;
}) {
  const [answers, setAnswers] = useState<Record<string, string | boolean>>({});
  const actionNarrative = detail?.narrative?.action;

  if (selectedNodeId === 'clarification') {
    const active = pause?.kind === 'clarification';
    const complete = active && pause.fields.every((field) => {
      const value = answers[field];
      return field === 'submission_declaration' ? value === true : Boolean(String(value ?? '').trim());
    });
    return (
      <section className="canvas-detail-card human-interaction-card">
        <header><MessageCircleQuestion size={15} /><div><span className="panel-kicker">Human interaction</span><h3>Clarification required</h3></div></header>
        <p>{actionNarrative ?? (active ? pause.message : detail ? 'The plain-language action explanation is temporarily unavailable.' : 'No clarification is active for this step yet.')}</p>
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
        <button disabled={!complete} onClick={() => onClarificationSubmit(answers)} type="button">Submit validated clarification</button>
      </section>
    );
  }

  if (selectedNodeId === 'human_approval' || selectedNodeId === 'pause_checkpoint') {
    const active = pause?.kind === 'approval';
    return (
      <section className="canvas-detail-card human-interaction-card approval-preview-card">
        <header><UserCheck size={15} /><div><span className="panel-kicker">Simulated approver</span><h3>Approval decision</h3></div><span className="simulated-role">Demo only</span></header>
        <p>{actionNarrative ?? (active ? pause.message : detail ? 'The plain-language approval explanation is temporarily unavailable.' : 'Approval details will appear if the action gate selects this route.')}</p>
        {detail ? <details className="recorded-facts"><summary>View approval record</summary><DetailRows items={[...detail.input_items, ...detail.output_items].slice(0, 6)} /></details> : null}
        <p><ShieldCheck size={12} /> The decision comes from the named approving role; the agent cannot approve its own request.</p>
        <div className="approval-buttons approval-recheck"><button disabled={!active} onClick={onApprovalRecheck} type="button">Re-check authoritative status</button></div>
      </section>
    );
  }

  if (selectedNodeId === 'human_admin_review') {
    return (
      <section className="canvas-detail-card human-interaction-card">
        <header><UserCog size={15} /><div><span className="panel-kicker">Human interaction</span><h3>Administrative handoff</h3></div></header>
        <p>{actionNarrative ?? (detail ? 'The plain-language handoff explanation is temporarily unavailable.' : 'No administrative handoff has been prepared yet.')}</p>
        {detail ? <DetailRows items={detail.state_changes.slice(0, 5)} /> : null}
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
            <details className="recorded-facts"><summary>View action record</summary><DetailRows items={detail.output_items.slice(0, 5)} /><div className="action-state-divider"><span>Persisted state</span></div><DetailRows items={detail.state_changes.slice(0, 5)} /></details>
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
      <NodeDetail detail={data.detail} node={data.selectedNode} />
      <HumanInteraction
        key={`${data.pause?.kind ?? 'none'}-${data.pause?.message ?? 'idle'}`}
        onApprovalRecheck={data.onApprovalRecheck}
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

const edgeTypes = {
  routedEdge: RoutedFlowEdge,
};

export function AgentGraphCanvas({
  onApprovalRecheck,
  onClarificationSubmit,
  onSelectNode,
  runSnapshot,
  selectedNodeId,
}: AgentGraphCanvasProps) {
  const statuses = runSnapshot?.node_statuses ?? {};
  const selectedBase = NODE_SUMMARIES[selectedNodeId] ?? NODE_SUMMARIES.pre_action_verifier;
  const selectedNode = { ...selectedBase, status: statuses[selectedNodeId] ?? 'idle' };
  const inspectorNode: Node<CanvasInspectorNodeData> = {
    id: 'canvas_inspector',
    type: 'inspectorNode',
    position: { x: 0, y: 130 },
    data: {
      selectedNode,
      selectedNodeId,
      detail: runSnapshot?.node_details[selectedNodeId] ?? null,
      pause: runSnapshot?.pause ?? null,
      onApprovalRecheck,
      onClarificationSubmit,
    },
    draggable: false,
    selectable: false,
    zIndex: 3,
  };
  const nodes: Node[] = [
    ...INITIAL_GRAPH_NODES.map((node) => ({
      ...node,
      data: { ...node.data, status: statuses[node.id] ?? 'idle' },
      ariaLabel: `${node.data.label}, ${statusLabels[statuses[node.id] ?? 'idle']}`,
      selected: node.id === selectedNodeId,
    })),
    inspectorNode,
  ];
  const traversedEdges = new Set(runSnapshot?.traversed_edges ?? []);
  const edges = GRAPH_EDGES.map((edge) => {
    const targetStatus = statuses[edge.target];
    if (traversedEdges.has(edge.id) && (targetStatus === 'running' || targetStatus === 'waiting')) {
      return { ...edge, animated: targetStatus === 'running', className: 'flow-edge edge-active' };
    }
    if (traversedEdges.has(edge.id)) {
      return { ...edge, animated: false, className: 'flow-edge edge-completed' };
    }
    return { ...edge, animated: false };
  });

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
        <ReactFlow
          defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12 } }}
          edges={edges}
          edgeTypes={edgeTypes}
          edgesFocusable
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
          proOptions={{ hideAttribution: true }}
          zoomOnDoubleClick={false}
        >
          <Background color="#dbe5f2" gap={24} size={1} variant={BackgroundVariant.Lines} />
          <Controls position="top-right" showInteractive={false} />
        </ReactFlow>
      </div>
    </section>
  );
}
