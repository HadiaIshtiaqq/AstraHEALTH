# Architecture

Modular monolith: one FastAPI process on `127.0.0.1` serves the API and the built React UI.

```
Crew member ──► React UI (Overview · Check-in · Trends · Digital Twin · Agents · Countermeasures · Reports · Settings)
                    │  HTTP on localhost only
                    ▼
FastAPI  ── validation (Pydantic + metric registry) ── netguard (blocks non-loopback sockets/DNS)
   │
   ▼
Orchestrator (run_id, correlation id, trace, per-agent timeout, failure isolation, persisted partial results)
   1 InputSense ─ 2 DataGuard ─ 3 BaselineIQ
   4 routed specialists in parallel: CardioGuard · NeuroMind · SleepSense · BoneGuard · NutriTrack · MissionContext
   5 AnomalyDetect (Isolation Forest + rolling robust z + CUSUM) when ≥2 health systems are submitted
   6 Safety & Evidence Gate: rule engine → severity · context rules (symptoms, cross-domain) · conflict detection
                             · TF-IDF evidence retrieval · overall state · next actions · alerts
   7 persist run  ──►  (background) optional local LLM explanation → JSON schema + safety guard → stored
   ▼
SQLite (observations raw + normalized, runs, agent results, alerts, tasks, audit, knowledge) · knowledge/index
```

## Agent routing

| Submitted | Agents |
|---|---|
| Heart rate / BP / temperature | DataGuard → BaselineIQ → CardioGuard |
| Sleep duration / quality | DataGuard → BaselineIQ → SleepSense |
| Mood / stress / fatigue | DataGuard → BaselineIQ → NeuroMind (+ SleepSense for fatigue) |
| Exercise / resistance / discomfort | DataGuard → BaselineIQ → BoneGuard |
| Fluid / appetite / mass / glucose | DataGuard → BaselineIQ → NutriTrack |
| Dosimeter record | MissionContext |
| Symptoms | Routed by body system |
| ≥2 health systems | + AnomalyDetect; ≥3 systems also adds MissionContext |

## Agent contracts

| Agent | Must not |
|---|---|
| CardioGuard | Diagnose arrhythmia or cardiovascular disease |
| NeuroMind | Diagnose depression, anxiety or cognitive impairment |
| SleepSense | Diagnose sleep disorders |
| BoneGuard | Claim bone-density loss or fracture risk without measurements |
| NutriTrack | Infer dehydration or deficiency from intake logs |
| AnomalyDetect | Call an anomaly an emergency by itself |
| MissionContext | Attribute a health change to a hazard |
| Safety & Evidence Gate | Let generated text override deterministic escalation, or prescribe treatment |

Every finding carries: code, summary, statement type (observation / interpretation / recommendation / limitation),
source observation IDs, rule IDs, severity, next steps, limitations and evidence references (or an explicit
"evidence unavailable" marker). Every run persists the model, rule-set, agent and index versions.

## Failure handling (architecture 3.7)

| Failure | Behaviour |
|---|---|
| Local LLM down / slow / invalid output | Deterministic template explanation; status shown; alerts unaffected |
| Agent exception or timeout | Marked failed; others continue; coverage incomplete → REVIEW (R-SYS-001) |
| Knowledge index unavailable | Findings shown with "evidence retrieval unavailable" |
| Malformed input | Rejected with per-field errors (HTTP 422); nothing saved |
| Implausible / stale / duplicate | Saved with flag, visible, excluded from analysis |
| Agents disagree | AGENT_CONFLICT → REVIEW (R-SYS-002) |
| No baseline | Values described, comparison marked unavailable, never "normal" |
