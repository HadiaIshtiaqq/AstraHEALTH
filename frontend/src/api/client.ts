import type {
  AgentDescription, Alert, AnalysisRun, MetricDef, Observation, ObservationDraft, Overview, ParseResult, Profile,
  SymptomDef, SystemHealth, Task, ValidationPreview,
} from "./types";

export class ApiError extends Error {
  status: number;
  details: unknown;
  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

async function raw(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  } catch {
    throw new ApiError(0, "The local ASTRAHEALTH service is not reachable. Nothing was saved.");
  }
  if (!res.ok) {
    let body: any = null;
    try { body = await res.json(); } catch { /* not JSON */ }
    const detail = body?.detail;
    throw new ApiError(res.status, typeof detail === "string" ? detail : detail?.message || `Request failed (${res.status})`, detail);
  }
  return res;
}

export async function download(path: string, filename: string, init?: RequestInit) {
  const res = await raw(path, init);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
  } catch {
    throw new ApiError(0, "The local ASTRAHEALTH service is not reachable. Nothing was saved.");
  }
  if (!res.ok) {
    let body: any = null;
    try { body = await res.json(); } catch { /* not JSON */ }
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : detail?.message || `Request failed (${res.status})`;
    throw new ApiError(res.status, message, detail);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown, headers: Record<string, string> = {}) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body), headers });

export const api = {
  health: () => request<SystemHealth>("/system/health"),
  registry: () => request<{ metrics: MetricDef[]; symptoms: SymptomDef[] }>("/metrics"),
  agents: () => request<{ agents: AgentDescription[] }>("/agents"),
  rules: () => request<{ version: string; status: string; checksum: string; notes: string; rules: any[] }>("/rules"),
  profiles: () => request<{ profiles: Profile[] }>("/profiles"),
  profile: (id: string) => request<Profile>(`/profiles/${id}`),
  createProfile: (display_name: string, timezone: string) => post<Profile>("/profiles", { display_name, timezone, role: "Crew member" }),
  updateProfile: (id: string, body: Partial<Profile> & { settings?: Record<string, unknown> }) =>
    request<Profile>(`/profiles/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  resetProfile: (id: string, adminPin: string) =>
    request<{ reset: string }>(`/profiles/${id}/reset?confirm=true`, { method: "POST", headers: { "X-Admin-PIN": adminPin } }),
  overview: (id: string) => request<Overview>(`/profiles/${id}/overview`),
  parse: (profile_id: string, text: string) => post<ParseResult>("/input/parse", { profile_id, text }),
  validate: (profile_id: string, observations: ObservationDraft[]) =>
    post<ValidationPreview>("/checkins/validate", { profile_id, observations }),
  submit: (body: { profile_id: string; observations: ObservationDraft[]; mode: string; raw_input_text?: string; notes?: string }) =>
    post<{ checkin_id: string; run_id: string | null }>("/checkins", body),
  series: (id: string, metrics: string[], days: number) =>
    request<{ series: Record<string, Observation[]>; start: string; end: string }>(
      `/metrics/${id}?days=${days}${metrics.map((m) => `&metric=${encodeURIComponent(m)}`).join("")}`),
  run: (runId: string) => request<AnalysisRun>(`/analysis-runs/${runId}`),
  runs: (id: string) => request<{ runs: any[] }>(`/profiles/${id}/analysis-runs`),
  startRun: (profile_id: string, simulate_failure: string[] = [], adminPin?: string) =>
    request<AnalysisRun>("/analysis-runs", { method: "POST", body: JSON.stringify({ profile_id, simulate_failure }),
      headers: adminPin ? { "X-Admin-PIN": adminPin } : {} }),
  explain: (runId: string) => post(`/analysis-runs/${runId}/explain`),
  alerts: (id: string, state?: string) => request<{ alerts: Alert[] }>(`/profiles/${id}/alerts${state ? `?state=${state}` : ""}`),
  ack: (alertId: string, actor_role = "crew", pin?: string, note?: string) =>
    post<Alert>(`/alerts/${alertId}/acknowledge`, { actor_role, pin, note }),
  confirmObs: (id: string, pin?: string, note?: string) => post<{ observation: any; run_id: string | null }>(`/observations/${id}/confirm`, { pin, note }),
  correctObs: (id: string, value: string | number, unit: string, reason: string, pin?: string) =>
    post<{ observation: any; run_id: string | null }>(`/observations/${id}/correct`, { value, unit, reason, pin }),
  retractObs: (id: string, reason: string, pin?: string) => post<{ observation: any; run_id: string | null }>(`/observations/${id}/retract`, { reason, pin }),
  removeTask: (taskId: string) => request<{ removed: string }>(`/tasks/${taskId}`, { method: "DELETE" }),
  setTimezone: (id: string, timezone: string) => request<any>(`/profiles/${id}`, { method: "PATCH", body: JSON.stringify({ timezone }) }),
  importRecords: (profile_id: string, format: "csv" | "json", content: string, dry_run: boolean, adminPin: string) =>
    post<{ rows: number; accepted: number; rejected: any[]; checkin_id: string | null; run_id?: string; metrics: Record<string, number> }>(
      "/imports", { profile_id, format, content, dry_run }, { "X-Admin-PIN": adminPin }),
  carePlan: (id: string) => request<any>(`/profiles/${id}/care-plan`),
  adoptPlan: (id: string, planId: string) => post<{ created: number }>(`/profiles/${id}/care-plan/${planId}/adopt`),
  tasks: (id: string, days = 7) =>
    request<{ today: Task[]; history: { date: string; total: number; completed: number }[]; checkin_streak: number }>(
      `/profiles/${id}/tasks?days=${days}`),
  completeTask: (taskId: string) => post<Task>(`/tasks/${taskId}/complete`, {}),
  reopenTask: (taskId: string) => post<Task>(`/tasks/${taskId}/reopen`),
  createReport: (profile_id: string, start?: string, end?: string) => post<any>("/reports", { profile_id, start, end }),
  knowledge: (q: string, k = 2) => request<{ available: boolean; results: any[] }>(`/knowledge/search?q=${encodeURIComponent(q)}&k=${k}`),
  documents: () => request<{ documents: any[]; index: any }>("/knowledge/documents"),
  scenarios: () => request<{ scenarios: { id: string; label: string; profile_id: string }[] }>("/demo/scenarios"),
  runScenario: (id: string, adminPin: string) => request<{ run_id: string; profile_id: string }>(`/demo/scenarios/${id}/run`,
    { method: "POST", headers: { "X-Admin-PIN": adminPin } }),
  reseed: (adminPin: string) => request(`/demo/reseed?confirm=true`, { method: "POST", headers: { "X-Admin-PIN": adminPin } }),
  deleteInitialSecrets: (adminPin: string) => request<{ deleted: boolean }>("/system/initial-secrets/delete",
    { method: "POST", headers: { "X-Admin-PIN": adminPin } }),
  audit: (adminPin: string) => request<{ events: any[]; chain: { intact: boolean; checked: number; broken_at?: string } }>("/system/audit?limit=40", { headers: { "X-Admin-PIN": adminPin } }),
};
