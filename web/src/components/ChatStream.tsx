import React, { useState, useRef, useEffect } from 'react';
import { Send, Terminal, HelpCircle, Layers, Trash2, ArrowUpRight, Cpu, Paperclip, X, Mic, MicOff, Volume2 } from 'lucide-react';
import { ChatMessage, uploadSessionFile } from '../lib/api';

interface ChatStreamProps {
  sessionId: string | null;
  messages: ChatMessage[];
  streamingText: string;
  streamingReasoning: string;
  activeTool: string | null;
  activeToolArgs: any;
  onSendMessage: (message: string, files?: { id: string, filename: string, bytes: number }[]) => void;
  onClearSession: () => void;
  onNewSession: () => void;
  voiceEnabled?: boolean;
  voiceLabel?: string;
  isRecording?: boolean;
  isTranscribing?: boolean;
  isSpeaking?: boolean;
  recordingSeconds?: number;
  audioLevel?: number;
  micMuted?: boolean;
  audioInputs?: MediaDeviceInfo[];
  selectedDeviceId?: string;
  onSelectDevice?: (deviceId: string) => void;
  onStartRecording?: () => void;
  onStopRecording?: () => Promise<string | null>;
  onToggleVoiceMode?: (enabled?: boolean) => Promise<void>;
  voiceError?: string | null;
}

