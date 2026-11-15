import { useEffect, useState } from "react";
import { BookOpen, Cpu, Database, ShieldCheck, TriangleAlert, WifiOff } from "lucide-react";
import { api } from "../api/client";
import type { Profile } from "../api/types";
import { PinDialog } from "../components/PinDialog";
import { Card, ErrorBox, PageHeader, Skeleton } from "../components/ui";
import { fmtTime } from "../lib/format";
import { useAdmin } from "../state/AdminContext";
import { useApp, useProfileData } from "../state/AppContext";

function Row({ label, ok, detail }: { label: string; ok: boolean | null; detail: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-t border-line py-2.5 first:border-0">
      <span className="text-sm font-medium text-navy">{label}</span>
      <span className={`text-right text-sm ${ok === null ? "text-muted" : ok ? "text-ok" : "text-monitor"}`}>
        {ok === null ? "" : ok ? "● " : "○ "}{detail}
      </span>
    </div>
  );
}

export default function Settings() {
  const { health, refresh, profileId } = useApp();
  const profile = useProfileData<Profile>((id) => api.profile(id));
  const [form, setForm] = useState<Record<string, string>>({});
  const [rules, setRules] = useState<any | null>(null);
  const [docs, setDocs] = useState<any[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [showAudit, setShowAudit] = useState(false);
  const [chain, setChain] = useState<{ intact: boolean; checked: number } | null>(null);
  const { withAdmin } = useAdmin();

  useEffect(() => {
    api.rules().then(setRules).catch(() => undefined);
    api.documents().then((d) => setDocs(d.documents)).catch(() => undefined);
    if (showAudit) withAdmin((pin) => api.audit(pin), "The audit log is visible to the admin only.").then((a) => { setAudit(a.events); setChain(a.chain); }).catch(() => undefined);
  }, [msg, showAudit]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (profile.data) setForm({
      display_name: profile.data.display_name,
      exercise_target_min: String(profile.data.settings.exercise_target_min ?? 120),
      resistance_sessions_per_week: String(profile.data.settings.resistance_sessions_per_week ?? 6),
    });
  }, [profile.data]);

  const save = async () => {
    setError(null);
    try {
      await api.updateProfile(profileId, { display_name: form.display_name, settings: {
        exercise_target_min: Number(form.exercise_target_min), resistance_sessions_per_week: Number(form.resistance_sessions_per_week) } });
      setMsg(`Saved ${new Date().toLocaleTimeString()} (change audited)`); refresh();
    } catch (e: any) { setError(e.message); }
  };
  const [pinError, setPinError] = useState<string | null>(null);
  const reset = async (pin: string) => {
    setPinError(null);
    try { await api.resetProfile(profileId, pin); setConfirmReset(false); setMsg("Demo profile reset to its synthetic scenario"); refresh(); }
    catch (e: any) { setPinError(e.message); }
  };

  return (
    <div>
      <PageHeader title="Settings & local runtime" subtitle="Profile configuration, the local runtime status and the versioned rule set. Changes are written to the audit log." />
      {error && <div className="mb-4"><ErrorBox message={error} /></div>}
      {health?.access_control?.initial_secrets_file_present && (
        <div role="status" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-review/40 bg-review-soft p-4 text-sm text-review">
          <span><b>Initial PINs are still stored in plain text</b> in <code>backend/data/INITIAL_SECRETS.txt</code>. Note them down, then delete the file.</span>
          <button className="btn btn-primary text-xs" onClick={() => withAdmin((pin) => api.deleteInitialSecrets(pin),
            "Entering the admin PIN proves you have noted it. The file is then deleted.")
            .then(() => { setMsg("Initial secrets file deleted"); refresh(); }).catch((e) => setError(e.message))}>
            I have noted them: delete the file
          </button>
        </div>
      )}
      <div className="grid gap-6 xl:grid-cols-2">
        <Card title={profile.data?.is_synthetic ? "Crew profile (synthetic demo)" : "Crew profile"}>
          {!profile.data ? <Skeleton className="h-40" /> : (
            <div className="space-y-4">
              <label className="block text-sm"><span className="font-medium text-navy">Display alias</span>
                <input className="mt-1 w-full rounded-xl border border-line px-3 py-2" value={form.display_name || ""} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></label>
              <div className="grid grid-cols-2 gap-3">
                <label className="text-sm"><span className="font-medium text-navy">Exercise plan (min/day)</span>
                  <input inputMode="numeric" className="mt-1 w-full rounded-xl border border-line px-3 py-2" value={form.exercise_target_min || ""} onChange={(e) => setForm({ ...form, exercise_target_min: e.target.value })} /></label>
                <label className="text-sm"><span className="font-medium text-navy">Resistance sessions / week</span>
                  <input inputMode="numeric" className="mt-1 w-full rounded-xl border border-line px-3 py-2" value={form.resistance_sessions_per_week || ""} onChange={(e) => setForm({ ...form, resistance_sessions_per_week: e.target.value })} /></label>
              </div>
              <p className="text-xs text-muted">Plan values come from the simulated mission countermeasure plan. Clinical thresholds are not editable here: they require a sourced, versioned rule set.</p>
              <div className="flex flex-wrap items-center gap-2">
                <button className="btn btn-primary" onClick={save}>Save profile</button>
                <button className="btn btn-ghost" onClick={() => setConfirmReset(true)}><TriangleAlert size={14} aria-hidden /> Reset demo data…</button>
                {confirmReset && (
                  <PinDialog title="Reset demo profile" error={pinError}
                    description="Deletes and regenerates this profile's synthetic data. Requires the admin PIN."
                    onCancel={() => setConfirmReset(false)} onSubmit={(pin) => reset(pin)} />
                )}
              </div>
              {msg && <p className="text-sm text-ok" role="status">{msg}</p>}
            </div>
          )}
        </Card>
        <Card title="Local runtime status" icon={<Cpu size={16} aria-hidden />}>
          {!health ? <Skeleton className="h-40" /> : (
            <div>
              <Row label="Offline network guard" ok={health.offline.guard_installed} detail={health.offline.guard_installed ? `On · ${health.offline.blocked_attempts} external attempt(s) blocked` : "Off (external network allowed)"} />
              <Row label="Database" ok={health.database.ok} detail={`${health.database.engine} · ${health.database.size_kb} KB`} />
              <Row label="Local LLM (optional)" ok={health.llm.reachable && health.llm.model_available}
                detail={health.llm.reachable && health.llm.model_available ? `${health.llm.provider} · ${health.llm.model} · prompt ${health.llm.prompt_version}` : health.llm.detail || "unavailable — deterministic explanations used"} />
              <Row label="Knowledge index" ok={health.knowledge_index.ready} detail={`${health.knowledge_index.documents} documents · ${health.knowledge_index.chunks} passages · ${health.knowledge_index.index_version}`} />
              <Row label="Rule set" ok={null} detail={`${health.ruleset.version} · ${health.ruleset.rules} rules · ${health.ruleset.status}`} />
              <Row label="Anomaly model" ok={null} detail={`${health.anomaly_model.name} ${health.anomaly_model.version}`} />
              <Row label="Server time" ok={null} detail={fmtTime(health.server_time)} />
              <p className="mt-3 flex items-center gap-2 text-xs text-muted"><WifiOff size={14} aria-hidden /> Health analysis works with the LLM stopped; it only drafts explanations.</p>
            </div>
          )}
        </Card>
        <Card title={`Versioned rule set ${rules ? `· ${rules.version}` : ""}`} icon={<ShieldCheck size={16} aria-hidden />}>
          {!rules ? <Skeleton className="h-40" /> : (
            <>
              <p className="mb-3 rounded-xl bg-monitor-soft p-3 text-xs font-semibold text-monitor">{rules.status}. {rules.notes}</p>
              <div className="max-h-80 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-white text-left text-muted"><tr><th className="p-1.5">Rule</th><th className="p-1.5">Severity</th><th className="p-1.5">Description</th></tr></thead>
                  <tbody>{rules.rules.map((r: any) => (
                    <tr key={r.rule_id} className="border-t border-line"><td className="p-1.5 font-mono">{r.rule_id}</td><td className="p-1.5">{r.severity}</td><td className="p-1.5">{r.description}</td></tr>))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Card>
        <Card title="Local knowledge library" icon={<BookOpen size={16} aria-hidden />}>
          <ul className="space-y-2 text-sm">{docs.map((d) => (
            <li key={d.document_id} className="flex justify-between gap-3 border-t border-line pt-2 first:border-0 first:pt-0">
              <span><b className="text-navy">{d.title}</b><span className="block text-xs text-muted">{d.publisher} · see {d.related_reference}</span></span>
              <code className="text-[11px] text-muted">{d.checksum}</code>
            </li>))}
          </ul>
        </Card>
        <Card title="Audit log (latest)" icon={<Database size={16} aria-hidden />} className="xl:col-span-2">
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-white text-left text-muted"><tr><th className="p-1.5">Time</th><th className="p-1.5">Role</th><th className="p-1.5">Action</th><th className="p-1.5">Object</th><th className="p-1.5">Metadata</th></tr></thead>
              <tbody>{audit.map((e) => (
                <tr key={e.event_id} className="border-t border-line"><td className="p-1.5 whitespace-nowrap">{fmtTime(e.timestamp)}</td><td className="p-1.5">{e.actor_role}</td>
                  <td className="p-1.5 font-mono">{e.action}</td><td className="p-1.5 font-mono">{e.object_id?.slice(0, 18)}</td><td className="p-1.5 text-muted">{e.metadata}</td></tr>))}
              </tbody>
            </table>
          </div>
          {!showAudit && <button className="btn btn-ghost mt-2" onClick={() => setShowAudit(true)}>Show audit log (admin)</button>}
          {chain && <p className={`mt-2 text-xs font-semibold ${chain.intact ? "text-ok" : "text-urgent"}`}>Hash chain {chain.intact ? "intact" : "BROKEN — records were altered"} ({chain.checked} events checked)</p>}
          <p className="mt-2 text-xs text-muted">Free-text health content is never written to the audit log. Entries are hash-chained, so edits are detectable.</p>
        </Card>
      </div>
    </div>
  );
}
