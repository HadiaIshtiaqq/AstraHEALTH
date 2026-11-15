import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bot, Play, ShieldCheck, X } from "lucide-react";
import { api } from "../api/client";
import type { AgentDescription, AgentResult, AnalysisRun } from "../api/types";
import { FindingCard, RunSummary } from "../components/analysis";
import { AgentStatusBadge, Card, ErrorBox, PageHeader, Skeleton, StatePill } from "../components/ui";
import { fmtTime } from "../lib/format";
import { useAdmin } from "../state/AdminContext";
import { useApp, useProfileData } from "../state/AppContext";

function AgentDetail({ agent, result, desc, onClose }: { agent: string; result?: AgentResult; desc?: AgentDescription; onClose: () => void }) {
  return (
    <div role="dialog" aria-modal="true" aria-label={`${desc?.name || agent} details`} className="fixed inset-0 z-40 flex justify-end bg-navy/30" onClick={onClose}>
      <div className="fade-in h-full w-full max-w-2xl overflow-y-auto bg-ivory p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold text-navy">{desc?.name || agent}</h2>
            <p className="text-sm text-muted">{desc?.scope}</p>
          </div>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Close"><X size={16} aria-hidden /></button>
        </div>
        <dl className="mb-5 grid gap-3 text-sm sm:grid-cols-2">
          <div><dt className="text-xs text-muted">Status</dt><dd>{result ? <AgentStatusBadge status={result.status} /> : <AgentStatusBadge status="idle" />}</dd></div>
          <div><dt className="text-xs text-muted">Version · duration</dt><dd className="font-medium">{desc?.version} · {result ? `${result.duration_ms.toFixed(1)} ms` : "—"}</dd></div>
          <div className="sm:col-span-2"><dt className="text-xs text-muted">Why it was activated</dt><dd>{result?.activation_reason || "Not routed for this check-in"}</dd></div>
          <div className="sm:col-span-2"><dt className="text-xs text-muted">Method</dt><dd>{result?.method || desc?.method}</dd></div>
          <div className="sm:col-span-2"><dt className="text-xs text-muted">Must not</dt><dd className="text-urgent">{desc?.must_not}</dd></div>
          {result?.error && <div className="sm:col-span-2"><ErrorBox message={result.error} /></div>}
        </dl>
        {result && (
          <>
            <h3 className="mb-2 text-sm font-semibold text-navy">Input observations ({result.input_observation_ids.length})</h3>
            <div className="mb-5 flex flex-wrap gap-1">{result.input_observation_ids.map((id) => <code key={id} className="rounded bg-white px-1.5 py-0.5 text-[11px]">{id}</code>)}
              {!result.input_observation_ids.length && <span className="text-sm text-muted">none</span>}</div>
            <h3 className="mb-2 text-sm font-semibold text-navy">Findings ({result.findings.length})</h3>
            <div className="mb-5 space-y-2">{result.findings.map((f, i) => <FindingCard key={i} f={f} />)}
              {!result.findings.length && <p className="text-sm text-muted">No findings.</p>}</div>
            {result.assessments.length > 0 && (
              <>
                <h3 className="mb-2 text-sm font-semibold text-navy">Metric assessments (used for conflict checks)</h3>
                <ul className="mb-5 text-sm">{result.assessments.map((a, i) => <li key={i}>{a.metric_code.replace(/_/g, " ")}: <b>{a.assessment}</b> {a.detail && <span className="text-muted">({a.detail})</span>}</li>)}</ul>
              </>
            )}
            {result.limitations.length > 0 && (
              <>
                <h3 className="mb-2 text-sm font-semibold text-navy">Limitations</h3>
                <ul className="mb-5 list-disc pl-5 text-sm">{result.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
              </>
            )}
            <details className="rounded-xl bg-white p-3">
              <summary className="cursor-pointer text-sm font-semibold text-navy">Structured output (JSON)</summary>
              <pre className="mt-2 max-h-96 overflow-auto text-[11px] leading-relaxed">{JSON.stringify(result.output, null, 2)}</pre>
            </details>
          </>
        )}
      </div>
    </div>
  );
}

export default function Agents() {
  const { profileId, refresh } = useApp();
  const { withAdmin } = useAdmin();
  const [params, setParams] = useSearchParams();
  const runParam = params.get("run");
  const animate = params.get("animate") === "1";
  const [agents, setAgents] = useState<AgentDescription[]>([]);
  const [run, setRun] = useState<AnalysisRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [fail, setFail] = useState("");
  const runs = useProfileData((id) => api.runs(id));

  useEffect(() => { api.agents().then((r) => setAgents(r.agents)).catch(() => undefined); }, []);
  useEffect(() => {
    setError(null);
    const load = runParam ? api.run(runParam) : api.overview(profileId).then((o) => o.latest_run);
    load.then((r) => {
      if (r && runParam && r.profile_id !== profileId) { setParams({}); return; } // profile switched
      setRun(r);
    }).catch((e) => setError(e.message));
  }, [runParam, profileId]); // eslint-disable-line react-hooks/exhaustive-deps

  const rerun = async () => {
    setBusy(true);
    try {
      const r = fail ? await withAdmin((pin) => api.startRun(profileId, [fail], pin), "Fault injection is a reviewer control.")
        : await api.startRun(profileId, []);
      refresh();
      setParams({ run: r.run_id, animate: "1" });
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  const gateDone = run?.trace.find((e) => e.agent_id === "safety_gate");
  const resultFor = (id: string): AgentResult | undefined => {
    if (id === "safety_gate" && run && gateDone) {
      return {
        run_id: run.run_id, agent_id: id, agent_name: "Safety & Evidence Gate", agent_version: gateDone.version || "",
        status: "completed", input_observation_ids: [], findings: run.assessment.findings.filter((f) => f.agent_id === "safety_gate"),
        assessments: [], limitations: [], activation_reason: "Runs after every analysis to consolidate all agent results",
        method: "Versioned rule engine, conflict detection, local evidence retrieval", error: null, requires_human_review: run.assessment.requires_human_review,
        duration_ms: gateDone.duration_ms,
        output: { monitoring_state: run.assessment.monitoring_state, coverage: run.assessment.coverage, ruleset: run.assessment.ruleset,
                  finding_counts: run.assessment.finding_counts, agent_routes: run.assessment.agent_routes },
      };
    }
    return run?.agent_results.find((r) => r.agent_id === id);
  };

  return (
    <div>
      <PageHeader title="AI agent command center" subtitle="Ten local specialist modules and a deterministic Safety & Evidence Gate. Each card reflects the real execution of the selected analysis run.">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted">Fault injection (demo)</span>
          <select value={fail} onChange={(e) => setFail(e.target.value)} className="rounded-xl border border-line bg-white px-2 py-2 text-sm">
            <option value="">None</option>
            {agents.filter((a) => !["input_sense", "safety_gate"].includes(a.agent_id)).map((a) => <option key={a.agent_id} value={a.agent_id}>Fail {a.name}</option>)}
          </select>
        </label>
        <button className="btn btn-primary" onClick={rerun} disabled={busy}><Play size={16} aria-hidden /> {busy ? "Running…" : "Re-run analysis"}</button>
      </PageHeader>
      {error && <ErrorBox message={error} />}
      {run && (
        <div className="mb-4 flex flex-wrap items-center gap-3 text-sm text-muted">
          <StatePill state={run.assessment.monitoring_state} />
          <span>Run <code className="text-xs">{run.run_id.slice(0, 8)}</code> · {fmtTime(run.completed_at)} · rules {run.ruleset_version} · {run.model_version}</span>
        </div>
      )}
      <section aria-label="Agents" className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {agents.map((a) => {
          const r = resultFor(a.agent_id);
          const isGate = a.agent_id === "safety_gate";
          const status = isGate ? (gateDone ? "completed" : "idle") : r ? r.status : "idle";
          const findings = isGate ? run?.assessment.findings.filter((f) => f.agent_id === "safety_gate").length ?? 0 : r?.findings.length ?? 0;
          return (
            <button key={a.agent_id} onClick={() => setOpen(a.agent_id)}
              className={`card flex flex-col gap-2 p-4 text-left transition-shadow hover:shadow-lg ${isGate ? "bg-navy text-white" : r ? "bg-lavender-soft" : "opacity-75"}`}>
              <div className="flex items-center justify-between gap-2">
                <span className={`flex items-center gap-2 font-semibold ${isGate ? "text-white" : "text-navy"}`}>
                  {isGate ? <ShieldCheck size={17} aria-hidden /> : <Bot size={17} aria-hidden />}{a.name}
                </span>
                <AgentStatusBadge status={status} />
              </div>
              <p className={`line-clamp-2 text-xs ${isGate ? "text-white/75" : "text-muted"}`}>{a.scope}</p>
              <div className={`mt-auto flex justify-between text-xs ${isGate ? "text-white/70" : "text-muted"}`}>
                <span>{findings} finding(s)</span><span>{r ? `${r.duration_ms.toFixed(1)} ms` : isGate && gateDone ? `${gateDone.duration_ms.toFixed(1)} ms` : "not activated"}</span>
              </div>
            </button>
          );
        })}
      </section>
      {!run && !error && <Skeleton className="h-64" />}
      {run && <RunSummary run={run} animate={animate} />}
      <Card className="mt-6" title="Recent analysis runs">
        {runs.data ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted"><tr><th className="p-2">Started</th><th className="p-2">State</th><th className="p-2">Coverage</th><th className="p-2">Rules</th><th className="p-2">Explanation</th><th className="p-2" /></tr></thead>
              <tbody>{runs.data.runs.map((r: any) => (
                <tr key={r.run_id} className="border-t border-line">
                  <td className="p-2">{fmtTime(r.started_at)}</td><td className="p-2">{r.overall_status && <StatePill state={r.overall_status} />}</td>
                  <td className="p-2">{r.coverage}</td><td className="p-2">{r.ruleset_version}</td><td className="p-2">{r.explanation_status}</td>
                  <td className="p-2"><button className="text-teal-ink hover:underline" onClick={() => setParams({ run: r.run_id })}>Open</button></td>
                </tr>))}
              </tbody>
            </table>
          </div>
        ) : <Skeleton className="h-24" />}
      </Card>
      {run && open && (
        <AgentDetail agent={open} result={resultFor(open)} desc={agents.find((a) => a.agent_id === open)} onClose={() => setOpen(null)} />
      )}
    </div>
  );
}
