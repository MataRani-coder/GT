import React, { useState, useEffect, useRef } from 'react';
import apiService from '../services/api';
import { WebcamEnrollModal } from './WebcamEnrollModal';
import { 
  Shield, Camera, Radio, AlertTriangle, Layers, 
  Compass, Crosshair, ZoomIn, ZoomOut, RefreshCw, ScanLine, Play, Square, RotateCcw, Wifi 
} from 'lucide-react';

const RoomScanView = ({ onEnvironmentData }) => {
  const videoRef = useRef(null);
  const captureRef = useRef(null);
  const mapRef = useRef(null);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  const [scanning, setScanning] = useState(false);
  const [status, setStatus] = useState('Ready to scan');
  const [data, setData] = useState(null);
  const [path, setPath] = useState([]);
  const [error, setError] = useState('');
  const [enrolling, setEnrolling] = useState(false);
  const [resumeAfterEnrollment, setResumeAfterEnrollment] = useState(false);
  const captureBusyRef = useRef(false);

  const stop = async () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    await Promise.resolve(apiService.stopCameraSession()).catch(() => {});
    if (videoRef.current) videoRef.current.srcObject = null;
    setScanning(false);
  };

  const capture = async () => {
    if (captureBusyRef.current) return;
    captureBusyRef.current = true;
    try {
    const video = videoRef.current;
    const canvas = captureRef.current;
    if (!video || !canvas || video.readyState < 2) return;
    const width = Math.min(960, video.videoWidth || 960);
    const height = Math.round(width * ((video.videoHeight || 540) / (video.videoWidth || 960)));
    canvas.width = width;
    canvas.height = height;
    canvas.getContext('2d').drawImage(video, 0, 0, width, height);
    await new Promise(resolve => canvas.toBlob(async blob => {
      if (!blob) { resolve(); return; }
      try {
        const result = await apiService.scanEnvironmentFrame(blob);
        if (!result) {
          setStatus('Backend scan unavailable');
          return;
        }
        setData(result);
        onEnvironmentData?.(result);
        if (result.pose) {
          setPath(prev => [...prev.slice(-119), { x: result.pose.x, y: result.pose.y }]);
        }
        setStatus(`LIVE · frame ${result.frame} · ${result.metrics?.objects ?? 0} objects`);
      } finally { resolve(); }
    }, 'image/jpeg', 0.72));
    } finally { captureBusyRef.current = false; }
  };

  const beginEnrollment = async () => {
    // Release both browser and backend camera ownership before enrollment.
    // Awaiting stop prevents a race where the enrollment session starts while
    // the surveillance/scan worker still owns the physical webcam.
    if (scanning) {
      await stop();
      setResumeAfterEnrollment(true);
    }
    setEnrolling(true);
  };

  const closeEnrollment = () => {
    setEnrolling(false);
    // Enrollment releases its browser stream and backend session on close.
    // Resume scanning only when the operator explicitly started it before
    // enrollment, avoiding an unexpected camera reacquisition.
  };

  const resumeScan = async () => {
    setResumeAfterEnrollment(false);
    await start();
  };

  const start = async () => {
    setError('');
    try {
      await apiService.resetEnvironmentScan();
      const session = await apiService.startCameraSession();
      if (!session) throw new Error('Could not release the surveillance webcam.');
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false
      });
      streamRef.current = stream;
      if (!videoRef.current) return;
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      setScanning(true);
      setStatus('SCANNING · move slowly around the room');
      await capture();
      timerRef.current = setInterval(capture, 850);
    } catch (e) {
      setError(e?.message || 'Camera permission was denied or unavailable.');
      setStatus('Camera unavailable');
      stop();
    }
  };

  const reset = async () => {
    stop();
    await apiService.resetEnvironmentScan();
    setData(null);
    setPath([]);
    setError('');
    setStatus('Ready to scan');
  };

  useEffect(() => () => stop(), []);

  useEffect(() => {
    const canvas = mapRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width = 900;
    const h = canvas.height = 520;
    ctx.fillStyle = '#05090d';
    ctx.fillRect(0, 0, w, h);

    // Relative world grid — coordinates are intentionally not presented as metres.
    ctx.strokeStyle = 'rgba(51,65,85,.32)';
    ctx.lineWidth = 1;
    for (let x = 0; x <= w; x += 45) { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,h); ctx.stroke(); }
    for (let y = 0; y <= h; y += 45) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke(); }

    const scale = 900;
    const originX = w / 2, originY = h / 2;
    const project = (x, y) => [originX + x * scale, originY + y * scale];

    // Accumulated camera path / pose trace.
    if (path.length > 1) {
      ctx.beginPath();
      path.forEach((p, i) => {
        const [x,y] = project(p.x, p.y);
        if (i === 0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
      });
      ctx.strokeStyle = 'rgba(6,182,212,.85)';
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    // Structural line segments from the current camera view.
    const segments = data?.segments || [];
    segments.forEach(seg => {
      const x1 = originX + (seg.x1 - .5) * 760 + (data?.pose?.x || 0) * -300;
      const y1 = originY + (seg.y1 - .5) * 440 + (data?.pose?.y || 0) * -300;
      const x2 = originX + (seg.x2 - .5) * 760 + (data?.pose?.x || 0) * -300;
      const y2 = originY + (seg.y2 - .5) * 440 + (data?.pose?.y || 0) * -300;
      ctx.strokeStyle = `rgba(148,163,184,${0.22 + (seg.strength || 0) * .65})`;
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke();
    });

    // Current camera position.
    const [cx, cy] = project(data?.pose?.x || 0, data?.pose?.y || 0);
    ctx.fillStyle = '#06b6d4';
    ctx.beginPath(); ctx.arc(cx, cy, 7, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = 'rgba(6,182,212,.45)';
    ctx.beginPath(); ctx.arc(cx, cy, 18, 0, Math.PI * 2); ctx.stroke();

    // Live detections projected into the relative room view.
    (data?.detections || []).forEach(d => {
      const x = originX + (d.x - .5) * 700 + (data?.pose?.x || 0) * -220;
      const y = originY + (d.y - .5) * 390 + (data?.pose?.y || 0) * -220;
      const isPerson = d.label === 'person';
      ctx.fillStyle = isPerson ? '#10b981' : '#f59e0b';
      ctx.beginPath(); ctx.arc(x, y, isPerson ? 6 : 5, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#e2e8f0';
      ctx.font = '11px "Share Tech Mono", monospace';
      ctx.fillText(`${d.label} ${(d.confidence * 100).toFixed(0)}%`, x + 9, y - 5);
    });

    ctx.fillStyle = '#64748b';
    ctx.font = '10px "Share Tech Mono", monospace';
    ctx.fillText('RELATIVE SPATIAL MAP · NOT TO SCALE', 18, h - 18);
  }, [data, path]);

  const metrics = data?.metrics || {};

  return (
    <div className="relative flex-1 min-h-0 w-full bg-[#05090d]">
      <div className="absolute inset-0 grid grid-cols-1 xl:grid-cols-[360px_1fr]">
        <div className="p-4 border-r border-slate-800 bg-[#080c11] overflow-y-auto">
          <div className="flex items-center gap-2 mb-3">
            <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400"><ScanLine size={18}/></div>
            <div>
              <div className="text-xs font-mono font-bold text-slate-100 uppercase">Live Room Scan</div>
              <div className="text-[10px] font-mono text-slate-500">Camera → spatial model → live detections</div>
            </div>
          </div>
          <div className="relative aspect-video rounded-xl overflow-hidden border border-slate-700 bg-black">
            <video ref={videoRef} muted playsInline className="w-full h-full object-cover" />
            {!scanning && <div className="absolute inset-0 grid place-items-center text-center p-5 bg-black/45">
              <div><Camera size={28} className="mx-auto text-cyan-400 mb-2"/>
                <div className="text-sm font-mono text-slate-200">Scan the room with your camera</div>
                <div className="text-[10px] text-slate-500 mt-1">Move slowly and pan across walls, doors and furniture.</div>
              </div>
            </div>}
            <canvas ref={captureRef} className="hidden" />
          </div>
          <div className="flex gap-2 mt-3">
            {!scanning
              ? <button onClick={start} className="flex-1 px-3 py-2 rounded-lg bg-cyan-500 text-black text-xs font-mono font-bold flex items-center justify-center gap-2"><Play size={14}/> START SCAN</button>
              : <button onClick={stop} className="flex-1 px-3 py-2 rounded-lg bg-rose-500/15 border border-rose-500/40 text-rose-300 text-xs font-mono font-bold flex items-center justify-center gap-2"><Square size={14}/> STOP</button>}
            <button onClick={reset} className="px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-300"><RotateCcw size={14}/></button>
          </div>
          <div className="grid grid-cols-2 gap-2 mt-2">
            <button onClick={beginEnrollment} className="px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/40 text-amber-300 text-[10px] font-mono font-bold flex items-center justify-center gap-2 hover:bg-amber-500/20">
              <Camera size={13}/> ADD PERSON
            </button>
            {resumeAfterEnrollment && !scanning
              ? <button onClick={resumeScan} className="px-3 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/40 text-emerald-300 text-[10px] font-mono font-bold flex items-center justify-center gap-2 hover:bg-emerald-500/20">
                  <Play size={13}/> RESUME SCAN
                </button>
              : <div className="px-3 py-2 rounded-lg border border-slate-800 bg-slate-950/60 text-slate-500 text-[9px] font-mono flex items-center justify-center text-center">CAMERA EXCLUSIVE MODE</div>}
          </div>
          <div className="mt-3 p-3 rounded-xl border border-slate-800 bg-black/20">
            <div className="text-[10px] font-mono text-cyan-400 flex items-center gap-2"><Wifi size={12}/> {status}</div>
            {error && <div className="text-[10px] font-mono text-rose-400 mt-2">{error}</div>}
          </div>
          <div className="grid grid-cols-2 gap-2 mt-3">
            {[
              ['OBJECTS', metrics.objects ?? 0],
              ['PEOPLE', metrics.people ?? 0],
              ['STRUCTURE', metrics.structure_lines ?? 0],
              ['COVERAGE', `${metrics.coverage ?? 0}%`],
            ].map(([label,value]) => <div key={label} className="p-2.5 rounded-lg border border-slate-800 bg-[#090d12]">
              <div className="text-[9px] font-mono text-slate-500">{label}</div>
              <div className="text-lg font-mono text-slate-100 mt-1">{value}</div>
            </div>)}
          </div>
          {data?.detections?.length > 0 && <div className="mt-3">
            <div className="text-[9px] font-mono text-slate-500 uppercase mb-2">Live detections</div>
            <div className="space-y-1.5 max-h-36 overflow-auto">
              {data.detections.map((d,i) => <div key={`${d.label}-${i}`} className="flex justify-between text-[10px] font-mono px-2 py-1.5 rounded bg-slate-900 border border-slate-800">
                <span className="text-slate-200">{d.label}</span><span className="text-cyan-400">{(d.confidence*100).toFixed(0)}%</span>
              </div>)}
            </div>
          </div>}
          {data?.stitching?.panorama && <div className="mt-3 rounded-xl border border-slate-800 bg-black overflow-hidden">
            <div className="px-3 py-2 text-[9px] font-mono text-cyan-400 uppercase">Incremental Image Stitch · {data.stitching.frames || 1} frames</div>
            <img src={data.stitching.panorama} alt="stitched room panorama" className="w-full max-h-40 object-contain" />
          </div>}
          <div className="mt-3 text-[9px] leading-4 font-mono text-slate-600">
            This view uses real camera frames and backend CV. The spatial map is relative and may drift; it is not a metric 3D reconstruction.
          </div>
        </div>
        <div className="relative min-h-[420px]">
          <canvas ref={mapRef} className="w-full h-full object-contain" />
          <div className="absolute top-3 left-3 px-2.5 py-1.5 rounded-lg bg-black/70 border border-slate-800 text-[10px] font-mono text-cyan-300">
            VIRTUAL ENVIRONMENT · LIVE
          </div>
          {data?.pose && <div className="absolute top-3 right-3 px-2.5 py-1.5 rounded-lg bg-black/70 border border-slate-800 text-[10px] font-mono text-slate-300">
            POSE {data.pose.angle.toFixed(1)}° · CONF {Math.round(data.pose.confidence*100)}%
          </div>}
        </div>
      </div>
      {enrolling && (
        <WebcamEnrollModal
          onClose={closeEnrollment}
          onSuccess={() => { setStatus('Person enrolled successfully. Surveillance identity gallery updated.'); }}
        />
      )}
    </div>
  );
};

export const TacticalMap = ({ 
  cameras = [], 
  sightings = [], 
  onSelectCamera 
}) => {
  const [selectedZone, setSelectedZone] = useState(null);
  const [viewMode, setViewMode] = useState('radar'); // 'radar', 'blueprint' or 'roomscan'
  const canvasRef = useRef(null);

  // Map only real persisted sightings. No synthetic people are shown.
  const [targets, setTargets] = useState([]);
  useEffect(() => {
    const positions = { cam_1: [0.18, 0.28], cam_2: [0.82, 0.28], cam_3: [0.18, 0.75], cam_4: [0.82, 0.75] };
    const latest = new Map();
    (sightings || []).forEach(row => {
      const key = Number(row.global_track_id);
      const prev = latest.get(key);
      if (!prev || Number(row.timestamp) > Number(prev.timestamp)) latest.set(key, row);
    });
    setTargets(Array.from(latest.values()).slice(0, 20).map((row, i) => {
      const [x, y] = positions[row.camera] || [0.5, 0.5];
      const suspect = row.face_review_status === 'denied';
      return { id: `live-${row.global_track_id}`, name: row.name || `Guest ${row.global_track_id}`, zone: row.camera, x, y, isSuspect: suspect, speed: 0, dir: i * 0.3 };
    }));
  }, [sightings]);

  // Canvas radar animation loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let frameId;
    let angle = 0;

    const render = () => {
      angle += 0.025;
      const w = canvas.width = canvas.parentElement.clientWidth || 600;
      const h = canvas.height = canvas.parentElement.clientHeight || 400;

      // Dark canvas background
      ctx.fillStyle = '#080C10';
      ctx.fillRect(0, 0, w, h);

      // Blueprint / Facility Grid
      ctx.strokeStyle = 'rgba(15, 23, 42, 0.9)';
      ctx.lineWidth = 1;
      const step = 28;
      for (let x = 0; x < w; x += step) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
      }
      for (let y = 0; y < h; y += step) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
      }

      // Facility Architectural Walls & Zones
      const drawZone = (x, y, zw, zh, label, accent, active) => {
        ctx.fillStyle = active ? `${accent}18` : 'rgba(15, 23, 42, 0.5)';
        ctx.fillRect(x, y, zw, zh);
        ctx.strokeStyle = active ? accent : 'rgba(51, 65, 85, 0.7)';
        ctx.lineWidth = active ? 2 : 1;
        ctx.strokeRect(x, y, zw, zh);

        ctx.fillStyle = active ? accent : '#64748B';
        ctx.font = 'bold 11px "Share Tech Mono", monospace';
        ctx.fillText(label.toUpperCase(), x + 10, y + 20);
      };

      // 4 Main Zones
      drawZone(w * 0.05, h * 0.1, w * 0.42, h * 0.38, 'Zone A: Main Lobby & Reception', '#06B6D4', selectedZone === 'Zone A');
      drawZone(w * 0.52, h * 0.1, w * 0.43, h * 0.38, 'Zone B: East Perimeter & Alley', '#F59E0B', selectedZone === 'Zone B');
      drawZone(w * 0.05, h * 0.53, w * 0.42, h * 0.4, 'Zone C: Server Vault & Lab', '#10B981', selectedZone === 'Zone C');
      drawZone(w * 0.52, h * 0.53, w * 0.43, h * 0.4, 'Zone D: Loading Dock & Logistics', '#8B5CF6', selectedZone === 'Zone D');

      // Camera FOV Cones
      const palette = ['#06B6D4', '#F59E0B', '#10B981', '#8B5CF6'];
      const camPositions = (cameras || []).map((cam, i) => ({
        id: cam.camera_id, x: w * (i % 2 ? 0.9 : 0.1), y: h * (i < 2 ? 0.15 : 0.85),
        angle: i % 2 ? 2.4 : 0.8, color: palette[i % palette.length], label: String(cam.name || cam.camera_id).slice(0, 12).toUpperCase()
      }));

      camPositions.forEach(c => {
        // Draw FOV cone
        ctx.save();
        ctx.translate(c.x, c.y);
        ctx.rotate(c.angle);

        const coneRadius = 90;
        const coneAngle = Math.PI / 3;

        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.arc(0, 0, coneRadius, -coneAngle / 2, coneAngle / 2);
        ctx.closePath();
        ctx.fillStyle = `${c.color}20`;
        ctx.fill();
        ctx.strokeStyle = `${c.color}60`;
        ctx.stroke();

        ctx.restore();

        // Camera Icon Base
        ctx.fillStyle = c.color;
        ctx.beginPath();
        ctx.arc(c.x, c.y, 6, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = '#FFFFFF';
        ctx.font = 'bold 9px "Share Tech Mono", monospace';
        ctx.fillText(c.label, c.x - 14, c.y - 10);
      });

      // Radar Sweep Effect (Centered)
      if (viewMode === 'radar') {
        const cx = w / 2;
        const cy = h / 2;
        const radarR = Math.min(w, h) * 0.42;

        ctx.save();
        ctx.beginPath();
        ctx.arc(cx, cy, radarR, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(6, 182, 212, 0.25)';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Range rings
        [0.3, 0.6, 1].forEach(frac => {
          ctx.beginPath();
          ctx.arc(cx, cy, radarR * frac, 0, Math.PI * 2);
          ctx.strokeStyle = 'rgba(6, 182, 212, 0.12)';
          ctx.stroke();
        });

        // Sweep cone
        const sweepGrad = ctx.createConicGradient(angle, cx, cy);
        sweepGrad.addColorStop(0, 'rgba(6, 182, 212, 0)');
        sweepGrad.addColorStop(0.85, 'rgba(6, 182, 212, 0)');
        sweepGrad.addColorStop(1, 'rgba(6, 182, 212, 0.35)');
        ctx.fillStyle = sweepGrad;
        ctx.beginPath();
        ctx.arc(cx, cy, radarR, 0, Math.PI * 2);
        ctx.fill();

        ctx.restore();
      }

      // Moving Target Pings
      targets.forEach(t => {
        const tx = t.x * w;
        const ty = t.y * h;

        // Ping wave
        const pingColor = t.isSuspect ? '#EF4444' : '#10B981';
        ctx.fillStyle = pingColor;
        ctx.beginPath();
        ctx.arc(tx, ty, 5, 0, Math.PI * 2);
        ctx.fill();

        // Pulsing halo
        const haloR = 6 + (Math.sin(angle * 4) * 3 + 3);
        ctx.strokeStyle = pingColor;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(tx, ty, haloR, 0, Math.PI * 2);
        ctx.stroke();

        // Label
        ctx.fillStyle = '#FFFFFF';
        ctx.font = 'bold 9px "Share Tech Mono", monospace';
        ctx.fillText(t.name.toUpperCase(), tx + 8, ty - 4);
      });

      frameId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(frameId);
  }, [targets, cameras, selectedZone, viewMode]);

  return (
    <div className="relative w-full h-[520px] rounded-2xl overflow-hidden border border-slate-800 bg-[#080C10] shadow-2xl flex flex-col">
      {/* Map Control Bar */}
      <div className="flex items-center justify-between px-5 py-3 bg-[#090d12] border-b border-slate-800 z-10 select-none">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
            <Crosshair size={18} />
          </div>
          <div>
            <h3 className="font-mono text-sm font-bold text-slate-100 uppercase tracking-wider">
              Tactical Facility 2D Operations Map
            </h3>
            <p className="text-[11px] font-mono text-slate-400">
              Live spatial coverage & target positioning telemetry
            </p>
          </div>
        </div>

        {/* View mode toggle & zone filters */}
        <div className="flex items-center gap-2">
          <div className="flex bg-slate-900 border border-slate-700/80 rounded-lg p-0.5">
            <button
              onClick={() => setViewMode('radar')}
              className={`px-3 py-1 rounded-md text-xs font-mono transition-colors ${
                viewMode === 'radar' 
                  ? 'bg-cyan-500 text-black font-bold' 
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Radar Sweep
            </button>
            <button
              onClick={() => setViewMode('blueprint')}
              className={`px-3 py-1 rounded-md text-xs font-mono transition-colors ${
                viewMode === 'blueprint' 
                  ? 'bg-cyan-500 text-black font-bold' 
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Blueprint Only
            </button>
            <button
              onClick={() => setViewMode('roomscan')}
              className={`px-3 py-1 rounded-md text-xs font-mono transition-colors ${
                viewMode === 'roomscan'
                  ? 'bg-cyan-500 text-black font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Live Room Scan
            </button>
          </div>

          {/* Clear filter */}
          {selectedZone && (
            <button
              onClick={() => setSelectedZone(null)}
              className="px-2.5 py-1 rounded-md bg-slate-800 text-xs font-mono text-slate-300 hover:text-white"
            >
              Clear Zone
            </button>
          )}
        </div>
      </div>

      {/* Map / Room Scan Canvas */}
      {viewMode === 'roomscan' ? (
        <RoomScanView onEnvironmentData={onEnvironmentData} />
      ) : (
      <div className="relative flex-1 w-full h-full overflow-hidden">
        <canvas ref={canvasRef} className="w-full h-full block cursor-pointer" />

        {/* Tactical Legend Overlay */}
        <div className="absolute bottom-4 left-4 p-3 rounded-xl bg-black/75 backdrop-blur-md border border-slate-800 text-[11px] font-mono space-y-1.5 z-10 pointer-events-none">
          <span className="text-slate-400 font-bold block mb-1 uppercase tracking-wider text-[10px]">
            Target Classification
          </span>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
            <span className="text-slate-200">Authorized Personnel</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping" />
            <span className="text-rose-400 font-semibold">Unidentified Guest / Intrusion</span>
          </div>
          <div className="flex items-center gap-2 pt-1 border-t border-slate-800">
            <span className="w-2.5 h-2.5 rounded bg-cyan-400/40 border border-cyan-400" />
            <span className="text-cyan-300">Camera FOV Cone</span>
          </div>
        </div>

        {/* Live Target Counts */}
        <div className="absolute top-4 right-4 p-3 rounded-xl bg-black/75 backdrop-blur-md border border-slate-800 text-[11px] font-mono space-y-1 z-10">
          <div className="flex items-center justify-between gap-4">
            <span className="text-slate-400">TRACKED TARGETS:</span>
            <span className="text-cyan-400 font-bold">{targets.length}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-slate-400">ACTIVE FOV CAMERAS:</span>
            <span className="text-emerald-400 font-bold">4 Channels</span>
          </div>
        </div>
      </div>
      )}
    </div>
  );
};

export default TacticalMap;
