import React, { useState, useEffect } from 'react';
import { Eye, ShieldAlert, Crosshair, ZoomIn, Info } from 'lucide-react';

interface RetinalHUDProps {
  screenshotUrl: string | null;
}

export const RetinalHUD: React.FC<RetinalHUDProps> = ({ screenshotUrl }) => {
  const [coords, setCoords] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1.0);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.round(((e.clientX - rect.left) / rect.width) * 1920);
    const y = Math.round(((e.clientY - rect.top) / rect.height) * 1080);
    setCoords({ x, y });
  };

  return (
    <div className="flex-1 h-full min-h-0 bg-stark-bg flex flex-col relative overflow-hidden">
      {/* HUD Header */}
      <div className="p-3 border-b border-white/5 bg-stark-panel/30 flex items-center justify-between shrink-0 font-mono text-[10px] text-white/50">
        <div className="flex items-center gap-1.5">
          <Eye className="w-3.5 h-3.5 text-stark-red" />
          <span>OPTICAL RETINAL HUD // VISION OVERLAY</span>
        </div>
          <span>LAST CAPTURE</span>
      </div>

      {/* Main viewport */}
      <div 
        className="flex-1 min-h-0 flex items-center justify-center p-6 relative cursor-crosshair"
        onMouseMove={handleMouseMove}
      >
        {/* Holographic grid backing */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(0,240,255,0.02)_1px,transparent_1px),linear-gradient(to_bottom,rgba(0,240,255,0.02)_1px,transparent_1px)] bg-[size:32px_32px] pointer-events-none" />

        <div className="relative border border-stark-cyan/30 bg-black/40 rounded overflow-hidden max-w-full max-h-full aspect-video flex items-center justify-center glow-cyan">
          
          {/* Aiming Reticle (Center crosshair) */}
          <div className="absolute w-12 h-12 flex items-center justify-center pointer-events-none z-10 opacity-70">
            <Crosshair className="w-8 h-8 text-stark-cyan animate-spin" style={{ animationDuration: '30s' }} />
            <div className="absolute w-1.5 h-1.5 rounded-full bg-stark-red" />
          </div>

          {/* Screenshot Display */}
          {screenshotUrl ? (
            <img 
              src={screenshotUrl} 
              alt="Holographic optical feed"
              className="max-w-full max-h-full object-contain select-none"
              style={{ transform: `scale(${zoom})`, transition: 'transform 0.1s ease-out' }}
            />
          ) : (
            <div className="p-8 text-center text-white/20 font-mono text-xs flex flex-col items-center justify-center space-y-3">
              <Crosshair className="w-8 h-8 text-white/5" />
              <div className="space-y-1">
                <div>AWAITING OPTICAL INPUT</div>
                <div className="text-[10px] text-white/10 uppercase">Optical capture feed</div>
              </div>
            </div>
          )}

          {/* Coordinates overlay */}
          <div className="absolute bottom-2 left-2 z-10 bg-black/70 px-2 py-1 rounded border border-white/5 font-mono text-[9px] text-stark-cyan">
            X: {coords.x}px // Y: {coords.y}px
          </div>

          {/* Targeting Brackets (Corners) */}
          <div className="absolute top-2 left-2 w-4 h-4 border-t-2 border-l-2 border-stark-cyan/40 pointer-events-none" />
          <div className="absolute top-2 right-2 w-4 h-4 border-t-2 border-r-2 border-stark-cyan/40 pointer-events-none" />
          <div className="absolute bottom-2 left-2 w-4 h-4 border-b-2 border-l-2 border-stark-cyan/40 pointer-events-none" />
          <div className="absolute bottom-2 right-2 w-4 h-4 border-b-2 border-r-2 border-stark-cyan/40 pointer-events-none" />
        </div>
      </div>

      {/* Control panel bar */}
      <div className="p-3 bg-black/25 border-t border-white/5 shrink-0 flex items-center justify-between font-mono text-[10px] text-white/40">
        <div className="flex items-center gap-3">
          <button 
            onClick={() => setZoom(prev => Math.min(prev + 0.2, 3.0))}
            className="flex items-center gap-1 hover:text-stark-cyan transition-colors"
          >
            <ZoomIn className="w-3.5 h-3.5" />
            ZOOM IN
          </button>
          <button 
            onClick={() => setZoom(1.0)}
            className="hover:text-stark-cyan transition-colors"
          >
            RESET
          </button>
        </div>
        <div className="flex items-center gap-1">
          <Info className="w-3.5 h-3.5 text-stark-gold" />
          <span>RESOLUTION: 1920x1080 [HDMI UPLINK]</span>
        </div>
      </div>
    </div>
  );
};
