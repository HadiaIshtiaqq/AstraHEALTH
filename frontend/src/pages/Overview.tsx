import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity, ArrowDownRight, ArrowRight, ArrowUpRight, ClipboardCheck, HeartPulse as CareIcon, Droplets, Dumbbell, Gauge, HeartPulse,
  Minus, Moon, Play, Radiation, Satellite, Smile, Trophy, Zap,
} from "lucide-react";
import { api } from "../api/client";
import type { Baseline, Finding, Observation, Overview as OverviewData } from "../api/types";
import { StateBanner, FindingCard } from "../components/analysis";
import { CarePlanPanel } from "../components/CarePlan";
import { Card, ErrorBox, SeverityBadge, Skeleton } from "../components/ui";
import { AGENT_LABELS, fmtTime, fmtValue, relative, shortLabel } from "../lib/format";
import { useAdmin } from "../state/AdminContext";
import { EkgLine, MissionOrbit, Starfield } from "../components/space";
import { useApp, useProfileData } from "../state/AppContext";

const CARDS: { code: string; Icon: typeof HeartPulse; accent: string; pair?: string }[] = [
  { code: "heart_rate", Icon: HeartPulse, accent: "bg-coral/25 text-coral-ink" },
  { code: "bp_systolic", Icon: Gauge, accent: "bg-coral/20 text-coral-ink", pair: "bp_diastolic" },
  { code: "sleep_duration", Icon: Moon, accent: "bg-sky/50 text-navy" },
  { code: "mood", Icon: Smile, accent: "bg-lavender/60 text-plum" },
  { code: "stress", Icon: Zap, accent: "bg-lavender/60 text-plum" },
  { code: "fatigue", Icon: Activity, accent: "bg-lavender/60 text-plum" },
  { code: "exercise_duration", Icon: Dumbbell, accent: "bg-mint text-teal-ink" },
  { code: "fluid_intake", Icon: Droplets, accent: "bg-sunshine/60 text-monitor" },
];

function MetricCard({ code, pair, Icon, accent, obs, pairObs, baseline, finding }: {
  code: string; pair?: string; Icon: typeof HeartPulse; accent: string; obs?: Observation; pairObs?: Observation;
  baseline?: Baseline; finding?: Finding;
}) {
  const { metrics } = useApp();
  const navigate = useNavigate();
  const m = metrics[code];
  if (!m) return null;
  const stale = obs && Date.now() - new Date(obs.measured_at).getTime() > 36 * 3600 * 1000;
  const z = baseline?.available && obs ? baseline.robust_z : null;
  const Trend = z == null ? Minus : z > 0.5 ? ArrowUpRight : z < -0.5 ? ArrowDownRight : ArrowRight;
  const trendText = z == null ? "no comparison" : z > 0.5 ? "above usual" : z < -0.5 ? "below usual" : "near usual";
  let status: React.ReactNode;
  if (!obs) status = <span className="text-unknown">Not measured — status unknown</span>;
  else if (obs.quality_status !== "valid") status = <span className="text-monitor">Flagged: {obs.quality_status.replace("_", " ")}</span>;
  else if (finding) status = <SeverityBadge severity={finding.severity} />;
  else if (!baseline?.available) status = <span className="text-unknown">No personal baseline yet</span>;
  else status = <span className="text-ok">Within usual personal range</span>;

  const label = pair ? "Blood pressure" : shortLabel(m.label);
  const value = pair ? `${fmtValue(obs?.normalized_value, m)}/${fmtValue(pairObs?.normalized_value, metrics[pair])}` : fmtValue(obs?.normalized_value, m);
  return (
    <button onClick={() => navigate(`/trends?metric=${code}`)}
      className="card lift group flex min-w-0 flex-col gap-3 p-4 text-left"
      aria-describedby={undefined}>
      <div className="flex items-center justify-between">
        <span className={`grid h-9 w-9 place-items-center rounded-xl ${accent}`}><Icon size={18} aria-hidden /></span>
        <span className="hidden items-center gap-1 text-xs text-muted sm:flex"><Trend size={14} aria-hidden />{trendText}</span>
      </div>
      <div>
        <div className="text-sm font-medium text-muted">{label}</div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-2xl font-semibold tabular-nums text-navy sm:text-3xl">{obs ? value : "--"}</span>
          {obs && m.value_type === "numeric" && <span className="text-sm text-muted">{m.normalized_unit}</span>}
        </div>
        <div className="mt-0.5 text-xs text-muted">
          {obs ? <>{fmtTime(obs.measured_at)} · {obs.source}{stale ? " · stale" : ""}</> : "Awaiting measurement"}
        </div>
        {baseline?.available && (
          <div className="mt-0.5 text-xs text-muted">Usual: {fmtValue(baseline.median, m)}{m.value_type === "numeric" ? ` ${m.normalized_unit}` : ""} · {baseline.n_days} days</div>
        )}
      </div>
      <div className="mt-auto text-xs font-semibold">{status}</div>
    </button>
  );
}

