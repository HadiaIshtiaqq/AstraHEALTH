"""Safety & Evidence Gate (Medical Officer agent).

Consolidates specialist results, applies the versioned rule set, detects conflicts,
retrieves evidence and decides the overall monitoring state. Deterministic: the
local LLM is never consulted here.
"""
from __future__ import annotations

from app.agents.base import AgentContext
from app.rag.index import KnowledgeIndex
from app.safety.certainty import grade as grade_certainty
from app.safety.evidence import attach_evidence
from app.safety.rules import RuleSet
from app.schemas.models import SEVERITY_ORDER, AgentResult, Finding, Severity, max_severity

GATE_ID = "safety_gate"
GATE_NAME = "Safety & Evidence Gate"
GATE_VERSION = "1.0.0"

SPECIALISTS = ("cardio_guard", "neuro_mind", "sleep_sense", "bone_guard", "nutri_track")

STATE_TEXT = {
    "URGENT": "Urgent escalation required",
    "REVIEW": "Qualified review recommended",
    "MONITOR": "Follow-up monitoring suggested",
    "WITHIN_CRITERIA": "Within configured monitoring criteria",
    "INCOMPLETE": "Incomplete — status unknown",
}


def detect_conflicts(results: list[AgentResult]) -> list[Finding]:
    """Two agents reading the same metric in opposite directions is escalated, never averaged."""
    by_metric: dict[str, dict[str, list[str]]] = {}
    for r in results:
        if r.status == "failed":
            continue
        for a in r.assessments:
            if a.assessment == "unknown":
                continue
            by_metric.setdefault(a.metric_code, {}).setdefault(a.assessment, []).append(r.agent_id)
    out = []
    for metric, views in by_metric.items():
        if "stable" in views and "changed" in views:
            names = {r.agent_id: r.agent_name for r in results}
            changed = ", ".join(names.get(a, a) for a in views["changed"])
            stable = ", ".join(names.get(a, a) for a in views["stable"])
            out.append(Finding(
                code="AGENT_CONFLICT",
                summary=f"Analysis modules disagree about {metric.replace('_', ' ')}: {changed} reports a change "
                        f"while {stable} reports it as stable. The disagreement is escalated, not averaged.",
                statement_type="limitation",
                metric_codes=[metric],
                data={"metric_code": metric, "changed_by": views["changed"], "stable_by": views["stable"]},
                agent_id=GATE_ID,
            ))
    return out


def consolidate(
    ctx: AgentContext,
    results: list[AgentResult],
    routed_agents: list[str],
    ruleset: RuleSet,
    index: KnowledgeIndex,
    missing_core: list[str],
) -> dict:
    findings: list[Finding] = []
    for r in results:
        for f in r.findings:
            f.agent_id = f.agent_id or r.agent_id
            findings.append(f)

    failed = [r for r in results if r.status == "failed"]
    for r in failed:
        findings.append(Finding(
            code="AGENT_FAILED",
            summary=f"{r.agent_name} did not complete ({r.error or 'error'}). Its measurements were not analysed; "
                    "coverage is incomplete.",
            statement_type="limitation",
            evidence_observation_ids=r.input_observation_ids,
            data={"agent_id": r.agent_id},
            agent_id=GATE_ID,
        ))
    findings += detect_conflicts(results)

    for f in findings:
        ruleset.apply_to_finding(f)

    symptom_ids: dict[str, list[str]] = {}
    for o in ctx.valid_checkin_observations:
        if o["metric_code"] == "symptom":
            symptom_ids.setdefault(o["value_text"], []).append(o["observation_id"])
    context = ruleset.context_findings(ctx.symptoms(), findings, results, symptom_ids)
    findings = context + findings

    explain = [f for f in findings if SEVERITY_ORDER[f.severity] >= SEVERITY_ORDER[Severity.MONITOR]
               or f.code in ("COMM_DELAY_NOTE", "RADIATION_RECORD_SUMMARY", "ROUTINE_CHANGE_NOTED")]
    retrieval = attach_evidence(explain, index)
    flags_by_metric: dict[str, list[str]] = {}
    for o in ctx.checkin_observations:
        if o["quality_status"] != "valid":
            flags_by_metric.setdefault(o["metric_code"], []).append(o["quality_status"])
    grade_certainty(findings, flags_by_metric)

    # Promote agent status to "review" when the rule engine assigns REVIEW/URGENT to its findings.
    for r in results:
        if r.status == "completed" and any(
            SEVERITY_ORDER[f.severity] >= SEVERITY_ORDER[Severity.REVIEW] for f in r.findings
        ):
            r.status = "review"
            r.requires_human_review = True

    top = max_severity([f.severity for f in findings])
    insufficient = [r.agent_id for r in results if r.status == "insufficient_data" and r.agent_id in SPECIALISTS]
    coverage_complete = not failed and not missing_core and not insufficient
    if top == Severity.INFO:
        state = "WITHIN_CRITERIA" if coverage_complete else "INCOMPLETE"
    else:
        state = top.value

    human_review = any(f.requires_human_review for f in findings) or bool(failed)
    actions: list[dict] = []
    seen: set[str] = set()
    for f in sorted(findings, key=lambda f: -SEVERITY_ORDER[f.severity]):
        for step in f.next_steps:
            if step not in seen and SEVERITY_ORDER[f.severity] >= SEVERITY_ORDER[Severity.MONITOR]:
                seen.add(step)
                actions.append({"severity": f.severity.value, "text": step, "rule_ids": f.rule_ids, "finding_code": f.code})
    if missing_core:
        actions.append({"severity": "INFO", "text": "Complete today's check-in: " + ", ".join(m.replace('_', ' ') for m in missing_core) + ".",
                        "rule_ids": [], "finding_code": "MISSING_CORE_MEASUREMENTS"})
    if human_review and not any("medical officer" in a["text"].lower() for a in actions):
        actions.insert(0, {"severity": top.value, "text": "Share this report with the onboard medical officer for review.",
                           "rule_ids": [], "finding_code": "HUMAN_REVIEW"})

    coverage = {
        "complete": coverage_complete,
        "routed_agents": routed_agents,
        "failed_agents": [r.agent_id for r in failed],
        "insufficient_data_agents": insufficient,
        "missing_core_metrics": missing_core,
    }
    headline = _headline(state, findings, coverage)
    return {
        "findings": findings,
        "assessment": {
            "monitoring_state": state,
            "state_label": STATE_TEXT[state],
            "overall_severity": top.value,
            "headline": headline,
            "requires_human_review": human_review,
            "next_actions": actions,
            "coverage": coverage,
            "evidence_retrieval": retrieval,
            "ruleset": {"version": ruleset.version, "status": ruleset.status, "checksum": ruleset.checksum},
            "finding_counts": {s.value: sum(1 for f in findings if f.severity == s) for s in Severity},
            "gate": {"id": GATE_ID, "name": GATE_NAME, "version": GATE_VERSION},
        },
    }


