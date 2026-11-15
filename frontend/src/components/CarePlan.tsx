import { useState } from "react";
import { Link } from "react-router-dom";
import { CalendarPlus, CircleCheck, HeartPulse, Target, TriangleAlert } from "lucide-react";
import { api } from "../api/client";
import { useApp, useProfileData } from "../state/AppContext";
import { SeverityBadge, Skeleton } from "./ui";

export interface CarePlanItem {
  plan_id: string; title: string; area: string; severity: "MONITOR" | "REVIEW" | "URGENT" | "INFO"; why: string;
  steps: string[]; goal: string; evidence_chunk: string; linked_findings: string[];
  task: { title: string; category: string; days: number }; needs_medical_officer: boolean;
  progress?: { status: "achieved" | "on_track" | "not_yet" | "no_data"; detail: string };
}
export interface CarePlanData { items: CarePlanItem[]; message: string; state: string; version?: string }

export function CarePlanItemCard({ item, compact = false }: { item: CarePlanItem; compact?: boolean }) {
  const [added, setAdded] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { profileId } = useApp();
  return (
    <article className="rounded-2xl border border-line bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={item.severity} />
        <span className="text-xs font-semibold uppercase tracking-wide text-muted">{item.area}</span>
      </div>
      <h3 className="mt-2 text-base font-semibold text-navy">{item.title}</h3>
      {!compact && <p className="mt-1 text-sm text-muted">{item.why}</p>}
      <ol className="mt-3 space-y-1.5">
        {(compact ? item.steps.slice(0, 3) : item.steps).map((s, i) => (
          <li key={i} className="flex gap-2 text-sm text-ink">
            <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-mint text-[11px] font-bold text-teal-ink">{i + 1}</span>{s}
          </li>
        ))}
      </ol>
      <p className="mt-3 flex items-start gap-2 rounded-xl bg-ivory p-2.5 text-sm text-navy">
        <Target size={16} className="mt-0.5 shrink-0 text-teal-ink" aria-hidden /> <span><b>Goal:</b> {item.goal}</span>
      </p>
      {item.progress && (
        <p className={`mt-2 rounded-xl px-2.5 py-1.5 text-xs font-semibold ${
          item.progress.status === "achieved" ? "bg-ok-soft text-ok" : item.progress.status === "on_track" ? "bg-sky/40 text-navy"
          : item.progress.status === "not_yet" ? "bg-monitor-soft text-monitor" : "bg-ivory-2 text-muted"}`}>
          Progress: {{ achieved: "goal reached", on_track: "on track", not_yet: "not yet", no_data: "waiting for data" }[item.progress.status]}
          <span className="font-normal"> — {item.progress.detail}</span>
        </p>
      )}
      {item.needs_medical_officer && (
        <p className="mt-2 flex items-center gap-1.5 text-xs font-semibold text-review">
          <TriangleAlert size={13} aria-hidden /> Also share with the medical officer — qualified review is recommended.
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {added === null ? (
          <button className="btn btn-primary text-xs" onClick={() => api.adoptPlan(profileId, item.plan_id)
            .then((r) => setAdded(r.created)).catch((e) => setError(e.message))}>
            <CalendarPlus size={14} aria-hidden /> Add “{item.task.title}” to my routine ({item.task.days} day{item.task.days > 1 ? "s" : ""})
          </button>
        ) : (
          <span className="flex items-center gap-1.5 text-sm font-semibold text-ok"><CircleCheck size={15} aria-hidden />
            {added ? `Added to your routine for ${added} day(s)` : "Already in your routine"} · <Link className="underline" to="/countermeasures">view</Link></span>
        )}
        <span className="text-[11px] text-muted">Source: local library {item.evidence_chunk}</span>
      </div>
      {error && <p role="alert" className="mt-2 text-xs text-urgent">{error}</p>}
    </article>
  );
}

export function CarePlanPanel({ compact = false, limit }: { compact?: boolean; limit?: number }) {
  const { data, loading } = useProfileData<CarePlanData>((id) => api.carePlan(id));
  if (loading && !data) return <Skeleton className="h-40" />;
  if (!data) return null;
  if (data.state === "URGENT") {
    return (
      <div className="rounded-2xl border border-urgent bg-urgent-soft p-4 text-sm text-urgent">
        <b className="flex items-center gap-2"><TriangleAlert size={16} aria-hidden /> No self-care plan during an urgent alert</b>
        <p className="mt-1">{data.message}</p>
      </div>
    );
  }
  const items = limit ? data.items.slice(0, limit) : data.items;
  return (
    <div className="space-y-3">
      <p className="flex items-start gap-2 text-sm text-muted"><HeartPulse size={16} className="mt-0.5 shrink-0 text-teal-ink" aria-hidden />{data.message}</p>
      {items.map((i) => <CarePlanItemCard key={i.plan_id} item={i} compact={compact} />)}
      {limit && data.items.length > limit && (
        <Link to="/care-plan" className="text-sm font-semibold text-teal-ink hover:underline">See all {data.items.length} recommendations →</Link>
      )}
    </div>
  );
}
