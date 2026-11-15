import { lazy, Suspense, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BookOpen, Bone, Brain, Eye, HeartPulse, Utensils, Wind } from "lucide-react";
import { api } from "../api/client";
import type { Finding, Overview, Severity } from "../api/types";
import { Card, ErrorBox, PageHeader, SeverityBadge, Skeleton } from "../components/ui";
import { fmtTime, fmtValue, shortLabel } from "../lib/format";
import { useApp, useProfileData } from "../state/AppContext";

interface Region {
  id: string; label: string; Icon: typeof Brain; metrics: string[]; symptoms: string[]; agents: string[]; query: string; note?: string;
}

const Body3D = lazy(() => import("../components/Body3D"));

const REGIONS: Region[] = [
  { id: "brain", label: "Brain, sleep & wellbeing", Icon: Brain, metrics: ["mood", "stress", "fatigue", "sleep_duration", "sleep_quality"],
    symptoms: ["confusion", "headache", "severe_headache", "insomnia", "low_energy"], agents: ["NeuroMind", "SleepSense"],
    query: "isolation confinement wellbeing sleep loss circadian" },
  { id: "eyes", label: "Eyes & vision", Icon: Eye, metrics: [], symptoms: ["vision_change"], agents: ["Safety & Evidence Gate"],
    query: "vision changes spaceflight neuro-ocular syndrome", note: "No eye measurements in the MVP; vision changes are routed for medical review." },
  { id: "heart", label: "Heart & circulation", Icon: HeartPulse, metrics: ["heart_rate", "bp_systolic", "bp_diastolic", "body_temperature"],
    symptoms: ["chest_pain", "palpitations", "dizziness", "fainting"], agents: ["CardioGuard"], query: "fluid shifts cardiovascular deconditioning microgravity" },
  { id: "lungs", label: "Lungs & breathing", Icon: Wind, metrics: [], symptoms: ["shortness_of_breath", "nasal_congestion"], agents: ["CardioGuard"],
    query: "fluid shifts nasal congestion breathlessness", note: "Respiratory measurements are not part of the MVP; only symptoms are recorded." },
  { id: "digestive", label: "Nutrition & digestion", Icon: Utensils, metrics: ["fluid_intake", "appetite", "body_mass"], symptoms: ["nausea"],
    agents: ["NutriTrack"], query: "nutrition fluid intake appetite body mass" },
  { id: "msk", label: "Bones & muscles", Icon: Bone, metrics: ["exercise_duration", "resistance_exercise", "msk_discomfort"], symptoms: ["back_pain"],
    agents: ["BoneGuard"], query: "bone muscle microgravity exercise countermeasure", note: "Bone density cannot be inferred from exercise logs." },
];

const SEV_RANK: Record<Severity, number> = { INFO: 0, MONITOR: 1, REVIEW: 2, URGENT: 3 };
const FILL: Record<string, string> = { URGENT: "#B54747", REVIEW: "#E39A5B", MONITOR: "#F3D68B", OK: "#BDEFE0", NONE: "#E8ECF2" };

function regionStatus(r: Region, findings: Finding[]): { sev: Severity | null; findings: Finding[] } {
  const hits = findings.filter((f) => f.severity !== "INFO" && (f.metric_codes.some((m) => r.metrics.includes(m))
    || (f.data?.symptoms || f.data?.matched || []).some((s: string) => r.symptoms.includes(s))));
  const sev = hits.reduce<Severity | null>((acc, f) => (!acc || SEV_RANK[f.severity] > SEV_RANK[acc] ? f.severity : acc), null);
  return { sev, findings: hits };
}

