import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  BookOpen, ChevronRight, CircleCheck, CircleDashed, CircleX, Cpu, LoaderCircle, RefreshCw, ShieldCheck, Sparkles,
  TriangleAlert,
} from "lucide-react";
import { api } from "../api/client";
import type { AnalysisRun, Assessment, Explanation, Finding, KnowledgeRef, TraceEvent } from "../api/types";
import { AGENT_LABELS, STATEMENT_LABEL } from "../lib/format";
import { CarePlanPanel } from "./CarePlan";
import { SeverityBadge, STATE_STYLE } from "./ui";
import { AgentConstellation } from "./space";

export function StateBanner({ assessment, compact = false }: { assessment: Assessment; compact?: boolean }) {
  const s = STATE_STYLE[assessment.monitoring_state];
  return (
    <div className={`flex items-start gap-3 rounded-2xl border p-4 ${s.cls}`}>
      <s.Icon size={compact ? 22 : 28} className="mt-0.5 shrink-0" aria-hidden />
      <div className="min-w-0">
        <div className="text-xs font-bold tracking-[0.12em]">MONITORING STATE · {s.short}</div>
        <div className={`${compact ? "text-base" : "text-lg"} font-semibold`}>{assessment.state_label}</div>
        <p className="mt-0.5 text-sm">{assessment.headline}</p>
        {assessment.requires_human_review && (
          <p className="mt-1 text-sm font-semibold">Human review: share with the onboard medical officer.</p>
        )}
      </div>
    </div>
  );
}

export function EvidencePanel({ refs, status }: { refs: KnowledgeRef[]; status: Finding["evidence_status"] }) {
  if (status === "unavailable" || (status === "found" && !refs.length)) {
    return <p className="text-xs text-muted">Evidence: no sufficiently relevant passage in the approved local library (no citation shown).</p>;
  }
  if (!refs.length) return null;
  return (
    <div className="space-y-2">
      {refs.map((r) => (
        <figure key={r.chunk_id} className="rounded-xl border border-line bg-ivory p-3">
          <figcaption className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
            <BookOpen size={13} aria-hidden className="text-teal-ink" />
            <span className="font-semibold text-navy">{r.title}</span>
            <span>· {r.section}</span>
            <span>· {r.publisher}, v{r.version} ({r.publication_date})</span>
            <code className="rounded bg-white px-1 text-[11px]">{r.chunk_id}</code>
          </figcaption>
          <blockquote className="text-sm leading-relaxed text-ink">“{r.passage}”</blockquote>
          <p className="mt-1 text-[11px] text-muted">{r.relevance_note}</p>
        </figure>
      ))}
    </div>
  );
}

const CERTAINTY: Record<string, [string, string]> = {
  strong: ["Strong evidence", "bg-ok-soft text-ok"], moderate: ["Moderate evidence", "bg-sky/50 text-navy"],
  limited: ["Limited evidence", "bg-unknown-soft text-unknown"], "self-reported": ["Self-reported", "bg-lavender-soft text-plum"],
};
export function CertaintyBadge({ level }: { level: string }) {
  const [label, cls] = CERTAINTY[level] || [level, "bg-ivory-2 text-muted"];
  return <span className={`chip ${cls}`} title="Certainty is graded from history length, persistence, corroboration and data quality">{label}</span>;
}

