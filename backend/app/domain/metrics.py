"""Metric registry: the single source of truth for indicators, units and conversions.

`plausible_range` is a *data-quality* bound on the normalized value (is this
physically/technically plausible as a measurement?). It is NOT a clinical threshold
and is never used to assign clinical severity.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class MetricDef:
    code: str
    label: str
    system: str  # cardio | neuro | sleep | bone | nutrition | mission | symptom | general
    normalized_unit: str
    units: dict[str, Callable[[float], float]]  # unit -> converter to normalized
    value_type: str = "numeric"  # numeric | scale | boolean | categorical
    plausible_range: tuple[float, float] | None = None
    scale_labels: tuple[str, ...] = ()
    description: str = ""
    higher_is: str = "neutral"  # used only for wording of direction
    aggregate: str = "mean"  # how daily values aggregate: mean | sum | last | max
    agents: tuple[str, ...] = field(default_factory=tuple)


def _identity(x: float) -> float:
    return x


METRICS: dict[str, MetricDef] = {
    m.code: m
    for m in [
        MetricDef(
            "heart_rate", "Heart rate", "cardio", "bpm", {"bpm": _identity, "beats/min": _identity},
            plausible_range=(20, 250), description="Heart rate with measurement context (resting / post-exercise).",
            agents=("cardio_guard",),
        ),
        MetricDef(
            "bp_systolic", "Blood pressure (systolic)", "cardio", "mmHg", {"mmHg": _identity, "kPa": lambda v: v * 7.50062},
            plausible_range=(50, 260), description="Systolic value; must be submitted with the diastolic value.",
            agents=("cardio_guard",),
        ),
        MetricDef(
            "bp_diastolic", "Blood pressure (diastolic)", "cardio", "mmHg", {"mmHg": _identity, "kPa": lambda v: v * 7.50062},
            plausible_range=(25, 160), description="Diastolic value; must be submitted with the systolic value.",
            agents=("cardio_guard",),
        ),
        MetricDef(
            "body_temperature", "Body temperature", "general", "°C",
            {"°C": _identity, "C": _identity, "degC": _identity, "°F": lambda v: (v - 32) * 5 / 9, "F": lambda v: (v - 32) * 5 / 9, "degF": lambda v: (v - 32) * 5 / 9},
            plausible_range=(30, 45), description="Body temperature; original unit and method are preserved.",
            agents=("cardio_guard",),
        ),
        MetricDef(
            "sleep_duration", "Sleep duration", "sleep", "h", {"h": _identity, "hours": _identity, "min": lambda v: v / 60},
            plausible_range=(0, 24), description="Duration of the most recent sleep period (not sleep quality).",
            higher_is="more", aggregate="last", agents=("sleep_sense",),
        ),
        MetricDef(
            "sleep_quality", "Sleep quality (self-report)", "sleep", "score", {"score": _identity},
            value_type="scale", plausible_range=(1, 5), scale_labels=("Very poor", "Poor", "Fair", "Good", "Very good"),
            description="Self-reported 1–5 scale. Prototype scale, not a validated instrument.", agents=("sleep_sense",),
        ),
        MetricDef(
            "mood", "Mood (self-report)", "neuro", "score", {"score": _identity},
            value_type="scale", plausible_range=(1, 5), scale_labels=("Very low", "Low", "Neutral", "Good", "Very good"),
            description="Self-reported 1–5 scale. Not a psychiatric assessment. Private by default.", agents=("neuro_mind",),
        ),
        MetricDef(
            "stress", "Stress (self-report)", "neuro", "score", {"score": _identity},
            value_type="scale", plausible_range=(1, 5), scale_labels=("Very low", "Low", "Moderate", "High", "Very high"),
            description="Self-reported 1–5 scale. Not a psychiatric assessment.", agents=("neuro_mind",),
        ),
        MetricDef(
            "fatigue", "Fatigue (self-report)", "neuro", "score", {"score": _identity},
            value_type="scale", plausible_range=(1, 5), scale_labels=("None", "Mild", "Moderate", "Marked", "Severe"),
            description="Self-reported 1–5 scale.", agents=("neuro_mind", "sleep_sense"),
        ),
        MetricDef(
            "fluid_intake", "Fluid intake", "nutrition", "mL",
            {"mL": _identity, "ml": _identity, "L": lambda v: v * 1000, "l": lambda v: v * 1000, "fl oz": lambda v: v * 29.5735},
            plausible_range=(0, 10000), description="Logged intake only; hydration status is not inferred.",
            aggregate="sum", agents=("nutri_track",),
        ),
        MetricDef(
            "appetite", "Appetite (self-report)", "nutrition", "score", {"score": _identity},
            value_type="scale", plausible_range=(1, 5), scale_labels=("Very low", "Low", "Usual", "Good", "Very good"),
            description="Self-reported 1–5 scale.", agents=("nutri_track",),
        ),
        MetricDef(
            "body_mass", "Body mass", "nutrition", "kg", {"kg": _identity, "lb": lambda v: v * 0.453592},
            plausible_range=(30, 250), description="Body mass from the mission mass-measurement device (simulated).",
            aggregate="last", agents=("nutri_track",),
        ),
        MetricDef(
            "exercise_duration", "Exercise duration", "bone", "min", {"min": _identity, "h": lambda v: v * 60, "hours": lambda v: v * 60},
            plausible_range=(0, 600), description="Total countermeasure exercise for the day.",
            aggregate="sum", agents=("bone_guard",),
        ),
        MetricDef(
            "resistance_exercise", "Resistance exercise completed", "bone", "bool", {"bool": _identity},
            value_type="boolean", plausible_range=(0, 1), description="Whether the scheduled resistance session was completed.",
            aggregate="max", agents=("bone_guard",),
        ),
        MetricDef(
            "msk_discomfort", "Musculoskeletal discomfort (self-report)", "bone", "score", {"score": _identity},
            value_type="scale", plausible_range=(1, 5), scale_labels=("None", "Mild", "Moderate", "Marked", "Severe"),
            description="Self-reported back/joint/muscle discomfort.", agents=("bone_guard",),
        ),
        MetricDef(
            "blood_glucose", "Blood glucose (optional)", "nutrition", "mg/dL", {"mg/dL": _identity, "mmol/L": lambda v: v * 18.0182},
            plausible_range=(20, 600), description="Optional. Only meaningful with a defined device and measurement context.",
            agents=("nutri_track",),
        ),
        MetricDef(
            "radiation_dose", "Radiation dose (dosimeter)", "mission", "mSv", {"mSv": _identity, "uSv": lambda v: v / 1000, "µSv": lambda v: v / 1000},
            plausible_range=(0, 1000), description="Personal dosimeter reading for the period (simulated).",
            aggregate="sum", agents=("mission_context",),
        ),
        MetricDef(
            "symptom", "Reported symptom", "symptom", "code", {"code": _identity},
            value_type="categorical", description="Self-reported symptom code.", aggregate="last",
            agents=("neuro_mind", "cardio_guard"),
        ),
    ]
}

# Symptom vocabulary (codes are what rules reference).
SYMPTOMS: dict[str, dict] = {
    "chest_pain": {"label": "Chest pain or pressure", "system": "cardio"},
    "shortness_of_breath": {"label": "Shortness of breath", "system": "cardio"},
    "palpitations": {"label": "Palpitations", "system": "cardio"},
    "dizziness": {"label": "Dizziness / light-headedness", "system": "cardio"},
    "fainting": {"label": "Fainting / near-fainting", "system": "cardio"},
    "confusion": {"label": "Confusion or disorientation", "system": "neuro"},
    "severe_headache": {"label": "Severe headache", "system": "neuro"},
    "headache": {"label": "Headache", "system": "neuro"},
    "vision_change": {"label": "Change in vision", "system": "neuro"},
    "nausea": {"label": "Nausea", "system": "nutrition"},
    "back_pain": {"label": "Back pain", "system": "bone"},
    "nasal_congestion": {"label": "Nasal congestion", "system": "general"},
    "insomnia": {"label": "Difficulty sleeping", "system": "sleep"},
    "low_energy": {"label": "Unusual tiredness", "system": "neuro"},
}

VALID_SOURCES = {"manual", "simulated", "device", "user_text", "import"}

CHECKIN_CORE_METRICS = ("heart_rate", "sleep_duration", "mood", "stress", "fatigue", "exercise_duration", "fluid_intake")


def get_metric(code: str) -> MetricDef | None:
    return METRICS.get(code)


def normalize(code: str, value: float, unit: str) -> tuple[float, str]:
    metric = METRICS[code]
    converter = metric.units[unit]
    return round(float(converter(float(value))), 4), metric.normalized_unit
