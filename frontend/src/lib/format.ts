import type { MetricDef, Observation } from "../api/types";

let displayTz = "UTC";
/** All times are displayed in the selected crew member's mission timezone (stored in UTC). */
export function setDisplayTz(tz: string) {
  try { new Intl.DateTimeFormat("en-GB", { timeZone: tz }); displayTz = tz; } catch { displayTz = "UTC"; }
}
export function getDisplayTz() { return displayTz; }
function tzLabel(d: Date): string {
  if (displayTz === "UTC") return "UTC";
  const part = new Intl.DateTimeFormat("en-GB", { timeZone: displayTz, timeZoneName: "short" }).formatToParts(d)
    .find((p) => p.type === "timeZoneName");
  return part?.value || displayTz;
}

export function fmtTime(iso?: string | null, withDate = true): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: displayTz });
  if (!withDate) return `${time} ${tzLabel(d)}`;
  const date = d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: displayTz });
  return `${date} ${time} ${tzLabel(d)}`;
}

/** Local calendar day (YYYY-MM-DD) in the display timezone. */
export function localDay(iso: string | Date, tz?: string): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return new Intl.DateTimeFormat("en-CA", { timeZone: tz || displayTz, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

/** Format a timestamp, or a plain YYYY-MM-DD calendar day, as "14 Nov". */
export function fmtDate(iso: string): string {
  const plainDay = iso.length === 10;
  return new Date(plainDay ? `${iso}T12:00:00Z` : iso)
    .toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: plainDay ? "UTC" : displayTz });
}

export function relative(iso?: string | null): string {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

export function fmtValue(value: number | null | undefined, metric?: MetricDef, digits?: number): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (!metric) return String(value);
  if (metric.value_type === "scale") return `${Math.round(value)}/5`;
  if (metric.value_type === "boolean") return value >= 1 ? "Yes" : "No";
  const d = digits ?? (["body_temperature", "sleep_duration", "body_mass"].includes(metric.code) ? 1 : 0);
  return value.toLocaleString("en-GB", { maximumFractionDigits: d, minimumFractionDigits: d });
}

export function obsValue(o: Observation, metric?: MetricDef): string {
  if (o.value_text) return o.value_text.replace(/_/g, " ");
  return fmtValue(o.normalized_value ?? o.value, metric);
}

export function shortLabel(label: string): string {
  return label.replace(/ \((self-report|dosimeter|optional)\)/, "").replace(/Blood pressure \((systolic|diastolic)\)/, (_m, p) => `BP ${p}`);
}

export const AGENT_LABELS: Record<string, string> = {
  input_sense: "InputSense", data_guard: "DataGuard", baseline_iq: "BaselineIQ", cardio_guard: "CardioGuard",
  neuro_mind: "NeuroMind", sleep_sense: "SleepSense", bone_guard: "BoneGuard", nutri_track: "NutriTrack",
  anomaly_detect: "AnomalyDetect", mission_context: "MissionContext", safety_gate: "Safety & Evidence Gate",
};

export const STATEMENT_LABEL: Record<string, string> = {
  observation: "Observation", interpretation: "Interpretation", recommendation: "Recommendation", limitation: "Limitation",
};
