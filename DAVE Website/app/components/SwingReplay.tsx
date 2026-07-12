"use client";

import { useEffect, useMemo, useRef, useState, ChangeEvent } from "react";

type Vec3 = { x: number; y: number; z: number };

type Frame = {
  timestamp_s: number;
  elapsed_s: number;
  joints_m: {
    shoulder: Vec3;
    elbow: Vec3;
    wrist: Vec3;
  };
  elbow_angle_deg: number;
  [key: string]: unknown;
};

type SwingReplayProps = {
  frames: Frame[] | null | undefined;
  /** Milliseconds between autoplay steps. Lower = faster playback. */
  playbackMsPerFrame?: number;
};

const VIEW_W = 300;
const VIEW_H = 220;
const PAD = 30;

export default function SwingReplay({
  frames,
  playbackMsPerFrame = 40,
}: SwingReplayProps) {
  const safeFrames = useMemo<Frame[]>(() => frames ?? [], [frames]);
  const hasFrames = safeFrames.length > 0;

  const [frameIndex, setFrameIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Whenever a *new* swing's frames arrive, jump back to frame 0 and resume
  // autoplay so each new swing replays automatically.
  useEffect(() => {
    setFrameIndex(0);
    setIsPlaying(true);
  }, [safeFrames]);

  useEffect(() => {
    if (!isPlaying || !hasFrames) return;

    intervalRef.current = setInterval(() => {
      setFrameIndex((current) => {
        const next = current + 1;
        return next >= safeFrames.length ? 0 : next; // loop back to start
      });
    }, playbackMsPerFrame);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isPlaying, hasFrames, safeFrames.length, playbackMsPerFrame]);

  // Compute a bounding box across ALL frames (not just the current one) so
  // the whole swing arc fits on screen without the skeleton drifting out of
  // view or the scale jumping around as frames change.
  const bounds = useMemo(() => {
    if (!hasFrames) return null;

    let minX = Infinity;
    let maxX = -Infinity;
    let minZ = Infinity;
    let maxZ = -Infinity;

    for (const f of safeFrames) {
      for (const joint of [f.joints_m.shoulder, f.joints_m.elbow, f.joints_m.wrist]) {
        minX = Math.min(minX, joint.x);
        maxX = Math.max(maxX, joint.x);
        minZ = Math.min(minZ, joint.z);
        maxZ = Math.max(maxZ, joint.z);
      }
    }

    return { minX, maxX, minZ, maxZ };
  }, [safeFrames, hasFrames]);

  const project = useMemo(() => {
    if (!bounds) return null;

    const rangeX = bounds.maxX - bounds.minX || 0.1;
    const rangeZ = bounds.maxZ - bounds.minZ || 0.1;
    const scale = Math.min(
      (VIEW_W - PAD * 2) / rangeX,
      (VIEW_H - PAD * 2) / rangeZ
    );
    const midX = (bounds.minX + bounds.maxX) / 2;
    const midZ = (bounds.minZ + bounds.maxZ) / 2;

    return (p: Vec3) => ({
      x: VIEW_W / 2 + (p.x - midX) * scale,
      y: VIEW_H / 2 - (p.z - midZ) * scale, // invert: +z is "up"
    });
  }, [bounds]);

  const frame = hasFrames ? safeFrames[frameIndex] : null;

  const points = useMemo(() => {
    if (!frame || !project) return null;
    return {
      shoulder: project(frame.joints_m.shoulder),
      elbow: project(frame.joints_m.elbow),
      wrist: project(frame.joints_m.wrist),
    };
  }, [frame, project]);

  const handleSeek = (event: ChangeEvent<HTMLInputElement>) => {
    setIsPlaying(false); // manual scrub pauses autoplay
    setFrameIndex(Number(event.target.value));
  };

  if (!hasFrames) {
    return (
      <div className="flex h-full items-center justify-center rounded-2xl border border-white/10 bg-slate-800/70 p-6 text-center text-sm text-slate-400">
        No frame data available for replay yet.
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col rounded-2xl border border-white/10 bg-slate-800/70 p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-semibold text-white">Swing Replay</span>
        <span className="text-xs text-slate-400">
          Frame {frameIndex + 1} / {safeFrames.length}
        </span>
      </div>

      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        className="w-full flex-1 rounded-xl bg-slate-950/60"
      >
        {points && (
          <>
            <line
              x1={points.shoulder.x}
              y1={points.shoulder.y}
              x2={points.elbow.x}
              y2={points.elbow.y}
              stroke="#e879f9"
              strokeWidth={6}
              strokeLinecap="round"
            />
            <line
              x1={points.elbow.x}
              y1={points.elbow.y}
              x2={points.wrist.x}
              y2={points.wrist.y}
              stroke="#c084fc"
              strokeWidth={6}
              strokeLinecap="round"
            />
            <circle cx={points.shoulder.x} cy={points.shoulder.y} r={6} fill="#f9fafb" />
            <circle cx={points.elbow.x} cy={points.elbow.y} r={5} fill="#f9fafb" />
            <circle cx={points.wrist.x} cy={points.wrist.y} r={5} fill="#f9fafb" />
          </>
        )}
      </svg>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-300">
        <p>
          Elbow angle:{" "}
          <span className="font-semibold text-white">
            {frame ? frame.elbow_angle_deg.toFixed(1) : "--"}°
          </span>
        </p>
        <p>
          Elapsed:{" "}
          <span className="font-semibold text-white">
            {frame ? frame.elapsed_s.toFixed(3) : "--"}s
          </span>
        </p>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={() => setIsPlaying((p) => !p)}
          className="rounded-xl bg-fuchsia-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-fuchsia-500"
        >
          {isPlaying ? "Pause" : "Play"}
        </button>
        <input
          type="range"
          min={0}
          max={safeFrames.length - 1}
          value={frameIndex}
          onChange={handleSeek}
          className="flex-1 accent-fuchsia-500"
        />
      </div>
    </div>
  );
}
