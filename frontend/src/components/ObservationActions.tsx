import { useState } from "react";
import { CircleCheck, Pencil, Undo2 } from "lucide-react";
import { api } from "../api/client";
import type { MetricDef, Observation } from "../api/types";
import { PinDialog } from "./PinDialog";

/** Confirm / correct / retract one measurement. Raw values stay immutable; every action is audited and re-analysed. */
export function ObservationActions({ o, metric, onDone }: { o: Observation; metric?: MetricDef; onDone: (runId: string | null) => void }) {
  const [mode, setMode] = useState<"idle" | "correct" | "retract" | "pin">("idle");
  const [officerAction, setOfficerAction] = useState<null | ((pin: string) => Promise<{ run_id: string | null }>)>(null);
  const [value, setValue] = useState(String(o.value ?? ""));
  const [unit, setUnit] = useState(o.unit);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const finished = ["superseded", "retracted"].includes(o.quality_status);
  if (finished) return <span className="text-[11px] text-muted">{o.status_note || o.quality_status}</span>;
  const run = (p: Promise<{ run_id: string | null }>, retryWithPin?: (pin: string) => Promise<{ run_id: string | null }>) =>
    p.then((r) => { setMode("idle"); setOfficerAction(null); setError(null); onDone(r.run_id); })
      .catch((e) => {
        if (e.status === 403 && retryWithPin) { setError(null); setOfficerAction(() => retryWithPin); return; }
        setError(e.message);
      });

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {o.quality_status === "pending_confirmation" && (
        <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => run(api.confirmObs(o.observation_id))}>
          <CircleCheck size={12} aria-hidden /> Confirm
        </button>
      )}
      {o.quality_status === "implausible" && (
        <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => setMode("pin")}>
          <CircleCheck size={12} aria-hidden /> Confirm (medical officer)
        </button>
      )}
      {o.metric_code !== "symptom" && mode !== "correct" && (
        <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => setMode("correct")}><Pencil size={12} aria-hidden /> Correct</button>
      )}
      {mode !== "retract" && (
        <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => setMode("retract")}><Undo2 size={12} aria-hidden /> Entered in error</button>
      )}
      {mode === "correct" && (
        <form className="flex flex-wrap items-center gap-1.5" onSubmit={(e) => { e.preventDefault(); run(api.correctObs(o.observation_id, value, unit, reason), (pin) => api.correctObs(o.observation_id, value, unit, reason, pin)); }}>
          <input aria-label="Corrected value" value={value} onChange={(e) => setValue(e.target.value)} className="w-20 rounded-lg border border-line px-2 py-1 text-xs" />
          <select aria-label="Unit" value={unit} onChange={(e) => setUnit(e.target.value)} className="rounded-lg border border-line px-1 py-1 text-xs">
            {(metric?.units || [o.unit]).map((u) => <option key={u}>{u}</option>)}
          </select>
          <input aria-label="Reason" placeholder="reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} className="w-36 rounded-lg border border-line px-2 py-1 text-xs" />
          <button className="btn btn-primary px-2 py-1 text-xs" disabled={reason.trim().length < 3}>Save</button>
          <button type="button" className="text-xs text-muted" onClick={() => setMode("idle")}>Cancel</button>
        </form>
      )}
      {mode === "retract" && (
        <form className="flex flex-wrap items-center gap-1.5" onSubmit={(e) => { e.preventDefault(); run(api.retractObs(o.observation_id, reason), (pin) => api.retractObs(o.observation_id, reason, pin)); }}>
          <input aria-label="Reason" placeholder="why was it wrong?" value={reason} onChange={(e) => setReason(e.target.value)} className="w-44 rounded-lg border border-line px-2 py-1 text-xs" />
          <button className="btn btn-danger px-2 py-1 text-xs" disabled={reason.trim().length < 3}>Retract</button>
          <button type="button" className="text-xs text-muted" onClick={() => setMode("idle")}>Cancel</button>
        </form>
      )}
      {mode === "pin" && (
        <PinDialog title="Confirm an implausible value" withNote error={error}
          description="This value is outside the physically plausible range. Only the medical officer can confirm it after a repeat measurement."
          onCancel={() => setMode("idle")} onSubmit={(pin, note) => run(api.confirmObs(o.observation_id, pin, note))} />
      )}
      {officerAction && (
        <PinDialog title="Medical officer required" error={error}
          description="Symptom reports, and values older than 24 hours, can only be changed by the medical officer."
          onCancel={() => setOfficerAction(null)} onSubmit={(pin) => run(officerAction(pin))} />
      )}
      {error && mode !== "pin" && !officerAction && <span role="alert" className="text-xs font-semibold text-urgent">{error}</span>}
    </div>
  );
}
