import { CircleCheck, Dumbbell, Droplets, Moon, Smile, Square, Trophy, Undo2, ClipboardCheck } from "lucide-react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { Card, ErrorBox, PageHeader, Skeleton } from "../components/ui";
import { fmtDate, fmtTime } from "../lib/format";
import { useProfileData } from "../state/AppContext";

const CAT_ICON: Record<string, typeof Dumbbell> = { exercise: Dumbbell, nutrition: Droplets, sleep: Moon, wellbeing: Smile, checkin: ClipboardCheck };
const CAT_STYLE: Record<string, string> = {
  exercise: "bg-mint text-teal-ink", nutrition: "bg-sunshine/60 text-monitor", sleep: "bg-sky/60 text-navy",
  wellbeing: "bg-lavender/70 text-plum", checkin: "bg-coral/25 text-coral-ink",
};

export default function Countermeasures() {
  const { data, error, loading, reload } = useProfileData((id) => api.tasks(id, 14));
  if (error) return <ErrorBox message={error} />;
  if (loading && !data) return <Skeleton className="h-96" />;
  if (!data) return null;
  const done = data.today.filter((t) => t.completed_at).length;
  const pct = data.today.length ? Math.round((done / data.today.length) * 100) : 0;
  const chart = data.history.map((h) => ({ day: fmtDate(h.date), pct: h.total ? Math.round((h.completed / h.total) * 100) : 0, ...h }));
  return (
    <div>
      <PageHeader title="Your routine" subtitle="Your exercise, nutrition, sleep and wellbeing routine. A task is only marked complete when you mark it — completion is never inferred." />
      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <Card title={`Today's routine · ${done}/${data.today.length}`}>
          <div className="mb-4 h-2 overflow-hidden rounded-full bg-ivory-2" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Routine completion">
            <div className="h-full rounded-full bg-teal-ink transition-all" style={{ width: `${pct}%` }} />
          </div>
          <ul className="space-y-2">
            {data.today.map((t) => {
              const Icon = CAT_ICON[t.category] || Square;
              return (
                <li key={t.task_id} className={`flex items-center gap-3 rounded-2xl border p-3 ${t.completed_at ? "border-ok/30 bg-ok-soft/60" : "border-line bg-white"}`}>
                  <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${CAT_STYLE[t.category] || "bg-ivory-2"}`}><Icon size={18} aria-hidden /></span>
                  <div className="min-w-0 flex-1">
                    <div className={`font-semibold text-navy ${t.completed_at ? "line-through decoration-ok/60" : ""}`}>{t.title}</div>
                    <div className="text-xs text-muted">{t.completed_at ? `Completed ${fmtTime(t.completed_at)}` : t.description}</div>
                  </div>
                  {!t.completed_at && t.title.endsWith("(care plan)") && (
                    <button className="btn btn-ghost px-2 text-xs" aria-label={`Remove ${t.title}`} onClick={() => api.removeTask(t.task_id).then(reload)}>Remove</button>
                  )}
                  {t.completed_at ? (
                    <button className="btn btn-ghost text-xs" onClick={() => api.reopenTask(t.task_id).then(reload)}><Undo2 size={14} aria-hidden /> Undo</button>
                  ) : (
                    <button className="btn btn-primary text-xs" onClick={() => api.completeTask(t.task_id).then(reload)}><CircleCheck size={14} aria-hidden /> Mark complete</button>
                  )}
                </li>
              );
            })}
          </ul>
        </Card>
        <div className="space-y-6">
          <Card title="Mission wellness achievements" icon={<Trophy size={16} aria-hidden />}>
            <div className="flex items-center gap-4">
              <div className="grid h-20 w-20 place-items-center rounded-full bg-sunshine/50 text-3xl font-bold text-navy">{data.checkin_streak}</div>
              <div><div className="font-semibold text-navy">Day check-in streak</div>
                <p className="text-xs text-muted">Consistency is rewarded. Reporting a symptom or an alert never breaks a streak — hiding one is never rewarded.</p></div>
            </div>
          </Card>
          <Card title="Routine completion — last 14 days">
            <div className="h-48" aria-hidden>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chart} margin={{ left: -20, right: 4 }} accessibilityLayer={false} tabIndex={-1}>
                  <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#5b6b80" }} interval={1} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "#5b6b80" }} unit="%" />
                  <Tooltip formatter={(v) => [`${v}%`, "Completed"]} />
                  <Bar dataKey="pct" fill="#20B8AD" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 text-xs text-muted">
              {chart.map((c) => `${c.day}: ${c.completed}/${c.total}`).join(" · ")}
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
