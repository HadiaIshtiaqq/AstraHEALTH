import { useEffect, useMemo, useState } from "react";
import { CircleCheck, ClipboardCheck, FileUp, Lock, MessageSquare, Send, Sparkles, TriangleAlert } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { AnalysisRun, ObservationDraft, ParseResult, ValidationPreview } from "../api/types";
import { RunSummary } from "../components/analysis";
import { ImportRecords } from "../components/ImportRecords";
import { Card, ErrorBox, PageHeader } from "../components/ui";
import { useApp } from "../state/AppContext";

type Form = Record<string, string>;
const DRAFT_KEY = "astra.checkin.draft";
const STEPS = ["Vitals", "Sleep & wellbeing", "Activity & intake", "Review & submit"];

function nowLocalInput(): string {
  const d = new Date();
  d.setSeconds(0, 0);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function Field({ label, children, hint, error }: { label: string; children: React.ReactNode; hint?: string; error?: string }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-navy">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && !error && <span className="mt-1 block text-xs text-muted">{hint}</span>}
      {error && <span role="alert" className="mt-1 block text-xs font-semibold text-urgent">{error}</span>}
    </label>
  );
}

const input = "w-full rounded-xl border border-line bg-white px-3 py-2.5 text-navy tabular-nums focus:border-teal";

function Scale({ value, onChange, labels, name }: { value: string; onChange: (v: string) => void; labels: string[]; name: string }) {
  return (
    <div role="radiogroup" aria-label={name} className="grid grid-cols-5 gap-1.5">
      {labels.map((l, i) => {
        const v = String(i + 1);
        const active = value === v;
        return (
          <button type="button" role="radio" aria-checked={active} key={v} onClick={() => onChange(active ? "" : v)}
            className={`rounded-xl border px-1 py-2 text-xs font-medium transition-colors ${active ? "border-teal-ink bg-teal-ink text-white" : "border-line bg-white text-navy hover:bg-ivory"}`}>
            <span className="block text-base font-semibold">{v}</span>{l}
          </button>
        );
      })}
    </div>
  );
}

function buildObservations(f: Form, symptoms: string[], measuredAt: string): ObservationDraft[] {
  const at = new Date(measuredAt).toISOString();
  const o: ObservationDraft[] = [];
  const add = (metric_code: string, key: string, unit: string, extra: Partial<ObservationDraft> = {}) => {
    if (f[key] !== undefined && f[key] !== "") o.push({ metric_code, value: f[key], unit, measured_at: at, source: "manual", ...extra });
  };
  add("heart_rate", "heart_rate", "bpm", { context: f.hr_context || null });
  add("bp_systolic", "bp_systolic", "mmHg");
  add("bp_diastolic", "bp_diastolic", "mmHg");
  add("body_temperature", "body_temperature", f.temp_unit || "°C");
  add("sleep_duration", "sleep_duration", "h");
  add("sleep_quality", "sleep_quality", "score");
  add("mood", "mood", "score");
  add("stress", "stress", "score");
  add("fatigue", "fatigue", "score");
  add("exercise_duration", "exercise_duration", "min");
  add("resistance_exercise", "resistance_exercise", "bool");
  add("fluid_intake", "fluid_intake", f.fluid_unit || "mL");
  add("appetite", "appetite", "score");
  add("body_mass", "body_mass", "kg");
  add("msk_discomfort", "msk_discomfort", "score");
  symptoms.forEach((s) => o.push({ metric_code: "symptom", value: s, unit: "code", measured_at: at, source: "manual" }));
  return o;
}

