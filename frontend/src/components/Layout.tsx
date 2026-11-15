import { Suspense, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import {
  ChartLine, ClipboardCheck, Dumbbell, FileText, HeartPulse, LayoutDashboard, Lock, PersonStanding,
  WifiOff,
} from "lucide-react";
import { api } from "../api/client";
import { useApp } from "../state/AppContext";
import { fmtTime } from "../lib/format";
import { Notifications } from "./Notifications";
import { BrandMark, IntroSplash, Starfield } from "./space";

// Crew-facing navigation only. Technical views (agent trace, system status) live behind the footer links.
const NAV = [
  { to: "/", label: "Overview", Icon: LayoutDashboard },
  { to: "/check-in", label: "Check-in", Icon: ClipboardCheck },
  { to: "/care-plan", label: "Care Plan", Icon: HeartPulse },
  { to: "/trends", label: "Health Trends", Icon: ChartLine },
  { to: "/digital-twin", label: "Digital Twin", Icon: PersonStanding },
  { to: "/countermeasures", label: "Routine", Icon: Dumbbell },
  { to: "/reports", label: "Reports", Icon: FileText },
];

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <BrandMark />
      <div className="leading-tight">
        <div className="text-[15px] font-bold tracking-wide text-white">ASTRAHEALTH</div>
        <div className="text-[10.5px] font-medium tracking-[0.14em] text-mint/80">MISSION HEALTH INTELLIGENCE</div>
      </div>
    </div>
  );
}

