"""Evidence retrieval for findings. No citation is ever fabricated: if nothing in the
approved library is relevant enough, the finding is marked 'evidence unavailable'."""
from __future__ import annotations

from app.rag.index import KnowledgeIndex
from app.schemas.models import Finding, KnowledgeRef

# Retrieval query per finding code (plain-language topic, not instructions).
QUERIES = {
    "HR_BASELINE_DEVIATION": "heart rate personal baseline measurement context repeat resting",
    "BP_BASELINE_DEVIATION": "blood pressure personal baseline measurement context posture repeat",
    "TEMP_BASELINE_DEVIATION": "repeat measurement standard conditions data quality",
    "CARDIO_SYMPTOM_REPORTED": "symptoms chest pain fainting breathlessness dizziness onboard medical officer",
    "URGENT_SYMPTOM_REPORTED": "symptoms chest pain fainting breathlessness dizziness onboard medical officer emergency",
    "URGENT_SYMPTOM_COMBINATION": "breathlessness together with dizziness onboard medical officer emergency procedures",
    "SYMPTOM_REQUIRES_REVIEW": "vision change severe headache report medical officer review",
    "NEURO_SYMPTOM_REPORTED": "headache in flight fluid shifts sleep loss stress medical review",
    "WELLBEING_SINGLE_DAY_CHANGE": "monitoring wellbeing self-reports mood stress fatigue",
    "WELLBEING_TREND_ADVERSE": "monitoring wellbeing self-reports gradual changes mood stress fatigue",
    "WELLBEING_MULTI_SIGNAL_DECLINE": "several wellbeing measures mood stress fatigue change together private conversation medical officer support",
    "SLEEP_BELOW_BASELINE": "sleep loss in flight insufficient sleep countermeasures",
    "SLEEP_SHORT_PATTERN": "repeated short sleep effects alertness mood sleep countermeasures protecting sleep periods",
    "EXERCISE_ADHERENCE_BELOW_PLAN": "exercise countermeasure adherence bone muscle loss microgravity",
    "RESISTANCE_SESSIONS_MISSED": "resistance exercise sessions countermeasure bone muscle",
    "MSK_DISCOMFORT_REPORTED": "back pain musculoskeletal discomfort spine flight",
    "FLUID_INTAKE_BELOW_BASELINE": "fluid intake logs hydration status complete logs",
    "APPETITE_BELOW_BASELINE": "appetite changes workload stress food fatigue",
    "BODY_MASS_CHANGE": "body mass measurement trend mass-measurement device",
    "MULTIVARIATE_ANOMALY": "anomaly detection unusual combination of signals prompt for follow-up not diagnosis",
    "PERSISTENT_CHANGE_DETECTED": "anomaly detection unusual patterns prompt follow-up",
    "CROSS_DOMAIN_PATTERN": "combined monitoring several body systems sleep mood exercise cardiovascular change together",
    "DATA_QUALITY_FLAG": "data quality impossible values flagged corrected kept for confirmation",
    "AGENT_FAILED": "unknown is not normal analysis fails incomplete status",
    "AGENT_CONFLICT": "conflicting results escalated medical officer human oversight",
    "RADIATION_RECORD_SUMMARY": "dosimetry dose records interpreting mission context",
    "COMM_DELAY_NOTE": "distance from earth communication delay onboard escalation",
    "ROUTINE_CHANGE_NOTED": "combined monitoring co-occurring changes do not establish cause",
}


def attach_evidence(findings: list[Finding], index: KnowledgeIndex, k: int = 2) -> dict:
    """Attach top-k passages to findings that need explanation. Returns retrieval status."""
    if not index.ready:
        for f in findings:
            if f.code in QUERIES:
                f.evidence_status = "unavailable"
                f.limitations.append("Evidence retrieval unavailable (knowledge index not loaded).")
        return {"available": False, "reason": index.error or "index not ready"}

    for f in findings:
        query = QUERIES.get(f.code)
        if query is None:
            continue
        try:
            hits = index.search(query + " " + " ".join(m.replace("_", " ") for m in f.metric_codes), k=k)
        except RuntimeError:
            hits = []
        refs = []
        for h in hits:
            if not index.has_chunk(h["chunk_id"]):  # validate before citing
                continue
            refs.append(KnowledgeRef(
                chunk_id=h["chunk_id"], document_id=h["document_id"], title=h["title"], publisher=h["publisher"],
                section=h["section"], version=h["version"], publication_date=h["publication_date"],
                passage=h["passage"], score=h["score"],
                relevance_note=f"Retrieved for {f.code.replace('_', ' ').lower()} (similarity {h['score']:.2f}).",
            ))
        f.knowledge_references = refs
        f.evidence_status = "found" if refs else "unavailable"
    return {"available": True}