export function FindingCard({ f, defaultOpen = false }: { f: Finding; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <article className="rounded-2xl border border-line bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={f.severity} />
        <span className="text-xs font-semibold text-muted">{AGENT_LABELS[f.agent_id || ""] || f.agent_id}</span>
        <span className="text-xs text-muted">· {STATEMENT_LABEL[f.statement_type] || f.statement_type}</span>
        {f.rule_ids.length > 0 && <span className="text-xs text-muted">· rule {f.rule_ids.join(", ")}</span>}
        {f.certainty && <CertaintyBadge level={f.certainty} />}
      </div>
      <p className="mt-2 text-sm text-ink">{f.summary}</p>
      {f.next_steps[0] && <p className="mt-1.5 text-sm font-medium text-navy">→ {f.next_steps[0]}</p>}
      <button onClick={() => setOpen(!open)} aria-expanded={open}
        className="mt-2 flex items-center gap-1 text-xs font-semibold text-teal-ink hover:underline">
        <ChevronRight size={14} className={`transition-transform ${open ? "rotate-90" : ""}`} aria-hidden />
        Why? Evidence, sources & limitations
      </button>
      {open && (
        <div className="fade-in mt-3 space-y-3">
          {f.certainty && f.certainty_reasons && f.certainty_reasons.length > 0 && (
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-muted">How sure is this? — {f.certainty}</div>
              <p className="text-[11px] text-muted">Rule-based grade from the reasons below; not a calibrated probability.</p>
              <ul className="mt-1 list-disc pl-5 text-sm text-ink">{f.certainty_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            </div>
          )}
          <EvidencePanel refs={f.knowledge_references} status={f.evidence_status} />
          {f.limitations.length > 0 && (
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-muted">Limitations</div>
              <ul className="mt-1 list-disc pl-5 text-sm text-ink">{f.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
            </div>
          )}
          <div className="text-xs text-muted">
            Source observations: {f.evidence_observation_ids.length
              ? f.evidence_observation_ids.map((id) => <code key={id} className="mr-1 rounded bg-ivory-2 px-1">{id}</code>)
              : "none (structural finding)"}
          </div>
        </div>
      )}
    </article>
  );
}

const STAGE_ICON: Record<string, typeof Cpu> = { safety: ShieldCheck };

/** Execution timeline populated from the real run trace (order, status, durations). */
export function AgentPipeline({ trace, animate = false }: { trace: TraceEvent[]; animate?: boolean }) {
  const [visible, setVisible] = useState(animate ? 0 : trace.length);
  useEffect(() => {
    if (!animate) { setVisible(trace.length); return; }
    setVisible(0);
    let i = 0;
    const t = setInterval(() => { i += 1; setVisible(i); if (i >= trace.length) clearInterval(t); }, 260);
    return () => clearInterval(t);
  }, [trace, animate]);
  return (
    <ol className="relative space-y-1" aria-label="Agent execution timeline">
      {trace.slice(0, visible).map((e, i) => {
        const Icon = e.status === "failed" ? CircleX : e.status === "insufficient_data" ? CircleDashed
          : e.status === "review" ? TriangleAlert : STAGE_ICON[e.stage] || CircleCheck;
        const color = e.status === "failed" ? "text-urgent" : e.status === "insufficient_data" ? "text-unknown"
          : e.status === "review" ? "text-review" : "text-ok";
        return (
          <li key={`${e.agent_id}-${i}`} className="fade-in flex gap-3 rounded-xl px-2 py-2 hover:bg-ivory">
            <div className="flex flex-col items-center">
              <Icon size={20} className={color} aria-hidden />
              {i < trace.length - 1 && <span className="mt-1 w-px flex-1 bg-line" />}
            </div>
            <div className="min-w-0 flex-1 pb-1">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-semibold text-navy">{e.name}</span>
                <span className="text-xs uppercase tracking-wide text-muted">{e.stage}</span>
                <span className="text-xs text-muted">· {e.status.replace("_", " ")}</span>
                <span className="ml-auto text-xs tabular-nums text-muted">{e.duration_ms.toFixed(1)} ms</span>
              </div>
              <p className="text-sm text-ink/90">{e.summary}</p>
            </div>
          </li>
        );
      })}
      {visible < trace.length && (
        <li className="flex items-center gap-2 px-2 py-2 text-sm text-muted">
          <LoaderCircle size={16} className="animate-spin" aria-hidden /> Replaying recorded execution…
        </li>
      )}
    </ol>
  );
}

/** Plain-language explanation; polls while the local LLM is drafting it. */
export function ExplanationPanel({ run }: { run: AnalysisRun }) {
  const [exp, setExp] = useState<Explanation | null>(run.explanation);
  const [status, setStatus] = useState(run.explanation_status);
  useEffect(() => { setExp(run.explanation); setStatus(run.explanation_status); }, [run]);
  const [askError, setAskError] = useState<string | null>(null);
  useEffect(() => {
    if (!["pending", "running"].includes(status)) return;
    let polls = 0;
    const t = setInterval(() => {
      polls += 1;
      if (polls > 75) { clearInterval(t); setStatus("unavailable"); return; } // stop after ~5 min
      api.run(run.run_id).then((r) => { setExp(r.explanation); setStatus(r.explanation_status); }).catch(() => undefined);
    }, 4000);
    return () => clearInterval(t);
  }, [status, run.run_id]);

  const drafting = ["pending", "running"].includes(status);
  const label = status === "generated" ? `Local LLM · ${exp?.model ?? ""}${exp?.latency_ms ? ` · ${(exp.latency_ms / 1000).toFixed(0)} s` : ""}`
    : status === "disabled" ? "Deterministic template (LLM disabled)"
    : status === "unavailable" ? "Deterministic template — AI explanation unavailable"
    : status === "fallback" ? "Deterministic template — LLM output failed validation"
    : drafting ? "Deterministic template · local LLM drafting…" : "Deterministic template";
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className={`chip ${status === "generated" ? "bg-lavender text-plum" : "bg-ivory-2 text-muted"}`}>
          {drafting ? <LoaderCircle size={12} className="animate-spin" aria-hidden /> : <Sparkles size={12} aria-hidden />} {label}
        </span>
        {!drafting && (
          <button className="text-xs font-semibold text-teal-ink hover:underline"
            onClick={() => { setAskError(null); api.explain(run.run_id).then(() => setStatus("pending")).catch((e) => setAskError(e.message)); }}>
            <RefreshCw size={12} className="mr-1 inline" aria-hidden />Ask local LLM again
          </button>
        )}
      </div>
      {askError && <p role="alert" className="mb-2 text-xs text-monitor">{askError}</p>}
      <ul className="space-y-2">
        {(exp?.statements || []).map((s, i) => (
          <li key={i} className="flex gap-3 text-sm">
            <span className={`chip mt-0.5 h-fit shrink-0 ${s.type === "recommendation" ? "bg-mint text-teal-ink" : s.type === "limitation" ? "bg-sunshine/60 text-monitor" : "bg-sky/50 text-navy"}`}>
              {STATEMENT_LABEL[s.type]}
            </span>
            <span className="text-ink">{s.text}{s.citations.length > 0 && <code className="ml-1 text-[11px] text-muted">[{s.citations.join(", ")}]</code>}</span>
          </li>
        ))}
      </ul>
      {exp?.rejected && exp.rejected.length > 0 && (
        <details className="mt-3 text-xs text-muted">
          <summary className="cursor-pointer font-semibold">{exp.rejected.length} generated statement(s) removed by the safety guard</summary>
          <ul className="mt-1 list-disc pl-5">{exp.rejected.map((r, i) => <li key={i}><b>{r.reason}</b>: {r.text}</li>)}</ul>
        </details>
      )}
      <p className="mt-3 text-[11px] text-muted">The explanation never changes the monitoring state, which is set by versioned deterministic rules ({run.ruleset_version}).</p>
    </div>
  );
}

export function RunSummary({ run, animate = false }: { run: AnalysisRun; animate?: boolean }) {
  const a = run.assessment;
  const flagged = a.findings.filter((f) => f.severity !== "INFO");
  const info = a.findings.filter((f) => f.severity === "INFO" && ["BASELINE_UNAVAILABLE", "MISSING_CORE_MEASUREMENTS", "MEASUREMENT_CONTEXT_MISSING", "AGENT_FAILED", "ANOMALY_NONE"].includes(f.code));
  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_1.15fr]">
      <section className="card p-5">
        <h2 className="mb-3 flex items-center gap-2 font-semibold text-navy"><Cpu size={18} aria-hidden /> Live intelligence pipeline</h2>
        <div className="mb-4"><AgentConstellation trace={run.trace} animate={animate} /></div>
        <AgentPipeline trace={run.trace} animate={animate} />
        <Link to={`/agents?run=${run.run_id}`} className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-teal-ink hover:underline">
          Technical trace (for reviewers) <ChevronRight size={14} aria-hidden />
        </Link>
      </section>
      <div className="space-y-4">
        <StateBanner assessment={a} />
        {a.next_actions.length > 0 && (
          <section className="card p-5">
            <h2 className="mb-2 font-semibold text-navy">What to do next</h2>
            <ol className="space-y-2">
              {a.next_actions.slice(0, 5).map((n, i) => (
                <li key={i} className="flex items-start gap-2 text-sm"><SeverityBadge severity={n.severity} /> <span>{n.text}</span></li>
              ))}
            </ol>
          </section>
        )}
        <section className="card p-5">
          <h2 className="mb-3 font-semibold text-navy">How to improve this</h2>
          <CarePlanPanel compact limit={3} />
        </section>
        <section className="card p-5">
          <h2 className="mb-2 font-semibold text-navy">Explanation</h2>
          <ExplanationPanel run={run} />
        </section>
        <section className="space-y-3">
          <h2 className="font-semibold text-navy">Findings ({flagged.length})</h2>
          {flagged.map((f, i) => <FindingCard key={`${f.code}-${i}`} f={f} />)}
          {info.map((f, i) => <FindingCard key={`i-${f.code}-${i}`} f={f} />)}
        </section>
      </div>
    </div>
  );
}
