# Principles of Self-Monitoring and Escalation

> ASTRAHEALTH educational note (team-authored summary for a hackathon prototype). Not an official NASA document.

## Repeat before reacting
An unexpected measurement should usually be repeated under standard conditions before it is interpreted. Recording the time, posture, device and recent activity makes the repeat measurement meaningful.

## Data quality first
Measurements with missing units, impossible values, duplicated entries or old timestamps should be flagged and corrected rather than silently accepted or discarded. Unusual values are kept and marked for confirmation because they may be exactly the ones that need attention.

## Anomalies are prompts, not diagnoses
Statistical anomaly detection highlights unusual patterns relative to a person's own history. It can be wrong, especially with limited data, and an anomaly or unusual combination of signals is a prompt for follow-up rather than a medical conclusion.

## Unknown is not normal
When data are missing or an analysis fails, the correct status is unknown or incomplete. Monitoring tools should never show a reassuring status in the absence of data.

## Human oversight and escalation
Decision-support tools assist crew members and medical staff. Urgent symptoms, persistent changes and conflicting results should be escalated to the onboard medical officer and, when communication allows, to the ground flight surgeon.
