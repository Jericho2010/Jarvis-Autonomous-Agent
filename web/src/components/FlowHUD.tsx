import React, { useMemo } from 'react';
import { ReactFlow, Background, Controls, Edge, Node, Position } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { SubagentStatus } from '../lib/api';
import { GraphEvent, formatGraphEventLabel } from '../lib/graphEvents';

interface FlowHUDProps {
  subagents: SubagentStatus[];
  currentAgentId: string;
  activeTool: string | null;
  graphEvents: GraphEvent[];
  onAgentClick?: (agentId: string) => void;
}

const AGENT_COLORS: Record<string, { color: string; bg: string }> = {
  jarvis: { color: '#00f0ff', bg: 'rgba(0, 240, 255, 0.1)' },
  friday: { color: '#e63946', bg: 'rgba(230, 57, 70, 0.1)' },
  homer: { color: '#00f0ff', bg: 'rgba(0, 240, 255, 0.08)' },
  plato: { color: '#ffd700', bg: 'rgba(255, 215, 0, 0.1)' },
};

export const FlowHUD: React.FC<FlowHUDProps> = ({
  subagents,
  currentAgentId,
  activeTool,
  graphEvents,
  onAgentClick,
}) => {
  const activeId = currentAgentId.toLowerCase();

  const { nodes, edges } = useMemo(() => {
    const initialNodes: Node[] = [
      {
        id: 'jarvis',
        type: 'default',
        data: {
          label: (
            <div className="text-center">
              <div>J.A.R.V.I.S.</div>
              {activeId === 'jarvis' && activeTool && (
                <div className="text-[8px] mt-1 opacity-80 font-normal">running: {activeTool}</div>
              )}
            </div>
          ),
        },
        position: { x: 220, y: 140 },
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
        style: {
          background: AGENT_COLORS.jarvis.bg,
          color: AGENT_COLORS.jarvis.color,
          border: `2px solid ${activeId === 'jarvis' ? AGENT_COLORS.jarvis.color : 'rgba(0,240,255,0.35)'}`,
          borderRadius: '8px',
          fontWeight: 'bold',
          fontSize: '11px',
          fontFamily: 'monospace',
          boxShadow: activeId === 'jarvis' ? '0 0 18px rgba(0, 240, 255, 0.35)' : '0 0 10px rgba(0, 240, 255, 0.15)',
          padding: '10px',
          width: 150,
          textAlign: 'center',
          cursor: 'default',
        },
      },
    ];

    const initialEdges: Edge[] = [];
    const specialists = [
      { id: 'homer', label: 'HOMER' },
      { id: 'friday', label: 'FRIDAY' },
      { id: 'plato', label: 'PLATO' },
    ];

    specialists.forEach((spec, index) => {
      const agent = subagents.find((s) => s.name.toLowerCase() === spec.id);
      const activity = agent?.activity || 'idle';
      const isActive = activeId === spec.id;
      const palette = AGENT_COLORS[spec.id] || AGENT_COLORS.jarvis;
      const angle = (index * 2 * Math.PI) / specialists.length - Math.PI / 2;
      const radius = 160;
      const x = 220 + radius * Math.cos(angle) - 60;
      const y = 140 + radius * Math.sin(angle);

      initialNodes.push({
        id: spec.id,
        type: 'default',
        data: {
          label: (
            <div className="text-center">
              <div>{spec.label}</div>
              {isActive && activeTool && (
                <div className="text-[8px] mt-1 opacity-80 font-normal">running: {activeTool}</div>
              )}
            </div>
          ),
        },
        position: { x, y },
        style: {
          background: palette.bg,
          color: palette.color,
          border: `1px solid ${isActive || activity === 'working' ? palette.color : 'rgba(255,255,255,0.2)'}`,
          borderRadius: '6px',
          fontFamily: 'monospace',
          fontSize: '10px',
          padding: '8px',
          width: 120,
          textAlign: 'center',
          boxShadow: isActive || activity === 'working' ? `0 0 14px ${palette.color}55` : 'none',
          cursor: 'pointer',
        },
      });

      initialEdges.push({
        id: `edge-${spec.id}`,
        source: 'jarvis',
        target: spec.id,
        animated: isActive || activity === 'working',
        style: {
          stroke: isActive || activity === 'working' ? palette.color : 'rgba(255, 255, 255, 0.15)',
          strokeWidth: isActive || activity === 'working' ? 2 : 1,
        },
      });
    });

    return { nodes: initialNodes, edges: initialEdges };
  }, [subagents, activeId, activeTool]);

  const onNodeClick = (_: React.MouseEvent, node: Node) => {
    if (node.id === 'jarvis') return;
    onAgentClick?.(node.id);
  };

  return (
    <div className="flex-1 h-full min-h-0 bg-stark-bg flex min-w-0">
      <div className="flex-1 relative min-w-0">
        <div className="absolute top-4 left-4 z-10 p-3 rounded border border-white/5 bg-stark-panel/60 backdrop-blur-md font-mono text-[10px] text-white/50 space-y-1">
          <div className="text-stark-cyan font-bold tracking-widest uppercase">COGNITIVE GRAPH</div>
          <div>Active: <span className="text-stark-gold">{activeId.toUpperCase()}</span></div>
          {activeTool && <div>Tool: <span className="text-white/70">{activeTool}</span></div>}
        </div>

        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          className="w-full h-full"
          onNodeClick={onNodeClick}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
        >
          <Background color="rgba(255, 255, 255, 0.03)" gap={16} size={1} />
          <Controls showInteractive={false} className="bg-stark-panel border border-white/10 text-white fill-white" />
        </ReactFlow>
      </div>

      <div className="w-72 shrink-0 border-l border-white/5 bg-stark-panel/20 flex flex-col min-h-0">
        <div className="p-3 border-b border-white/5 font-mono text-[10px] text-stark-cyan font-bold tracking-widest uppercase">
          Session Timeline
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1.5 font-mono text-[10px]">
          {graphEvents.length === 0 ? (
            <div className="text-white/30 p-2">No handoffs or tools yet this session.</div>
          ) : (
            graphEvents.map((event, idx) => (
              <div
                key={`${event.ts}-${idx}`}
                className="p-2 rounded border border-white/5 bg-black/20 text-white/60"
              >
                <div className="text-[9px] text-white/30">
                  {new Date(event.ts).toLocaleTimeString()}
                </div>
                <div className="text-white/80 mt-0.5">{formatGraphEventLabel(event)}</div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default FlowHUD;
