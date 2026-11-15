"""Versioned deterministic rule engine — the only component that assigns severity."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas.models import SEVERITY_ORDER, AgentResult, Finding, Severity


AREA_NAMES = {"cardio_guard": "heart & circulation", "neuro_mind": "wellbeing", "sleep_sense": "sleep",
              "bone_guard": "exercise & muscles", "nutri_track": "nutrition & fluids"}


def _get_path(obj: Any, dotted: str) -> Any:
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
    return cur


def _matches(value: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return value in expected
    if isinstance(expected, dict):
        ok = True
        if "gte" in expected:
            ok &= value is not None and value >= expected["gte"]
        if "lte" in expected:
            ok &= value is not None and value <= expected["lte"]
        return ok
    return value == expected


class RuleSet:
    def __init__(self, data: dict, checksum: str):
        self.data = data
        self.version: str = data["version"]
        self.status: str = data.get("status", "")
        self.checksum = checksum
        defaults = data.get("defaults", {})
        self.rules: list[dict] = [{**defaults, **r} for r in data["rules"]]
        self.by_id = {r["rule_id"]: r for r in self.rules}

    @classmethod
    def load(cls, path: Path) -> "RuleSet":
        raw = path.read_bytes()
        return cls(json.loads(raw), hashlib.sha256(raw).hexdigest()[:16])

    # ---------------------------------------------------------------- per-finding rules
    def apply_to_finding(self, finding: Finding) -> Finding:
        matched = []
        for rule in self.rules:
            if rule["type"] != "finding":
                continue
            cond = rule["condition"]
            if cond.get("finding_code") != finding.code:
                continue
            where = cond.get("where", {})
            if all(_matches(_get_path(finding, k), v) for k, v in where.items()):
                matched.append(rule)
        if matched:
            top = max(matched, key=lambda r: SEVERITY_ORDER[Severity(r["severity"])])
            finding.severity = Severity(top["severity"])
            finding.rule_ids = [r["rule_id"] for r in matched]
            finding.next_steps = list(dict.fromkeys(r["next_step"] for r in matched))
            finding.requires_human_review = any(r.get("requires_human_review") for r in matched)
        else:
            finding.severity = Severity.INFO
            finding.rule_ids = []
        return finding

    # ---------------------------------------------------------------- context rules
    def context_findings(self, symptoms: set[str], findings: list[Finding], agent_results: list[AgentResult],
                         symptom_obs_ids: dict[str, list[str]]) -> list[Finding]:
        out: list[Finding] = []
        specialists = {"cardio_guard", "neuro_mind", "sleep_sense", "bone_guard", "nutri_track"}
        for rule in self.rules:
            if rule["type"] != "context":
                continue
            cond = rule["condition"]
            hit: list[str] = []
            if "symptoms_any" in cond:
                hit = sorted(set(cond["symptoms_any"]) & symptoms)
                if not hit:
                    continue
            elif "symptoms_all" in cond:
                if not set(cond["symptoms_all"]) <= symptoms:
                    continue
                hit = sorted(cond["symptoms_all"])
            elif "requires_finding" in cond:
                if not any(f.code == cond["requires_finding"] for f in findings):
                    continue
                flagged_agents = {
                    f.agent_id for f in findings
                    if f.agent_id in specialists and SEVERITY_ORDER[f.severity] >= SEVERITY_ORDER[Severity.MONITOR]
                }
                if len(flagged_agents) < cond.get("min_specialists_flagged", 2):
                    continue
                hit = sorted(flagged_agents)
            else:
                continue
            evidence = [i for s in hit for i in symptom_obs_ids.get(s, [])]
            if "requires_finding" in cond:
                evidence = sorted({i for f in findings if f.agent_id in hit or f.code == cond["requires_finding"]
                                   for i in f.evidence_observation_ids})
            if "requires_finding" in cond:
                summary = (f"{rule['title']}: an unusual combination of signals together with changes in "
                           + ", ".join(AREA_NAMES.get(h, h.replace('_', ' ')) for h in hit) + ".")
            else:
                summary = f"{rule['title']}: " + ", ".join(h.replace('_', ' ') for h in hit) + "."
            out.append(Finding(
                code=rule["finding_code"],
                summary=summary,
                statement_type="interpretation",
                evidence_observation_ids=evidence,
                data={"matched": hit, "rule_id": rule["rule_id"]},
                severity=Severity(rule["severity"]),
                rule_ids=[rule["rule_id"]],
                next_steps=[rule["next_step"]],
                requires_human_review=bool(rule.get("requires_human_review")),
                agent_id="safety_gate",
                limitations=["Rule is a demonstration placeholder pending clinical review."],
            ))
        return out

    def rule(self, rule_id: str) -> dict | None:
        return self.by_id.get(rule_id)

    def describe(self) -> dict:
        return {"version": self.version, "status": self.status, "checksum": self.checksum,
                "notes": self.data.get("notes"), "rules": self.rules}


@lru_cache(maxsize=1)
def get_ruleset() -> RuleSet:
    return RuleSet.load(settings.ruleset_path)
