import React, { useState, useEffect, useRef, memo } from 'react';
import auth from '../services/auth';
import { 
  Maximize2, Minimize2, ZoomIn, ZoomOut, Camera as CameraIcon, 
  UserPlus, Sliders, Shield, AlertTriangle, Eye, EyeOff, Radio,
  RefreshCw, Move, Check
} from 'lucide-react';

export const CameraFeed = memo(({ 
  camera, 
  onEnrollSnapshot, 
  isFocused = false, 
  onToggleFocus,
  onOpenSettings
}) => {
  const [zoomLevel, setZoomLevel] = useState(1);
  const [panPos, setPanPos] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showHud, setShowHud] = useState(true);
  const [showPtz, setShowPtz] = useState(false);
  const [hasStreamError, setHasStreamError] = useState(false);
  const [flashSnapshot, setFlashSnapshot] = useState(false);
  
  const containerRef = useRef(null);
  const imageRef = useRef(null);

  // Timecode
  const [timecode, setTimecode] = useState('');
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const pad = n => String(n).padStart(2, '0');
      const ms = String(now.getMilliseconds()).padStart(3, '0').slice(0, 2);
      setTimecode(`${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}.${ms}`);
    };
    updateTime();
    const id = setInterval(updateTime, 100);
    return () => clearInterval(id);
  }, []);

  // Digital Zoom & Pan handling
  const handleZoom = (delta) => {
    setZoomLevel(prev => {
      const next = Math.min(Math.max(1, prev + delta), 4);
      if (next === 1) setPanPos({ x: 0, y: 0 });
      return next;
    });
  };

  const handleMouseDown = (e) => {
    if (zoomLevel <= 1) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - panPos.x, y: e.clientY - panPos.y });
  };

  const handleMouseMove = (e) => {
    if (!isDragging || zoomLevel <= 1) return;
    setPanPos({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y
    });
  };

  const handleMouseUp = () => setIsDragging(false);

  // Take snapshot
  const triggerSnapshot = () => {
    setFlashSnapshot(true);
    setTimeout(() => setFlashSnapshot(false), 200);

    // Create an offscreen canvas to grab frame
    const canvas = document.createElement('canvas');
    canvas.width = 640;
    canvas.height = 360;
    const ctx = canvas.getContext('2d');

    if (imageRef.current && !hasStreamError) {
      try {
        ctx.drawImage(imageRef.current, 0, 0, 640, 360);
      } catch (e) {
        console.warn('[Ghost Trail] Snapshot unavailable:', e);
      }
    }

    canvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ghost_trail_${camera.camera_id}_${Date.now()}.png`;
      a.click();
      URL.revokeObjectURL(url);
    }, 'image/png');
  };

  // Snapshot to enroll
  const handleEnrollClick = () => {
    setFlashSnapshot(true);
    setTimeout(() => setFlashSnapshot(false), 200);

    const canvas = document.createElement('canvas');
    canvas.width = 640;
    canvas.height = 360;
    const ctx = canvas.getContext('2d');

    if (imageRef.current && !hasStreamError) {
      try {
        ctx.drawImage(imageRef.current, 0, 0, 640, 360);
      } catch (e) {
        console.warn('[Ghost Trail] Snapshot unavailable:', e);
      }
    }

    canvas.toBlob((blob) => {
      if (blob && onEnrollSnapshot) {
        onEnrollSnapshot(blob, camera.camera_id);
      }
    }, 'image/jpeg', 0.92);
  };

  // Toggle fullscreen
  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch(() => {});
      setIsFullscreen(true);
    } else {
      document.exitFullscreen().catch(() => {});
      setIsFullscreen(false);
    }
  };

  const isLive = camera.enabled && camera.online;

  return (
    <div
      ref={containerRef}
      className={`group relative rounded-xl overflow-hidden border transition-all duration-300 flex flex-col ${
        isFocused 
          ? 'border-cyan-500 shadow-[0_0_25px_rgba(6,182,212,0.25)] ring-1 ring-cyan-500/40' 
          : 'border-slate-800 bg-[#0d131a] hover:border-slate-700 shadow-lg'
      }`}
    >
      {/* Card Header Bar */}
      <div className="flex items-center justify-between px-3.5 py-2.5 bg-[#090d12]/90 border-b border-slate-800/80 backdrop-blur-sm z-20 select-none">
        <div className="flex items-center gap-2.5">
          <div className="relative flex items-center justify-center">
            <span className={`w-2.5 h-2.5 rounded-full ${isLive ? 'bg-emerald-500' : 'bg-rose-500'}`} />
            {isLive && (
              <span className="absolute w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping opacity-75" />
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold tracking-wider text-slate-100 uppercase">
                {camera.name || `Channel ${camera.camera_id}`}
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono tracking-widest bg-slate-800/80 text-cyan-400 border border-slate-700/60 uppercase">
                {camera.camera_id}
              </span>
            </div>
            {camera.zone && (
              <span className="text-[10px] font-mono text-slate-400">
                {camera.zone}
              </span>
            )}
          </div>
        </div>

        {/* Action icons */}
        <div className="flex items-center gap-1">
          {/* HUD toggle */}
          <button
            onClick={() => setShowHud(!showHud)}
            title={showHud ? 'Hide Telemetry HUD' : 'Show Telemetry HUD'}
            className={`p-1.5 rounded-md text-xs transition-colors ${
              showHud ? 'text-cyan-400 bg-cyan-950/40 hover:bg-cyan-900/60' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {showHud ? <Eye size={14} /> : <EyeOff size={14} />}
          </button>

          {/* PTZ overlay toggle */}
          <button
            onClick={() => setShowPtz(!showPtz)}
            title="Digital PTZ Controls"
            className={`p-1.5 rounded-md text-xs transition-colors ${
              showPtz ? 'text-amber-400 bg-amber-950/40 hover:bg-amber-900/60' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Move size={14} />
          </button>

          {/* Quick Snapshot */}
          <button
            onClick={triggerSnapshot}
            title="Take High-Res Snapshot"
            className="p-1.5 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <CameraIcon size={14} />
          </button>

          {/* Enroll Face from Feed */}
          {onEnrollSnapshot && (
            <button
              onClick={handleEnrollClick}
              title="Enroll Person From This Feed"
              className="p-1.5 rounded-md text-amber-400 hover:text-amber-300 hover:bg-amber-950/40 transition-colors"
            >
              <UserPlus size={14} />
            </button>
          )}

          {/* Focus mode */}
          {onToggleFocus && (
            <button
              onClick={onToggleFocus}
              title={isFocused ? 'Unfocus Channel' : 'Focus Mode (1x1)'}
              className={`p-1.5 rounded-md text-xs transition-colors ${
                isFocused ? 'text-cyan-400 bg-cyan-950/50' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <Radio size={14} />
            </button>
          )}

          {/* Fullscreen */}
          <button
            onClick={toggleFullscreen}
            title="Toggle Fullscreen"
            className="p-1.5 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </div>

      {/* Video Viewport Area */}
      <div 
        className="relative flex-1 bg-black overflow-hidden flex items-center justify-center min-h-[220px] cursor-crosshair select-none"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {/* Shutter flash effect */}
        {flashSnapshot && (
          <div className="absolute inset-0 bg-white z-50 pointer-events-none animate-pulse" />
        )}

        {/* Video Canvas or Live MJPEG Image */}
        <div 
          className="relative w-full h-full flex items-center justify-center transition-transform duration-75"
          style={{
            transform: `scale(${zoomLevel}) translate(${panPos.x / zoomLevel}px, ${panPos.y / zoomLevel}px)`,
            cursor: zoomLevel > 1 ? (isDragging ? 'grabbing' : 'grab') : 'default'
          }}
        >
          {camera.enabled && !hasStreamError ? (
            <img
              ref={imageRef}
              src={`/api/stream/${camera.camera_id}?token=${encodeURIComponent(auth.getToken() || '')}`}
              alt={`Stream ${camera.camera_id}`}
              className="w-full h-full object-contain pointer-events-none"
              onError={() => setHasStreamError(true)}
              onLoad={() => setHasStreamError(false)}
            />
          ) : null}

          <div className={`absolute inset-0 flex items-center justify-center bg-[#080c10] ${camera.enabled && !hasStreamError ? 'hidden' : 'flex'}`}>
            <div className="text-center font-mono px-6">
              <div className="text-rose-400 text-xs font-bold tracking-[0.25em]">{camera.enabled ? 'CAMERA OFFLINE' : 'CAMERA DISABLED'}</div>
              <div className="mt-2 text-[10px] text-slate-500 tracking-wider">{camera.enabled ? (camera.error || 'VIDEO STREAM UNAVAILABLE') : 'CHANNEL IS DISABLED'}</div>
              <div className="mt-3 inline-flex items-center gap-2 px-2 py-1 rounded border border-rose-500/20 bg-rose-500/5 text-[9px] text-rose-300"><span className="w-1.5 h-1.5 rounded-full bg-rose-400" />REAL FEED REQUIRED</div>
            </div>
          </div>
        </div>

        {/* Live HUD Telemetry Overlays */}
        {showHud && (
          <div className="absolute inset-0 pointer-events-none flex flex-col justify-between p-3 z-10">
            {/* Top HUD stats */}
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <span className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-black/60 backdrop-blur-md border border-slate-700/60 text-rose-500 font-mono text-[10px] font-bold">
                  <span className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-rose-500 animate-pulse' : 'bg-slate-600'}`} />
                  {isLive ? 'REC' : 'NO SIGNAL'}
                </span>
                <span className="px-2 py-0.5 rounded bg-black/60 backdrop-blur-md border border-slate-700/60 text-slate-300 font-mono text-[10px]">
                  {timecode}
                </span>
              </div>

              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded bg-black/60 backdrop-blur-md border border-slate-700/60 text-emerald-400 font-mono text-[10px] flex items-center gap-1">
                  <Radio size={10} className="animate-spin" />
                  {camera.fps != null ? `${camera.fps} FPS` : 'FPS N/A'}
                </span>
                <span className="px-2 py-0.5 rounded bg-black/60 backdrop-blur-md border border-slate-700/60 text-cyan-400 font-mono text-[10px]">
                  {isLive ? 'STREAM' : 'NO SIGNAL'}
                </span>
                {zoomLevel > 1 && (
                  <span className="px-2 py-0.5 rounded bg-cyan-900/70 border border-cyan-400/60 text-cyan-300 font-mono text-[10px] font-bold">
                    {zoomLevel.toFixed(1)}x ZOOM
                  </span>
                )}
              </div>
            </div>

            {/* Tactical Crosshairs */}
            <div className="absolute inset-0 pointer-events-none flex items-center justify-center opacity-30">
              <div className="w-8 h-8 border border-cyan-400/40 rounded-full flex items-center justify-center">
                <div className="w-1 h-1 bg-cyan-400 rounded-full" />
              </div>
            </div>

            {/* Bottom HUD stats */}
            <div className="flex items-end justify-between">
              <div className="flex flex-col gap-0.5 font-mono text-[9px] text-slate-400 bg-black/60 backdrop-blur-sm px-2 py-1 rounded border border-slate-800/80">
                <span className="text-slate-300 font-semibold tracking-wider">
                  ENCODER: H.264 / MJPEG
                </span>
                <span>{isLive ? 'LIVE VIDEO STREAM' : 'VIDEO STREAM UNAVAILABLE'}</span>
                <span>{isLive ? 'AI INFERENCE: BACKEND CONTROLLED' : 'AI INFERENCE: UNAVAILABLE'}</span>
              </div>

              <div className="flex items-center gap-1 font-mono text-[10px] text-slate-400 bg-black/60 backdrop-blur-sm px-2 py-1 rounded border border-slate-800/80">
                <Shield size={11} className="text-emerald-400" />
                <span>GHOST TRAIL ACTIVE</span>
              </div>
            </div>
          </div>
        )}

        {/* Digital PTZ Controls Overlay */}
        {showPtz && (
          <div className="absolute bottom-12 right-3 z-30 bg-slate-950/85 backdrop-blur-md border border-slate-700/80 p-2 rounded-xl shadow-2xl flex flex-col items-center gap-1">
            <div className="text-[9px] font-mono text-cyan-400 uppercase tracking-widest mb-1">
              PTZ Matrix
            </div>
            {/* Pan up */}
            <button
              onClick={() => setPanPos(p => ({ ...p, y: p.y + 30 }))}
              className="w-7 h-7 rounded bg-slate-800 hover:bg-cyan-600 text-slate-200 text-xs flex items-center justify-center font-bold"
            >
              ▲
            </button>
            <div className="flex gap-1">
              {/* Pan left */}
              <button
                onClick={() => setPanPos(p => ({ ...p, x: p.x + 30 }))}
                className="w-7 h-7 rounded bg-slate-800 hover:bg-cyan-600 text-slate-200 text-xs flex items-center justify-center font-bold"
              >
                ◀
              </button>
              {/* Reset center */}
              <button
                onClick={() => { setZoomLevel(1); setPanPos({ x: 0, y: 0 }); }}
                className="w-7 h-7 rounded bg-slate-700 hover:bg-rose-600 text-slate-200 text-[10px] flex items-center justify-center font-mono font-bold"
              >
                RST
              </button>
              {/* Pan right */}
              <button
                onClick={() => setPanPos(p => ({ ...p, x: p.x - 30 }))}
                className="w-7 h-7 rounded bg-slate-800 hover:bg-cyan-600 text-slate-200 text-xs flex items-center justify-center font-bold"
              >
                ▶
              </button>
            </div>
            {/* Pan down */}
            <button
              onClick={() => setPanPos(p => ({ ...p, y: p.y - 30 }))}
              className="w-7 h-7 rounded bg-slate-800 hover:bg-cyan-600 text-slate-200 text-xs flex items-center justify-center font-bold mb-1"
            >
              ▼
            </button>
            {/* Zoom in / out */}
            <div className="flex gap-1 w-full pt-1 border-t border-slate-800">
              <button
                onClick={() => handleZoom(0.5)}
                className="flex-1 py-1 rounded bg-slate-800 hover:bg-cyan-600 text-slate-200 text-xs flex items-center justify-center"
                title="Zoom In"
              >
                <ZoomIn size={12} />
              </button>
              <button
                onClick={() => handleZoom(-0.5)}
                className="flex-1 py-1 rounded bg-slate-800 hover:bg-cyan-600 text-slate-200 text-xs flex items-center justify-center"
                title="Zoom Out"
              >
                <ZoomOut size={12} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Footer Info Strip */}
      <div className="px-3 py-1.5 bg-[#090d12] border-t border-slate-800/80 flex items-center justify-between text-[11px] font-mono text-slate-400">
        <div className="flex items-center gap-2">
          <span className="truncate max-w-[200px]" title={camera.source}>
            SRC: {camera.actual_source ?? camera.source ?? 'Default Input (0)'}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {camera.enabled ? (
            <span className="text-emerald-400 flex items-center gap-1 font-semibold">
              <Check size={12} /> ACTIVE
            </span>
          ) : (
            <span className="text-slate-500 font-semibold">PAUSED</span>
          )}
        </div>
      </div>
    </div>
  );
});

export default CameraFeed;
