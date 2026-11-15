import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { Observation, Profile } from "../api/types";
import { ObservationActions } from "../components/ObservationActions";
import { Card, ErrorBox, PageHeader, Skeleton } from "../components/ui";
import { fmtDate, fmtTime, fmtValue, localDay, shortLabel } from "../lib/format";
import { useApp, useProfileData } from "../state/AppContext";

const METRIC_CHOICES = ["heart_rate", "bp_systolic", "bp_diastolic", "body_temperature", "sleep_duration", "sleep_quality",
  "mood", "stress", "fatigue", "exercise_duration", "fluid_intake", "appetite", "body_mass", "radiation_dose"];
const SUMMED = new Set(["fluid_intake", "exercise_duration", "radiation_dose"]); 
const LATEST = new Set(["sleep_duration", "body_mass"]);
const RANGES = [7, 14, 30, 42];

interface Point { day: string; label: string; value: number | null; n: number; obs: Observation[] }

export default function Trends() {
  const [params, setParams] = useSearchParams();
  const { metrics, refresh } = useApp();
  const metric = params.get("metric") || "heart_rate";
  const [days, setDays] = useState(30);
  const [showTable, setShowTable] = useState(false);
  const profile = useProfileData<Profile>((id) => api.profile(id));
  const series = useProfileData((id) => api.series(id, [metric], days), [metric, days]);
  const m = metrics[metric];
  const baseline = profile.data?.computed_baselines?.[metric];
  const dayTz = profile.data?.timezone || "UTC"; // same day boundaries as the analysis

  const { points, flagged } = useMemo(() => {
    const obs = series.data?.series[metric] || [];
    const valid = obs.filter((o) => o.quality_status === "valid" && o.normalized_value !== null);
    const byDay = new Map<string, Observation[]>();
    valid.forEach((o) => { const d = localDay(o.measured_at, dayTz); byDay.set(d, [...(byDay.get(d) || []), o]); });
    const pts: Point[] = [];
    const end = new Date();
    for (let i = days - 1; i >= 0; i--) {
      const d = localDay(new Date(end.getTime() - i * 86400000), dayTz);
      const items = byDay.get(d) || [];
      const vals = items.map((o) => o.normalized_value as number);
      // Same daily aggregation as the backend: sums for intake/exercise/dose, latest report for sleep and body mass, mean otherwise.
      const value = !vals.length ? null
        : SUMMED.has(metric) ? vals.reduce((a, b) => a + b, 0)
        : LATEST.has(metric) ? vals[vals.length - 1]
        : vals.reduce((a, b) => a + b, 0) / vals.length;
      pts.push({ day: d, label: fmtDate(d), value, n: items.length, obs: items });
    }
    return { points: pts, flagged: obs.filter((o) => o.quality_status !== "valid") };
  }, [series.data, metric, days, dayTz]);

  const present = points.filter((p) => p.value !== null);
  const missing = points.length - present.length;
  const first = present[0]?.value, last = present[present.length - 1]?.value;
  const summary = present.length
    ? `${shortLabel(m?.label || metric)} over the last ${days} days: ${present.length} days recorded, ${missing} day(s) missing. ` +
      `Range ${fmtValue(Math.min(...present.map((p) => p.value!)), m)}–${fmtValue(Math.max(...present.map((p) => p.value!)), m)} ${m?.normalized_unit}; ` +
      `first ${fmtValue(first, m)}, latest ${fmtValue(last, m)}.` +
      (baseline?.available ? ` Personal usual range ${fmtValue(baseline.p10, m)}–${fmtValue(baseline.p90, m)}.` : " No personal baseline yet.")
    : "No valid measurements in this period.";

  return (
    <div>
      <PageHeader title="Health trends" subtitle="Your measurements compared with your own history. Gaps show days with no valid measurement; they are never interpolated." />
      <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Metric">
        {METRIC_CHOICES.filter((c) => metrics[c]).map((c) => (
          <button key={c} role="tab" aria-selected={metric === c} onClick={() => setParams({ metric: c })}
            className={`rounded-full border px-3 py-1.5 text-sm font-medium ${metric === c ? "border-navy bg-navy text-white" : "border-line bg-white text-navy hover:bg-ivory"}`}>
            {shortLabel(metrics[c].label)}
          </button>
        ))}
      </div>
      <Card title={m ? `${m.label} (${m.normalized_unit})` : metric}
        action={
          <div className="flex gap-1" role="group" aria-label="Range">
            {RANGES.map((r) => (
              <button key={r} onClick={() => setDays(r)} aria-pressed={days === r}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${days === r ? "bg-teal-ink text-white" : "bg-ivory-2 text-navy"}`}>{r}d</button>
            ))}
          </div>
        }>
        {series.error && <ErrorBox message={series.error} />}
        {series.loading && !series.data ? <Skeleton className="h-80" /> : (
          <div className="h-80" aria-hidden>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={points} margin={{ top: 10, right: 16, bottom: 0, left: -8 }} accessibilityLayer={false} tabIndex={-1}>
                <CartesianGrid stroke="#ece6da" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#5b6b80" }} interval="preserveStartEnd" minTickGap={18} />
                <YAxis tick={{ fontSize: 11, fill: "#5b6b80" }} domain={["auto", "auto"]} width={52} />
                {baseline?.available && baseline.p10 !== undefined && baseline.p90 !== undefined && (
                  <ReferenceArea y1={baseline.p10} y2={baseline.p90} fill="#20B8AD" fillOpacity={0.1} stroke="none" />
                )}
                {baseline?.available && <ReferenceLine y={baseline.median} stroke="#0f7a72" strokeDasharray="4 4" />}
                <Tooltip content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const p = payload[0].payload as Point;
                  return (
                    <div className="rounded-xl border border-line bg-white p-3 text-xs shadow-lg">
                      <div className="font-semibold text-navy">{p.label}</div>
                      {p.value === null ? <div className="text-unknown">No valid measurement (gap)</div> : (
                        <>
                          <div className="text-sm text-navy">{fmtValue(p.value, m)} {m?.normalized_unit}{SUMMED.has(metric) && p.n > 1 ? " (day total)" : ""}</div>
                          {p.obs.slice(0, 3).map((o) => (
                            <div key={o.observation_id} className="text-muted">{fmtTime(o.measured_at, false)} · {o.value} {o.unit} · {o.source}{o.context ? ` · ${o.context}` : ""}{o.is_synthetic ? " · synthetic" : ""}</div>
                          ))}
                        </>
                      )}
                    </div>
                  );
                }} />
                <Line type="monotone" dataKey="value" stroke="#14263C" strokeWidth={2.2} connectNulls={false} animationDuration={500}
                  dot={{ r: 3, fill: "#20B8AD", stroke: "#14263C", strokeWidth: 1 }} activeDot={{ r: 5 }} isAnimationActive />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-muted">
          <span className="flex items-center gap-1.5"><span className="h-0.5 w-5 bg-navy" /> Daily value</span>
          {baseline?.available && <span className="flex items-center gap-1.5"><span className="h-3 w-5 rounded bg-teal/20" /> Personal usual range (10th–90th percentile, 30 days)</span>}
          {baseline?.available && <span className="flex items-center gap-1.5"><span className="h-0 w-5 border-t-2 border-dashed border-teal-ink" /> Personal median</span>}
          <span>Gaps = missing days</span>
        </div>
        <p className="mt-3 rounded-xl bg-ivory p-3 text-sm text-ink" aria-live="polite">{summary}</p>
        <button className="mt-3 text-sm font-semibold text-teal-ink hover:underline" onClick={() => setShowTable(!showTable)} aria-expanded={showTable}>
          {showTable ? "Hide" : "Show"} data table
        </button>
        {showTable && (
          <div className="mt-2 max-h-80 overflow-auto rounded-xl border border-line">
            <table className="w-full text-sm">
              <caption className="sr-only">{m?.label} daily values</caption>
              <thead className="sticky top-0 bg-ivory text-left text-xs text-muted"><tr><th className="p-2">Date (UTC)</th><th className="p-2">Value</th><th className="p-2">Readings</th><th className="p-2">Source</th></tr></thead>
              <tbody>{[...points].reverse().map((p) => (
                <tr key={p.day} className="border-t border-line"><td className="p-2">{p.label}</td>
                  <td className="p-2 tabular-nums">{p.value === null ? <span className="text-unknown">missing</span> : `${fmtValue(p.value, m)} ${m?.normalized_unit}`}</td>
                  <td className="p-2">{p.n}</td><td className="p-2 text-muted">{[...new Set(p.obs.map((o) => o.source))].join(", ") || "—"}</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Card>
      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <Card title="Personal baseline">
          {!baseline ? <Skeleton className="h-24" /> : baseline.available ? (
            <>
              <dl className="grid grid-cols-3 gap-3 text-sm">
                {([["Median", baseline.median], ["Robust spread", baseline.robust_spread], ["Mean", baseline.mean], ["Min", baseline.min], ["Max", baseline.max], ["EWMA", baseline.ewma]] as const).map(([k, v]) => (
                  <div key={k}><dt className="text-xs text-muted">{k}</dt><dd className="font-semibold tabular-nums text-navy">{fmtValue(v ?? null, m, 1)}</dd></div>
                ))}
              </dl>
              <p className="mt-3 text-xs text-muted">{baseline.n_days} days of valid history · confidence {baseline.confidence} · 14-day slope {baseline.slope_per_day_14d ?? "—"} {m?.normalized_unit}/day</p>
            </>
          ) : <p className="text-sm text-unknown">Baseline unavailable: {baseline.reason} Values are described, not compared.</p>}
        </Card>
        <Card title={`Flagged & corrected measurements (${flagged.length})`}>
          {flagged.length ? (
            <ul className="space-y-2 text-sm">{flagged.map((o) => (
              <li key={o.observation_id} className="rounded-lg bg-monitor-soft px-3 py-2">
                <div className="flex justify-between gap-2">
                  <span>{fmtTime(o.measured_at)} · {o.value} {o.unit}</span>
                  <span className="font-semibold text-monitor">{o.quality_status.replace("_", " ")}</span>
                </div>
                <div className="mt-1.5"><ObservationActions o={o} metric={m} onDone={() => { series.reload(); refresh(); }} /></div>
              </li>))}
            </ul>
          ) : <p className="text-sm text-muted">No flagged measurements in this period. Flagged values are kept and shown here, never silently discarded.</p>}
        </Card>
      </div>
      <Card className="mt-6" title="Recent measurements — correct mistakes without double counting">
        <ul className="divide-y divide-line text-sm">
          {[...(series.data?.series[metric] || [])].filter((o) => o.quality_status === "valid").reverse().slice(0, 8).map((o) => (
            <li key={o.observation_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span>{fmtTime(o.measured_at)} · <b className="tabular-nums">{o.value} {o.unit}</b> · {o.source}{o.is_synthetic ? " · synthetic" : ""}</span>
              <ObservationActions o={o} metric={m} onDone={() => { series.reload(); refresh(); }} />
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted">A correction creates a new value and marks the old one “superseded”; both stay in the record and reports. Analysis re-runs automatically.</p>
      </Card>
    </div>
  );
}
