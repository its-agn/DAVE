"use client";

import { useEffect, useMemo, useRef, useState, ChangeEvent } from "react";
import { Canvas } from "@react-three/fiber";
import { Line, OrbitControls } from "@react-three/drei";

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

// Data axes: x = down-positive (head-to-toe), y = left-positive (shoulder-to-shoulder), z = forward-positive (out of the person's front).
// three.js axes: X = right, Y = up, Z = toward viewer.
// Both x and y need negating: "down" must become negative-Y (up-positive),
// and "left" must become negative-X (right-positive). z maps through
// unchanged since "forward" already agrees with three's +Z-toward-viewer.
function toScene(v: Vec3): [number, number, number] {
  return [-v.y, -v.x, v.z];
}

function ArmSkeleton({ frame }: { frame: Frame }) {
  const shoulder = toScene(frame.joints_m.shoulder);
  const elbow = toScene(frame.joints_m.elbow);
  const wrist = toScene(frame.joints_m.wrist);

  return (
    <>
      <Line points={[shoulder, elbow]} color="#e879f9" lineWidth={4} />
      <Line points={[elbow, wrist]} color="#c084fc" lineWidth={4} />

      <mesh position={shoulder}>
        <sphereGeometry args={[0.014, 16, 16]} />
        <meshStandardMaterial color="#f9fafb" />
      </mesh>
      <mesh position={elbow}>
        <sphereGeometry args={[0.011, 16, 16]} />
        <meshStandardMaterial color="#f9fafb" />
      </mesh>
      <mesh position={wrist}>
        <sphereGeometry args={[0.011, 16, 16]} />
        <meshStandardMaterial color="#fbcfe8" />
      </mesh>
    </>
  );
}

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

  const frame = hasFrames ? safeFrames[frameIndex] : null;

  const handleSeek = (event: ChangeEvent<HTMLInputElement>) => {
    setIsPlaying(false); // manual scrub pauses autoplay
    setFrameIndex(Number(event.target.value));
  };

  if (!hasFrames || !frame) {
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

      <div className="relative min-h-[280px] flex-1 overflow-hidden rounded-xl bg-slate-950/60">
        <Canvas camera={{ position: [0.7, 0.5, 0.9], fov: 45 }}>
          <ambientLight intensity={0.6} />
          <directionalLight position={[1, 1.5, 1]} intensity={1} />
          <gridHelper args={[1, 10, "#475569", "#334155"]} />
          <axesHelper args={[0.15]} />
          <ArmSkeleton frame={frame} />
          <OrbitControls target={[0, 0, 0]} enablePan={false} />
        </Canvas>

        <div className="pointer-events-none absolute bottom-2 left-2 rounded-lg bg-slate-900/70 px-2 py-1 text-[10px] leading-4 text-slate-300">
          <span className="text-rose-400">red</span> = side-to-side ·{" "}
          <span className="text-emerald-400">green</span> = up/down ·{" "}
          <span className="text-sky-400">blue</span> = out · drag to orbit
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-300">
        <p>
          Elbow angle:{" "}
          <span className="font-semibold text-white">
            {frame.elbow_angle_deg.toFixed(1)}°
          </span>
        </p>
        <p>
          Elapsed:{" "}
          <span className="font-semibold text-white">
            {frame.elapsed_s.toFixed(3)}s
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
