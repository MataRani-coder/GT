# Ghost Trail — Evaluation & Benchmarking

Ghost Trail does **not** ship invented accuracy claims. The evaluation harness calculates metrics from ground-truth annotations and prediction logs supplied by the team.

## Metrics

- **Detection:** precision, recall, F1 using configurable IoU (default 0.50).
- **Cross-camera Re-ID:** pairwise precision, recall, specificity and F1.
- **Risk engine:** precision, recall, specificity and F1 for the configured escalation threshold (default 60/100).
- **Latency:** mean, median, p95, p99, min and max in milliseconds.

## Quick sanity check

```bash
python evaluate.py --self-test
```

The self-test is a tiny synthetic fixture. **Its numbers are not product performance and must not be used in the pitch.**

## Real benchmark

### Detection
Create two JSON files containing lists of:

```json
[
  {"frame_id": 1, "class_id": 0, "bbox": [x1, y1, x2, y2]}
]
```

Then:

```bash
python evaluate.py --gt-detections ground_truth.json --pred-detections predictions.json --iou 0.50 --out reports/detection.json
```

### Re-ID
Create rows such as:

```json
[
  {"ground_truth_same_identity": 1, "predicted_same_identity": 1},
  {"ground_truth_same_identity": 1, "predicted_same_identity": 0}
]
```

Run:

```bash
python evaluate.py --reid reid_pairs.json --out reports/reid.json
```

### Risk engine
Use:

```json
[
  {"ground_truth_risky": 1, "risk_score": 74},
  {"ground_truth_risky": 0, "risk_score": 21}
]
```

Run:

```bash
python evaluate.py --risk risk_labels.json --threshold 60 --out reports/risk.json
```

### Latency
Put one measured inference latency in milliseconds per line:

```text
31.4
29.8
34.1
```

Run:

```bash
python evaluate.py --latency latency_ms.csv --out reports/latency.json
```

## Recommended hackathon test protocol

Use a held-out set of short recordings rather than tuning and evaluating on the same clips. Include:

1. Different people and clothing combinations.
2. Different camera angles and lighting.
3. Partial occlusions.
4. Camera handoffs.
5. Normal traffic and deliberately labeled security scenarios.
6. False-alarm cases such as long but legitimate dwell time.

Record the dataset version, camera count, resolution, hardware, model versions, thresholds and date alongside every report.

## What to put on the pitch slide

Only publish values generated from a real benchmark. A useful slide is:

| Metric | Measured result |
|---|---:|
| Detection precision | **run benchmark** |
| Detection recall | **run benchmark** |
| Cross-camera Re-ID F1 | **run benchmark** |
| Risk escalation F1 | **run benchmark** |
| Median latency | **run benchmark** |
| P95 latency | **run benchmark** |
| False alerts/hour | **add event-count benchmark** |

Never replace `run benchmark` with an estimate.