def _headline(state: str, findings: list[Finding], coverage: dict) -> str:
    if state == "URGENT":
        f = next(f for f in findings if f.severity == Severity.URGENT)
        return f"{f.summary} {f.next_steps[0] if f.next_steps else ''}".strip()
    flagged = [f for f in findings if SEVERITY_ORDER[f.severity] >= SEVERITY_ORDER[Severity.MONITOR]]
    if state in ("REVIEW", "MONITOR"):
        areas = sorted({f.agent_id for f in flagged if f.agent_id})
        return (f"{len(flagged)} finding(s) need attention across {len(areas)} analysis area(s). "
                + ("Qualified review is recommended." if state == "REVIEW" else "Follow the monitoring steps below."))
    if state == "INCOMPLETE":
        parts = []
        if coverage["failed_agents"]:
            parts.append("an analysis module failed")
        if coverage["missing_core_metrics"]:
            parts.append(f"{len(coverage['missing_core_metrics'])} core measurement(s) are missing")
        if coverage["insufficient_data_agents"]:
            parts.append("some areas lack enough history for comparison")
        return "Status unknown: " + ", ".join(parts) + ". No reassurance is given without complete data."
    return "All submitted measurements are within this crew member's configured monitoring criteria."


def template_explanation(findings: list[Finding], assessment: dict) -> list[dict]:
    """Deterministic plain-language explanation used when the LLM is unavailable or rejected."""
    statements: list[dict] = []
    used_chunks: set[str] = set()
    for f in findings:
        if SEVERITY_ORDER[f.severity] < SEVERITY_ORDER[Severity.MONITOR]:
            continue
        statements.append({"type": f.statement_type if f.statement_type != "limitation" else "observation",
                           "text": f.summary, "finding_codes": [f.code],
                           "citations": [r.chunk_id for r in f.knowledge_references[:1]], "source": "template"})
        for ref in f.knowledge_references[:1]:
            if ref.chunk_id in used_chunks:
                continue
            used_chunks.add(ref.chunk_id)
            statements.append({"type": "interpretation",
                               "text": f"Background ({ref.title}, “{ref.section}”): {ref.passage.split('. ')[0]}.",
                               "finding_codes": [f.code], "citations": [ref.chunk_id], "source": "template"})
    for a in assessment["next_actions"][:4]:
        statements.append({"type": "recommendation", "text": a["text"], "finding_codes": [a["finding_code"]],
                           "citations": [], "source": "template"})
    lims = assessment["coverage"]
    if not lims["complete"]:
        statements.append({"type": "limitation", "text": "Analysis coverage is incomplete, so the absence of a finding is not reassurance.",
                           "finding_codes": [], "citations": [], "source": "template"})
    if not statements:
        statements.append({"type": "observation", "text": assessment["headline"], "finding_codes": [], "citations": [],
                           "source": "template"})
    return statements[:12]