function Body({ selected, onSelect, statusOf }: { selected: string; onSelect: (id: string) => void; statusOf: (id: string) => string }) {
  const part = (id: string, label: string, children: React.ReactNode) => (
    <g role="button" tabIndex={0} aria-label={label} aria-pressed={selected === id} onClick={() => onSelect(id)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(id); } }}
      className="cursor-pointer outline-none" style={{ fill: FILL[statusOf(id)], stroke: selected === id ? "#14263C" : "#9aa7b8", strokeWidth: selected === id ? 2.5 : 1.2 }}>
      {children}
    </g>
  );
  return (
    <svg viewBox="0 0 200 420" className="mx-auto h-[460px] max-w-full" aria-label="Body systems">
      <defs><radialGradient id="glow" cx="50%" cy="40%" r="60%"><stop offset="0%" stopColor="#20B8AD" stopOpacity="0.18" /><stop offset="100%" stopColor="#20B8AD" stopOpacity="0" /></radialGradient></defs>
      <ellipse cx="100" cy="200" rx="95" ry="200" fill="url(#glow)" />
      {/* silhouette */}
      <g fill="#f4efe6" stroke="#cfc6b6" strokeWidth="1.2">
        <circle cx="100" cy="46" r="30" />
        <path d="M70 84 Q100 76 130 84 L150 100 L162 200 L150 204 L138 120 L136 220 L128 400 L108 400 L102 250 L98 250 L92 400 L72 400 L64 220 L62 120 L50 204 L38 200 L50 100 Z" />
      </g>
      {part("msk", "Bones and muscles", <>
        <rect x="74" y="250" width="16" height="140" rx="7" /><rect x="110" y="250" width="16" height="140" rx="7" />
        <rect x="42" y="110" width="12" height="86" rx="6" transform="rotate(8 48 150)" /><rect x="146" y="110" width="12" height="86" rx="6" transform="rotate(-8 152 150)" />
      </>)}
      {part("brain", "Brain, sleep and wellbeing", <path d="M78 40 Q80 20 100 20 Q120 20 122 40 Q124 52 112 54 L88 54 Q76 52 78 40 Z" />)}
      {part("eyes", "Eyes and vision", <><circle cx="90" cy="60" r="5" /><circle cx="110" cy="60" r="5" /></>)}
      {part("lungs", "Lungs and breathing", <><path d="M76 104 Q70 140 78 162 L94 160 L94 110 Z" /><path d="M124 104 Q130 140 122 162 L106 160 L106 110 Z" /></>)}
      {part("heart", "Heart and circulation", <path d="M100 150 L88 138 Q82 130 90 124 Q96 121 100 128 Q104 121 110 124 Q118 130 112 138 Z" />)}
      {part("digestive", "Nutrition and digestion", <ellipse cx="100" cy="196" rx="24" ry="20" />)}
    </svg>
  );
}

function Education({ query }: { query: string }) {
  const [items, setItems] = useState<any[] | null>(null);
  useEffect(() => { setItems(null); api.knowledge(query, 2).then((r) => setItems(r.results)).catch(() => setItems([])); }, [query]);
  if (!items) return <Skeleton className="h-20" />;
  if (!items.length) return <p className="text-sm text-muted">No relevant passage in the local library.</p>;
  return (
    <div className="space-y-2">
      {items.map((r) => (
        <figure key={r.chunk_id} className="rounded-xl bg-ivory p-3">
          <figcaption className="mb-1 flex items-center gap-1.5 text-xs text-muted"><BookOpen size={13} aria-hidden className="text-teal-ink" />
            <b className="text-navy">{r.title}</b> · {r.section}</figcaption>
          <p className="text-sm leading-relaxed">{r.passage}</p>
          <p className="mt-1 text-[11px] text-muted">{r.publisher} — related reference: {r.related_reference}</p>
        </figure>
      ))}
    </div>
  );
}