function Sidebar() {
  const { health } = useApp();
  const hosted = health?.mode === "hosted_demo";
  return (
    <aside className="space-bg sticky top-0 hidden h-screen w-64 shrink-0 flex-col gap-8 overflow-hidden p-5 text-white lg:flex">
      <Starfield density={0.0005} />
      <div className="relative z-10"><Brand /></div>
      <nav aria-label="Main" className="relative z-10 flex flex-col gap-1">
        {NAV.map(({ to, label, Icon }) => (
          <NavLink key={to} to={to} end={to === "/"}
            className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
              isActive ? "bg-white/12 text-white ring-1 ring-teal/50 shadow-[0_0_18px_rgb(32_184_173/0.25)]" : "text-white/75 hover:bg-white/7 hover:text-white"}`}>
            <Icon size={18} aria-hidden /> {label}
          </NavLink>
        ))}
      </nav>
      <div className="relative z-10 mt-auto rounded-2xl bg-white/7 p-4 backdrop-blur-sm text-xs leading-relaxed text-white/75 ring-1 ring-white/10">
        <div className="mb-1 flex items-center gap-1.5 font-semibold text-white"><Lock size={13} aria-hidden /> {hosted ? "Public demo" : "Your data stays here"}</div>
        {hosted ? "Online demo with synthetic crew only. The mission version runs fully offline with a local AI model. Do not enter real health data."
          : "All analysis runs on this device."} Prototype only — not a medical device.
      </div>
    </aside>
  );
}

function MobileNav() {
  return (
    <nav aria-label="Main" className="scrollbar-thin space-bg flex gap-1 overflow-x-auto px-3 py-2 lg:hidden">
      {NAV.map(({ to, label, Icon }) => (
        <NavLink key={to} to={to} end={to === "/"}
          className={({ isActive }) => `flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium ${
            isActive ? "bg-white/15 text-white" : "text-white/70"}`}>
          <Icon size={15} aria-hidden /> {label}
        </NavLink>
      ))}
    </nav>
  );
}

function Clock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 30000); return () => clearInterval(t); }, []);
  return <span className="tabular-nums">{fmtTime(now.toISOString())}</span>;
}

function TopBar() {
  const { profiles, profileId, setProfileId, profile, health, healthError, refresh } = useApp();
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const create = () => api.createProfile(newName.trim(), Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC")
    .then((p) => { setAdding(false); setNewName(""); refresh(); setProfileId(p.profile_id); })
    .catch((e) => setAddError(e.message));
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-white/85 backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
        <div className="lg:hidden"><span className="font-bold text-navy">ASTRAHEALTH</span></div>
        {profile && (
          <div className="flex items-baseline gap-2 text-sm">
            <span className="font-semibold text-navy">{profile.mission_name}</span>
            {profile.mission_day != null && (
              <span className="rounded-lg bg-navy px-2 py-0.5 text-xs font-bold tracking-wider text-white">
                DAY {String(profile.mission_day).padStart(3, "0")}
              </span>
            )}
          </div>
        )}
        <span className={`chip ${healthError ? "bg-urgent-soft text-urgent" : "bg-mint-soft text-teal-ink"}`}
          title={healthError || `${health?.offline.blocked_attempts ?? 0} external connection attempts blocked`}>
          <WifiOff size={13} aria-hidden /> {healthError ? "SERVICE UNREACHABLE" : health?.mode === "hosted_demo" ? "HOSTED DEMO" : "LOCAL · OFFLINE"}
        </span>
        <div className="ml-auto flex items-center gap-3 text-sm text-muted">
          <span className="hidden xl:inline"><Clock /></span>
          <label className="flex items-center gap-2">
            <span className="sr-only">Crew profile</span>
            <select value={profileId} onChange={(e) => e.target.value === "__new" ? setAdding(true) : setProfileId(e.target.value)}
              className="max-w-52 rounded-xl border border-line bg-white px-3 py-2 text-sm font-medium text-navy">
              {profiles.map((p) => <option key={p.profile_id} value={p.profile_id}>{p.display_name}{p.is_synthetic ? " (demo)" : ""}</option>)}
              <option value="__new">+ Add crew member…</option>
            </select>
          </label>
          <Notifications />
        </div>
      </div>
      {adding && (
        <div role="dialog" aria-modal="true" aria-labelledby="add-crew" className="fixed inset-0 z-50 grid place-items-center bg-navy/40 p-4">
          <form className="card w-full max-w-sm p-6" onSubmit={(e) => { e.preventDefault(); create(); }}>
            <h2 id="add-crew" className="text-lg font-semibold text-navy">Add crew member</h2>
            <p className="mt-1 text-sm text-muted">Creates a real (non-synthetic) profile with no history. Personal baselines appear after 7 days of check-ins.</p>
            <label className="mt-4 block text-sm font-medium text-navy">Name or call sign
              <input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} maxLength={80}
                className="mt-1 w-full rounded-xl border border-line px-3 py-2" /></label>
            {addError && <p role="alert" className="mt-2 text-sm text-urgent">{addError}</p>}
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" className="btn btn-ghost" onClick={() => setAdding(false)}>Cancel</button>
              <button className="btn btn-primary" disabled={!newName.trim()}>Create profile</button>
            </div>
          </form>
        </div>
      )}
    </header>
  );
}

export default function Layout() {
  const location = useLocation();
  return (
    <div className="flex min-h-full overflow-x-clip">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded-lg focus:bg-white focus:p-2">
        Skip to content
      </a>
      <IntroSplash />
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <MobileNav />
        <main id="main" className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6">
          <Suspense fallback={<div className="skeleton h-64" aria-label="Loading page" />}>
            <div key={location.pathname} className="page-enter"><Outlet /></div>
          </Suspense>
        </main>
        <footer className="border-t border-line px-6 py-3 text-center text-xs text-muted">
          ASTRAHEALTH AI · Hackathon prototype · Not a medical device · Synthetic data only · Demo rules, not clinically validated
          <span className="mx-2">·</span>For reviewers: <Link className="underline" to="/agents">agent trace</Link>
          <span className="mx-1">/</span><Link className="underline" to="/settings">system</Link>
          <span className="mx-1">/</span><a className="underline" href="/?intro=1">replay intro</a>
        </footer>
      </div>
    </div>
  );
}
