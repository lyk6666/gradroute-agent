import type { MouseEvent as ReactMouseEvent } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
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
import {
  GRAPH_EDGES,
  INITIAL_GRAPH_NODES,
  NODE_SUMMARIES,
  type AgentNodeData,
  type NodeStatus,
  type NodeSummary,
} from './workspace-data';
import '@xyflow/react/dist/style.css';

type AgentGraphCanvasProps = {
  onSelectNode: (nodeId: string) => void;
  selectedNodeId: string;
};

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
      <Handle id="left" position={Position.Left} type="target" />
      <Handle id="top" position={Position.Top} type="source" />
      <Handle id="left" position={Position.Left} type="source" />
      <span className="agent-node-icon"><Icon aria-hidden="true" size={14} /></span>
      <span className="agent-node-copy"><strong>{data.label}</strong><small><StatusIcon status={data.status} /> {statusLabels[data.status]}</small></span>
      <Handle id="right" position={Position.Right} type="source" />
      <Handle id="bottom" position={Position.Bottom} type="source" />
      <Handle id="right" position={Position.Right} type="target" />
      <Handle id="bottom" position={Position.Bottom} type="target" />
    </div>
  );
}

const nodeTypes = { agentNode: AgentFlowNode };

function NodeDetail({ node }: { node: NodeSummary }) {
  const Icon = node.icon;
  return (
    <section className="canvas-detail-card node-detail-card" aria-label={`${node.label} details`}>
      <header>
        <span className="detail-node-icon"><Icon size={15} /></span>
        <div><span className="panel-kicker">Selected node</span><h3>{node.label}</h3></div>
        <span className={`detail-status status-${node.status}`}><StatusIcon status={node.status} />{statusLabels[node.status]}</span>
      </header>
      <p className="node-purpose">{node.purpose}</p>
      <dl className="node-summary-list">
        <div><dt>Input</dt><dd>{node.input}</dd></div>
        <div><dt>Output</dt><dd>{node.output}</dd></div>
        <div><dt>State</dt><dd>{node.stateChange}</dd></div>
      </dl>
      <div className="node-tool-summary">
        <span>Tools</span>
        <strong>{node.tools.length ? node.tools.join(' · ') : 'No external tool used'}</strong>
      </div>
    </section>
  );
}

function HumanInteraction({ selectedNodeId }: { selectedNodeId: string }) {
  if (selectedNodeId === 'clarification') {
    return (
      <section className="canvas-detail-card human-interaction-card">
        <header><MessageCircleQuestion size={15} /><div><span className="panel-kicker">Human interaction</span><h3>Clarification required</h3></div></header>
        <p>Confirm whether the pending external prerequisite credit has supporting evidence.</p>
        <label><span>Response</span><textarea disabled placeholder="Clarification response is enabled in UI-3." rows={2} /></label>
        <button disabled type="button">Submit clarification in UI-3</button>
      </section>
    );
  }

  if (selectedNodeId === 'human_approval' || selectedNodeId === 'pause_checkpoint') {
    return (
      <section className="canvas-detail-card human-interaction-card approval-preview-card">
        <header><UserCheck size={15} /><div><span className="panel-kicker">Simulated approver</span><h3>Approval decision</h3></div><span className="simulated-role">Demo only</span></header>
        <dl>
          <div><dt>Action</dt><dd>Submit prerequisite exception</dd></div>
          <div><dt>Approver</dt><dd>CCDS Undergraduate Office</dd></div>
          <div><dt>Version</dt><dd>Approval v1</dd></div>
        </dl>
        <p><ShieldCheck size={12} /> Evidence and policy basis must remain authoritative at resume.</p>
        <div className="approval-buttons"><button disabled type="button">Approve</button><button disabled type="button">Reject</button><button disabled type="button">Leave pending</button></div>
      </section>
    );
  }

  if (selectedNodeId === 'human_admin_review') {
    return (
      <section className="canvas-detail-card human-interaction-card">
        <header><UserCog size={15} /><div><span className="panel-kicker">Human interaction</span><h3>Administrative handoff</h3></div></header>
        <p>The agent prepares blockers, attempted plans, supporting evidence and the required administrative role. This is not an approval.</p>
        <ProvenanceBadge kind="derived" />
      </section>
    );
  }

  return (
    <section className="canvas-detail-card human-interaction-card interaction-empty">
      <header><UserCheck size={15} /><div><span className="panel-kicker">Human interaction</span><h3>No action at this node</h3></div></header>
      <p>Clarification, simulated approval and administrative handoff controls appear here only when their corresponding node is selected.</p>
    </section>
  );
}

export function AgentGraphCanvas({ onSelectNode, selectedNodeId }: AgentGraphCanvasProps) {
  const selectedNode = NODE_SUMMARIES[selectedNodeId] ?? NODE_SUMMARIES.pre_action_verifier;
  const nodes = INITIAL_GRAPH_NODES.map((node) => ({ ...node, selected: node.id === selectedNodeId }));

  return (
    <section className="workspace-panel graph-panel">
      <header className="workspace-panel-header graph-panel-header">
        <div><span className="panel-kicker">Plan → Act → Observe → Verify → Replan</span><h2>Agent execution graph</h2></div>
        <div className="graph-legend" aria-label="Graph status legend">
          <span><i className="legend-running" />Current</span>
          <span><i className="legend-selected" />Selected</span>
          <span><i className="legend-completed" />Completed</span>
          <span><i className="legend-idle" />Not visited</span>
          <b>Static preview</b>
        </div>
      </header>

      <div className="agent-canvas-shell">
        <ReactFlow
          defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12 } }}
          edges={GRAPH_EDGES}
          edgesFocusable
          elementsSelectable
          fitView
          fitViewOptions={{ padding: 0.04, maxZoom: 0.8 }}
          maxZoom={1.45}
          minZoom={0.34}
          nodeTypes={nodeTypes}
          nodes={nodes}
          nodesConnectable={false}
          nodesDraggable={false}
          onNodeClick={(_event: ReactMouseEvent, node) => onSelectNode(node.id)}
          panOnScroll
          proOptions={{ hideAttribution: true }}
          zoomOnDoubleClick={false}
        >
          <Background color="#dbe5f2" gap={24} size={1} variant={BackgroundVariant.Lines} />
          <Controls position="top-right" showInteractive={false} />
        </ReactFlow>

        <aside className="canvas-internal-rail">
          <NodeDetail node={selectedNode} />
          <HumanInteraction selectedNodeId={selectedNodeId} />
        </aside>
      </div>
    </section>
  );
}
