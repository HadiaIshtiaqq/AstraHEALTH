import { useState } from "react";
import { FileUp, Upload } from "lucide-react";
import { api } from "../api/client";
import { useAdmin } from "../state/AdminContext";
import { useApp } from "../state/AppContext";
import { Card, ErrorBox } from "./ui";

const SAMPLE = `metric_code,value,unit,measured_at,context
heart_rate,61,bpm,2026-10-01T07:30:00Z,resting
sleep_duration,7.2,h,2026-10-01T07:30:00Z,
mood,4,score,2026-10-01T07:30:00Z,`;

/** Historical record import (CSV / JSON) through the same validator as manual input. */
export function ImportRecords({ onDone }: { onDone: (runId: string) => void }) {
  const { profileId, refresh } = useApp();
  const { withAdmin } = useAdmin();
  const [content, setContent] = useState("");
  const [format, setFormat] = useState<"csv" | "json">("csv");
  const [preview, setPreview] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = (file: File) => {
    setFormat(file.name.toLowerCase().endsWith(".json") ? "json" : "csv");
    file.text().then((t) => { setContent(t); setPreview(null); });
  };
  const go = async (dry: boolean) => {
    setBusy(true); setError(null);
    try {
      const r = await withAdmin((pin) => api.importRecords(profileId, format, content, dry, pin), "Importing historical records is an admin task.");
      setPreview(r);
      if (!dry && r.run_id) { refresh(); onDone(r.run_id); }
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Import historical records" icon={<FileUp size={16} aria-hidden />}>
        <p className="mb-3 text-sm text-muted">CSV columns: <code>metric_code, value, unit, measured_at</code> (optional <code>context</code>), or a JSON list of the same fields.
          Every row is validated like a manual entry; invalid rows are reported and skipped, never silently fixed. Symptom reports cannot be imported. Requires the admin PIN.</p>
        <input type="file" accept=".csv,.json,text/csv,application/json" aria-label="Choose a CSV or JSON file"
          onChange={(e) => e.target.files?.[0] && load(e.target.files[0])} className="mb-3 block text-sm" />
        <textarea rows={8} value={content} onChange={(e) => { setContent(e.target.value); setPreview(null); }}
          placeholder={SAMPLE} aria-label="Records to import" className="w-full rounded-xl border border-line bg-ivory p-3 font-mono text-xs" />
        <div className="mt-3 flex flex-wrap gap-2">
          <select aria-label="Format" value={format} onChange={(e) => setFormat(e.target.value as "csv" | "json")} className="rounded-xl border border-line px-2 py-2 text-sm">
            <option value="csv">CSV</option><option value="json">JSON</option>
          </select>
          <button className="btn btn-ghost" disabled={!content || busy} onClick={() => go(true)}>Check file</button>
          <button className="btn btn-primary" disabled={!content || busy || !preview || preview.accepted === 0} onClick={() => go(false)}>
            <Upload size={16} aria-hidden /> Import {preview ? preview.accepted : ""} valid row(s)
          </button>
          <button className="btn btn-ghost text-xs" onClick={() => { setContent(SAMPLE); setFormat("csv"); setPreview(null); }}>Use sample</button>
        </div>
        {error && <div className="mt-3"><ErrorBox message={error} /></div>}
      </Card>
      <Card title="Validation result">
        {!preview ? <p className="text-sm text-muted">Check the file to see what will be imported.</p> : (
          <div className="space-y-3 text-sm">
            <p><b className="text-ok">{preview.accepted}</b> of {preview.rows} rows valid
              {Object.keys(preview.metrics).length > 0 && <> · {Object.entries(preview.metrics).map(([k, v]) => `${k.replace(/_/g, " ")} ×${v}`).join(", ")}</>}</p>
            {preview.rejected.length > 0 && (
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-urgent">Rejected ({preview.rejected.length})</div>
                <ul className="mt-1 max-h-60 space-y-1 overflow-y-auto">
                  {preview.rejected.map((r: any, i: number) => <li key={i} className="rounded-lg bg-urgent-soft px-2 py-1 text-xs">Row {r.row ?? "—"}: {r.errors.join("; ")}</li>)}
                </ul>
              </div>
            )}
            <p className="text-xs text-muted">Imported history counts towards personal baselines and is labelled with source “import”.</p>
          </div>
        )}
      </Card>
    </div>
  );
}
