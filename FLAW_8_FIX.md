# Flaw #8 — Contextual Object Assessment

## Problem
The previous implementation treated selected YOLO classes as threats immediately. A backpack, car, handbag, or suitcase is not inherently a threat.

## Fix
Ghost Trail now separates:

1. **Object of Interest** — YOLO detected a configured class. This is informational and can be rendered/tracked.
2. **Contextual Object Alert** — an alert is emitted only when configured contextual evidence is present.

Default unattended-object rule:
- Classes: backpack/bag (24), handbag (26), suitcase/luggage (28)
- Object remains stationary for at least 10 seconds
- No nearby person is present
- The same tracked object must satisfy the rule before an alert is generated

Vehicles (class 2) are monitored by default but do not trigger the unattended-object alert rule.

## Result
`OBJECT OF INTEREST: BACKPACK` is not presented as `THREAT DETECTED`.
A `CONTEXTUAL OBJECT ALERT` contains the observed evidence and duration.
