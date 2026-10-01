# Flaw #6 — Explainable 0–100 Behavioral Risk Score

Ghost Trail no longer treats individual thresholds as direct risk labels. The behavior engine now calculates a normalized 0–100 score from independent evidence factors and derives the risk tier from that score.

## Factors

- Dwell time: up to 30 points
- Repeat passes: up to 25 points
- Cross-camera movement: up to 20 points
- Off-hours context: up to 15 points

The score is capped at 100.

## Default bands

- `0–29`: Normal
- `30–59`: Watch
- `60–79`: Suspicious
- `80–100`: High Risk

The `60` Suspicious threshold is also the biometric escalation gate.

## Why this is better

A single signal such as "person stayed for 45 seconds" cannot automatically trigger biometric processing. Multiple contextual signals can combine to cross the escalation threshold, making the decision explainable and configurable.

The alert payload now includes:

- `risk_score`
- `risk_tier`
- `risk_factors`

Example:

`Risk 72/100 — Dwell time (45s) +30, Repeat passes (3) +25, Cross-camera movement (3 zones) +20`

The Alerts dashboard renders the score and factor breakdown when these fields are available.

## Configuration

See `config.yaml` under `behavior:`. The score weights and score bands are configurable.

## Verification

`test_behavior_score.py` verifies that:

1. Normal activity remains low risk.
2. Dwell alone does not automatically reach biometric escalation.
3. Multiple independent signals can cross the escalation threshold.
4. The factor explanation contains the contributing evidence.
