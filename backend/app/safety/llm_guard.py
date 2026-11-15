"""Validation of generated explanations against schema and safety policy.

Generated text is advisory. These checks remove any statement that:
- has an invalid structure or statement type (AI-05),
- cites a passage that was not provided (fabricated citation, TC-011),
- contains a number not present in the validated findings or passages (invented threshold, AI-03),
- uses diagnostic or medication language (AI-04),
- offers reassurance that contradicts a REVIEW/URGENT state (AI-01, AI-07).
The deterministic severity is never read from, or changed by, the LLM output.
"""
from __future__ import annotations

import re
from typing import Any

ALLOWED_TYPES = {"observation", "interpretation", "recommendation", "limitation"}
MAX_STATEMENTS = 8
MAX_LEN = 400

DIAGNOSTIC = re.compile(
    r"\b(diagnos\w*|you (?:have|are suffering from|suffer from)|disorder|disease|depression|depressed|"
    r"anxiety disorder|arrhythmia|atrial|hypertensi\w*|hypotensi\w*|tachycardi\w*|bradycardi\w*|infection|"
    r"dehydrat\w*|osteopor\w*|prescri\w*|medication|medicine|drug|pill|tablet|dosage|\d+\s?mg\b|ibuprofen|"
    r"paracetamol|acetaminophen|aspirin|melatonin|zolpidem|antidepress\w*|sedative)\b",
    re.IGNORECASE,
)
# Implied diagnosis or clinical judgement phrased without diagnostic keywords.
IMPLIED_DIAGNOSIS = re.compile(
    r"\b(you (?:may|might|could|probably|likely) (?:have|be suffering|be developing)|"
    r"(?:a|an|the) (?:serious|underlying|medical|heart|cardiac|mental|psychiatric|sleep|neurolog\w*) "
    r"(?:condition|problem|issue|illness|abnormality)|"
    r"(?:suggests?|indicates?|points? to|consistent with|signs? of|symptoms? of) (?:a |an )?(?:\w+ ){0,2}"
    r"(?:condition|disease|disorder|illness|problem|issue|infection|syndrome|deficiency)|"
    r"heart (?:problem|attack|failure)|stroke|cancer|"
    r"(?:is|are) (?:caused|due) (?:by|to) (?:radiation|microgravity|the mission))\b",
    re.IGNORECASE,
)
ALARM = re.compile(r"\b(serious|severe|dangerous|alarming|life[- ]threatening|critical)\b", re.IGNORECASE)
REASSURANCE = re.compile(
    r"\b(normal|nothing to worry|no need to|not urgent|no cause for concern|ignore|safe to continue|"
    r"you(?:'re| are) fine|everything is fine|not serious|can wait|downgrad\w*)\b",
    re.IGNORECASE,
)
# Clinical concepts an explanation may only mention if the findings/passages already do.
CLINICAL_TERMS = re.compile(
    r"\b(immun\w*|inflamm\w*|hormon\w*|cortisol|infection|virus|bacteri\w*|kidney|renal|liver|hepat\w*|thyroid|"
    r"blood sugar|glucose|diabet\w*|cholesterol|oxygen saturation|anemi\w*|electrolyte\w*|sodium|potassium|"
    r"brain|cognit\w*|memory|concussion|seizure|stroke|cancer|tumou?r|cataract\w*|vision|eye\w*|ocular|"
    r"bone density|fracture\w*|osteo\w*|muscle atrophy|cardiac|heart (?:muscle|failure|attack|disease)|arter\w*|clot\w*)\b",
    re.IGNORECASE)
NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?")


def _numbers(text: str) -> set[str]:
    out = set()
    for raw in NUMBER.findall(text):
        cleaned = raw.replace(",", ".").lstrip("+")
        try:
            value = float(cleaned)
        except ValueError:
            continue
        out.add(f"{value:g}")
        out.add(f"{abs(value):g}")
    return out


def allowed_numbers(findings: list[dict], passages: list[dict]) -> set[str]:
    allowed: set[str] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                walk(v)
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            for digits in (0, 1, 2):
                allowed.add(f"{round(float(obj), digits):g}")
                allowed.add(f"{abs(round(float(obj), digits)):g}")
        elif isinstance(obj, str):
            allowed.update(_numbers(obj))

    walk(findings)
    for p in passages:
        allowed.update(_numbers(p.get("passage", "")))
    allowed.update({"1", "2", "3", "4", "5"})  # scale points and small counts used in templates
    return allowed


