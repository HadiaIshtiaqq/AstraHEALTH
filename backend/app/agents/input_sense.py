"""InputSense — converts free text into *candidate* structured observations.

Deterministic local NLP (regular expressions + dictionaries + simple negation
handling). Nothing extracted here is saved until the crew member confirms it.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.agents.base import AgentContext, BaseAgent
from app.db.database import iso
from app.domain.metrics import METRICS, SYMPTOMS
from app.schemas.models import Finding

NUM = r"(\d{1,4}(?:[.,]\d{1,2})?)"
NEGATIONS = ("no ", "not ", "without ", "never ", "denies ", "don't ", "do not ", "isn't ", "wasn't ", "haven't ", "no longer ")

SYMPTOM_PATTERNS: dict[str, list[str]] = {
    "chest_pain": [r"chest (?:pain|pressure|tightness)", r"pain in (?:my|the) chest", r"tight chest"],
    "shortness_of_breath": [r"short(?:ness)? of breath", r"breathless", r"can'?t (?:catch my )?breathe?", r"trouble breathing", r"difficulty breathing"],
    "palpitations": [r"palpitations?", r"heart (?:is )?(?:racing|pounding|fluttering)", r"racing heart"],
    "dizziness": [r"dizz(?:y|iness)", r"light[- ]?headed", r"vertigo"],
    "fainting": [r"faint(?:ed|ing)?", r"passed out", r"blacked out", r"almost fainted"],
    "confusion": [r"confus(?:ed|ion)", r"disoriented", r"can'?t think straight"],
    "severe_headache": [r"severe headache", r"worst headache", r"intense headache"],
    "headache": [r"headache", r"head (?:hurts|aches?)"],
    "vision_change": [r"blurr(?:y|ed) vision", r"vision (?:is )?(?:blurry|changed|worse)", r"trouble seeing", r"change in (?:my )?vision"],
    "nausea": [r"nause(?:a|ous|ated)", r"feel(?:ing)? sick to my stomach", r"queasy", r"space ?sick"],
    "back_pain": [r"back (?:pain|hurts|ache)", r"backache", r"sore back"],
    "nasal_congestion": [r"congest(?:ed|ion)", r"stuffy nose", r"blocked nose"],
    "insomnia": [r"can'?t sleep", r"couldn'?t sleep", r"trouble sleeping", r"insomnia", r"woke up (?:a lot|repeatedly|many times)"],
}

FATIGUE_WORDS = {
    5: [r"exhausted", r"completely drained", r"extremely tired"],
    4: [r"(?:unusually|very|really|so) tired", r"worn out", r"drained", r"fatigued"],
    3: [r"tired", r"fatigue", r"low energy", r"sluggish"],
}
STRESS_WORDS = {
    5: [r"overwhelmed", r"extremely stressed", r"panick"],
    4: [r"(?:very|really|so) stressed", r"anxious", r"on edge", r"tense"],
    3: [r"stressed", r"under pressure", r"worried"],
    2: [r"a bit stressed", r"slightly stressed"],
}
MOOD_WORDS = {
    1: [r"hopeless", r"miserable", r"very (?:low|down|sad)"],
    2: [r"\bsad\b", r"feeling down", r"\bdown\b", r"\blow mood\b", r"unhappy", r"lonely", r"isolated", r"homesick"],
    3: [r"not (?:too |that |so )?bad", r"\bso-so\b", r"\bmeh\b", r"could be better", r"(?:feel|feeling|i'?m) okay-ish"],
    # Positive levels only from explicit statements about mood or feeling ("good sleep" is not a mood).
    4: [r"(?:feel|feeling|felt|mood is|mood's|i'?m|i am) (?:pretty |quite )?(?:good|fine|ok|okay|positive|content)\b",
        r"in a good mood"],
    5: [r"(?:feel|feeling|felt|mood is|i'?m|i am) (?:really |very )?(?:great|excellent|fantastic)\b"],
}


def _has_adverse(text: str) -> bool:
    """True when a non-negated symptom is mentioned anywhere in the text."""
    for patterns in SYMPTOM_PATTERNS.values():
        for pattern in patterns:
            m = re.search(pattern, text)
            if m and not _negated(text, m.start()):
                return True
    return False


def _num(text: str) -> float:
    return float(text.replace(",", "."))


def _negated(text: str, start: int) -> bool:
    window = text[max(0, start - 25):start]
    clause = re.split(r"[.;,!?]| but | and ", window)[-1]
    return any(neg in f" {clause}" for neg in NEGATIONS)


class InputSenseAgent(BaseAgent):
    agent_id = "input_sense"
    name = "InputSense"
    scope = "Input interpretation: intent detection, entity extraction, unit normalization, clarification questions"
    method = "Local rule-based NLP: regular expressions, symptom dictionary, negation window"
    must_not = "Save unconfirmed extractions or infer a diagnosis from text"

    def parse(self, text: str, reference_time: datetime) -> dict:
        t = " " + text.lower().replace("’", "'") + " "
        observations: list[dict] = []
        clarifications: list[dict] = []
        intents: set[str] = set()
        spans: list[dict] = []
        measured_at = iso(reference_time)

        def add(metric: str, value, unit: str | None, match: re.Match | None, **extra):
            obs = {
                "metric_code": metric,
                "value": value,
                "unit": unit,
                "measured_at": extra.pop("measured_at", measured_at),
                "source": "user_text",
                "method": "input_sense_extraction",
                "context": extra.pop("context", None),
                "confirmed": False,
                "label": METRICS[metric].label if metric in METRICS else metric,
                "evidence_text": match.group(0).strip() if match else None,
                **extra,
            }
            observations.append(obs)
            intents.add(METRICS[metric].system if metric in METRICS else metric)
            if match:
                spans.append({"start": match.start() - 1, "end": match.end() - 1, "metric_code": metric})

        # Blood pressure: "120/80", "bp 120 over 80"
        m = re.search(r"(?:blood pressure|bp)?\s*(?:is|was|of|:)?\s*(\d{2,3})\s*(?:/|over)\s*(\d{2,3})(?:\s*mm ?hg)?", t)
        if m and ("pressure" in t or "bp" in t or "mmhg" in t.replace(" ", "")):
            add("bp_systolic", _num(m.group(1)), "mmHg", m)
            add("bp_diastolic", _num(m.group(2)), "mmHg", m)

        # Heart rate / pulse
        approx = re.search(r"\b(?:heart ?rate|pulse|hr)\b[^\d.;!?]{0,20}?(?:in the |around the )?(\d)0'?s\b", t)
        m = (re.search(rf"\b(?:heart ?rate|pulse|hr)\b[^\d.;!?]{{0,20}}?{NUM}\s*(?:bpm|beats)?", t)
             or re.search(rf"{NUM}\s*(?:bpm|beats per minute)", t))
        if approx:
            # "pulse is in the 80s": a range, not a measurement -> mid-point, must be confirmed or replaced
            add("heart_rate", int(approx.group(1)) * 10 + 5, "bpm", approx)
            observations[-1]["time_note"] = "Approximate (a range was given) - please enter the measured value."
            clarifications.append({"metric_code": "heart_rate", "field": "value",
                                   "question": f"You said the {approx.group(1)}0s - what was the exact reading?",
                                   "options": [str(int(approx.group(1)) * 10 + i) for i in (0, 3, 5, 7, 9)]})
            m = None
        if m:
            context = None
            if re.search(r"resting|at rest|woke|wake|lying|sitting|seated", t):
                context = "resting"
            elif re.search(r"after (?:my )?(?:workout|exercise|run|training|treadmill|ared|cycle)", t):
                context = "post_exercise"
            add("heart_rate", _num(m.group(1)), "bpm", m, context=context)
            if context is None:
                clarifications.append({
                    "metric_code": "heart_rate",
                    "field": "context",
                    "question": "Was this heart rate measured at rest or after exercise?",
                    "options": ["resting", "post_exercise", "other"],
                })

        # Temperature
        m = re.search(rf"(?:temp(?:erature)?|fever)\D{{0,15}}?{NUM}\s*(°?\s*[cf]\b|degrees?\s*[cf]?)?", t)
        if m:
            val = _num(m.group(1))
            unit_raw = (m.group(2) or "").replace("°", "").replace("degrees", "").replace("degree", "").strip()
            unit = "°F" if unit_raw == "f" or (not unit_raw and val > 50) else "°C"
            add("body_temperature", val, unit, m)
            if not unit_raw:
                clarifications.append({"metric_code": "body_temperature", "field": "unit",
                                       "question": f"Is {val:g} in °C or °F?", "options": ["°C", "°F"]})

        # Sleep duration
        m = (re.search(rf"slept\s*(?:for\s*)?(?:about\s*|around\s*|only\s*|just\s*)?{NUM}\s*(hours?|hrs?|h\b|minutes?|mins?)", t)
             or re.search(rf"{NUM}\s*(hours?|hrs?|h)\s*(?:of\s*)?sleep", t)
             or re.search(rf"sleep\D{{0,12}}{NUM}\s*(hours?|hrs?|h\b)", t))
        if m:
            unit = "min" if m.group(2).startswith("min") else "h"
            add("sleep_duration", _num(m.group(1)), unit, m)
            clarifications.append({"metric_code": "sleep_duration", "field": "measured_at",
                                   "question": "Does this refer to your most recent sleep period?", "options": ["yes", "no"]})
        if re.search(r"slept (?:badly|poorly|terribly)|bad sleep|poor sleep|restless night", t):
            mm = re.search(r"slept (?:badly|poorly|terribly)|bad sleep|poor sleep|restless night", t)
            add("sleep_quality", 2, "score", mm)
        elif re.search(r"slept (?:well|great|fine)|good sleep|good night'?s sleep", t):
            mm = re.search(r"slept (?:well|great|fine)|good sleep|good night'?s sleep", t)
            add("sleep_quality", 4, "score", mm)

        # Fluid intake
        m = re.search(rf"(?:drank|drink|drunk|fluid|water|intake)\D{{0,20}}?{NUM}\s*(ml|millilit(?:er|re)s?|l\b|lit(?:er|re)s?|fl ?oz)", t) \
            or re.search(rf"{NUM}\s*(ml|l|lit(?:er|re)s?)\s*(?:of\s*)?(?:water|fluid)", t)
        if m:
            u = m.group(2).replace(" ", "")
            unit = "mL" if u.startswith("ml") or u.startswith("milli") else ("fl oz" if "oz" in u else "L")
            add("fluid_intake", _num(m.group(1)), unit, m)

        # Exercise
        ex_word = r"(?:exercis\w*|work(?:ed)? ?out|treadmill|cycl\w*|ared|resistance|weights|training|\bran\b|\brun\b)"
        unit_re = r"(minutes?|mins?|min\b|hours?|hrs?|h\b)"
        segments: list[tuple[float, re.Match]] = []
        for mm in re.finditer(rf"{NUM}\s*{unit_re}\s*(?:of\s*|on\s*(?:the\s*)?)?{ex_word}", t):
            segments.append((_num(mm.group(1)) * (60 if mm.group(2).startswith("h") else 1), mm))
        if not segments:
            for mm in re.finditer(rf"{ex_word}[^\d.;!?]{{0,25}}?{NUM}\s*{unit_re}", t):
                segments.append((_num(mm.group(1)) * (60 if mm.group(2).startswith("h") else 1), mm))
        if segments:
            add("exercise_duration", sum(v for v, _ in segments), "min", segments[0][1])
            observations[-1]["evidence_text"] = " + ".join(s.group(0).strip() for _, s in segments)
            if len(segments) > 1:
                observations[-1]["time_note"] = f"Summed {len(segments)} exercise sessions - please confirm the total."
        if re.search(r"(?:did|completed|finished) (?:my |the )?(?:resistance|ared|weights)", t):
            mm = re.search(r"(?:did|completed|finished) (?:my |the )?(?:resistance|ared|weights)", t)
            add("resistance_exercise", 1, "bool", mm)
        elif re.search(r"(?:skipped|missed|didn'?t do) (?:my |the )?(?:resistance|ared|weights|workout|exercise)", t):
            mm = re.search(r"(?:skipped|missed|didn'?t do) (?:my |the )?(?:resistance|ared|weights|workout|exercise)", t)
            add("resistance_exercise", 0, "bool", mm)

        # Body mass
        m = re.search(rf"(?:weigh\w*|mass)\D{{0,12}}?{NUM}\s*(kg|kilo\w*|lbs?|pounds?)", t)
        if m:
            add("body_mass", _num(m.group(1)), "lb" if m.group(2).startswith(("lb", "pound")) else "kg", m)

        # Self-report scales
        for metric, table in (("fatigue", FATIGUE_WORDS), ("stress", STRESS_WORDS), ("mood", MOOD_WORDS)):
            for level in sorted(table, key=lambda lv: -abs(lv - 3)):
                if metric == "mood" and level >= 4 and (_has_adverse(t) or any(
                        o["metric_code"] in ("stress", "fatigue") and o["value"] >= 4 for o in observations)):
                    continue  # do not infer a positive mood alongside symptoms or high stress/fatigue
                found = None
                for pattern in table[level]:
                    mm = re.search(pattern, t)
                    if mm and not _negated(t, mm.start()):
                        found = mm
                        break
                if found:
                    add(metric, level, "score", found)
                    clarifications.append({
                        "metric_code": metric, "field": "value",
                        "question": f"We interpreted “{found.group(0).strip()}” as {METRICS[metric].label.lower()} "
                                    f"{level}/5 ({METRICS[metric].scale_labels[level - 1]}). Is that right?",
                        "options": [str(i) for i in range(1, 6)],
                    })
                    break

        # Symptoms (with negation handling)
        negated: list[str] = []
        for code, patterns in SYMPTOM_PATTERNS.items():
            for pattern in patterns:
                mm = re.search(pattern, t)
                if not mm:
                    continue
                if _negated(t, mm.start()):
                    negated.append(code)
                    break
                if code == "headache" and any(o.get("value") == "severe_headache" for o in observations):
                    break
                add("symptom", code, "code", mm)
                onset = None
                if re.search(r"since (?:this )?morning|today", t):
                    onset = "today"
                elif re.search(r"yesterday|since last night|last night", t):
                    onset = "since_yesterday"
                elif re.search(r"for (?:a few|several|\d+) days|all week", t):
                    onset = "several_days"
                observations[-1]["onset"] = onset
                observations[-1]["label"] = SYMPTOMS[code]["label"]
                break

        symptom_obs = [o for o in observations if o["metric_code"] == "symptom"]
        if symptom_obs:
            clarifications.append({
                "metric_code": "symptom", "field": "trend",
                "question": "Are these symptoms new, persistent, or getting worse?",
                "options": ["new", "persistent", "worsening"],
            })

        # Temporal hints
        if re.search(r"yesterday|last night", t):
            for o in observations:
                if o["metric_code"] != "sleep_duration" and "yesterday" in t:
                    o["measured_at"] = iso(reference_time - timedelta(days=1))
                    o["time_note"] = "Interpreted as yesterday — please confirm the time."

        return {
            "intents": sorted(intents),
            "observations": observations,
            "negated_symptoms": negated,
            "clarifications": clarifications,
            "requires_confirmation": bool(observations),
            "spans": spans,
            "method": self.method,
            "llm_used": False,
        }

    def analyze(self, ctx: AgentContext):  # orchestrator trace step
        mode = ctx.settings.get("checkin_mode", "manual")
        raw = ctx.settings.get("raw_input_text")
        ids = [o["observation_id"] for o in ctx.checkin_observations]
        sources = sorted({o["source"] for o in ctx.checkin_observations})
        if mode == "conversation" and raw:
            parsed = self.parse(raw, ctx.reference_time)
            summary = (f"Interpreted free-text input into {len(parsed['observations'])} candidate observation(s); "
                       f"{len(ids)} were confirmed by the crew member and saved.")
            output = {"intents": parsed["intents"], "candidates": len(parsed["observations"]),
                      "negated_symptoms": parsed["negated_symptoms"]}
        else:
            summary = f"Received {len(ids)} structured observation(s) from the {mode} check-in form."
            output = {"sources": sources}
        finding = Finding(code="INPUT_RECEIVED", summary=summary, statement_type="observation",
                          evidence_observation_ids=ids)
        return self.result(ctx, "completed", [finding], ids, output=output,
                           activation_reason="Runs on every new submission")
