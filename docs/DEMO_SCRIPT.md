# 4-minute demo script

**Before presenting:**
1. Run `scripts\start.ps1` and open http://127.0.0.1:8765.
2. Ask for one explanation to warm the LLM.
3. Have the medical officer and admin PINs from `backend/data/INITIAL_SECRETS.txt` (noted down, then the file
   deleted). The demo-scenario buttons ask for the admin PIN once.
4. Run `scripts\verify_offline.ps1 -AdminPin <pin>`; it should report all checks passed.
5. Disconnect Wi-Fi.

| Time | Step | Show |
|---|---|---|
| 0:00–0:30 | **Mission context** | Crew Alpha Overview: ARES-01 day 42, "LOCAL · OFFLINE", "SYNTHETIC DATA", "Within configured monitoring criteria". Every value has a unit, a timestamp and the personal usual range. |
| 0:30–1:00 | **Check-in** | Check-in → AI conversation → pick an example prompt (e.g. "Tired and short sleep") → Interpret locally. Extracted values, "no chest pain" recognised as negated, clarification questions. Confirm and submit. |
| 1:00–1:50 | **Detection** | Overview → scenario "Gradual multi-signal change". Qualified review is recommended. Open a finding → **certainty** ("Strong evidence: 30 days of history, seen over several days, corroborated by AnomalyDetect"), the evidence passage and the limitations. |
| 1:50–2:30 | **What to do** | **Care Plan**: five recommendations with steps and goals tied to her own usual range (e.g. "sleep back within 6.6–7.7 h for 3 nights"). Add "Protected sleep window" to the routine and show it under Routine. |
| 2:30–3:20 | **Urgent event** | Overview → scenario "Potential urgent event" (admin PIN). One red notification, an URGENT state, and no self-care plan, only "contact the medical officer now". Show that the crew cannot clear it and that retracting the symptom needs the medical officer. |
| 3:20–4:00 | **Safety & offline** | The medical officer PIN clears the alert (a wrong PIN is rejected). Reports → PDF and encrypted PDF. The footer's "system" link shows the network guard is on, all with Wi-Fi off. |

**Closing line:** "ASTRAHEALTH knows what changed, how sure it is, and what to do next. Safety rules decide, and the
AI only explains."
