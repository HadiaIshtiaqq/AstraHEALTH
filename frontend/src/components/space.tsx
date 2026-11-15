import { useEffect, useMemo, useRef, useState } from "react";
import type { TraceEvent } from "../api/types";

/** Space visuals: all drawn locally (SVG + canvas), no external assets. Motion stops when the OS asks for reduced motion. */

export function useMotion(): boolean {
  const query = "(prefers-reduced-motion: reduce)";
  const [ok, setOk] = useState(() => typeof window === "undefined" || !window.matchMedia?.(query).matches);
  useEffect(() => {
    const mq = window.matchMedia?.(query);
    if (!mq) return;
    const on = () => setOk(!mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return ok;
}

// ---------------------------------------------------------------- starfield (canvas)
export function Starfield({ density = 0.00028, shooting = true, className = "" }: { density?: number; shooting?: boolean; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const motion = useMotion();
  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const tints = ["255,255,255", "189,239,224", "216,199,255", "255,236,200"];
    type Star = { x: number; y: number; r: number; p: number; s: number; c: string };
    let w = 0, h = 0, stars: Star[] = [], raf = 0, last = 0;
    let shot: { x: number; y: number; vx: number; vy: number; life: number } | null = null;

    const draw = (t: number) => {
      ctx.clearRect(0, 0, w, h);
      for (const s of stars) {
        if (motion) { s.x -= 0.012 * s.r; if (s.x < -2) s.x = w + 2; }
        const a = motion ? 0.3 + 0.7 * (0.5 + 0.5 * Math.sin((t / 1000) * s.s + s.p)) : 0.75;
        ctx.beginPath();
        ctx.fillStyle = `rgba(${s.c},${a})`;
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fill();
        if (s.r > 1.15) { // soft glow on the brightest stars
          ctx.fillStyle = `rgba(${s.c},${a * 0.12})`;
          ctx.beginPath(); ctx.arc(s.x, s.y, s.r * 3.2, 0, Math.PI * 2); ctx.fill();
        }
      }
      if (motion && shooting) {
        if (!shot && Math.random() < 0.0035) shot = { x: Math.random() * w * 0.8 + w * 0.2, y: Math.random() * h * 0.4, vx: -(4 + Math.random() * 3), vy: 2 + Math.random() * 1.5, life: 1 };
        if (shot) {
          const g = ctx.createLinearGradient(shot.x, shot.y, shot.x - shot.vx * 14, shot.y - shot.vy * 14);
          g.addColorStop(0, `rgba(255,255,255,${shot.life})`); g.addColorStop(1, "rgba(255,255,255,0)");
          ctx.strokeStyle = g; ctx.lineWidth = 1.6;
          ctx.beginPath(); ctx.moveTo(shot.x, shot.y); ctx.lineTo(shot.x - shot.vx * 14, shot.y - shot.vy * 14); ctx.stroke();
          shot.x += shot.vx; shot.y += shot.vy; shot.life -= 0.018;
          if (shot.life <= 0 || shot.x < 0 || shot.y > h) shot = null;
        }
      }
    };
    const resize = () => {
      const r = canvas.getBoundingClientRect();
      w = r.width; h = r.height;
      canvas.width = Math.max(1, w * dpr); canvas.height = Math.max(1, h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = Math.max(25, Math.min(400, Math.round(w * h * density)));
      stars = Array.from({ length: n }, () => ({
        x: Math.random() * w, y: Math.random() * h, r: Math.random() ** 2 * 1.4 + 0.25,
        p: Math.random() * Math.PI * 2, s: 0.4 + Math.random() * 1.6, c: tints[Math.floor(Math.random() * tints.length)],
      }));
      draw(performance.now());
    };
    const loop = (t: number) => {
      if (t - last > 40) { draw(t); last = t; } // ~25 fps is plenty and keeps the CPU free for analysis
      raf = requestAnimationFrame(loop);
    };
    const onVis = () => { cancelAnimationFrame(raf); if (!document.hidden && motion) raf = requestAnimationFrame(loop); };
    resize();
    const ro = new ResizeObserver(resize); ro.observe(canvas);
    if (motion) raf = requestAnimationFrame(loop);
    document.addEventListener("visibilitychange", onVis);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); document.removeEventListener("visibilitychange", onVis); };
  }, [density, shooting, motion]);
  return <canvas ref={ref} aria-hidden className={`pointer-events-none absolute inset-0 h-full w-full ${className}`} />;
}

// ---------------------------------------------------------------- planets (SVG, rotating surface)
type Kind = "earth" | "mars" | "moon" | "gas";
const PALETTE: Record<Kind, { base: string; spots: string[]; glow: string; clouds?: boolean; cap?: boolean; bands?: string[] }> = {
  earth: { base: "#1d5ea8", spots: ["#3f9d5a", "#5fae4f", "#2d7a46", "#c9b27a"], glow: "#6cc5ff", clouds: true, cap: true },
  mars: { base: "#c0532c", spots: ["#8a3a1e", "#d97b4c", "#a24527", "#e39a68"], glow: "#ff9a6b", cap: true },
  moon: { base: "#b9b4ab", spots: ["#8f8a82", "#a29d95", "#d4d0c8"], glow: "#e8eef7" },
  gas: { base: "#d9b88a", spots: ["#b5763f"], glow: "#ffd9a0", bands: ["#e8cfa6", "#c08a52", "#f1e0c0", "#a8703f", "#dcb88a"] },
};

function rng(seed: string) {
  let h = 1779033703 ^ seed.length;
  for (let i = 0; i < seed.length; i++) { h = Math.imul(h ^ seed.charCodeAt(i), 3432918353); h = (h << 13) | (h >>> 19); }
  return () => { h = Math.imul(h ^ (h >>> 16), 2246822507); h = Math.imul(h ^ (h >>> 13), 3266489909); return ((h ^= h >>> 16) >>> 0) / 4294967296; };
}

export function SvgPlanet({ cx, cy, r, kind, id, spin = 40, motion = true, cap }: {
  cx: number; cy: number; r: number; kind: Kind; id: string; spin?: number; motion?: boolean; cap?: boolean;
}) {
  const pal = PALETTE[kind];
  const W = r * 4; // texture tile width; two tiles scroll for a seamless rotation
  const spots = useMemo(() => {
    const rand = rng(id + kind);
    const out: { x: number; y: number; rx: number; ry: number; fill: string; o: number }[] = [];
    const count = kind === "gas" ? 2 : kind === "moon" ? 14 : 11;
    for (let i = 0; i < count; i++) {
      const rx = r * (kind === "moon" ? 0.08 + rand() * 0.16 : 0.18 + rand() * 0.42);
      const ry = kind === "moon" ? rx : rx * (0.45 + rand() * 0.5);
      out.push({ x: rx + rand() * (W - 2 * rx), y: (rand() - 0.5) * r * 1.5, rx, ry, fill: pal.spots[i % pal.spots.length], o: 0.75 + rand() * 0.25 });
    }
    if (pal.clouds) for (let i = 0; i < 7; i++) {
      const rx = r * (0.25 + rand() * 0.45);
      out.push({ x: rx + rand() * (W - 2 * rx), y: (rand() - 0.5) * r * 1.6, rx, ry: r * (0.05 + rand() * 0.08), fill: "#ffffff", o: 0.45 + rand() * 0.25 });
    }
    return out;
  }, [id, kind, r, W, pal]);
  const tile = (dx: number) => (
    <g transform={`translate(${dx} 0)`}>
      {spots.map((s, i) => <ellipse key={i} cx={s.x} cy={s.y} rx={s.rx} ry={s.ry} fill={s.fill} opacity={s.o} />)}
    </g>
  );
  return (
    <g>
      <defs>
        <clipPath id={`${id}-clip`}><circle cx={cx} cy={cy} r={r} /></clipPath>
        <radialGradient id={`${id}-shade`} cx="34%" cy="30%" r="78%">
          <stop offset="0%" stopColor="#fff" stopOpacity="0.3" />
          <stop offset="42%" stopColor="#fff" stopOpacity="0" />
          <stop offset="76%" stopColor="#020611" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#020611" stopOpacity="0.9" />
        </radialGradient>
        <radialGradient id={`${id}-glow`}>
          <stop offset="62%" stopColor={pal.glow} stopOpacity="0.45" />
          <stop offset="100%" stopColor={pal.glow} stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx={cx} cy={cy} r={r * 1.32} fill={`url(#${id}-glow)`} />
      <g clipPath={`url(#${id}-clip)`}>
        <rect x={cx - r} y={cy - r} width={2 * r} height={2 * r} fill={pal.base} />
        {pal.bands?.map((b, i) => (
          <rect key={i} x={cx - r} y={cy - r + (i * 2 * r) / pal.bands!.length + r * 0.08} width={2 * r} height={(r * 2) / pal.bands!.length * 0.55} fill={b} opacity="0.85" />
        ))}
        <g transform={`translate(${cx - r} ${cy})`}>
          <g>
            {motion && <animateTransform attributeName="transform" type="translate" from="0 0" to={`${-W} 0`} dur={`${spin}s`} repeatCount="indefinite" />}
            {tile(0)}{tile(W)}
          </g>
        </g>
        {(cap ?? pal.cap) && <ellipse cx={cx} cy={cy - r * 0.95} rx={r * 0.5} ry={r * 0.17} fill="#f6f2ec" opacity="0.9" />}
        <circle cx={cx} cy={cy} r={r} fill={`url(#${id}-shade)`} />
      </g>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={pal.glow} strokeOpacity="0.45" strokeWidth={Math.max(0.8, r * 0.04)} />
    </g>
  );
}

// ---------------------------------------------------------------- mission map: Earth -> Mars transfer
export function MissionOrbit({ progress, day, missionName }: { progress: number | null; day: number | null; missionName: string }) {
  const motion = useMotion();
  const sun = { x: 235, y: 150 };
  const earth = { x: 115, y: 150 }, mars = { x: 430, y: 150 };
  const t = { cx: 272.5, cy: 150, rx: 157.5, ry: 70 };
  const p = progress == null ? null : Math.min(1, Math.max(0.02, progress));
  const th = p == null ? 0 : Math.PI + p * Math.PI;
  const ship = p == null ? null : { x: t.cx + t.rx * Math.cos(th), y: t.cy + t.ry * Math.sin(th) };
  const angle = (Math.atan2(t.ry * Math.cos(th), -t.rx * Math.sin(th)) * 180) / Math.PI;
  const label = p == null
    ? "Mission map: no mission assigned; Earth-orbit monitoring view."
    : `Mission map: ${missionName}, day ${day}, about ${Math.round(p * 100)} percent of the way from Earth to Mars.`;
  return (
    <svg viewBox="0 0 470 270" role="img" aria-label={label} className="h-auto w-full max-w-[520px]">
      <defs>
        <radialGradient id="mo-sun">
          <stop offset="0%" stopColor="#fff7d6" />
          <stop offset="35%" stopColor="#ffd36b" />
          <stop offset="70%" stopColor="#ff9f43" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#ff9f43" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="mo-trail" x1="0" x2="1">
          <stop offset="0%" stopColor="#20b8ad" stopOpacity="0.2" />
          <stop offset="100%" stopColor="#bdefe0" />
        </linearGradient>
      </defs>
      <text x={sun.x} y="30" textAnchor="middle" fill="#bdefe0" fontSize="11" fontWeight="700" letterSpacing="2">
        {p == null ? "EARTH-ORBIT MONITORING" : `${missionName.replace(/\s*\(.*\)/, "").toUpperCase()} · DAY ${day} · ${Math.round(p * 100)}% TO MARS`}
      </text>
      {/* sun */}
      <circle cx={sun.x} cy={sun.y} r="34" fill="url(#mo-sun)">
        {motion && <animate attributeName="r" values="31;37;31" dur="5s" repeatCount="indefinite" />}
      </circle>
      <circle cx={sun.x} cy={sun.y} r="11" fill="#fff3c4" />
      {/* orbits */}
      {[{ rx: 120, ry: 42, c: "#6cc5ff" }, { rx: 195, ry: 68, c: "#ff9a6b" }].map((o, i) => (
        <ellipse key={i} cx={sun.x} cy={sun.y} rx={o.rx} ry={o.ry} fill="none" stroke={o.c} strokeOpacity="0.35" strokeWidth="1" strokeDasharray="2 6">
          {motion && <animate attributeName="stroke-dashoffset" from="0" to={i ? "-80" : "80"} dur={i ? "14s" : "9s"} repeatCount="indefinite" />}
        </ellipse>
      ))}
      {/* transfer trajectory */}
      {p != null && ship && (
        <>
          <path d={`M ${earth.x} ${earth.y} A ${t.rx} ${t.ry} 0 0 1 ${mars.x} ${mars.y}`} fill="none" stroke="#d8c7ff" strokeOpacity="0.5" strokeWidth="1.2" strokeDasharray="5 6">
            {motion && <animate attributeName="stroke-dashoffset" from="22" to="0" dur="1.6s" repeatCount="indefinite" />}
          </path>
          <path d={`M ${earth.x} ${earth.y} A ${t.rx} ${t.ry} 0 0 1 ${ship.x} ${ship.y}`} fill="none" stroke="url(#mo-trail)" strokeWidth="2.6" strokeLinecap="round" />
        </>
      )}
      <SvgPlanet cx={earth.x} cy={earth.y} r={17} kind="earth" id="mo-earth" spin={24} motion={motion} />
      <g>
        {motion && <animateMotion dur="7s" repeatCount="indefinite" path={`M ${earth.x - 30} ${earth.y} a 30 11 0 1 0 60 0 a 30 11 0 1 0 -60 0`} />}
        <SvgPlanet cx={motion ? 0 : earth.x + 30} cy={motion ? 0 : earth.y} r={4.2} kind="moon" id="mo-moon" spin={30} motion={motion} />
      </g>
      <SvgPlanet cx={mars.x} cy={mars.y} r={13} kind="mars" id="mo-mars" spin={30} motion={motion} />
      <text x={earth.x} y={earth.y + 36} textAnchor="middle" fill="#cfe9ff" fontSize="10" fontWeight="600" letterSpacing="2">EARTH</text>
      <text x={mars.x} y={mars.y + 32} textAnchor="middle" fill="#ffd0b8" fontSize="10" fontWeight="600" letterSpacing="2">MARS</text>
      {/* spacecraft with a crew "heartbeat" signal */}
      {ship ? (
        <g transform={`translate(${ship.x} ${ship.y})`}>
          {motion && [0, 0.8].map((d) => (
            <circle key={d} r="4" fill="none" stroke="#20b8ad" strokeWidth="1.4">
              <animate attributeName="r" values="4;20" dur="1.6s" begin={`${d}s`} repeatCount="indefinite" />
              <animate attributeName="stroke-opacity" values="0.9;0" dur="1.6s" begin={`${d}s`} repeatCount="indefinite" />
            </circle>
          ))}
          <g transform={`rotate(${angle})`}>
            <path d="M 9 0 L -6 -5 L -3 0 L -6 5 Z" fill="#f8f5ef" />
            <path d="M -4 -2 L -11 0 L -4 2 Z" fill="#ffb067">
              {motion && <animate attributeName="opacity" values="1;0.4;1" dur="0.5s" repeatCount="indefinite" />}
            </path>
          </g>
        </g>
      ) : (
        <g>
          {motion && <animateMotion dur="11s" repeatCount="indefinite" path={`M ${earth.x - 52} ${earth.y} a 52 20 0 1 1 104 0 a 52 20 0 1 1 -104 0`} />}
          <circle cx={motion ? 0 : earth.x + 52} cy={motion ? 0 : earth.y} r="3" fill="#bdefe0" />
        </g>
      )}
    </svg>
  );
}

// ---------------------------------------------------------------- heartbeat line
export function EkgLine({ className = "" }: { className?: string }) {
  const pts = "0,30 60,30 75,30 82,18 90,42 98,4 106,52 114,30 135,30 200,30 215,30 222,22 230,38 238,10 246,48 254,30 280,30 400,30";
  return (
    <svg viewBox="0 0 400 60" preserveAspectRatio="none" aria-hidden className={className}>
      <polyline points={pts} fill="none" stroke="#20b8ad" strokeOpacity="0.25" strokeWidth="1.5" />
      <polyline points={pts} fill="none" stroke="#bdefe0" strokeWidth="2" strokeLinejoin="round" className="ekg" />
    </svg>
  );
}

// ---------------------------------------------------------------- agent constellation
const STATUS_COLOR: Record<string, string> = {
  completed: "#20b8ad", review: "#f5a524", failed: "#ef6b6b", insufficient_data: "#8b9bb4",
};

export function AgentConstellation({ trace, animate = false }: { trace: TraceEvent[]; animate?: boolean }) {
  const motion = useMotion();
  const [visible, setVisible] = useState(animate ? 0 : trace.length);
  useEffect(() => { // same pace as the timeline next to it
    if (!animate) { setVisible(trace.length); return; }
    setVisible(0);
    let i = 0;
    const t = setInterval(() => { i += 1; setVisible(i); if (i >= trace.length) clearInterval(t); }, 260);
    return () => clearInterval(t);
  }, [trace, animate]);
  const n = trace.length || 1;
  const c = { x: 200, y: 112 }, rx = 165, ry = 80;
  const nodes = trace.map((e, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    return { e, x: c.x + rx * Math.cos(a), y: c.y + ry * Math.sin(a), lit: i < visible };
  });
  const current = trace[Math.min(visible, trace.length) - 1];
  const done = visible >= trace.length;
  return (
    <div className="relative overflow-hidden rounded-2xl space-bg">
      <Starfield density={0.0006} shooting={false} />
      <svg viewBox="0 0 400 228" role="img" className="relative h-auto w-full"
        aria-label={`${Math.min(visible, trace.length)} of ${trace.length} pipeline steps finished`}>
        <ellipse cx={c.x} cy={c.y} rx={rx} ry={ry} fill="none" stroke="#bdefe0" strokeOpacity="0.18" strokeDasharray="3 5" />
        {motion && [0, 2.5, 5].map((d) => (
          <circle key={d} r="1.8" fill="#bdefe0" opacity="0.8">
            <animateMotion dur="7.5s" begin={`${d}s`} repeatCount="indefinite" path={`M ${c.x - rx} ${c.y} a ${rx} ${ry} 0 1 1 ${2 * rx} 0 a ${rx} ${ry} 0 1 1 ${-2 * rx} 0`} />
          </circle>
        ))}
        {nodes.map(({ e, x, y, lit }, i) => lit && (
          <line key={`b${i}`} x1={c.x} y1={c.y} x2={x} y2={y} stroke={STATUS_COLOR[e.status] || "#20b8ad"} strokeOpacity="0.45" strokeWidth="1" strokeDasharray="3 4">
            {motion && <animate attributeName="stroke-dashoffset" from="14" to="0" dur="0.9s" repeatCount="indefinite" />}
          </line>
        ))}
        {/* crew core */}
        <circle cx={c.x} cy={c.y} r="30" fill="#20b8ad" opacity="0.12">
          {motion && <animate attributeName="r" values="26;34;26" dur="1.2s" repeatCount="indefinite" />}
        </circle>
        <SvgPlanet cx={c.x} cy={c.y} r={19} kind="earth" id="ac-core" spin={18} motion={motion} />
        {nodes.map(({ e, x, y, lit }, i) => {
          const col = STATUS_COLOR[e.status] || "#20b8ad";
          return (
            <g key={i}>
              {lit && <circle cx={x} cy={y} r="11" fill={col} opacity="0.22" />}
              <circle cx={x} cy={y} r="6" fill={lit ? col : "#1d3450"} stroke={lit ? "#fff" : "#4b6585"} strokeWidth="1.2" />
              <text x={x} y={y + (y > c.y ? 19 : -11)} textAnchor="middle" fontSize="8.5" fontWeight="600" fill={lit ? "#e6f8f1" : "#8ea3bf"}>
                {e.name.replace(" & Evidence Gate", " Gate")}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="relative px-4 pb-3 text-center text-xs font-medium text-mint" aria-live="polite">
        {done ? `All ${trace.length} pipeline steps complete` : current ? `${current.name} reporting…` : "Agents coming online…"}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- brand mark
export function BrandMark() {
  const motion = useMotion();
  return (
    <svg viewBox="0 0 44 44" className="h-11 w-11" aria-hidden>
      <ellipse cx="22" cy="22" rx="19" ry="7" fill="none" stroke="#bdefe0" strokeOpacity="0.5" transform="rotate(-24 22 22)" />
      <SvgPlanet cx={22} cy={22} r={10} kind="earth" id="brand" spin={16} motion={motion} />
      <g transform="rotate(-24 22 22)">
        <g>
          {motion && <animateMotion dur="5s" repeatCount="indefinite" path="M 3 22 a 19 7 0 1 0 38 0 a 19 7 0 1 0 -38 0" />}
          <circle cx={motion ? 0 : 41} cy={motion ? 0 : 22} r="2.4" fill="#20b8ad" />
        </g>
      </g>
    </svg>
  );
}

// ---------------------------------------------------------------- opening screen for live presentations
export function IntroSplash() {
  const motion = useMotion();
  const [show, setShow] = useState(() => {
    try {
      if (new URLSearchParams(window.location.search).has("intro")) return true;
      if (navigator.webdriver) return false; // automated tests
      return sessionStorage.getItem("astra-intro") !== "seen";
    } catch { return false; }
  });
  const btn = useRef<HTMLButtonElement>(null);
  const close = () => { try { sessionStorage.setItem("astra-intro", "seen"); } catch { /* storage unavailable */ } setShow(false); };
  useEffect(() => {
    if (!show) return;
    btn.current?.focus();
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [show]);
  if (!show) return null;
  const agents = ["InputSense", "DataGuard", "BaselineIQ", "CardioGuard", "NeuroMind", "SleepSense", "BoneGuard", "NutriTrack", "MissionContext", "AnomalyDetect"];
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="intro-title" className="fixed inset-0 z-[100] overflow-hidden space-bg text-white">
      <Starfield density={0.0005} />
      <svg viewBox="0 0 1000 600" preserveAspectRatio="xMidYMax slice" className="intro-rise pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
        <SvgPlanet cx={500} cy={930} r={470} kind="mars" id="intro-mars" spin={160} motion={motion} cap={false} />
        <SvgPlanet cx={170} cy={140} r={46} kind="earth" id="intro-earth" spin={22} motion={motion} />
        <SvgPlanet cx={238} cy={102} r={11} kind="moon" id="intro-moon" spin={40} motion={motion} />
        <ellipse cx="840" cy="150" rx="70" ry="16" fill="none" stroke="#f1e0c0" strokeOpacity="0.6" strokeWidth="5" transform="rotate(-18 840 150)" />
        <SvgPlanet cx={840} cy={150} r={34} kind="gas" id="intro-gas" spin={50} motion={motion} />
      </svg>
      <div className="relative z-10 flex h-full flex-col items-center justify-center px-6 text-center">
        <div className="intro-fade text-xs font-semibold tracking-[0.35em] text-mint/90" style={{ animationDelay: "0.2s" }}>THE NEXT FRONTIER · 2026</div>
        <h1 id="intro-title" className="intro-title mt-4 text-4xl font-bold sm:text-6xl">ASTRAHEALTH AI</h1>
        <p className="intro-fade mt-4 max-w-xl text-base text-white/85 sm:text-lg" style={{ animationDelay: "1.4s" }}>
          Autonomous crew health intelligence for missions where Earth is minutes away.
        </p>
        <ul className="mt-8 flex max-w-2xl flex-wrap justify-center gap-2" aria-label="Specialist agents">
          {agents.map((a, i) => (
            <li key={a} className="intro-agent rounded-full border border-white/15 px-3 py-1 text-xs font-medium"
              style={{ animationDelay: `${1.8 + i * 0.18}s` }}>{a}</li>
          ))}
        </ul>
        <button ref={btn} onClick={close} className="intro-fade btn mt-10 bg-teal px-6 py-3 text-base text-navy hover:bg-mint" style={{ animationDelay: "3.4s" }}>
          Enter mission console
        </button>
        <p className="intro-fade mt-3 text-xs text-white/60" style={{ animationDelay: "3.6s" }}>Fully offline · local AI · not a medical device</p>
      </div>
    </div>
  );
}
