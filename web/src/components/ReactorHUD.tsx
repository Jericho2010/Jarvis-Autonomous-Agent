import React from 'react';

interface ReactorHUDProps {
  status: 'online' | 'offline';
  port: number | null;
}

export const ReactorHUD: React.FC<ReactorHUDProps> = ({ status, port }) => {
  const isOnline = status === 'online';
  
  return (
    <div className="flex flex-col items-center justify-center p-6 border-b border-white/5 bg-stark-panel/40">
      <div className="relative flex items-center justify-center w-28 h-28">
        {/* Outer glowing ring */}
        <div className={`absolute inset-0 rounded-full border border-dashed animate-[spin_20s_linear_infinite] ${
          isOnline ? 'border-stark-cyan/40 glow-cyan' : 'border-stark-red/40 glow-red'
        }`} />
        
        {/* Ring segment layers */}
        <div className={`absolute w-[85%] h-[85%] rounded-full border-2 border-double animate-[spin_10s_linear_infinite_reverse] ${
          isOnline ? 'border-stark-cyan/30' : 'border-stark-red/30'
        }`} />
        
        {/* Arc reactor core elements */}
        <div className="absolute w-[60%] h-[60%] flex items-center justify-center">
          <svg className="w-full h-full" viewBox="0 0 100 100">
            {/* Reactor segments */}
            {[...Array(8)].map((_, i) => {
              const angle = (i * 360) / 8;
              return (
                <rect
                  key={i}
                  x="46"
                  y="12"
                  width="8"
                  height="12"
                  rx="1"
                  transform={`rotate(${angle} 50 50)`}
                  fill={isOnline ? 'var(--color-stark-cyan)' : 'var(--color-stark-red)'}
                  opacity={isOnline ? '0.7' : '0.4'}
                  className={isOnline ? 'animate-pulse' : ''}
                  style={{ animationDelay: `${i * 150}ms` }}
                />
              );
            })}
            
            {/* Central core circle */}
            <circle
              cx="50"
              cy="50"
              r="15"
              fill={isOnline ? 'var(--color-stark-gold)' : 'var(--color-stark-red)'}
              opacity="0.9"
              className={isOnline ? 'animate-pulse shadow-lg' : ''}
            />
          </svg>
        </div>
      </div>
      
      {/* Diagnostics details */}
      <div className="mt-4 text-center">
        <h3 className="text-xs font-mono tracking-widest text-white/50">SYSTEM CORE</h3>
        <div className="flex items-center justify-center gap-1.5 mt-1">
          <span className={`inline-block w-2 h-2 rounded-full ${isOnline ? 'bg-stark-cyan animate-ping' : 'bg-stark-red'}`} />
          <span className="text-[11px] font-mono font-bold tracking-wider">
            {isOnline ? `ONLINE // PORT ${port}` : 'OFFLINE // ROTATING'}
          </span>
        </div>
        <div className="text-[10px] font-mono text-white/30 mt-0.5 uppercase tracking-wide">
          Mark XLVIII Interface
        </div>
      </div>
    </div>
  );
};
