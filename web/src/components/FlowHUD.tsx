import React, { useMemo } from 'react';
import { ReactFlow, Background, Controls, Edge, Node, Position } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { SubagentStatus } from '../lib/api';

interface FlowHUDProps {
  subagents: SubagentStatus[];
}

export const FlowHUD: React.FC<FlowHUDProps> = ({ subagents }) => {
  // Build nodes and edges dynamically based on active subagents
  const { nodes, edges } = useMemo(() => {
    const initialNodes: Node[] = [
      {
        id: 'jarvis',
        type: 'default',
        data: { label: 'J.A.R.V.I.S. // CORE' },
        position: { x: 250, y: 150 },
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
        style: {
          background: 'rgba(0, 240, 255, 0.1)',
          color: '#00f0ff',
          border: '2px solid #00f0ff',
          borderRadius: '8px',
          fontWeight: 'bold',
          fontSize: '11px',
          fontFamily: 'monospace',
          boxShadow: '0 0 15px rgba(0, 240, 255, 0.2)',
          padding: '10px',
          width: 150,
          textAlign: 'center'
        }
      }
    ];

    const initialEdges: Edge[] = [];

    // Map subagents to peripheral nodes
    subagents.forEach((agent, index) => {
      const angle = (index * 2 * Math.PI) / Math.max(subagents.length, 3);
      const radius = 150;
      const x = 250 + radius * Math.cos(angle) - 75; // center is 250, node width is 150
      const y = 150 + radius * Math.sin(angle);
      
      const agentId = agent.name.toLowerCase();
      
      let color = '#a0a0a0';
      let bgColor = 'rgba(255, 255, 255, 0.05)';
      if (agentId.includes('friday')) {
        color = '#e63946'; // red
        bgColor = 'rgba(230, 57, 70, 0.1)';
      } else if (agentId.includes('homer')) {
        color = '#00f0ff'; // cyan
        bgColor = 'rgba(0, 240, 255, 0.1)';
      } else if (agentId.includes('plato')) {
        color = '#ffd700'; // gold
        bgColor = 'rgba(255, 215, 0, 0.1)';
      }

      initialNodes.push({
        id: agentId,
        type: 'default',
        data: { label: `${agent.name.toUpperCase()} // SUB` },
        position: { x, y },
        style: {
          background: bgColor,
          color,
          border: `1px solid ${color}`,
          borderRadius: '6px',
          fontFamily: 'monospace',
          fontSize: '10px',
          padding: '8px',
          width: 120,
          textAlign: 'center',
          boxShadow: agent.activity === 'working' ? `0 0 12px ${color}44` : 'none'
        }
      });

      // Add edge from jarvis to agent
      initialEdges.push({
        id: `edge-${agentId}`,
        source: 'jarvis',
        target: agentId,
        animated: agent.activity === 'working',
        style: {
          stroke: agent.activity === 'working' ? color : 'rgba(255, 255, 255, 0.15)',
          strokeWidth: agent.activity === 'working' ? 2 : 1
        }
      });
    });

    return { nodes: initialNodes, edges: initialEdges };
  }, [subagents]);

  return (
    <div className="flex-1 h-full min-h-0 bg-stark-bg relative">
      {/* Title Header */}
      <div className="absolute top-4 left-4 z-10 p-3 rounded border border-white/5 bg-stark-panel/60 backdrop-blur-md font-mono text-[10px] text-white/50 space-y-1">
        <div className="text-stark-cyan font-bold tracking-widest uppercase">COGNITIVE GRAPH HUD</div>
        <div>FLOW Telemetry & Dispatch Nodes</div>
      </div>
      
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        className="w-full h-full"
      >
        <Background color="rgba(255, 255, 255, 0.03)" gap={16} size={1} />
        <Controls showInteractive={false} className="bg-stark-panel border border-white/10 text-white fill-white" />
      </ReactFlow>
    </div>
  );
};
export default FlowHUD;