_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "be", "with", "this", "that", "your",
         "you", "it", "as", "by", "at", "from", "may", "can", "not", "has", "have", "was", "were", "should", "their"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _STOP}


def grounded(text: str, sources: list[str], min_overlap: float = 0.35) -> bool:
    """True when enough of the statement's content words come from one approved source sentence."""
    words = _words(text)
    if not words:
        return False
    return any(len(words & _words(s)) / len(words) >= min_overlap for s in sources)


def validate_explanation(output: Any, findings: list[dict], passages: list[dict], overall_severity: str,
                         care_steps: list[str] | None = None) -> dict:
    accepted: list[dict] = []
    rejected: list[dict] = []
    if not isinstance(output, dict) or not isinstance(output.get("statements"), list):
        return {"valid": False, "accepted": [], "rejected": [{"text": str(output)[:200], "reason": "schema: missing 'statements' list"}]}

    valid_chunks = {p["chunk_id"] for p in passages}
    valid_codes = {f["code"] for f in findings}
    numbers_ok = allowed_numbers(findings, passages)
    escalated = overall_severity in ("REVIEW", "URGENT")
    limitation_sources = [l for f in findings for l in f.get("limitations", [])] + [
        "Analysis is based on a short synthetic history.", "Self-reported values have not been clinically assessed.",
        "A single measurement may not represent a trend."]
    step_sources = [s for f in findings for s in f.get("next_steps", [])] + list(care_steps or [])
    fact_sources = [f.get("summary", "") for f in findings] + [p.get("passage", "") for p in passages] + [
        " ".join(f.get("summary", "") for f in findings)]

    for item in output["statements"][: MAX_STATEMENTS * 2]:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            rejected.append({"text": str(item)[:200], "reason": "schema: statement must be an object with text"})
            continue
        text = item["text"].strip()
        stype = str(item.get("type", "")).lower()
        if stype not in ALLOWED_TYPES:
            rejected.append({"text": text, "reason": f"schema: invalid statement type '{stype}'"})
            continue
        if not text or len(text) > MAX_LEN:
            rejected.append({"text": text[:200], "reason": "schema: empty or too long"})
            continue
        citations = item.get("citations") or []
        if not isinstance(citations, list) or any(c not in valid_chunks for c in citations):
            rejected.append({"text": text, "reason": "citation not in the provided evidence"})
            continue
        if DIAGNOSTIC.search(text):
            rejected.append({"text": text, "reason": "diagnostic or medication language"})
            continue
        if IMPLIED_DIAGNOSIS.search(text):
            rejected.append({"text": text, "reason": "implied diagnosis, condition or causal attribution"})
            continue
        if overall_severity != "URGENT" and ALARM.search(text):
            rejected.append({"text": text, "reason": "alarm language not supported by the deterministic state"})
            continue
        if stype != "limitation" and not any(c in valid_codes for c in (item.get("finding_codes") or [])):
            rejected.append({"text": text, "reason": "statement not linked to a validated finding"})
            continue
        source_text = " ".join(fact_sources + limitation_sources + step_sources).lower()
        new_terms = [t.lower() for t in CLINICAL_TERMS.findall(text) if t.lower() not in source_text]
        if new_terms:
            rejected.append({"text": text, "reason": f"introduces clinical concept(s) not in the findings: {sorted(set(new_terms))}"})
            continue
        if escalated and REASSURANCE.search(text):  # safety reason first
            rejected.append({"text": text, "reason": "reassurance contradicts the deterministic escalation state"})
            continue
        if stype in ("observation", "interpretation") and not grounded(text, fact_sources, min_overlap=0.3):
            rejected.append({"text": text, "reason": "statement not grounded in the findings or retrieved passages"})
            continue
        if stype == "limitation" and not grounded(text, limitation_sources):
            rejected.append({"text": text, "reason": "limitation not grounded in the analysis's known limitations"})
            continue
        if stype == "recommendation" and not grounded(text, step_sources):
            rejected.append({"text": text, "reason": "recommendation not grounded in approved next steps or the care plan"})
            continue
        unknown_numbers = _numbers(text) - numbers_ok
        if unknown_numbers:
            rejected.append({"text": text, "reason": f"unsupported number(s) {sorted(unknown_numbers)} not in validated findings"})
            continue
        codes = [c for c in (item.get("finding_codes") or []) if c in valid_codes]
        accepted.append({"type": stype, "text": text, "finding_codes": codes, "citations": citations, "source": "llm"})
        if len(accepted) >= MAX_STATEMENTS:
            break
    return {"valid": bool(accepted), "accepted": accepted, "rejected": rejected}
