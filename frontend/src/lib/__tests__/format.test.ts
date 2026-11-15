import { describe, expect, it } from "vitest";
import type { MetricDef } from "../../api/types";
import { fmtDate, fmtTime, fmtValue, localDay, setDisplayTz, shortLabel } from "../format";

const metric = (code: string, value_type: MetricDef["value_type"] = "numeric"): MetricDef => ({
  code, label: code, system: "x", normalized_unit: "u", units: ["u"], value_type, plausible_range: null,
  scale_labels: [], description: "", agents: [],
});

describe("format", () => {
  it("formats values by metric type and never invents a value", () => {
    expect(fmtValue(3, metric("mood", "scale"))).toBe("3/5");
    expect(fmtValue(1, metric("resistance_exercise", "boolean"))).toBe("Yes");
    expect(fmtValue(7.25, metric("sleep_duration"))).toBe("7.3");
    expect(fmtValue(null, metric("heart_rate"))).toBe("—");
    expect(fmtValue(Number.NaN, metric("heart_rate"))).toBe("—");
  });

  it("assigns the calendar day in the requested time zone", () => {
    expect(localDay("2026-11-14T22:30:00Z", "UTC")).toBe("2026-11-14");
    expect(localDay("2026-11-14T22:30:00Z", "Asia/Karachi")).toBe("2026-11-15");
  });

  it("labels times with the display zone and falls back to UTC for invalid zones", () => {
    setDisplayTz("Not/AZone");
    expect(fmtTime("2026-11-14T07:30:00Z")).toBe("14 Nov 07:30 UTC");
    setDisplayTz("UTC");
    expect(fmtDate("2026-11-14")).toBe("14 Nov");
  });

  it("shortens labels without merging systolic and diastolic", () => {
    expect(shortLabel("Mood (self-report)")).toBe("Mood");
    expect(shortLabel("Blood pressure (systolic)")).not.toBe(shortLabel("Blood pressure (diastolic)"));
  });
});