function ManualCheckin({ onDone }: { onDone: (runId: string) => void }) {
  const { profileId, metrics, symptoms: symptomDefs, refresh } = useApp();
  const stored = useMemo(() => { try { return JSON.parse(localStorage.getItem(DRAFT_KEY) || "null"); } catch { return null; } }, []);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<Form>(stored?.form || { temp_unit: "°C", fluid_unit: "mL", hr_context: "resting" });
  const [symptoms, setSymptoms] = useState<string[]>(stored?.symptoms || []);
  const [measuredAt, setMeasuredAt] = useState(nowLocalInput());
  const [preview, setPreview] = useState<ValidationPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string) => (e: { target: { value: string } } | string) =>
    setForm((f) => ({ ...f, [k]: typeof e === "string" ? e : e.target.value }));

  useEffect(() => {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify({ form, symptoms })); } catch { /* ignore */ }
  }, [form, symptoms]);

  const observations = buildObservations(form, symptoms, measuredAt);
  // Inline validation (debounced) against the backend validator — the single source of truth.
  useEffect(() => {
    if (!observations.length) { setPreview(null); return; }
    const t = setTimeout(() => api.validate(profileId, observations).then(setPreview).catch(() => undefined), 350);
    return () => clearTimeout(t);
  }, [JSON.stringify(observations), profileId]); // eslint-disable-line react-hooks/exhaustive-deps

  const issueFor = (code: string) => {
    const idx = observations.findIndex((o) => o.metric_code === code);
    const item = preview?.observations.find((p) => p.index === idx);
    return item?.errors[0] || item?.messages.find((m) => !m.startsWith("Measurement context")) || undefined;
  };

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const r = await api.submit({ profile_id: profileId, observations, mode: "manual" });
      try { localStorage.removeItem(DRAFT_KEY); } catch { /* ignore */ }
      refresh();
      if (r.run_id) onDone(r.run_id);
    } catch (e) {
      const err = e as ApiError;
      const details = (err.details as any)?.errors?.map((x: any) => x.message).join(" · ");
      setError(details ? `${err.message} ${details}` : err.message);
    } finally { setBusy(false); }
  };

  const sl = (code: string) => metrics[code]?.scale_labels || ["1", "2", "3", "4", "5"];
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <Card>
        <ol className="mb-6 grid grid-cols-4 gap-2" aria-label="Check-in steps">
          {STEPS.map((s, i) => (
            <li key={s}>
              <button onClick={() => setStep(i)} aria-current={step === i ? "step" : undefined}
                className={`w-full rounded-xl px-2 py-2 text-left text-xs font-semibold ${step === i ? "bg-navy text-white" : i < step ? "bg-mint-soft text-teal-ink" : "bg-ivory-2 text-muted"}`}>
                <span className="block text-[10px]">STEP {i + 1}</span>{s}
              </button>
            </li>
          ))}
        </ol>

        {step === 0 && (
          <div className="fade-in grid gap-5 sm:grid-cols-2">
            <Field label="Heart rate (bpm)" error={issueFor("heart_rate")}>
              <input inputMode="numeric" className={input} value={form.heart_rate || ""} onChange={set("heart_rate")} placeholder="e.g. 62" />
            </Field>
            <Field label="Measurement context" hint="Comparisons use resting readings">
              <select className={input} value={form.hr_context || ""} onChange={set("hr_context")}>
                <option value="resting">Resting (seated)</option><option value="post_exercise">After exercise</option><option value="">Not recorded</option>
              </select>
            </Field>
            <Field label="Blood pressure — systolic (mmHg)" error={preview?.checkin_errors[0] || issueFor("bp_systolic")}>
              <input inputMode="numeric" className={input} value={form.bp_systolic || ""} onChange={set("bp_systolic")} placeholder="e.g. 118" />
            </Field>
            <Field label="Blood pressure — diastolic (mmHg)" error={issueFor("bp_diastolic")} hint="Both values are required together">
              <input inputMode="numeric" className={input} value={form.bp_diastolic || ""} onChange={set("bp_diastolic")} placeholder="e.g. 76" />
            </Field>
            <Field label="Body temperature" error={issueFor("body_temperature")}>
              <div className="flex gap-2">
                <input inputMode="decimal" className={input} value={form.body_temperature || ""} onChange={set("body_temperature")} placeholder="e.g. 36.7" />
                <select aria-label="Temperature unit" className={`${input} w-24`} value={form.temp_unit} onChange={set("temp_unit")}>
                  <option>°C</option><option>°F</option>
                </select>
              </div>
            </Field>
          </div>
        )}

        {step === 1 && (
          <div className="fade-in space-y-5">
            <Field label="Sleep duration — last sleep period (hours)" error={issueFor("sleep_duration")}>
              <input inputMode="decimal" className={`${input} max-w-48`} value={form.sleep_duration || ""} onChange={set("sleep_duration")} placeholder="e.g. 7.2" />
            </Field>
            {(["sleep_quality", "mood", "stress", "fatigue"] as const).map((k) => (
              <div key={k}>
                <div className="mb-1 text-sm font-medium text-navy">{metrics[k]?.label}</div>
                <Scale name={metrics[k]?.label || k} value={form[k] || ""} onChange={set(k)} labels={sl(k)} />
              </div>
            ))}
            <fieldset>
              <legend className="mb-2 text-sm font-medium text-navy">Symptoms today (optional)</legend>
              <div className="flex flex-wrap gap-2">
                {Object.values(symptomDefs).map((s) => {
                  const on = symptoms.includes(s.code);
                  return (
                    <button type="button" key={s.code} aria-pressed={on}
                      onClick={() => setSymptoms((x) => on ? x.filter((c) => c !== s.code) : [...x, s.code])}
                      className={`rounded-full border px-3 py-1.5 text-xs font-medium ${on ? "border-coral-ink bg-coral/25 text-coral-ink" : "border-line bg-white text-navy hover:bg-ivory"}`}>
                      {on && <CircleCheck size={12} className="mr-1 inline" aria-hidden />}{s.label}
                    </button>
                  );
                })}
              </div>
              <p className="mt-2 text-xs text-muted">If a symptom feels like an emergency, contact the onboard medical officer directly — do not wait for this app.</p>
            </fieldset>
          </div>
        )}

        {step === 2 && (
          <div className="fade-in grid gap-5 sm:grid-cols-2">
            <Field label="Exercise today (minutes)" error={issueFor("exercise_duration")} hint="Adds to anything already logged today. To fix an earlier entry, use Health Trends → Correct.">
              <input inputMode="numeric" className={input} value={form.exercise_duration || ""} onChange={set("exercise_duration")} placeholder="e.g. 120" />
            </Field>
            <Field label="Resistance session completed?">
              <select className={input} value={form.resistance_exercise || ""} onChange={set("resistance_exercise")}>
                <option value="">Not recorded</option><option value="1">Yes</option><option value="0">No</option>
              </select>
            </Field>
            <Field label="Fluid intake" error={issueFor("fluid_intake")} hint="Adds to today's total. Logged intake only — hydration status is not inferred.">
              <div className="flex gap-2">
                <input inputMode="decimal" className={input} value={form.fluid_intake || ""} onChange={set("fluid_intake")} placeholder="e.g. 2300" />
                <select aria-label="Fluid unit" className={`${input} w-24`} value={form.fluid_unit} onChange={set("fluid_unit")}>
                  <option>mL</option><option>L</option><option>fl oz</option>
                </select>
              </div>
            </Field>
            <Field label="Body mass (kg, optional)" error={issueFor("body_mass")}>
              <input inputMode="decimal" className={input} value={form.body_mass || ""} onChange={set("body_mass")} />
            </Field>
            <div className="sm:col-span-2">
              <div className="mb-1 text-sm font-medium text-navy">{metrics.appetite?.label}</div>
              <Scale name="Appetite" value={form.appetite || ""} onChange={set("appetite")} labels={sl("appetite")} />
            </div>
            <div className="sm:col-span-2">
              <div className="mb-1 text-sm font-medium text-navy">{metrics.msk_discomfort?.label}</div>
              <Scale name="Musculoskeletal discomfort" value={form.msk_discomfort || ""} onChange={set("msk_discomfort")} labels={sl("msk_discomfort")} />
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="fade-in space-y-4">
            <Field label="Measurement time (your local time; stored in UTC)" hint="Confirm when these measurements were taken">
              <input type="datetime-local" className={`${input} max-w-64`} value={measuredAt} onChange={(e) => setMeasuredAt(e.target.value)} />
            </Field>
            <div className="overflow-x-auto rounded-xl border border-line">
              <table className="w-full text-sm">
                <caption className="sr-only">Measurements to submit</caption>
                <thead className="bg-ivory text-left text-xs text-muted"><tr><th className="p-2">Measurement</th><th className="p-2">Value</th><th className="p-2">Unit</th><th className="p-2">Source</th><th className="p-2">Check</th></tr></thead>
                <tbody>
                  {observations.map((o, i) => {
                    const p = preview?.observations.find((x) => x.index === i);
                    return (
                      <tr key={i} className="border-t border-line">
                        <td className="p-2 font-medium text-navy">{metrics[o.metric_code]?.label}</td>
                        <td className="p-2 tabular-nums">{String(o.value).replace(/_/g, " ")}</td>
                        <td className="p-2">{o.unit}</td>
                        <td className="p-2 text-muted">manual</td>
                        <td className="p-2">{p?.errors.length ? <span className="font-semibold text-urgent">{p.errors[0]}</span>
                          : p && p.quality_status !== "valid" ? <span className="text-monitor">{p.quality_status.replace("_", " ")}</span>
                          : <span className="text-ok">OK</span>}</td>
                      </tr>
                    );
                  })}
                  {!observations.length && <tr><td colSpan={5} className="p-3 text-muted">Nothing entered yet.</td></tr>}
                </tbody>
              </table>
            </div>
            {preview && preview.checkin_errors.map((e) => <ErrorBox key={e} message={e} />)}
            {error && <ErrorBox message={error} />}
          </div>
        )}

        <div className="mt-6 flex items-center justify-between">
          <button className="btn btn-ghost" disabled={step === 0} onClick={() => setStep(step - 1)}>Back</button>
          {step < 3 ? <button className="btn btn-primary" onClick={() => setStep(step + 1)}>Continue</button>
            : <button className="btn btn-primary" disabled={busy || !observations.length || (preview ? !preview.ok : false)} onClick={submit}>
                <Send size={16} aria-hidden /> {busy ? "Saving & analysing…" : "Submit check-in"}
              </button>}
        </div>
      </Card>
      <aside className="space-y-4">
        <Card title="Your data stays on this device" icon={<Lock size={16} aria-hidden />}>
          <p className="text-sm text-muted">Measurements are validated locally before analysis. Raw values are kept unchanged; converted values are stored separately. Drafts are saved in this browser.</p>
        </Card>
        <Card title="Entered so far">
          <p className="text-3xl font-semibold text-navy">{observations.length}</p>
          <p className="text-xs text-muted">observations · {preview ? (preview.ok ? "all valid so far" : "fix highlighted fields") : "not yet checked"}</p>
        </Card>
      </aside>
    </div>
  );
}

