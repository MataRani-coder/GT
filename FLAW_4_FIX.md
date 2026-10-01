# Flaw #4 — InsightFace dependency and biometric capability integrity

## Fixed

- Added `insightface>=0.7.3` to `requirements.txt`.
- Added `onnxruntime>=1.17.0` for the CPU ArcFace runtime.
- Added `face_recognition.required: true` to `config.yaml`.
- `FaceRecognizer` no longer silently falls back to OSNet when biometric recognition is required.
- Startup now fails clearly if InsightFace, ONNX Runtime, or the configured ArcFace model cannot be initialized.
- Added `check_face_stack.py` for an explicit preflight check.
- `/api/status` now exposes face-recognition availability, model, status, and initialization error.

## Expected behavior

If the biometric stack is unavailable, Ghost Trail reports an error instead of presenting the system as if ArcFace face verification is active.

Install dependencies with:

```bash
python -m pip install -r requirements.txt
python check_face_stack.py
```

The default model is `buffalo_l`, configured in `config.yaml`. InsightFace may need to download its model assets on first initialization.
