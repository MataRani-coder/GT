"""Verify the declared InsightFace/ONNX face-recognition stack before launch."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f) or {}

face_cfg = cfg.get("face_recognition", {})
required = bool(face_cfg.get("required", True))
model = face_cfg.get("model_name", "buffalo_l")

missing = [name for name in ("insightface", "onnxruntime") if importlib.util.find_spec(name) is None]

print("=== Ghost Trail Face Stack Check ===")
print(f"Required: {required}")
print(f"ArcFace model: {model}")

if missing:
    print("MISSING: " + ", ".join(missing))
    print("Install with: python -m pip install -r requirements.txt")
    sys.exit(1 if required else 0)

try:
    from face_recognizer import FaceRecognizer
    recognizer = FaceRecognizer(
        model_name=model,
        device=face_cfg.get("device", "cpu"),
        det_size=tuple(face_cfg.get("det_size", [320, 320])),
        face_sim_threshold=face_cfg.get("face_sim_threshold", 0.40),
        required=required,
    )
    print(f"Status: {recognizer.status}")
    print(f"Available: {recognizer.available}")
except Exception as exc:
    print(f"FAILED: {exc}")
    sys.exit(1)

print("Face-recognition stack check passed.")
