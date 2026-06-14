import React, { useEffect, useRef } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';

interface ConsoleHUDProps {
  logs: string[];
}

export const ConsoleHUD: React.FC<ConsoleHUDProps> = ({ logs }) => {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);

  useEffect(() => {
    if (!terminalRef.current) return;

    // Initialize Terminal
    const term = new Terminal({
      cursorBlink: true,
      theme: {
        background: '#121214',
        foreground: '#00f0ff',
        cursor: '#ffd700',
        selectionBackground: 'rgba(0, 240, 255, 0.3)',
        red: '#e63946',
        green: '#4ade80',
        yellow: '#ffd700',
        blue: '#3b82f6',
        cyan: '#00f0ff'
      },
      fontFamily: 'Geist Mono, ui-monospace, monospace',
      fontSize: 12,
      lineHeight: 1.2
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(terminalRef.current);
    fitAddon.fit();

    xtermRef.current = term;
    fitAddonRef.current = fitAddon;

    term.writeln('\x1b[1;33m⬡ J.A.R.V.I.S. // MARK XLVIII DIAGNOSTICS CONSOLE\x1b[0m');
    term.writeln('\x1b[1;36m[System Online] Connection Matrix Initialized.\x1b[0m\r\n');

    // Handle resizing
    const handleResize = () => {
      if (fitAddonRef.current) {
        fitAddonRef.current.fit();
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      term.dispose();
    };
  }, []);

  // Write new logs to the terminal
  useEffect(() => {
    if (!xtermRef.current || logs.length === 0) return;
    
    // Clear and re-write logs to preserve order and avoid duplication on re-render
    xtermRef.current.clear();
    xtermRef.current.writeln('\x1b[1;33m⬡ J.A.R.V.I.S. // MARK XLVIII DIAGNOSTICS CONSOLE\x1b[0m');
    xtermRef.current.writeln('\x1b[1;36m[System Online] Connection Matrix Initialized.\x1b[0m\r\n');
    
    logs.forEach(log => {
      // Clean and write log line
      xtermRef.current?.writeln(log);
    });
  }, [logs]);

  return (
    <div className="flex-1 h-full min-h-0 bg-stark-bg flex flex-col">
      <div className="p-3 border-b border-white/5 bg-stark-panel/30 flex items-center justify-between shrink-0 font-mono text-[10px] text-white/50">
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-stark-cyan animate-pulse" />
          <span>STARK_CORE_STREAM.LOG</span>
        </div>
        <span>TTY // ACTIVE CONNECTION</span>
      </div>
      <div className="flex-1 p-3 min-h-0 overflow-hidden">
        <div ref={terminalRef} className="w-full h-full" />
      </div>
    </div>
  );
};