const EXAMPLE_PROMPTS = [
  { label: "Morning check-in", text: "Good morning. Resting heart rate 64 bpm, BP 118/76. Slept 7 hours and slept well. Feeling good, a bit stressed about today's EVA prep." },
  { label: "Tired and short sleep", text: "My heart rate is 105 BPM, I slept for 4 hours, and I have been feeling unusually tired. A bit dizzy since this morning but no chest pain. Drank 1.5 L of water." },
  { label: "Exercise and intake", text: "Did 30 min on the treadmill and 45 min resistance. Drank 2 L of water today. Appetite is fine, weight 71.8 kg." },
  { label: "Low mood", text: "Feeling down and lonely this week, stressed and worn out. Slept about 5 hours. Skipped my resistance session." },
  { label: "Approximate values", text: "Pulse is in the 80s after my workout, temperature 37.4 C, back hurts a little." },
  { label: "Urgent symptoms", text: "I have chest pain and shortness of breath, and I feel dizzy." },
];

function ConversationCheckin({ onDone }: { onDone: (runId: string) => void }) {
  const { profileId, metrics, refresh } = useApp();
  const [text, setText] = useState("");
  const [parsed, setParsed] = useState<ParseResult | null>(null);
  const [rows, setRows] = useState<(ObservationDraft & { include: boolean })[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const analyse = async () => {
    setError(null);
    try {
      const r = await api.parse(profileId, text);
      setParsed(r);
      setRows(r.observations.map((o) => ({ ...o, include: true })));
      setAnswers({});
    } catch (e: any) { setError(e.message); }
  };

  const answer = (metric: string, field: string, value: string) => {
    setAnswers((a) => ({ ...a, [`${metric}.${field}`]: value }));
    setRows((rs) => rs.map((r) => {
      if (r.metric_code !== metric) return r;
      if (field === "context") return { ...r, context: value };
      if (field === "unit") return { ...r, unit: value };
      if (field === "value") return { ...r, value: Number(value) };
      return r;
    }));
  };

  const submit = async () => {
    setBusy(true); setError(null);
    const observations = rows.filter((r) => r.include).map(({ include: _i, label: _l, evidence_text: _e, onset: _o, time_note: _t, ...o }) =>
      ({ ...o, confirmed: true }));
    try {
      const r = await api.submit({ profile_id: profileId, observations, mode: "conversation", raw_input_text: text });
      refresh();
      if (r.run_id) onDone(r.run_id);
    } catch (e) {
      const err = e as ApiError;
      setError(`${err.message} ${(err.details as any)?.errors?.map((x: any) => x.message).join(" · ") || ""}`);
    } finally { setBusy(false); }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Describe how you feel" icon={<MessageSquare size={16} aria-hidden />}>
        <label htmlFor="talk" className="sr-only">Describe how you feel</label>
        <textarea id="talk" rows={6} value={text} onChange={(e) => setText(e.target.value)}
          className="w-full rounded-2xl border border-line bg-ivory p-4 text-sm leading-relaxed focus:border-teal"
          placeholder="e.g. My heart rate is 105 BPM, I slept for 4 hours, and I have been feeling unusually tired." />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button className="btn btn-primary" disabled={!text.trim()} onClick={analyse}><Sparkles size={16} aria-hidden /> Interpret locally</button>
        </div>
        <div className="mt-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Try an example prompt</div>
          <div className="flex flex-col gap-1.5">
            {EXAMPLE_PROMPTS.map((ex) => (
              <button key={ex.label} type="button" onClick={() => { setText(ex.text); setParsed(null); setRows([]); }}
                className="rounded-xl border border-line bg-white px-3 py-2 text-left text-xs hover:bg-ivory">
                <span className="font-semibold text-navy">{ex.label}:</span> <span className="text-ink">{ex.text}</span>
              </button>
            ))}
          </div>
        </div>
        <p className="mt-3 text-xs text-muted">InputSense uses local rule-based language processing. Nothing is saved until you confirm each value.</p>
        {parsed && (
          <div className="mt-4 space-y-3">
            {parsed.negated_symptoms.length > 0 && (
              <p className="text-xs text-muted">Recognised as <b>not</b> present: {parsed.negated_symptoms.join(", ").replace(/_/g, " ")}</p>
            )}
            {parsed.clarifications.map((c) => (
              <div key={`${c.metric_code}.${c.field}`} className="rounded-xl bg-sky/30 p-3">
                <p className="text-sm font-medium text-navy">{c.question}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {c.options.map((o) => (
                    <button key={o} onClick={() => answer(c.metric_code, c.field, o)} aria-pressed={answers[`${c.metric_code}.${c.field}`] === o}
                      className={`rounded-full border px-3 py-1 text-xs font-medium ${answers[`${c.metric_code}.${c.field}`] === o ? "border-navy bg-navy text-white" : "border-line bg-white"}`}>
                      {o.replace("_", " ")}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card title="Confirm extracted observations" icon={<ClipboardCheck size={16} aria-hidden />}>
        {!parsed ? <p className="text-sm text-muted">Extracted measurements will appear here for confirmation.</p> : rows.length === 0 ? (
          <p className="text-sm text-muted">No measurements recognised. Try including a value and unit, or use the manual check-in.</p>
        ) : (
          <div className="space-y-2">
            {rows.map((r, i) => (
              <div key={i} className={`rounded-xl border p-3 ${r.include ? "border-teal/50 bg-mint-soft/50" : "border-line bg-white opacity-70"}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <input type="checkbox" id={`inc-${i}`} checked={r.include} onChange={(e) => setRows((rs) => rs.map((x, j) => j === i ? { ...x, include: e.target.checked } : x))} />
                  <label htmlFor={`inc-${i}`} className="font-semibold text-navy">{r.label || metrics[r.metric_code]?.label}</label>
                  {r.evidence_text && <span className="text-xs text-muted">from “{r.evidence_text}”</span>}
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-sm">
                  {r.metric_code === "symptom" ? <span className="rounded-lg bg-white px-2 py-1">{String(r.value).replace(/_/g, " ")}{r.onset ? ` · onset: ${r.onset.replace("_", " ")}` : ""}</span> : (
                    <>
                      <input aria-label="Value" className="w-24 rounded-lg border border-line bg-white px-2 py-1 tabular-nums" value={r.value ?? ""}
                        onChange={(e) => setRows((rs) => rs.map((x, j) => j === i ? { ...x, value: e.target.value } : x))} />
                      <select aria-label="Unit" className="rounded-lg border border-line bg-white px-2 py-1" value={r.unit || ""}
                        onChange={(e) => setRows((rs) => rs.map((x, j) => j === i ? { ...x, unit: e.target.value } : x))}>
                        {(metrics[r.metric_code]?.units || [r.unit || ""]).map((u) => <option key={u}>{u}</option>)}
                      </select>
                      {r.metric_code === "heart_rate" && <span className="rounded-lg bg-white px-2 py-1 text-xs">context: {r.context || "not given"}</span>}
                    </>
                  )}
                </div>
                {r.time_note && <p className="mt-1 text-xs text-monitor">{r.time_note}</p>}
              </div>
            ))}
            {error && <ErrorBox message={error} />}
            <button className="btn btn-primary mt-2 w-full" disabled={busy || !rows.some((r) => r.include)} onClick={submit}>
              <Send size={16} aria-hidden /> {busy ? "Saving & analysing…" : `Confirm & submit ${rows.filter((r) => r.include).length} observation(s)`}
            </button>
          </div>
        )}
      </Card>
    </div>
  );
}

export default function CheckIn() {
  const [mode, setMode] = useState<"manual" | "conversation" | "import">("manual");
  const [run, setRun] = useState<AnalysisRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const onDone = (runId: string) => api.run(runId).then(setRun).catch((e) => setError(e.message));

  if (run) {
    return (
      <div>
        <PageHeader title="Check-in saved and analysed" subtitle={`Stored locally at ${new Date(run.completed_at).toLocaleTimeString()} · run ${run.run_id.slice(0, 8)}`}>
          <button className="btn btn-ghost" onClick={() => setRun(null)}>New check-in</button>
        </PageHeader>
        {run.assessment.monitoring_state === "URGENT" && (
          <div role="alert" className="mb-5 flex items-center gap-3 rounded-2xl bg-urgent p-4 text-white">
            <TriangleAlert size={26} aria-hidden /> <b>Urgent: contact the onboard medical officer now.</b> This alert cannot be downgraded by AI-generated text.
          </div>
        )}
        <RunSummary run={run} animate />
      </div>
    );
  }
  return (
    <div>
      <PageHeader title="Daily health check-in" subtitle="How would you like to provide your health information?" />
      <div role="tablist" className="mb-6 grid max-w-3xl grid-cols-1 gap-3 sm:grid-cols-3">
        {([["manual", "Manual check-in", "Enter measurements individually", ClipboardCheck], ["conversation", "AI conversation", "Describe how you feel naturally", MessageSquare], ["import", "Import records", "Historical CSV / JSON or device export", FileUp]] as const).map(([k, t, d, Icon]) => (
          <button key={k} role="tab" aria-selected={mode === k} onClick={() => setMode(k)}
            className={`card flex items-start gap-3 p-4 text-left ${mode === k ? "ring-2 ring-teal-ink" : ""}`}>
            <Icon size={20} className="mt-0.5 text-teal-ink" aria-hidden />
            <span><span className="block font-semibold text-navy">{t}</span><span className="text-xs text-muted">{d}</span></span>
          </button>
        ))}
      </div>
      {error && <ErrorBox message={error} />}
      {mode === "manual" ? <ManualCheckin onDone={onDone} /> : mode === "conversation" ? <ConversationCheckin onDone={onDone} /> : <ImportRecords onDone={onDone} />}
    </div>
  );
}
