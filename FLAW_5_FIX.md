# Flaw #5 Fix — Strict Anonymous-by-Default Biometric Escalation

## Previous issue

The tracker could invoke face extraction for a new track or on periodic retry before the behavior engine had classified the person as suspicious. That contradicted the product claim that biometric processing is behavior-gated.

## New policy

The production pipeline now follows one rule:

`Person detected -> body Re-ID only -> local behavior evaluated -> Suspicious/High-Risk -> face extraction allowed`

Face extraction is no longer triggered by:

- a newly created track
- periodic probe retries
- a previously reviewed identity
- an existing local name/global identity

The local behavior gate is evaluated before every possible face extraction.

## Changed files

- `sentinel_tracker.py` — removed `is_new_track`, `already_reviewed`, and periodic `retry_face` bypasses.
- `main.py` — aligned the CLI pipeline with the same behavior-gated face policy.
- `FLAW_5_FIX.md` — documents the policy.

## Verification

Python syntax should be checked with:

```bash
python -m py_compile sentinel_tracker.py main.py behavior_analyzer.py
```
