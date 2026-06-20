import React, { useState, useEffect, useRef } from 'react';
import { 
  discoverPort,
  getApiUrl,
  listSessions, 
  createSession, 
  sendChatMessage, 
  getSessionStream, 
  Session, 
  ChatMessage, 
  SubagentStatus,
  getSessionHistory,
  getSessionModel,
  setSessionModel,
  getAvailableModels,
  getSessionDetail,
  switchSessionAgent
} from './lib/api';
import { ReactorHUD } from './components/ReactorHUD';
import { SubagentsRoster } from './components/SubagentsRoster';
import { ChatStream } from './components/ChatStream';
import { ConsoleHUD } from './components/ConsoleHUD';
import { RetinalHUD } from './components/RetinalHUD';
import { FlowHUD } from './components/FlowHUD';
import { useVoiceMode } from './hooks/useVoiceMode';

import { 
  Bot, 
  MessageSquare, 
  Layers, 
  Terminal, 
  Eye, 
  Plus, 
  Sparkles,
  ChevronRight,
  ShieldAlert
} from 'lucide-react';

export default function App() {
  const [status, setStatus] = useState<'online' | 'offline'>('offline');
  const [port, setPort] = useState<number | null>(null);
  const [currentModel, setCurrentModel] = useState<string>('house-party');
  const [currentAgent, setCurrentAgent] = useState<string>('jarvis');
  
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  
  // Tab states
  const [activeTab, setActiveTab] = useState<'chat' | 'network' | 'retinal' | 'terminal'>('chat');
  
  // Streaming states
  const [streamingText, setStreamingText] = useState('');
  const [streamingReasoning, setStreamingReasoning] = useState('');
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [activeToolArgs, setActiveToolArgs] = useState<any>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null);
  
  const eventSourceRef = useRef<EventSource | null>(null);
  const voice = useVoiceMode();
  const playSpeechRef = useRef(voice.playSpeech);
  playSpeechRef.current = voice.playSpeech;

  // Subagents Status Matrix
  const [subagents, setSubagents] = useState<SubagentStatus[]>([
    { name: 'friday', activity: 'idle', nestedLevel: 1 },
    { name: 'homer', activity: 'idle', nestedLevel: 1 },
    { name: 'plato', activity: 'idle', nestedLevel: 1 }
  ]);

  // Discover server and load sessions
  useEffect(() => {
    async function initServer() {
      try {
        const resolvedPort = await discoverPort();
        setPort(resolvedPort);
        setStatus('online');
        
        const sessionsList = await listSessions();
        setSessions(sessionsList);
        
        if (sessionsList.length > 0) {
          setCurrentSessionId(sessionsList[0].session_id);
        } else {
          // If no sessions, create a new one
          const newId = await createSession();
          setCurrentSessionId(newId);
          const updatedList = await listSessions();
          setSessions(updatedList);
        }
      } catch (e) {
        setStatus('offline');
        console.error('Server offline or failed to connect:', e);
      }
    }
    
    initServer();
    
    // Polling server health
    const interval = setInterval(async () => {
      try {
        const baseUrl = await getApiUrl();
        const res = await fetch(`${baseUrl}/health`);
        const data = await res.json();
        if (data.service === 'jarvis') {
          setStatus('online');
        } else {
          setStatus('offline');
        }
      } catch (e) {
        setStatus('offline');
      }
    }, 4000);
    
    return () => clearInterval(interval);
  }, [port]);

  // Manage SSE connection lifecycle when currentSessionId changes
  useEffect(() => {
    if (!currentSessionId) return;
    
    // Reset states
    setMessages([]);
    setStreamingText('');
    setStreamingReasoning('');
    setActiveTool(null);
    setActiveToolArgs(null);
    setScreenshotUrl(null);

    // Fetch actual history and details
    getSessionHistory(currentSessionId).then(history => {
      setMessages(history);
    });
    getSessionDetail(currentSessionId).then(detail => {
      if (detail) {
        setCurrentModel(detail.model || 'house-party');
        setCurrentAgent(detail.agent_id || 'jarvis');
      }
    });
    
    // Write TTY clear line
    setLogs(['\x1b[33m--- Connecting to session: ' + currentSessionId + ' ---\x1b[0m']);

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    let accumulatedText = '';
    let accumulatedReasoning = '';

    getSessionStream(currentSessionId, (type, data) => {
      const timestamp = Date.now();
      
      if (type === 'text_chunk') {
        const chunk = data.text || '';
        accumulatedText += chunk;
        setStreamingText(accumulatedText);
        
        // Write raw to TTY logs
        setLogs(prev => [...prev, `\x1b[36m${chunk.replace('\n', '\r\n')}\x1b[0m`]);
        
        // If friday or homer is writing, set their status to working
        updateSubagentActivity(accumulatedText);
        
      } else if (type === 'reasoning_chunk') {
        const chunk = data.text || '';
        accumulatedReasoning += chunk;
        setStreamingReasoning(accumulatedReasoning);
        
        setLogs(prev => [...prev, `\x1b[33m[Think]: ${chunk.replace('\n', '\r\n')}\x1b[0m`]);
        
      } else if (type === 'tool_call_start') {
        const name = data.name || 'tool';
        const args = data.arguments || {};
        setActiveTool(name);
        setActiveToolArgs(args);
        
        setLogs(prev => [
          ...prev, 
          `\x1b[1;31m⚙ TOOL START: ${name.toUpperCase()}\x1b[0m`,
          `\x1b[37m  Args: ${JSON.stringify(args)}\x1b[0m`
        ]);
        
        // Update specific subagent activity based on tool call
        if (name.toLowerCase() === 'sys_session_send') {
          const targetAgent = args.subagent || '';
          setSubagents(prev => prev.map(sa => 
            sa.name.toLowerCase() === targetAgent.toLowerCase() 
              ? { ...sa, activity: 'working', lastMessage: 'Delegated: ' + (args.prompt || '').slice(0, 40) + '...' }
              : sa
          ));
        }
        
      } else if (type === 'tool_call_complete') {
        const name = data.name || 'tool';
        const output = data.output || data.error || '';
        setActiveTool(null);
        setActiveToolArgs(null);
        
        setLogs(prev => [
          ...prev, 
          `\x1b[1;32m✔ TOOL COMPLETE: ${name.toUpperCase()}\x1b[0m`,
          `\x1b[37m  Output: ${typeof output === 'string' ? output.slice(0, 150) : 'Object output'}...\x1b[0m`
        ]);
        
        // Check if output contains screenshot path or image data (Homer / Friday)
        if (output && typeof output === 'string' && (output.includes('.png') || output.includes('.jpg'))) {
          // Attempt to match path
          const match = output.match(/(\/[^\s]+?\.(?:png|jpg))/);
          if (match && match[1]) {
            setScreenshotUrl(match[1]);
            setActiveTab('retinal'); // Switch viewport to Retinal HUD on screenshot capture!
          }
        }
        
        // Reset subagent activity on complete
        if (name.toLowerCase() === 'sys_session_send') {
          setSubagents(prev => prev.map(sa => ({ ...sa, activity: 'done' })));
        }
      } else if (type === 'user_message') {
        const text = data.text || '';
        setMessages(prev => [...prev, {
          role: 'user',
          content: text,
          timestamp: data.timestamp ? data.timestamp * 1000 : Date.now()
        }]);
        setLogs(prev => [...prev, `\x1b[1;33m❯ USER: ${text}\x1b[0m`]);

      } else if (type === 'agent_changed') {
        const agentId = data.agent_id || 'jarvis';
        setCurrentAgent(agentId);
        setLogs(prev => [...prev, `\x1b[36m⬡ ACTIVE AGENT SWITCHED TO: ${agentId.toUpperCase()}\x1b[0m`]);

      } else if (type === 'title_changed') {
        const title = data.title || '';
        listSessions().then(setSessions);
        setLogs(prev => [...prev, `\x1b[36m⬡ SESSION TITLE SET TO: ${title}\x1b[0m`]);

      } else if (type === 'voice_ready') {
        const text = data.text || '';
        if (text) {
          void playSpeechRef.current(text);
        }
        void voice.refreshStatus();

      } else if (type === 'turn_complete') {
        // Construct final message
        let finalContent = '';
        if (accumulatedReasoning) {
          finalContent += `<think>\n${accumulatedReasoning}\n</think>\n`;
        }
        finalContent += accumulatedText;
        
        if (finalContent.trim()) {
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: finalContent,
            timestamp
          }]);
        }
        
        // Reset streaming buffers
        setStreamingText('');
        setStreamingReasoning('');
        accumulatedText = '';
        accumulatedReasoning = '';
        
        // Reset subagents activity
        setSubagents(prev => prev.map(sa => ({ ...sa, activity: 'idle', lastMessage: undefined })));
        
        setLogs(prev => [...prev, '\x1b[1;36m✔ TURN COMPLETED // J.A.R.V.I.S. READY\x1b[0m\r\n']);
        
        // Refresh sessions list
        listSessions().then(setSessions);
      }
    }).then(source => {
      eventSourceRef.current = source;
    });

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [currentSessionId]);

  const updateSubagentActivity = (text: string) => {
    // Check if J.A.R.V.I.S. is delegating in text
    const lower = text.toLowerCase();
    if (lower.includes('delegating task to friday')) {
      setSubagents(prev => prev.map(sa => sa.name === 'friday' ? { ...sa, activity: 'working' } : sa));
    } else if (lower.includes('delegating task to homer')) {
      setSubagents(prev => prev.map(sa => sa.name === 'homer' ? { ...sa, activity: 'working' } : sa));
    } else if (lower.includes('delegating task to plato')) {
      setSubagents(prev => prev.map(sa => sa.name === 'plato' ? { ...sa, activity: 'working' } : sa));
    }
  };

  const handleSwitchAgent = async (agentId: string) => {
    if (!currentSessionId) return;
    const ok = await switchSessionAgent(currentSessionId, agentId);
    if (ok) {
      setCurrentAgent(agentId);
      setLogs(prev => [...prev, `\x1b[36m⬡ ACTIVE AGENT SET TO: ${agentId.toUpperCase()}\x1b[0m`]);
    } else {
      setLogs(prev => [...prev, `\x1b[1;31m❌ Failed to switch active agent!\x1b[0m`]);
    }
  };

  const handleSendMessage = async (text: string, files?: { id: string, filename: string, bytes: number }[]) => {
    if (!currentSessionId) return;
    
    const timestamp = Date.now();
    
    // Add user message to state
    setMessages(prev => [...prev, {
      role: 'user',
      content: text,
      timestamp
    }]);
    
    setLogs(prev => [...prev, `\x1b[1;33m❯ USER: ${text}${files && files.length > 0 ? ' (with ' + files.length + ' attachments)' : ''}\x1b[0m`]);

    // Command Interceptor
    const cmd = text.trim();
    if (cmd.startsWith('/')) {
      const parts = cmd.split(' ');
      const base = parts[0].toLowerCase();
      
      if (base === '/help') {
        const lines = [
          '### J.A.R.V.I.S. Core Command Manual\n',
          '  ▪ `/help` - Show this system manual',
          '  ▪ `/new` - Start a fresh dialogue session',
          '  ▪ `/clear` - Clear conversation history',
          '  ▪ `/models` - List available models in matrix',
          '  ▪ `/model <index|name|house_party>` - Set primary routing model',
          '  ▪ `/subagents` - Display cognitive subagent directory',
          '  ▪ `/tasks` - Display implementation tasks checklist',
          '  ▪ `/skills` - List all loaded skill modules',
          '  ▪ `/voicemode` - Toggle spoken butler voice (`/voicemode on|off`)'
        ];
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: lines.join('\n'),
          timestamp: Date.now()
        }]);
        return;
      }
      
      if (base === '/models') {
        try {
          const models = await getAvailableModels();
          const lines = [
            '**Stark Core Matrix Models:**',
            ...models.map((m, idx) => {
              const bullet = m === currentModel ? '⬡' : ' ';
              const suffix = m === 'house-party' ? ' (Dynamic Multi-Model Protocol)' : '';
              return `  ${bullet} ${idx + 1}. **${m}**${suffix}`;
            }),
            '\nUsage: `/model <index|name|house_party>`'
          ];
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: lines.join('\n'),
            timestamp: Date.now()
          }]);
        } catch (e) {
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: '❌ Failed to retrieve available models from API server.',
            timestamp: Date.now()
          }]);
        }
        return;
      } 
      
      if (base === '/model') {
        if (parts.length < 2) {
          try {
            const models = await getAvailableModels();
            const lines = [
              '**Stark Core Matrix Models:**',
              ...models.map((m, idx) => {
                const bullet = m === currentModel ? '⬡' : ' ';
                const suffix = m === 'house-party' ? ' (Dynamic Multi-Model Protocol)' : '';
                return `  ${bullet} ${idx + 1}. **${m}**${suffix}`;
              }),
              '\nUsage: `/model <index|name|house_party>`'
            ];
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: lines.join('\n'),
              timestamp: Date.now()
            }]);
          } catch (e) {
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: '❌ Failed to retrieve available models from API server.',
              timestamp: Date.now()
            }]);
          }
          return;
        }
        const arg = parts.slice(1).join(' ').trim().toLowerCase();
        try {
          const models = await getAvailableModels();
          let matched: string | null = null;
          if (['house_party', 'houseparty', 'house', 'h', 'dynamic', 'd'].includes(arg)) {
            matched = 'house-party';
          } else {
            const idx = parseInt(arg, 10) - 1;
            if (!isNaN(idx) && idx >= 0 && idx < models.length) {
              matched = models[idx];
            } else {
              matched = models.find(m => m.toLowerCase().includes(arg)) || null;
            }
          }
          
          if (!matched) {
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: `❌ Model '${arg}' not found in matrix.`,
              timestamp: Date.now()
            }]);
            return;
          }
          
          const ok = await setSessionModel(currentSessionId, matched);
          if (ok) {
            setCurrentModel(matched);
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: `✓ Primary routing set to: **${matched}**`,
              timestamp: Date.now()
            }]);
          } else {
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: `❌ Failed to update model.`,
              timestamp: Date.now()
            }]);
          }
        } catch (e) {
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: `❌ Connection error.`,
            timestamp: Date.now()
          }]);
        }
        return;
      }

      if (base === '/voicemode') {
        try {
          if (parts.length < 2) {
            const status = await voice.refreshStatus();
            const lines = [
              '### Voice Mode Status',
              `  ▪ **State:** ${status?.enabled ? 'ON' : 'OFF'}`,
              `  ▪ **Voice:** ${status?.voice || 'unresolved'} (${status?.gender || 'unknown'})`,
              `  ▪ **TTS:** ${status?.tts_available ? 'available' : 'unavailable'}`,
              `  ▪ **STT:** ${status?.stt_available ? 'available' : 'unavailable'}`,
            ];
            if (status?.persona_warning) {
              lines.push(`  ▪ **Warning:** ${status.persona_warning}`);
            }
            lines.push('\nUsage: `/voicemode on|off`');
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: lines.join('\n'),
              timestamp: Date.now()
            }]);
            return;
          }

          const arg = parts[1].trim().toLowerCase();
          let enabled: boolean | null = null;
          if (['on', 'true', '1', 'yes', 'enable'].includes(arg)) enabled = true;
          if (['off', 'false', '0', 'no', 'disable'].includes(arg)) enabled = false;
          if (enabled === null) {
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: 'Usage: `/voicemode on|off`',
              timestamp: Date.now()
            }]);
            return;
          }

          await voice.toggleVoiceMode(enabled);
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: enabled
              ? '✓ Voice mode enabled. Jarvis will speak in a male English butler voice. Hold the microphone button to dictate.'
              : '✓ Voice mode disabled.',
            timestamp: Date.now()
          }]);
        } catch (e) {
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: `❌ Failed to update voice mode: ${e instanceof Error ? e.message : 'Unknown error'}`,
            timestamp: Date.now()
          }]);
        }
        return;
      }
      
      if (['/subagents', '/agents', '/sub'].includes(base)) {
        const lines = [
          '### Cognitive Sub-routines Matrix\n',
          '**F.R.I.D.A.Y. (Tactical HUD Assistant)**',
          '  ▪ **Focus:** Desktop automation, window management, screen captures & execution.',
          '  ▪ **Model:** `nvidia/stepfun-ai/step-3.7-flash`',
          "  ▪ **Usage:** Ask J.A.R.V.I.S.: 'Ask Friday to take a screenshot' or 'Run command on Friday'.\n",
          '**H.O.M.E.R. (Scholarly Research Intel)**',
          '  ▪ **Focus:** Multi-engine web search, clean page structures, Playwright navigation & grounding.',
          '  ▪ **Model:** `nvidia/mistralai/mistral-large-3-675b-instruct-2512`',
          "  ▪ **Usage:** Ask J.A.R.V.I.S.: 'Ask Homer to search the web for...'.\n",
          '**P.L.A.T.O. (Logical Strategy Consultant)**',
          '  ▪ **Focus:** Deep reasoning, static code analysis, complex problem solving & drafting.',
          '  ▪ **Model:** `nvidia/deepseek-ai/deepseek-v4-pro`',
          "  ▪ **Usage:** Ask J.A.R.V.I.S.: 'Ask Plato to review my code in...'"
        ];
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: lines.join('\n'),
          timestamp: Date.now()
        }]);
        return;
      }
    }

    const ok = await sendChatMessage(currentSessionId, text, files);
    if (!ok) {
      setLogs(prev => [...prev, '\x1b[1;31m❌ Error sending prompt to API server!\x1b[0m']);
    }
  };

  const handleNewSession = async () => {
    try {
      const newId = await createSession();
      setCurrentSessionId(newId);
      const updatedList = await listSessions();
      setSessions(updatedList);
    } catch (e) {
      console.error('Failed to create new session:', e);
    }
  };

  const handleClearSession = () => {
    setMessages([]);
    setStreamingText('');
    setStreamingReasoning('');
    setLogs([]);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-stark-bg text-white font-sans antialiased select-none">
      
      {/* 1. Left Sidebar: Session history & Reactor Core */}
      <div className="w-64 border-r border-white/5 bg-stark-panel/30 flex flex-col h-full shrink-0">
        <div className="p-4 border-b border-white/5 flex items-center justify-between">
          <h1 className="text-xs font-mono font-bold tracking-widest text-stark-cyan flex items-center gap-1.5">
            <Bot className="w-4 h-4 text-stark-cyan animate-pulse glow-cyan" />
            J.A.R.V.I.S.
          </h1>
          <button 
            onClick={handleNewSession}
            className="p-1 rounded bg-stark-cyan/10 text-stark-cyan hover:bg-stark-cyan/20 border border-stark-cyan/25 glow-cyan transition-all"
            title="Start New dialogue"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>
        
        {/* Arc Reactor Diagnostics view */}
        <ReactorHUD status={status} port={port} />
        
        {/* Sessions list */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          <div className="text-[9px] font-mono text-white/30 uppercase px-2 py-1.5 tracking-wider">
            DIALOGUE SESSION HISTORY
          </div>
          {sessions.map((s) => (
            <button
              key={s.session_id}
              onClick={() => setCurrentSessionId(s.session_id)}
              className={`w-full text-left p-2 rounded text-xs font-mono flex items-center justify-between transition-all border ${
                currentSessionId === s.session_id
                  ? 'bg-stark-cyan/5 border-stark-cyan/25 text-stark-cyan glow-cyan'
                  : 'bg-transparent border-transparent text-white/60 hover:bg-white/5 hover:text-white'
              }`}
            >
              <span className="truncate">{s.title || s.session_id}</span>
              <ChevronRight className="w-3 h-3 opacity-40 shrink-0" />
            </button>
          ))}
        </div>
      </div>

      {/* 2. Main Area: Tabs navigation + Viewport */}
      <div className="flex-1 flex flex-col h-full min-w-0">
        {/* Top Navbar */}
        <div className="h-12 border-b border-white/5 bg-stark-panel/20 flex items-center justify-between px-4 shrink-0">
          <div className="flex items-center gap-4 font-mono text-xs">
            <div className="flex items-center gap-1">
              <span className="text-white/40">HUD MODE //</span>
              <span className="text-stark-cyan font-bold tracking-wider uppercase">{activeTab}</span>
            </div>
            <div className="h-3 w-[1px] bg-white/10" />
            <div className="flex items-center gap-1">
              <span className="text-white/40">MODEL //</span>
              <span className="text-stark-gold font-bold tracking-wider uppercase">{currentModel}</span>
            </div>
            <div className="h-3 w-[1px] bg-white/10" />
            <div className="flex items-center gap-1">
              <span className="text-white/40">AGENT //</span>
              <span className="text-stark-cyan font-bold tracking-wider uppercase">{currentAgent}</span>
            </div>
          </div>
          
          {/* HUD Navigation Tabs */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => setActiveTab('chat')}
              className={`px-3 py-1.5 rounded text-xs font-mono flex items-center gap-1 transition-all border ${
                activeTab === 'chat'
                  ? 'bg-stark-cyan/10 border-stark-cyan/20 text-stark-cyan glow-cyan'
                  : 'bg-transparent border-transparent text-white/50 hover:text-white hover:bg-white/5'
              }`}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              CONSOLE
            </button>
            <button
              onClick={() => setActiveTab('network')}
              className={`px-3 py-1.5 rounded text-xs font-mono flex items-center gap-1 transition-all border ${
                activeTab === 'network'
                  ? 'bg-stark-cyan/10 border-stark-cyan/20 text-stark-cyan glow-cyan'
                  : 'bg-transparent border-transparent text-white/50 hover:text-white hover:bg-white/5'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              MATRIX
            </button>
            <button
              onClick={() => setActiveTab('retinal')}
              className={`px-3 py-1.5 rounded text-xs font-mono flex items-center gap-1 transition-all border relative ${
                activeTab === 'retinal'
                  ? 'bg-stark-cyan/10 border-stark-cyan/20 text-stark-cyan glow-cyan'
                  : 'bg-transparent border-transparent text-white/50 hover:text-white hover:bg-white/5'
              }`}
            >
              <Eye className="w-3.5 h-3.5" />
              RETINAL
              {screenshotUrl && activeTab !== 'retinal' && (
                <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-stark-red rounded-full animate-ping" />
              )}
            </button>
            <button
              onClick={() => setActiveTab('terminal')}
              className={`px-3 py-1.5 rounded text-xs font-mono flex items-center gap-1 transition-all border ${
                activeTab === 'terminal'
                  ? 'bg-stark-cyan/10 border-stark-cyan/20 text-stark-cyan glow-cyan'
                  : 'bg-transparent border-transparent text-white/50 hover:text-white hover:bg-white/5'
              }`}
            >
              <Terminal className="w-3.5 h-3.5" />
              TTY
            </button>
          </div>
        </div>

        {/* HUD Viewport display */}
        <div className="flex-1 min-h-0 flex">
          {activeTab === 'chat' && (
            <ChatStream
              sessionId={currentSessionId}
              messages={messages}
              streamingText={streamingText}
              streamingReasoning={streamingReasoning}
              activeTool={activeTool}
              activeToolArgs={activeToolArgs}
              onSendMessage={handleSendMessage}
              onClearSession={handleClearSession}
              onNewSession={handleNewSession}
              voiceEnabled={voice.voiceEnabled}
              voiceLabel={voice.voiceLabel}
              isRecording={voice.isRecording}
              isTranscribing={voice.isTranscribing}
              isSpeaking={voice.isSpeaking}
              recordingSeconds={voice.recordingSeconds}
              audioLevel={voice.audioLevel}
              micMuted={voice.micMuted}
              audioInputs={voice.audioInputs}
              selectedDeviceId={voice.selectedDeviceId}
              onSelectDevice={voice.setSelectedDeviceId}
              voiceError={voice.voiceError}
              onStartRecording={voice.startRecording}
              onStopRecording={voice.stopRecording}
              onToggleVoiceMode={async (enabled?: boolean) => {
                await voice.toggleVoiceMode(enabled);
              }}
            />
          )}
          {activeTab === 'network' && <FlowHUD subagents={subagents} />}
          {activeTab === 'retinal' && <RetinalHUD screenshotUrl={screenshotUrl} />}
          {activeTab === 'terminal' && <ConsoleHUD logs={logs} />}
        </div>
      </div>

      {/* 3. Right Sidebar: Cognitive subagent tree */}
      <SubagentsRoster 
        subagents={subagents} 
        currentAgentId={currentAgent} 
        onSwitchAgent={handleSwitchAgent} 
      />
      
    </div>
  );
}