export default function DigitalTwin() {
  const { metrics, symptoms } = useApp();
  const { data, error, loading } = useProfileData<Overview>((id) => api.overview(id));
  const [selected, setSelected] = useState("heart");
  const [view, setView] = useState<"2d" | "3d">("2d");
  if (error) return <ErrorBox message={error} />;
  if (loading && !data) return <Skeleton className="h-96" />;
  const findings = data?.latest_run?.assessment.findings || [];
  const statusOf = (id: string) => {
    const r = REGIONS.find((x) => x.id === id)!;
    const s = regionStatus(r, findings);
    if (s.sev) return s.sev;
    const hasData = r.metrics.some((m) => data?.latest_values[m]);
    return hasData ? "OK" : "NONE";
  };
  const region = REGIONS.find((r) => r.id === selected)!;
  const rs = regionStatus(region, findings);

  return (
    <div>
      <PageHeader title="Digital human twin" subtitle="Select a body system to see its linked measurements, latest findings and background information. 2D by default for reliability; an optional 3D view is available. Every region is also in the list." />
      <div className="grid gap-6 lg:grid-cols-[minmax(260px,360px)_1fr]">
        <Card>
          <div className="mb-3 hidden justify-center gap-1 md:flex" role="group" aria-label="View">
            {(["2d", "3d"] as const).map((v) => (
              <button key={v} onClick={() => setView(v)} aria-pressed={view === v}
                className={`rounded-lg px-3 py-1 text-xs font-semibold ${view === v ? "bg-navy text-white" : "bg-ivory-2 text-navy"}`}>{v.toUpperCase()}</button>
            ))}
          </div>
          {view === "2d" ? <Body selected={selected} onSelect={setSelected} statusOf={statusOf} /> : (
            <Suspense fallback={<Skeleton className="h-[440px]" />}><Body3D selected={selected} onSelect={setSelected} statusOf={statusOf} /></Suspense>
          )}
          <div className="mt-2 flex flex-wrap justify-center gap-3 text-[11px] text-muted">
            {[["URGENT", "Urgent"], ["REVIEW", "Review"], ["MONITOR", "Monitor"], ["OK", "Within criteria"], ["NONE", "No data"]].map(([k, l]) => (
              <span key={k} className="flex items-center gap-1"><span className="h-3 w-3 rounded-sm border border-line" style={{ background: FILL[k] }} />{l}</span>
            ))}
          </div>
        </Card>
        <div className="space-y-6">
          <nav aria-label="Body systems" className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {REGIONS.map((r) => {
              const st = statusOf(r.id);
              return (
                <button key={r.id} onClick={() => setSelected(r.id)} aria-pressed={selected === r.id}
                  className={`card flex items-center gap-2 p-3 text-left ${selected === r.id ? "ring-2 ring-teal-ink" : ""}`}>
                  <r.Icon size={18} className="shrink-0 text-teal-ink" aria-hidden />
                  <span className="min-w-0"><span className="block truncate text-sm font-semibold text-navy">{r.label}</span>
                    <span className="text-xs text-muted">{st === "OK" ? "Within criteria" : st === "NONE" ? "No recent data" : st.toLowerCase()}</span></span>
                </button>
              );
            })}
          </nav>
          <Card title={region.label} icon={<region.Icon size={18} aria-hidden className="text-teal-ink" />}
            action={rs.sev ? <SeverityBadge severity={rs.sev} /> : undefined}>
            <p className="mb-4 text-xs text-muted">Analysed by: {region.agents.join(", ")}{region.note ? ` · ${region.note}` : ""}</p>
            {region.metrics.length > 0 && (
              <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-3">
                {region.metrics.map((code) => {
                  const o = data?.latest_values[code];
                  const m = metrics[code];
                  return (
                    <Link key={code} to={`/trends?metric=${code}`} className="rounded-xl border border-line p-3 hover:bg-ivory">
                      <div className="text-xs text-muted">{m ? shortLabel(m.label) : code}</div>
                      <div className="text-xl font-semibold tabular-nums text-navy">{o ? fmtValue(o.normalized_value, m) : "--"}
                        {o && m?.value_type === "numeric" && <span className="ml-1 text-xs font-normal text-muted">{m.normalized_unit}</span>}</div>
                      <div className="text-[11px] text-muted">{o ? fmtTime(o.measured_at) : "not measured"}</div>
                    </Link>
                  );
                })}
              </div>
            )}
            <h3 className="mb-2 text-sm font-semibold text-navy">Latest findings</h3>
            {rs.findings.length ? (
              <ul className="mb-5 space-y-2">{rs.findings.map((f, i) => (
                <li key={i} className="flex items-start gap-2 text-sm"><SeverityBadge severity={f.severity} /> <span>{f.summary}</span></li>))}
              </ul>
            ) : <p className="mb-5 text-sm text-muted">No findings needing attention for this system in the latest analysis.</p>}
            <h3 className="mb-2 text-sm font-semibold text-navy">Symptoms tracked</h3>
            <p className="mb-5 text-sm text-muted">{region.symptoms.map((s) => symptoms[s]?.label || s).join(" · ")}</p>
            <h3 className="mb-2 text-sm font-semibold text-navy">Learn more (local library)</h3>
            <Education query={region.query} />
          </Card>
        </div>
      </div>
    </div>
  );
}
