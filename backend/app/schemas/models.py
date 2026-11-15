"""Typed contracts (Pydantic) for API payloads and agent messages."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "INFO"
    MONITOR = "MONITOR"
    REVIEW = "REVIEW"
    URGENT = "URGENT"


SEVERITY_ORDER = {Severity.INFO: 0, Severity.MONITOR: 1, Severity.REVIEW: 2, Severity.URGENT: 3}


def max_severity(values: list[Severity]) -> Severity:
    return max(values, key=lambda s: SEVERITY_ORDER[s]) if values else Severity.INFO


AgentStatus = Literal["completed", "review", "insufficient_data", "failed", "skipped"]
StatementType = Literal["observation", "interpretation", "recommendation", "limitation"]
QualityStatus = Literal[
    "valid", "invalid", "implausible", "stale", "duplicate", "pending_confirmation", "self_reported"
]


# ---------------------------------------------------------------- observations
class ObservationIn(BaseModel):
    metric_code: str = Field(..., min_length=1, max_length=64)
    value: float | int | str | bool | None = None
    unit: str | None = None
    measured_at: str | None = None
    source: str | None = "manual"
    method: str | None = None
    context: str | None = Field(None, description="e.g. resting, post_exercise, seated")
    confirmed: bool = True


class CheckinIn(BaseModel):
    profile_id: str
    observations: list[ObservationIn] = Field(..., min_length=1)
    mode: Literal["manual", "conversation", "import", "simulated"] = "manual"
    notes: str | None = Field(None, max_length=2000)
    raw_input_text: str | None = Field(None, max_length=4000)
    run_analysis: bool = True


class ParseTextIn(BaseModel):
    profile_id: str
    text: str = Field(..., min_length=1, max_length=4000)


class AnalysisRunIn(BaseModel):
    profile_id: str
    checkin_id: str | None = None
    requested_agents: list[str] | None = None
    simulate_failure: list[str] = Field(default_factory=list, description="Demo only: agents to force-fail")
    generate_explanation: bool = True


class ProfileIn(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=80)
    role: str | None = None
    mission_id: str = "NONE"  # real profiles are not on the fictional demo mission
    timezone: str = "UTC"
    settings: dict[str, Any] = Field(default_factory=dict)


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    role: str | None = None
    timezone: str | None = None
    settings: dict[str, Any] | None = None


class ReportIn(BaseModel):
    profile_id: str
    start: str | None = None
    end: str | None = None


class AckIn(BaseModel):
    actor_role: Literal["crew", "medical_officer", "flight_surgeon", "admin"] = "crew"
    note: str | None = Field(None, max_length=500)
    pin: str | None = Field(None, max_length=32, description="Medical officer PIN; required for URGENT alerts")


class ConfirmIn(BaseModel):
    note: str | None = Field(None, max_length=500)
    pin: str | None = Field(None, max_length=32, description="Medical officer PIN; required for implausible values")
    actor_role: Literal["crew", "medical_officer"] = "crew"
    rerun: bool = True


class CorrectIn(BaseModel):
    value: float | int | str
    unit: str
    reason: str = Field(..., min_length=3, max_length=300)
    rerun: bool = True
    pin: str | None = Field(None, max_length=32, description="Medical officer PIN; required for symptoms or values older than 24 h")


class RetractIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=300)
    rerun: bool = True
    pin: str | None = Field(None, max_length=32, description="Medical officer PIN; required for symptoms or values older than 24 h")


class ImportIn(BaseModel):
    profile_id: str
    format: Literal["csv", "json"] = "csv"
    content: str = Field(..., min_length=1, max_length=2_000_000)
    dry_run: bool = False


class DeviceRecordsIn(BaseModel):
    profile_id: str
    records: list[dict[str, Any]] = Field(..., min_length=1, max_length=5000)


class EncryptedExportIn(BaseModel):
    format: Literal["pdf", "csv", "html"] = "pdf"
    passphrase: str = Field(..., min_length=10, max_length=200)


class TaskCompleteIn(BaseModel):
    note: str | None = Field(None, max_length=500)


# ---------------------------------------------------------------- agents
class KnowledgeRef(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    publisher: str
    section: str
    version: str | None = None
    publication_date: str | None = None
    passage: str
    score: float
    relevance_note: str


class Finding(BaseModel):
    code: str
    summary: str
    statement_type: StatementType = "observation"
    metric_codes: list[str] = Field(default_factory=list)
    evidence_observation_ids: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    # Assigned by the rule engine, never by an agent's free-form opinion or the LLM.
    severity: Severity = Severity.INFO
    rule_ids: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    knowledge_references: list[KnowledgeRef] = Field(default_factory=list)
    evidence_status: Literal["not_requested", "found", "unavailable"] = "not_requested"
    agent_id: str | None = None
    certainty: Literal["strong", "moderate", "limited", "self-reported"] | None = None
    certainty_reasons: list[str] = Field(default_factory=list)


class MetricAssessment(BaseModel):
    """An agent's directional read of one metric, used for cross-agent conflict checks."""

    metric_code: str
    assessment: Literal["stable", "changed", "unknown"]
    detail: str = ""


class AgentResult(BaseModel):
    run_id: str
    agent_id: str
    agent_name: str
    agent_version: str
    status: AgentStatus
    input_observation_ids: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    assessments: list[MetricAssessment] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    limitations: list[str] = Field(default_factory=list)
    activation_reason: str = ""
    method: str = ""
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0.0
    created_at: str = ""
