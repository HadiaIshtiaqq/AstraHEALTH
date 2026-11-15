# Test report

Run all tests with `scripts\run_tests.ps1`. Results from 14 Nov 2026 on the target laptop:

- **Backend (pytest):** 83 passed, 0 failed. Temporary database; the LLM path is tested with a stubbed model.
- **Frontend unit (Vitest):** 4 passed (formatting, time-zone day boundaries, labels).
- **Browser (Playwright):** 28 passed, 0 failed: 7 user flows and 7 WCAG 2.2 A/AA audits (axe-core), each in Microsoft Edge and Google Chrome. Separate server and database on port 8799.
- **Offline verification (`scripts/verify_offline.ps1`):** all checks passed. The server and Ollama listen only on loopback, and there were no external connections during a full workflow.

## Backend coverage
- **Functional TC-001 … TC-016:** validation, units, stale and implausible values, baselines, agent failure, LLM
  stopped, conflicts, export, offline guard, persistence, reset.
- **Safety AI-01 … AI-08 + TC-011:** no downgrade of escalation, document injection, invented thresholds,
  diagnosis and medication, invalid JSON, missing data never green, synthetic labelling, no fabricated citations.
- **Regression tests for every flaw found in review (`tests/test_fixes.py`):**

| Flaw | Test |
|---|---|
| 1 | A re-reported urgent symptom always escalates. |
| 2 | The crew can't dismiss URGENT; a wrong PIN is rejected; the medical officer PIN works. |
| 3 | InputSense: "hrs" is not heart rate; no positive mood next to symptoms; exercise sessions are summed; post-exercise context is detected. |
| 4 | The guard blocks implied diagnoses and causal claims. |
| 5 | Implausible values can be confirmed with the medical officer PIN. |
| 6 | Corrections supersede (no double counting); re-entered sleep replaces, not sums. |
| 7 | The demo clock shift keeps seeded data current. |
| 8 | Day boundaries use the crew member's timezone. |
| 10 | Alerts are de-duplicated (occurrence count) and MONITOR items consolidated. |
| 11 | No spurious agent conflicts on the seeded profiles. |
| 12 | A submitted check-in completes the check-in task. |
| 13 | One LLM generation at a time (409); interrupted explanations are recovered at startup. |
| 14 | Destructive endpoints require the admin PIN. |
| 15 | Content-Security-Policy restricts the browser to the local server. |
| 16 | PDF export is valid; the encrypted export round-trips; a wrong passphrase fails. |
| 17 | CSV import validates rows, skips bad ones and is not "stale"; the device adapter works. |

- **New features:**
  - care plan generated, non-prescriptive, goals relative to the personal baseline, adopt is idempotent
  - no self-care plan in an URGENT state
  - certainty grades with reasons on findings
  - LLM limitation and recommendation statements must be grounded

- **Round 3 (`tests/test_round3.py`):**
  - retracting an urgent symptom needs the medical officer, and the state stays URGENT while the alert is open
  - one notification per urgent event
  - PIN lockout (429 after 5 wrong attempts)
  - PINs hashed and free text encrypted at rest
  - idempotent double submit
  - Overview baselines cover every metric
  - care-plan progress and task removal
  - crew-friendly wording
  - backups respect disk space
  - InputSense ranges ("in the 80s") and neutral mood
  - every LLM statement must be grounded

- **Round 4 (`tests/test_round4.py`):**
  - demo scenarios, fault injection and imports need the admin PIN; imports reject symptoms
  - wrong PINs cause only a bounded 60 s cool-down, after which the real PIN works, and failures are audited
  - all secret keys wrapped (DPAPI)
  - the hash-chained audit log detects tampering
  - the demo clock shift leaves the audit log untouched
  - backups are encrypted and restorable
  - the guard blocks new clinical concepts
  - the full LLM pipeline runs with a stubbed model
  - 16 concurrent check-ins are all saved

## Browser end-to-end (`frontend/e2e/app.spec.ts`)
1. The overview shows state and labels, with a notification bell instead of banners.
2. Navigation is crew-relevant only (no AI Agents or Settings).
3. Manual check-in shows inline BP validation, then saves, analyses and shows a care plan.
4. URGENT shows a persistent pill; a wrong PIN is rejected; the medical officer PIN clears it.
5. A care-plan item is added to the routine.
6. Keyboard users can skip to content.
7. A 390 px phone viewport has no horizontal scroll.

## Still manual
- A physical Wi-Fi-off rehearsal on the presentation laptop (the software check above passes).
- A screen-reader pass (the automated WCAG audit passes).

> Earth-Link (delay-tolerant ground handoff) was removed at the team's request; its tests were removed with it.
