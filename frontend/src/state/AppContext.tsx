import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { MetricDef, Profile, SymptomDef, SystemHealth } from "../api/types";
import { setDisplayTz } from "../lib/format";

interface AppState {
  profiles: Profile[];
  profile: Profile | null;
  profileId: string;
  setProfileId: (id: string) => void;
  metrics: Record<string, MetricDef>;
  symptoms: Record<string, SymptomDef>;
  health: SystemHealth | null;
  healthError: string | null;
  refreshKey: number;
  refresh: () => void;
  loading: boolean;
}

const Ctx = createContext<AppState | null>(null);

function readStored(): string {
  const fromUrl = new URLSearchParams(window.location.search).get("profile");
  if (fromUrl) return fromUrl;
  try { return localStorage.getItem("astra.profile") || "crew-demo-01"; } catch { return "crew-demo-01"; }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileIdState] = useState<string>(readStored);
  const [metrics, setMetrics] = useState<Record<string, MetricDef>>({});
  const [symptoms, setSymptoms] = useState<Record<string, SymptomDef>>({});
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);

  const setProfileId = useCallback((id: string) => {
    setProfileIdState(id);
    try { localStorage.setItem("astra.profile", id); } catch { /* storage unavailable */ }
  }, []);
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  useEffect(() => {
    api.registry().then((r) => {
      setMetrics(Object.fromEntries(r.metrics.map((m) => [m.code, m])));
      setSymptoms(Object.fromEntries(r.symptoms.map((s) => [s.code, s])));
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    api.profiles().then((r) => {
      setProfiles(r.profiles);
      if (r.profiles.length && !r.profiles.some((p) => p.profile_id === profileId)) setProfileId(r.profiles[0].profile_id);
    }).catch(() => undefined).finally(() => setLoading(false));
  }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const load = () => api.health().then((h) => { setHealth(h); setHealthError(null); })
      .catch((e) => setHealthError(e.message));
    load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, [refreshKey]);

  const profile = useMemo(() => profiles.find((p) => p.profile_id === profileId) || null, [profiles, profileId]);
  // Times are shown in the viewer's local zone; day boundaries for analysis follow the profile's zone.
  setDisplayTz(Intl.DateTimeFormat().resolvedOptions().timeZone || profile?.timezone || "UTC");

  return (
    <Ctx.Provider value={{ profiles, profile, profileId, setProfileId, metrics, symptoms, health, healthError, refreshKey, refresh, loading }}>
      {children}
    </Ctx.Provider>
  );
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside provider");
  return v;
}

/** Load data for the current profile; re-runs when profile or refreshKey changes. */
export function useProfileData<T>(loader: (profileId: string) => Promise<T>, deps: unknown[] = []) {
  const { profileId, refreshKey } = useApp();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [local, setLocal] = useState(0);
  useEffect(() => {
    let live = true;
    setLoading(true);
    loader(profileId)
      .then((d) => { if (live) { setData(d); setError(null); } })
      .catch((e) => { if (live) setError(e.message); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [profileId, refreshKey, local, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, error, loading, reload: () => setLocal((n) => n + 1), setData };
}
