# Camera Fix / Diagnostic

The camera pipeline was updated because the dashboard can show `NO SIGNAL` when
OpenCV cannot open the Windows webcam backend. Ghost Trail now tries:

1. the configured camera index with DirectShow;
2. the same index with Media Foundation;
3. the OpenCV default backend;
4. camera indices 0-3 as a recovery path when the configured local index fails.

The stream reader also uses normal frame reads and a small latest-frame queue,
so it does not rely on the previous grab/retrieve sequence.

## Diagnose the machine

From the Ghost Trail project root:

```bash
python test_camera.py
```

If no camera is found, check:

- Windows Settings → Privacy & security → Camera → camera access enabled.
- Close Teams/Zoom/OBS/browser tabs that may own the webcam.
- Check Device Manager → Cameras for the webcam driver.
- Try changing `source: 0` in `config.yaml` to the working index printed by the test.

## What the dashboard now reports

`GET /api/cameras` includes:

- `online`
- `actual_source`
- `backend`
- `error`

So an offline camera should expose a concrete diagnostic instead of only `NO SIGNAL`.