const ZONES = ["UTC", "America/Chicago", "America/New_York", "Europe/London", "Europe/Berlin", "Asia/Karachi", "Asia/Tokyo"];
function TimezonePicker({ profileId, value }: { profileId: string; value: string }) {
  const { refresh } = useApp();
  return (
    <label className="block text-xs text-muted">Crew time zone (sets where each day starts for analysis; times are shown in your local zone)
      <select value={value} onChange={(e) => api.setTimezone(profileId, e.target.value).then(refresh)}
        className="mt-1 w-full rounded-lg border border-line bg-white px-2 py-1.5 text-sm text-navy">
        {[...new Set([value, ...ZONES])].map((z) => <option key={z}>{z}</option>)}
      </select>
    </label>
  );
}

function DemoScenarios() {
  const { setProfileId, refresh } = useApp();
  const { withAdmin } = useAdmin();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scenarios = [
    { id: "healthy", label: "Healthy baseline", hint: "Crew Alpha · stable check-in" },
    { id: "gradual", label: "Gradual multi-signal change", hint: "Crew Bravo · sleep, mood, HR drift" },
    { id: "urgent", label: "Potential urgent event", hint: "Crew Charlie · urgent symptom rule" },
    { id: "agent_failure", label: "Agent failure", hint: "SleepSense fault injected" },
  ];
  const run = async (id: string) => {
    setBusy(id); setError(null);
    try {
      const r = await withAdmin((pin) => api.runScenario(id, pin), "Demo scenarios add synthetic check-ins, so they need the admin PIN.");
      setProfileId(r.profile_id);
      refresh();
      navigate(`/analysis/${r.run_id}?animate=1`);
    } catch (e: any) { setError(e.message); } finally { setBusy(null); }
  };
  return (
    <Card title="Scripted demo scenarios" icon={<Play size={16} aria-hidden />}>
      <p className="mb-3 text-xs text-muted">Submits a synthetic check-in and runs the real agent pipeline.</p>
      <div className="grid gap-2">
        {scenarios.map((s) => (
          <button key={s.id} disabled={!!busy} onClick={() => run(s.id)}
            className="flex items-center justify-between rounded-xl border border-line px-3 py-2 text-left hover:bg-ivory disabled:opacity-60">
            <span><span className="block text-sm font-semibold text-navy">{s.label}</span><span className="text-xs text-muted">{s.hint}</span></span>
            {busy === s.id ? <span className="text-xs text-muted">Running…</span> : <Play size={14} className="text-teal-ink" aria-hidden />}
          </button>
        ))}
      </div>
      {error && <div className="mt-2"><ErrorBox message={error} /></div>}
    </Card>
  );
}