export const ChatStream: React.FC<ChatStreamProps> = ({
  sessionId,
  messages,
  streamingText,
  streamingReasoning,
  activeTool,
  activeToolArgs,
  onSendMessage,
  onClearSession,
  onNewSession,
  voiceEnabled = false,
  voiceLabel = 'Male Butler',
  isRecording = false,
  isTranscribing = false,
  isSpeaking = false,
  recordingSeconds = 0,
  audioLevel = 0,
  micMuted = false,
  audioInputs = [],
  selectedDeviceId = '',
  onSelectDevice,
  onStartRecording,
  onStopRecording,
  onToggleVoiceMode,
  voiceError = null,
}) => {
  const [input, setInput] = useState('');
  const [showCommands, setShowCommands] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [attachedFiles, setAttachedFiles] = useState<{ id: string; filename: string; bytes: number }[]>([]);
  const [uploading, setUploading] = useState(false);
  
  const SLASH_COMMANDS = [
    { cmd: '/help', desc: 'Show help manual' },
    { cmd: '/new', desc: 'Start a fresh dialogue session' },
    { cmd: '/voicemode', desc: 'Toggle spoken butler voice (/voicemode on|off)' },
    { cmd: '/clear', desc: 'Clear conversation history' },
    { cmd: '/tasks', desc: 'Show active implementation tasks' },
    { cmd: '/skills', desc: 'List loaded skill modules' },
    { cmd: '/models', desc: 'List available cognitive models' },
    { cmd: '/model', desc: 'Set primary routing model (e.g. /model 2)' },
    { cmd: '/subagents', desc: 'Display details of cognitive subagents' },
  ];

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streamingText, streamingReasoning, activeTool]);

  const handlePaperclipClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !sessionId) return;
    
    setUploading(true);
    try {
      const res = await uploadSessionFile(sessionId, file);
      setAttachedFiles(prev => [...prev, res]);
    } catch (err) {
      console.error('Failed to upload file:', err);
      alert('Failed to upload file');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const removeAttachedFile = (id: string) => {
    setAttachedFiles(prev => prev.filter(f => f.id !== id));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() && attachedFiles.length === 0) return;
    
    const cmd = input.trim().toLowerCase();
    if (cmd === '/clear') {
      onClearSession();
    } else if (cmd === '/new') {
      onNewSession();
    } else {
      onSendMessage(input.trim(), attachedFiles);
    }
    
    setInput('');
    setAttachedFiles([]);
    setShowCommands(false);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setInput(val);
    if (val.startsWith('/')) {
      setShowCommands(true);
    } else {
      setShowCommands(false);
    }
  };

  const selectCommand = (cmd: string) => {
    setInput(cmd);
    setShowCommands(false);
  };

  const handleMicClick = async () => {
    if (uploading || !sessionId) return;
    if (isTranscribing) return;

    if (isRecording) {
      const transcript = await onStopRecording?.();
      const text = transcript?.trim();
      if (text) {
        setInput('');
        onSendMessage(text);
      }
      return;
    }

    if (!voiceEnabled && onToggleVoiceMode) {
      await onToggleVoiceMode(true);
    }
    await onStartRecording?.();
  };

  const parseMessageContent = (text: string) => {
    // Basic parser for inline code, code blocks, thinking tags, and bold text
    if (!text) return null;
    
    // Extract thinking tags
    let thinking = '';
    let bodyText = text;
    
    if (text.includes('<think>')) {
      const parts = text.split('<think>', 2);
      const beforeThink = parts[0];
      if (parts[1] && parts[1].includes('</think>')) {
        const subParts = parts[1].split('</think>', 2);
        thinking = subParts[0] ? subParts[0].trim() : '';
        bodyText = beforeThink + subParts[1];
      } else {
        thinking = parts[1];
        bodyText = beforeThink;
      }
    }
    
    return (
      <div className="space-y-3 font-sans text-sm leading-relaxed">
        {/* Thinking box */}
        {thinking && (
          <div className="p-3 border border-stark-gold/30 rounded bg-stark-gold/5 text-stark-gold font-mono text-xs glow-gold relative overflow-hidden">
            <div className="absolute top-0 right-0 bg-stark-gold/10 text-[9px] px-1.5 py-0.5 rounded-bl tracking-widest font-bold uppercase">
              THINKING LOG
            </div>
            <div className="whitespace-pre-wrap">{thinking}</div>
          </div>
        )}
        
        {/* Main Body */}
        <div className="whitespace-pre-wrap font-sans text-sm text-white/90">
          {formatBodyMarkdown(bodyText)}
        </div>
      </div>
    );
  };

  const formatBodyMarkdown = (text: string) => {
    // 1. Match code blocks: ```lang\ncode\n```
    const codeBlockRegex = /```(\w*)\n([\s\S]*?)\n```/g;
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match;

    while ((match = codeBlockRegex.exec(text)) !== null) {
      // Add text before code block
      const prevText = text.slice(lastIndex, match.index);
      if (prevText) {
        parts.push(<span key={`text-${lastIndex}`}>{formatInlineElements(prevText)}</span>);
      }

      // Add code block
      const lang = match[1] || 'code';
      const code = match[2];
      parts.push(
        <div key={`code-${match.index}`} className="my-3 border border-white/10 rounded overflow-hidden font-mono text-xs text-stark-cyan shadow-inner">
          <div className="bg-white/5 px-3 py-1.5 text-[10px] text-white/40 uppercase tracking-widest flex items-center justify-between border-b border-white/5">
            <span>{lang}</span>
            <span className="text-[9px] text-stark-cyan/60">Stark Core Matrix File</span>
          </div>
          <pre className="p-3 bg-black/45 overflow-x-auto whitespace-pre">{code}</pre>
        </div>
      );

      lastIndex = codeBlockRegex.lastIndex;
    }

    const remainingText = text.slice(lastIndex);
    if (remainingText) {
      parts.push(<span key={`text-${lastIndex}`}>{formatInlineElements(remainingText)}</span>);
    }

    return parts;
  };

  const formatInlineElements = (text: string) => {
    // Match inline code: `code` and bold: **text**
    const inlineRegex = /`([^`]+)`|\*\*([^*]+)\*\*/g;
    const elements: React.ReactNode[] = [];
    let lastIndex = 0;
    let match;

    while ((match = inlineRegex.exec(text)) !== null) {
      const prevText = text.slice(lastIndex, match.index);
      if (prevText) {
        elements.push(prevText);
      }

      if (match[1]) {
        // Inline code
        elements.push(
          <code key={`inline-code-${match.index}`} className="bg-white/10 px-1 py-0.5 rounded font-mono text-xs text-stark-cyan">
            {match[1]}
          </code>
        );
      } else if (match[2]) {
        // Bold
        elements.push(
          <strong key={`bold-${match.index}`} className="font-bold text-white">
            {match[2]}
          </strong>
        );
      }

      lastIndex = inlineRegex.lastIndex;
    }

    const remainingText = text.slice(lastIndex);
    if (remainingText) {
      elements.push(remainingText);
    }

    return elements;
  };

  return (
    <div className="flex-1 flex flex-col h-full min-h-0 bg-stark-bg border-r border-white/5 relative">
      {/* Active tool diagnostics bar */}
      {activeTool && (
        <div className="bg-stark-red/10 border-b border-stark-red/20 px-4 py-2 flex items-center gap-2.5 font-mono text-xs text-stark-red animate-pulse">
          <span className="relative flex w-2 h-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-stark-red opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-stark-red"></span>
          </span>
          <span>⚙ TOOL RUNNING: {activeTool.toUpperCase()}</span>
          {activeToolArgs && (
            <span className="text-[10px] text-white/50 truncate flex-1">
              {JSON.stringify(activeToolArgs)}
            </span>
          )}
        </div>
      )}

      {voiceEnabled ? (
        <div className="bg-stark-gold/10 border-b border-stark-gold/20 px-4 py-1.5 flex items-center gap-2 font-mono text-[10px] text-stark-gold uppercase tracking-widest">
          <Volume2 className={`w-3.5 h-3.5 ${isSpeaking ? 'animate-pulse' : ''}`} />
          <span>Voice Mode · Male Butler · {voiceLabel}</span>
          {audioInputs.length > 0 && (
            <select
              value={selectedDeviceId}
              onChange={(e) => onSelectDevice?.(e.target.value)}
              disabled={isRecording || isTranscribing}
              title="Select microphone input device"
              className="bg-black/40 border border-stark-gold/30 text-stark-gold rounded px-1 py-0.5 text-[10px] max-w-[160px] focus:outline-none disabled:opacity-50"
            >
              <option value="">Default mic</option>
              {audioInputs.map((device, idx) => (
                <option key={device.deviceId || idx} value={device.deviceId}>
                  {device.label || `Microphone ${idx + 1}`}
                </option>
              ))}
            </select>
          )}
          {micMuted && (
            <span className="text-stark-red normal-case">Mic muted (OS)</span>
          )}
          {isRecording && (
            <span className="text-stark-red animate-pulse">
              ● Recording {recordingSeconds}s — click mic again when done
              {audioLevel > 0 ? ` · Mic ${audioLevel}%` : ' · Mic silent?'}
            </span>
          )}
          {isTranscribing && <span className="text-stark-cyan animate-pulse">Transcribing…</span>}
          {isSpeaking && <span className="text-stark-cyan animate-pulse">Speaking…</span>}
          {voiceError && <span className="text-stark-red normal-case">{voiceError}</span>}
        </div>
      ) : (
        <div className="bg-white/5 border-b border-white/10 px-4 py-1.5 flex items-center gap-2 font-mono text-[10px] text-white/40 uppercase tracking-widest">
          <Mic className="w-3.5 h-3.5" />
          <span>Voice mode off — click the mic or type /voicemode on</span>
        </div>
      )}

      {/* Main message stream list */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-4"
      >
        {messages.length === 0 && !streamingText && !streamingReasoning && (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 text-white/30 space-y-4">
            <Cpu className="w-10 h-10 text-white/10" />
            <div className="space-y-1">
              <h3 className="text-sm font-mono font-bold uppercase tracking-widest text-stark-cyan/60">
                Cognitive Console Initialized
              </h3>
              <p className="text-xs max-w-sm font-sans">
                Awaiting commands or prompts. Type <code className="bg-white/5 px-1 py-0.5 rounded font-mono">/help</code> to view system tools.
              </p>
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div 
            key={i}
            className={`flex flex-col max-w-[85%] ${
              msg.role === 'user' ? 'ml-auto items-end' : 'mr-auto items-start'
            }`}
          >
            {/* User message bubble */}
            {msg.role === 'user' ? (
              <div className="p-3 rounded-lg border border-stark-cyan/20 bg-stark-cyan/5 text-stark-cyan font-sans text-sm glow-cyan whitespace-pre-wrap">
                {msg.content}
              </div>
            ) : (
              // Assistant message bubble
              <div className="w-full p-4 rounded-lg border border-white/5 bg-stark-panel/40 shadow-inner">
                <div className="flex items-center gap-1.5 mb-2 border-b border-white/5 pb-1 text-[10px] font-mono text-white/30 uppercase tracking-widest">
                  <BotIcon className="w-3.5 h-3.5" />
                  <span>J.A.R.V.I.S. Response</span>
                </div>
                {parseMessageContent(msg.content)}
              </div>
            )}
          </div>
        ))}

        {/* Live streaming bubble */}
        {(streamingText || streamingReasoning) && (
          <div className="flex flex-col mr-auto max-w-[85%] items-start w-full">
            <div className="w-full p-4 rounded-lg border border-stark-cyan/20 bg-stark-cyan/5 shadow-inner glow-cyan">
              <div className="flex items-center gap-1.5 mb-2 border-b border-white/5 pb-1 text-[10px] font-mono text-stark-cyan uppercase tracking-widest animate-pulse">
                <Cpu className="w-3.5 h-3.5" />
                <span>Streaming Telemetry...</span>
              </div>
              
              {/* Combine text and reasoning live */}
              <div className="space-y-3 font-sans text-sm leading-relaxed">
                {streamingReasoning && (
                  <div className="p-3 border border-stark-gold/30 rounded bg-stark-gold/5 text-stark-gold font-mono text-xs glow-gold">
                    <div className="text-[9px] font-bold uppercase tracking-widest mb-1 opacity-70">
                      THINKING LOG
                    </div>
                    <div className="whitespace-pre-wrap">{streamingReasoning}</div>
                  </div>
                )}
                
                {streamingText && (
                  <div className="whitespace-pre-wrap font-sans text-sm text-white/90">
                    {formatBodyMarkdown(streamingText)}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Commands Autocomplete Overlay */}
      {showCommands && (
        <div className="absolute bottom-16 left-4 right-4 bg-stark-panel border border-stark-cyan/30 rounded-lg p-2 glow-cyan z-30 font-mono text-xs">
          <div className="px-2 py-1 text-white/30 uppercase text-[10px] tracking-wider border-b border-white/5 mb-1">
            System Slash Commands
          </div>
          <div className="max-h-40 overflow-y-auto space-y-1">
            {SLASH_COMMANDS.filter(c => {
              const commandPart = input.split(' ')[0].toLowerCase();
              return c.cmd.startsWith(commandPart);
            }).map((item) => (
              <button
                key={item.cmd}
                onClick={() => selectCommand(item.cmd)}
                className="w-full text-left p-1.5 rounded hover:bg-stark-cyan/10 hover:text-stark-cyan flex items-center justify-between"
              >
                <span className="font-bold text-white/95">{item.cmd}</span>
                <span className="text-white/40 text-[10px]">{item.desc}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Attached Files Pill Row */}
      {attachedFiles.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-4 py-2 border-t border-white/5 bg-black/10 shrink-0">
          {attachedFiles.map(file => (
            <div 
              key={file.id} 
              className="flex items-center gap-1 bg-stark-cyan/10 border border-stark-cyan/25 text-stark-cyan px-2 py-0.5 rounded text-xs font-mono glow-cyan"
            >
              <span>{file.filename}</span>
              <button 
                type="button" 
                onClick={() => removeAttachedFile(file.id)}
                className="hover:text-white transition-colors ml-0.5"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Message input console */}
      <form 
        onSubmit={handleSubmit}
        className="p-3 bg-black/25 border-t border-white/5 relative z-10"
      >
        <div className="relative flex items-center gap-1.5">
          <button
            type="button"
            onClick={handlePaperclipClick}
            disabled={uploading || !sessionId}
            className={`p-2 rounded-md hover:bg-white/5 focus:outline-none transition-all shrink-0 ${
              uploading ? 'text-stark-gold animate-pulse' : 'text-white/40 hover:text-white'
            }`}
            title="Attach file"
          >
            <Paperclip className="w-4.5 h-4.5" />
          </button>
          <button
            type="button"
            onClick={() => onToggleVoiceMode?.()}
            disabled={!sessionId}
            className={`p-2 rounded-md focus:outline-none transition-all shrink-0 ${
              voiceEnabled
                ? 'bg-stark-gold/15 text-stark-gold border border-stark-gold/30'
                : 'text-white/40 hover:text-stark-gold hover:bg-white/5'
            }`}
            title={voiceEnabled ? 'Voice mode on — click to disable' : 'Enable voice mode (butler TTS + dictation)'}
          >
            <Volume2 className="w-4.5 h-4.5" />
          </button>
          <button
            type="button"
            onClick={handleMicClick}
            disabled={isTranscribing || uploading || !sessionId}
            className={`p-2 rounded-md focus:outline-none transition-all shrink-0 ${
              isRecording
                ? 'bg-stark-red/20 text-stark-red animate-pulse'
                : voiceEnabled
                  ? 'text-stark-gold hover:bg-stark-gold/10'
                  : 'text-white/30 hover:text-stark-gold hover:bg-white/5'
            }`}
            title={
              isRecording
                ? 'Click to stop and send'
                : voiceEnabled
                  ? 'Click to start speaking'
                  : 'Click to enable voice mode and start speaking'
            }
          >
            {isRecording ? <MicOff className="w-4.5 h-4.5" /> : <Mic className="w-4.5 h-4.5" />}
          </button>
          <input 
            type="file" 
            ref={fileInputRef} 
            onChange={handleFileChange} 
            className="hidden" 
          />
          <div className="relative flex-1 flex items-center">
            <input
              type="text"
              value={input}
              onChange={handleInputChange}
              placeholder={uploading ? "Uploading file..." : "Ask anything, or type / for commands…"}
              disabled={uploading}
              className="w-full bg-stark-panel/75 border border-white/10 rounded-lg px-4 py-2.5 pr-12 text-sm text-white focus:outline-none focus:border-stark-cyan/40 focus:ring-1 focus:ring-stark-cyan/15 font-sans placeholder-white/25 transition-all"
            />
            <button
              type="submit"
              disabled={uploading}
              className="absolute right-2 p-1.5 rounded-md bg-stark-cyan/10 text-stark-cyan hover:bg-stark-cyan/25 focus:outline-none transition-all glow-cyan"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
        <div className="flex items-center justify-between mt-2 font-mono text-[9px] text-white/20 px-1">
          <span>PRESS ENTER TO SEND // ALT+ENTER FOR MULTILINE</span>
          <span>MARK XLVIII CORE ENGINES</span>
        </div>
      </form>
    </div>
  );
};

const BotIcon = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M12 2V6M12 18V22M4.93 4.93L7.76 7.76M16.24 16.24L19.07 19.07M2 12H6M18 12H22M4.93 19.07L7.76 16.24M16.24 7.76L19.07 4.93" />
    <circle cx="12" cy="12" r="4" />
  </svg>
);
