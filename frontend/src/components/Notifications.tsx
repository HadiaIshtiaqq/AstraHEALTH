import { useEffect, useRef, useState } from "react";
import { Bell, Lock, TriangleAlert, X } from "lucide-react";
import { api } from "../api/client";
import type { Alert } from "../api/types";
import { fmtTime } from "../lib/format";
import { useApp } from "../state/AppContext";
import { PinDialog } from "./PinDialog";
import { SeverityBadge } from "./ui";

/**
 * Notification centre in the top bar (replaces full-width banners).
 * Safety: an open URGENT alert still shows a persistent, compact pill that cannot be dismissed
 * by the crew member — only the medical officer can acknowledge it.
 */
export function Notifications() {
  const { profileId, refreshKey, refresh } = useApp();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [open, setOpen] = useState(false);
  const [pinFor, setPinFor] = useState<Alert | null>(null);
  const [pinError, setPinError] = useState<string | null>(null);
  const seen = useRef<Set<string>>(new Set());
  const [fresh, setFresh] = useState(false);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    api.alerts(profileId, "open").then((r) => {
      if (!live) return;
      const newUrgent = r.alerts.some((a) => a.severity === "URGENT" && !seen.current.has(a.alert_id));
      r.alerts.forEach((a) => seen.current.add(a.alert_id));
      setFresh(newUrgent);
      setAlerts(r.alerts);
    }).catch(() => undefined);
    return () => { live = false; };
  }, [profileId, refreshKey]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (panel.current && !panel.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  const order = { URGENT: 0, REVIEW: 1, MONITOR: 2, INFO: 3 } as const;
  const sorted = [...alerts].sort((a, b) => order[a.severity] - order[b.severity]);
  const urgent = sorted.filter((a) => a.severity === "URGENT");
  const count = alerts.length;

  return (
    <div className="relative flex items-center gap-2" ref={panel}>
      {urgent.length > 0 && (
        <button onClick={() => setOpen(true)}
          className={`chip bg-urgent py-1.5 text-white ${fresh ? "urgent-pulse" : ""}`} aria-label="Urgent alert active: open notifications">
          <TriangleAlert size={14} aria-hidden /> URGENT · contact medical officer
        </button>
      )}
      <button onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="dialog"
        aria-label={`Notifications: ${count} open`} className="relative grid h-10 w-10 place-items-center rounded-xl border border-line bg-white hover:bg-ivory">
        <Bell size={18} className="text-navy" aria-hidden />
        {count > 0 && (
          <span className={`absolute -right-1.5 -top-1.5 grid h-5 min-w-5 place-items-center rounded-full px-1 text-[11px] font-bold text-white ${urgent.length ? "bg-urgent" : sorted[0]?.severity === "REVIEW" ? "bg-review" : "bg-monitor"}`}>
            {count}
          </span>
        )}
      </button>
      {open && (
        <div role="dialog" aria-label="Notifications"
          className="fade-in absolute right-0 top-12 z-40 w-[min(92vw,420px)] overflow-hidden rounded-2xl border border-line bg-white shadow-2xl">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <span className="font-semibold text-navy">Notifications</span>
            <button className="rounded-lg p-1 hover:bg-ivory" onClick={() => setOpen(false)} aria-label="Close"><X size={16} aria-hidden /></button>
          </div>
          <ul className="max-h-[70vh] divide-y divide-line overflow-y-auto">
            {sorted.length === 0 && <li className="px-4 py-6 text-center text-sm text-muted">No open notifications.</li>}
            {sorted.map((a) => (
              <li key={a.alert_id} className={`px-4 py-3 ${a.severity === "URGENT" ? "bg-urgent-soft" : ""}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <SeverityBadge severity={a.severity} />
                  <span className="text-sm font-semibold text-navy">{a.title}</span>
                </div>
                <p className="mt-1 text-sm text-ink">{a.reason}</p>
                <p className="mt-1 text-xs font-semibold text-navy">→ {a.next_step}</p>
                <div className="mt-2 flex items-center justify-between gap-2">
                  <span className="text-[11px] text-muted">{fmtTime(a.created_at)}{(a.occurrences ?? 1) > 1 ? ` · seen ${a.occurrences}×` : ""}</span>
                  {a.severity === "URGENT" ? (
                    <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => { setPinError(null); setPinFor(a); }}>
                      <Lock size={12} aria-hidden /> Medical officer
                    </button>
                  ) : (
                    <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => api.ack(a.alert_id).then(refresh)}>Mark as read</button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {pinFor && (
        <PinDialog title="Medical officer acknowledgement" withNote error={pinError}
          description={`Urgent alerts can only be cleared by the onboard medical officer after assessment: "${pinFor.title}".`}
          onCancel={() => setPinFor(null)}
          onSubmit={(pin, note) => api.ack(pinFor.alert_id, "medical_officer", pin, note)
            .then(() => { setPinFor(null); refresh(); })
            .catch((e) => setPinError(e.message))} />
      )}
    </div>
  );
}
