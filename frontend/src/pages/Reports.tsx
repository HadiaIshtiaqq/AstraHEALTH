import { useState } from "react";
import { Download, FileText, Lock, Printer } from "lucide-react";
import { api, download } from "../api/client";
import { Card, ErrorBox, PageHeader, SeverityBadge, StatePill, SyntheticChip } from "../components/ui";
import { fmtTime } from "../lib/format";
import { useApp } from "../state/AppContext";

const day = (offset: number) => new Date(Date.now() + offset * 86400000).toISOString().slice(0, 10);

export default function Reports() {
  const { profileId } = useApp();
  const [start, setStart] = useState(day(-7));
  const [end, setEnd] = useState(day(0));
  const [report, setReport] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [passphrase, setPassphrase] = useState("");
  const [encMsg, setEncMsg] = useState<string | null>(null);

  const generate = async () => {
    setBusy(true); setError(null);
    try {
      setReport(await api.createReport(profileId, `${start}T00:00:00Z`, `${end}T23:59:59Z`));
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <div>
      <PageHeader title="Mission health reports" subtitle="A concise, timestamped report for the onboard medical officer or a ground flight surgeon. Generated and stored locally; exported only when you choose." />
      <Card className="no-print mb-6">
        <div className="flex flex-wrap items-end gap-4">
          <label className="text-sm"><span className="mb-1 block font-medium text-navy">From</span>
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="rounded-xl border border-line px-3 py-2" /></label>
          <label className="text-sm"><span className="mb-1 block font-medium text-navy">To</span>
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="rounded-xl border border-line px-3 py-2" /></label>
          <button className="btn btn-primary" onClick={generate} disabled={busy}><FileText size={16} aria-hidden /> {busy ? "Generating…" : "Generate report"}</button>
          {report && (
            <>
              <button className="btn btn-ghost" onClick={() => download(`/reports/${report.report_id}/export.pdf`, `astrahealth-${report.report_id}.pdf`).catch((e) => setError(e.message))}><Download size={16} aria-hidden /> PDF</button>
              <a className="btn btn-ghost" href={`/api/v1/reports/${report.report_id}/export.csv`} download><Download size={16} aria-hidden /> CSV</a>
              <a className="btn btn-ghost" href={`/api/v1/reports/${report.report_id}/export.html`} target="_blank" rel="noreferrer"><Printer size={16} aria-hidden /> Print view</a>
            </>
          )}
        </div>
        {report && (
          <form className="mt-4 flex flex-wrap items-end gap-3 border-t border-line pt-4" onSubmit={(e) => {
            e.preventDefault(); setError(null);
            download(`/reports/${report.report_id}/export.enc`, `astrahealth-${report.report_id}.pdf.astra.enc`,
              { method: "POST", body: JSON.stringify({ format: "pdf", passphrase }) })
              .then(() => { setPassphrase(""); setEncMsg("Encrypted PDF downloaded. The recipient decrypts it with scripts/decrypt_report.py and the passphrase."); })
              .catch((err) => setError(err.message));
          }}>
            <label className="text-sm"><span className="mb-1 flex items-center gap-1 font-medium text-navy"><Lock size={14} aria-hidden /> Encrypted export passphrase (min. 10 characters)</span>
              <input type="password" autoComplete="new-password" value={passphrase} onChange={(e) => setPassphrase(e.target.value)} className="w-72 rounded-xl border border-line px-3 py-2" /></label>
            <button className="btn btn-primary" disabled={passphrase.length < 10}><Lock size={16} aria-hidden /> Download encrypted PDF</button>
            {encMsg && <p className="w-full text-xs text-ok" role="status">{encMsg}</p>}
          </form>
        )}
        {error && <div className="mt-3"><ErrorBox message={error} /></div>}
      </Card>

      {report && (
        <article className="card fade-in space-y-6 p-6 sm:p-8">
          <header className="flex flex-wrap items-start justify-between gap-4 border-b border-line pb-4">
            <div>
              <h2 className="text-xl font-semibold text-navy">{report.header.profile_alias}</h2>
              <p className="text-sm text-muted">{report.header.mission} · day {report.header.mission_day} · {report.header.environment}</p>
              <p className="text-sm text-muted">Window {fmtTime(report.header.window_start)} → {fmtTime(report.header.window_end)} · generated {fmtTime(report.generated_at)}</p>
            </div>
            <div className="text-right text-xs text-muted">
              <SyntheticChip />
              <div className="mt-2">App {report.versions.app} · Rules {report.versions.ruleset} ({report.versions.ruleset_checksum})</div>
              <div>{report.versions.anomaly_model} · Index {report.versions.knowledge_index}</div>
            </div>
          </header>
          <p className="rounded-xl border border-monitor/40 bg-monitor-soft p-3 text-sm font-semibold text-monitor">{report.disclaimer}</p>
          <section>
            <h3 className="mb-2 font-semibold text-navy">Latest assessment</h3>
            {report.latest_assessment ? (
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <StatePill state={report.latest_assessment.monitoring_state} />
                <span>{report.latest_assessment.headline}</span>
                <span className="text-muted">· unresolved REVIEW/URGENT alerts: {report.unresolved_alerts}</span>
              </div>
            ) : <p className="text-sm text-muted">No analysis run in this window — status unknown.</p>}
          </section>
          <section>
            <h3 className="mb-2 font-semibold text-navy">Findings ({report.findings.length})</h3>
            <ul className="space-y-2">{report.findings.map((f: any, i: number) => (
              <li key={i} className="rounded-xl border border-line p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2"><SeverityBadge severity={f.severity} /><code className="text-xs">{f.code}</code>
                  <span className="text-xs text-muted">{f.agent_id} · rules {f.rule_ids.join(", ") || "—"}</span></div>
                <p className="mt-1">{f.summary}</p>
                <p className="mt-1 text-xs text-muted">Evidence: {f.references.length ? f.references.map((r: any) => `${r.title} — ${r.section} [${r.chunk_id}]`).join("; ") : f.evidence_status}
                  {" · "}Source observations: {f.evidence_observation_ids.length}</p>
              </li>))}
            </ul>
          </section>
          <section>
            <h3 className="mb-2 font-semibold text-navy">Alerts ({report.alerts.length})</h3>
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <thead className="text-left text-xs text-muted"><tr><th className="p-2">Severity</th><th className="p-2">Alert</th><th className="p-2">Next step</th><th className="p-2">State</th><th className="p-2">Created</th></tr></thead>
              <tbody>{report.alerts.map((a: any) => (
                <tr key={a.alert_id} className="border-t border-line"><td className="p-2"><SeverityBadge severity={a.severity} /></td><td className="p-2">{a.title}</td>
                  <td className="p-2">{a.next_step}</td><td className="p-2">{a.state}</td><td className="p-2 whitespace-nowrap">{fmtTime(a.created_at)}</td></tr>))}
              </tbody></table></div>
          </section>
          <section>
            <h3 className="mb-2 font-semibold text-navy">Metric summary</h3>
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <thead className="text-left text-xs text-muted"><tr><th className="p-2">Metric</th><th className="p-2">Unit</th><th className="p-2">n</th><th className="p-2">Min</th><th className="p-2">Median</th><th className="p-2">Max</th></tr></thead>
              <tbody>{report.metric_summaries.map((m: any) => (
                <tr key={m.metric_code} className="border-t border-line"><td className="p-2">{m.label}</td><td className="p-2">{m.unit}</td><td className="p-2">{m.n}</td>
                  <td className="p-2">{m.min ?? "missing"}</td><td className="p-2">{m.median ?? "—"}</td><td className="p-2">{m.max ?? "—"}</td></tr>))}
              </tbody></table></div>
            <p className="mt-2 text-xs text-muted">{report.measurements.length} individual measurements with units, timestamps, source and quality status are included in the CSV and printable exports.</p>
          </section>
          <section>
            <h3 className="mb-2 font-semibold text-navy">Sources cited</h3>
            <ul className="list-disc pl-5 text-sm">{report.sources.map((s: any) => <li key={s.document_id}>{s.title} — {s.publisher}, v{s.version} ({s.publication_date})</li>)}
              {!report.sources.length && <li className="text-muted">No evidence cited.</li>}</ul>
          </section>
        </article>
      )}
    </div>
  );
}
