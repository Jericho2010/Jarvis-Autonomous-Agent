import React, { useState } from 'react';
import { Bot, Terminal, Eye, Cpu, BookOpen, Compass, CornerDownRight, CheckCircle, AlertTriangle } from 'lucide-react';
import { SubagentStatus, getSubagentDetails, SubagentDetail } from '../lib/api';

interface SubagentsRosterProps {
  subagents: SubagentStatus[];
}

export const SubagentsRoster: React.FC<SubagentsRosterProps> = ({ subagents }) => {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [details, setDetails] = useState<SubagentDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const handleAgentClick = async (name: string) => {
    const cleanName = name.toLowerCase();
    if (!['friday', 'homer', 'plato'].includes(cleanName)) return;

    setSelectedAgent(name);
    setLoading(true);
    try {
      const data = await getSubagentDetails(cleanName);
      setDetails(data);
    } catch (e) {
      console.error(e);
      setDetails(null);
    } finally {
      setLoading(false);
    }
  };
  
  const getAgentIcon = (name: string) => {
    const n = name.toLowerCase();
    if (n.includes('friday')) return Cpu;
    if (n.includes('homer')) return Eye;
    if (n.includes('plato')) return BookOpen;
    return Bot;
  };

  const getStatusDetails = (activity: SubagentStatus['activity']) => {
    switch (activity) {
      case 'working':
        return {
          color: 'text-stark-cyan',
          bgColor: 'bg-stark-cyan/10',
          dotColor: 'bg-stark-cyan',
          label: '夢想 // Dreaming'
        };
      case 'awaiting':
        return {
          color: 'text-stark-gold',
          bgColor: 'bg-stark-gold/10',
          dotColor: 'bg-stark-gold',
          label: 'Awaiting Action'
        };
      case 'done':
        return {
          color: 'text-green-400',
          bgColor: 'bg-green-400/10',
          dotColor: 'bg-green-400',
          label: 'Offline // Idle'
        };
      case 'failed':
        return {
          color: 'text-stark-red',
          bgColor: 'bg-stark-red/10',
          dotColor: 'bg-stark-red',
          label: 'Error Alert'
        };
      default:
        return {
          color: 'text-white/40',
          bgColor: 'bg-white/5',
          dotColor: 'bg-white/20',
          label: 'Offline // Idle'
        };
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0 bg-stark-panel/30 border-l border-white/5 w-72 shrink-0">
      <div className="p-4 border-b border-white/5">
        <h2 className="text-xs font-mono font-bold tracking-widest text-stark-cyan flex items-center gap-1.5">
          <Cpu className="w-3.5 h-3.5" />
          COGNITIVE MATRIX
        </h2>
      </div>
      
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {/* Core J.A.R.V.I.S. node */}
        <div className="p-2.5 rounded border border-white/5 bg-stark-panel/50 hover:border-stark-cyan/20 transition-all">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-stark-cyan glow-cyan" />
              <span className="text-xs font-bold font-mono">J.A.R.V.I.S. (Core)</span>
            </div>
            <span className="text-[9px] font-mono text-stark-cyan px-1.5 py-0.5 rounded bg-stark-cyan/10 border border-stark-cyan/15">
              ORCHESTRATOR
            </span>
          </div>
          <p className="text-[10px] text-white/40 font-mono mt-1">Stark Core Matrix Core routing active.</p>
        </div>

        {/* Subagents Tree list */}
        <div className="space-y-1.5">
          <div className="text-[10px] font-mono font-bold text-white/30 uppercase px-1 tracking-wider">
            Active Sub-routines
          </div>
          
          {subagents.map((agent) => {
            const Icon = getAgentIcon(agent.name);
            const status = getStatusDetails(agent.activity);
            const isClickable = ['friday', 'homer', 'plato'].includes(agent.name.toLowerCase());
            
            return (
              <div 
                key={agent.name}
                onClick={() => isClickable && handleAgentClick(agent.name)}
                style={{ paddingLeft: `${agent.nestedLevel * 14}px` }}
                className={`flex flex-col p-2 rounded transition-all hover:bg-white/5 border border-transparent ${
                  isClickable ? 'cursor-pointer hover:border-white/10' : ''
                } ${
                  agent.activity === 'working' ? 'bg-stark-cyan/5 border-stark-cyan/10' : ''
                }`}
              >
                <div className="flex items-center gap-1">
                  {agent.nestedLevel > 0 && (
                    <CornerDownRight className="w-3.5 h-3.5 text-white/20 -ml-1.5" />
                  )}
                  <Icon className={`w-3.5 h-3.5 ${agent.activity === 'working' ? 'text-stark-cyan' : 'text-white/60'}`} />
                  <span className="text-xs font-mono font-bold text-white/80">{agent.name.toUpperCase()}</span>
                  
                  <span className="flex-1" />
                  
                  {/* Status dot */}
                  <span className={`inline-flex items-center gap-1 text-[9px] font-mono px-1.5 py-0.5 rounded ${status.bgColor} ${status.color}`}>
                    {agent.activity === 'working' ? (
                      <span className="relative flex w-1.5 h-1.5">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-stark-cyan opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-stark-cyan"></span>
                      </span>
                    ) : (
                      <span className={`w-1.5 h-1.5 rounded-full ${status.dotColor}`} />
                    )}
                    {status.label}
                  </span>
                </div>
                
                {agent.lastMessage && (
                  <p className="text-[10px] text-white/50 font-mono pl-[18px] mt-1 truncate border-l border-white/5">
                    {agent.lastMessage}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>
      
      {/* Bottom telemetry panel */}
      <div className="p-3 bg-black/20 border-t border-white/5 font-mono text-[10px] text-white/30 space-y-1.5">
        <div className="flex justify-between">
          <span>HOST CORE:</span>
          <span className="text-stark-gold font-bold">NVIDIA NIM APIS</span>
        </div>
        <div className="flex justify-between">
          <span>SYS TEMP:</span>
          <span className="text-white/60">42.4°C [STABLE]</span>
        </div>
        <div className="flex justify-between">
          <span>THREAT LEVEL:</span>
          <span className="text-white/60">ZERO [STANDBY]</span>
        </div>
      </div>

      {/* Roster Profile Details Modal */}
      {selectedAgent && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4 font-sans text-white">
          <div className="bg-stark-panel border border-stark-cyan/30 rounded-lg max-w-lg w-full overflow-hidden shadow-2xl glow-cyan flex flex-col max-h-[85vh]">
            {/* Modal Header */}
            <div className="p-4 border-b border-white/5 flex items-center justify-between bg-black/25">
              <div className="flex items-center gap-2">
                <Bot className="w-5 h-5 text-stark-cyan glow-cyan" />
                <div>
                  <h3 className="text-sm font-bold font-mono text-white uppercase tracking-wider">{selectedAgent} Roster Profile</h3>
                  <p className="text-[10px] text-white/40 font-mono">Cognitive Matrix Agent Details</p>
                </div>
              </div>
              <button 
                onClick={() => { setSelectedAgent(null); setDetails(null); }}
                className="text-white/45 hover:text-stark-red transition-colors font-mono text-xs border border-white/10 hover:border-stark-red/30 px-2 py-1 rounded bg-white/5 cursor-pointer"
              >
                CLOSE [X]
              </button>
            </div>

            {/* Modal Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {loading ? (
                <div className="py-12 flex flex-col items-center justify-center gap-2 text-white/40">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-stark-cyan"></div>
                  <span className="text-xs font-mono">RETRIEVING PROFILE TELEMETRY...</span>
                </div>
              ) : details ? (
                <>
                  {/* Model Spec */}
                  <div className="p-3 bg-black/20 border border-white/5 rounded">
                    <span className="text-[10px] font-mono text-white/30 uppercase block mb-1">PRIMARY ROUTING MODEL:</span>
                    <span className="text-xs font-mono font-bold text-stark-gold">{details.model}</span>
                  </div>

                  {/* Instructions / Soul Prompt */}
                  <div className="space-y-1.5">
                    <span className="text-[10px] font-mono text-white/30 uppercase block">SOUL PROMPT & INSTRUCTIONS:</span>
                    <div className="p-3 bg-black/40 border border-white/5 rounded text-xs text-white/80 font-sans leading-relaxed max-h-48 overflow-y-auto whitespace-pre-wrap select-text selection:bg-stark-cyan/35 selection:text-white">
                      {details.instructions}
                    </div>
                  </div>

                  {/* Active Tool Inventory */}
                  <div className="space-y-2">
                    <span className="text-[10px] font-mono text-white/30 uppercase block">ACTIVE TOOL INVENTORY:</span>
                    <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                      {details.tools && details.tools.length > 0 ? (
                        details.tools.map((tool, idx) => (
                          <div key={idx} className="p-2 border border-white/5 bg-white/5 rounded flex flex-col">
                            <span className="text-xs font-mono font-bold text-stark-cyan uppercase tracking-wider">{tool.name}</span>
                            <span className="text-[10px] text-white/50 mt-0.5">{tool.description}</span>
                          </div>
                        ))
                      ) : (
                        <div className="text-xs text-white/30 italic">No tools registered for this agent.</div>
                      )}
                    </div>
                  </div>
                </>
              ) : (
                <div className="py-8 text-center text-xs text-stark-red font-mono">
                  FAILED TO LOAD AGENT TELEMETRY
                </div>
              )}
            </div>
            
            {/* Modal Footer */}
            <div className="p-3 border-t border-white/5 bg-black/15 flex justify-end">
              <button 
                onClick={() => { setSelectedAgent(null); setDetails(null); }}
                className="text-xs font-mono bg-stark-cyan/15 hover:bg-stark-cyan/25 text-stark-cyan border border-stark-cyan/20 px-3 py-1.5 rounded transition-all glow-cyan cursor-pointer"
              >
                PROCEED
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