export default function Overview() {
  const { data, error, loading } = useProfileData<OverviewData>((id) => api.overview(id));
  if (error) return <ErrorBox message={error} />;
  if (loading && !data) return <div className="grid gap-4 md:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-40" />)}</div>;
  if (!data) return null;
  const run = data.latest_run;
  const a = run?.assessment;
  // Baselines for every metric (not only those in the last check-in), with today's z-score from the latest run where available.
  const runBaselines: Record<string, Baseline> = run?.agent_results.find((r) => r.agent_id === "baseline_iq")?.output?.baselines || {};
  const baselines: Record<string, Baseline> = Object.fromEntries(Object.entries(data.computed_baselines || {}).map(
    ([k, b]) => [k, { ...b, robust_z: runBaselines[k]?.robust_z ?? null }]));
  const findingFor = (code: string) => a?.findings.find((f) => f.severity !== "INFO" && f.metric_codes.includes(code) && f.agent_id !== "anomaly_detect");
  const flagged = (a?.findings || []).filter((f) => f.severity !== "INFO");
  const p = data.profile;
  const tasksDone = data.tasks_today.filter((t) => t.completed_at).length;

  return (
    <div className="space-y-6">
      <section className="space-bg relative overflow-hidden rounded-3xl p-6 text-white shadow-[0_20px_60px_rgb(5_11_22/0.35)] sm:p-8">
        <Starfield />
        <EkgLine className="pointer-events-none absolute inset-x-0 bottom-0 h-14 w-full opacity-60" />
        <div className="relative z-10 grid items-center gap-6 lg:grid-cols-[1fr_minmax(0,480px)]">
          <div>
            <div className="text-xs font-semibold tracking-[0.18em] text-mint/80">MISSION HEALTH OVERVIEW</div>
            <h1 className="glow-text mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Your health, in focus.</h1>
            <p className="mt-2 max-w-xl text-sm text-white/75">
              {p.display_name} · {p.role} · {p.environment}. Latest analysis {relative(run?.completed_at)}.
            </p>
          <div className="mt-5 flex flex-wrap gap-3">
            {data.checkin_due ? (
              <Link to="/check-in" className="btn bg-teal text-navy hover:bg-mint"><ClipboardCheck size={18} aria-hidden /> Complete today's check-in</Link>
            ) : (
              <span className="chip bg-white/15 text-white">Today's check-in submitted</span>
            )}
            <Link to="/reports" className="btn border border-white/25 text-white hover:bg-white/10">Generate report</Link>
          </div>
          </div>
          <div className="flex justify-center lg:justify-end">
            <MissionOrbit missionName={p.mission_name} day={p.mission_day}
              progress={p.has_mission && p.mission_day != null ? p.mission_day / (p.planned_duration_days || 540) : null} />
          </div>
        </div>
      </section>

      {/* Hierarchy 1–2: escalation and overall state first */}
      {a ? <StateBanner assessment={a} /> : <div className="card p-5 text-sm text-muted">No analysis yet. Complete a check-in to start monitoring. Status: unknown.</div>}
      {a?.monitoring_state === "URGENT" && data.urgent_acknowledged && !data.open_alerts.some((x) => x.severity === "URGENT") && (
        <p className="-mt-3 rounded-xl bg-ok-soft px-4 py-2 text-sm text-ok">
          Urgent alert acknowledged by the medical officer {fmtTime(data.urgent_acknowledged.acknowledged_at)}
          {data.urgent_acknowledged.acknowledged_note ? ` — “${data.urgent_acknowledged.acknowledged_note}”` : ""}. The state updates with the next check-in.
        </p>
      )}

      {/* Hierarchy 3: what changed vs. own baseline */}
      <section aria-label="Current indicators" className="stagger grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-4">
        {CARDS.map((c) => (
          <MetricCard key={c.code} {...c} obs={data.latest_values[c.code]} pairObs={c.pair ? data.latest_values[c.pair] : undefined}
            baseline={baselines[c.code]} finding={findingFor(c.code)} />
        ))}
      </section>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          {/* Hierarchy 4: what to do next */}
          <Card title="Next actions" icon={<ArrowRight size={16} aria-hidden />}>
            {a?.next_actions.length ? (
              <ol className="space-y-2.5">
                {a.next_actions.slice(0, 5).map((n, i) => (
                  <li key={i} className="flex items-start gap-3 text-sm"><SeverityBadge severity={n.severity} /> <span className="text-ink">{n.text}</span></li>
                ))}
              </ol>
            ) : <p className="text-sm text-muted">No follow-up actions from the latest analysis. Keep to your routine schedule.</p>}
            <div className="mt-4 flex flex-wrap gap-2">
              <Link to="/check-in" className="btn btn-primary text-sm">Repeat a measurement</Link>
              <Link to="/countermeasures" className="btn btn-ghost text-sm">Today's routine ({tasksDone}/{data.tasks_today.length})</Link>
            </div>
          </Card>
          {/* Hierarchy 5: why */}
          <Card title={`Recent findings (${flagged.length})`}>
            {flagged.length ? <div className="space-y-3">{flagged.slice(0, 4).map((f, i) => <FindingCard key={i} f={f} />)}</div>
              : <p className="text-sm text-muted">No findings that need attention in the latest analysis.</p>}
            {a && !a.coverage.complete && (
              <p className="mt-3 rounded-xl bg-unknown-soft p-3 text-sm text-unknown">
                Coverage incomplete{a.coverage.missing_core_metrics.length ? ` — not measured: ${a.coverage.missing_core_metrics.join(", ").replace(/_/g, " ")}` : ""}
                {a.coverage.failed_agents.length ? ` — failed: ${a.coverage.failed_agents.map((x) => AGENT_LABELS[x]).join(", ")}` : ""}.
              </p>
            )}
          </Card>
        </div>
        <div className="space-y-6">
          <Card title="What to improve" icon={<CareIcon size={16} aria-hidden />}
            action={<Link to="/care-plan" className="text-sm font-semibold text-teal-ink hover:underline">Full care plan</Link>}>
            <CarePlanPanel compact limit={2} />
          </Card>
          <Card title="Mission context" icon={<Satellite size={16} aria-hidden />}>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-xs text-muted">Mission day</dt><dd className="font-semibold text-navy">{p.mission_day ?? "No mission assigned"}</dd></div>
              <div><dt className="text-xs text-muted">Gravity</dt><dd className="font-semibold text-navy">{p.gravity_context}</dd></div>
              <div className="col-span-2"><dt className="text-xs text-muted">Communication</dt><dd className="font-semibold text-navy">{p.communication_mode}</dd></div>
              <div className="col-span-2"><dt className="sr-only">Display time zone</dt><dd><TimezonePicker profileId={p.profile_id} value={p.timezone} /></dd></div>
              <div className="col-span-2 flex items-center gap-2 text-xs text-muted"><dt className="sr-only">Radiation</dt><dd className="flex items-center gap-2"><Radiation size={14} aria-hidden />
                {data.latest_values.radiation_dose ? `Last dosimeter record ${fmtValue(data.latest_values.radiation_dose.normalized_value ?? null, undefined)} mSv${p.is_synthetic ? " (simulated)" : ""}` : "No dosimeter record"}</dd>
              </div>
            </dl>
          </Card>
          <Card title="Wellness consistency" icon={<Trophy size={16} aria-hidden />}>
            <p className="text-3xl font-semibold text-navy">{data.checkin_streak} <span className="text-base font-normal text-muted">day check-in streak</span></p>
            <p className="mt-1 text-xs text-muted">Rewards completing check-ins — never for hiding symptoms or dismissing alerts.</p>
          </Card>
          <DemoScenarios />
        </div>
      </div>
    </div>
  );
}
