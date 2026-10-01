"""Ghost Trail webcam diagnostic.

Run on Windows from the project root:
    python test_camera.py

It checks camera indices 0-3 with DirectShow, Media Foundation and the
OpenCV default backend, and prints the first backend that returns a frame.
"""
from __future__ import annotations

import cv2


def main() -> int:
    found = []
    backends = [
        (getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY), "DirectShow"),
        (getattr(cv2, "CAP_MSMF", cv2.CAP_ANY), "MediaFoundation"),
        (getattr(cv2, "CAP_ANY", 0), "OpenCV-default"),
    ]

    print("Ghost Trail camera diagnostic")
    print("Checking camera indices 0-3...\n")

    for index in range(4):
        for backend, name in backends:
            cap = None
            try:
                cap = cv2.VideoCapture(index, backend)
                opened = cap.isOpened()
                ok, frame = cap.read() if opened else (False, None)
                if ok and frame is not None and frame.size:
                    h, w = frame.shape[:2]
                    print(f"[OK] camera {index}: {name} -> {w}x{h}")
                    found.append((index, name))
                    cap.release()
                    break
                print(f"[--] camera {index}: {name} -> opened={opened}, frame={ok}")
            except Exception as exc:
                print(f"[!!] camera {index}: {name} -> {exc}")
            finally:
                if cap is not None:
                    cap.release()

    print()
    if found:
        print("Working camera(s):")
        for index, backend in found:
            print(f"  index={index}, backend={backend}")
        print("Set config.yaml source to the working index if Ghost Trail does not auto-detect it.")
        return 0

    print("No working camera was found.")
    print("Check Windows Settings > Privacy & security > Camera and make sure camera access is enabled.")
    print("Also close Teams, Zoom, OBS, browser camera tabs, or other applications using the webcam.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
