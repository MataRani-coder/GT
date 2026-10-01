from __future__ import annotations

import argparse
import time
from collections import defaultdict
from typing import Any, Dict, List

import cv2
import numpy as np
import yaml

from alert_manager import AlertManager, ALERT_CONTEXTUAL_OBJECT, ALERT_THREAT_OBJECT, ALERT_UNKNOWN_PERSON
from behavior_analyzer import BehaviorAnalyzer
from object_context import ObjectContextEngine
from database import IdentityDatabase
from detector import YoloDetector
from face_recognizer import FaceRecognizer
from identity_manager import GlobalIdentityManager
from stream_manager import StreamManager
from tracker import (
    DeepReIDExtractor,
    ReIDCandidate,
    ReIDMicroBatcher,
    SingleCameraTracker,
    annotate_tracked_objects,
    make_grid_with_offline,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ghost Trail (baseline CLI) — Multi-Camera Perimeter Tracking")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to YAML config")
    return parser.parse_args()


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_source(raw_source: Any) -> Any:
    if isinstance(raw_source, str) and raw_source.isdigit():
        return int(raw_source)
    return raw_source


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)

    camera_configs = cfg["cameras"]
    for camera_cfg in camera_configs:
        camera_cfg["source"] = _parse_source(camera_cfg["source"])

    detector = YoloDetector(
        weights=cfg["model"]["weights"],
        device=cfg["model"].get("device", "auto"),
        conf_thres=cfg["model"].get("conf_thres", 0.40),
        iou_thres=cfg["model"].get("iou_thres", 0.45),
        classes=cfg["model"].get("classes"),
    )
    class_map = detector.class_name_map()

    stream_manager = StreamManager(camera_configs=camera_configs, stream_cfg=cfg["stream"])
    all_camera_ids = [str(cam["camera_id"]) for cam in camera_configs]
    trackers = {
        cam["camera_id"]: SingleCameraTracker(**cfg["tracker"])
        for cam in camera_configs
    }

    reid_enabled = bool(cfg.get("reid", {}).get("enabled", True))
    db = IdentityDatabase(cfg["database"]["db_path"])

    # ── Body Re-ID extractor (OSNet) ─────────────────────────────────
    feature_encoder = DeepReIDExtractor(
        model_name=cfg["reid"].get("model_name", "osnet_x1_0"),
        model_weights=cfg["reid"].get("reid_model_weights"),
        device=cfg["reid"].get("device", cfg["model"].get("device", "cpu")),
        input_size=tuple(cfg["reid"].get("input_size", [256, 128])),
    )

    # ── Face recognizer (ArcFace via InsightFace) ────────────────────
    face_cfg = cfg.get("face_recognition", {})
    face_recognizer = FaceRecognizer(
        model_name=face_cfg.get("model_name", "buffalo_sc"),
        device=face_cfg.get("device", cfg["reid"].get("device", "cpu")),
        det_size=tuple(face_cfg.get("det_size", [320, 320])),
        face_sim_threshold=face_cfg.get("face_sim_threshold", 0.40),
        required=bool(face_cfg.get("required", True)),
    )

    # ── Identity manager (dual-model, vote-based) ───────────────────
    global_manager = GlobalIdentityManager(
        db=db,
        face_recognizer=face_recognizer,
        face_threshold=face_cfg.get("face_threshold", 0.52),
        confirm_frames=cfg["reid"].get("confirm_frames", 10),
        body_registered_threshold=cfg["reid"].get("body_registered_threshold", 0.90),
        body_guest_threshold=cfg["reid"].get("body_guest_threshold", 0.55),
        max_time_gap_sec=cfg["reid"].get("max_time_gap_sec", 30.0),
        guest_handoff_grace_sec=cfg["reid"].get("guest_handoff_grace_sec", 10.0),
        guest_handoff_body_threshold=cfg["reid"].get("guest_handoff_body_threshold", 0.44),
        guest_handoff_face_threshold=cfg["reid"].get("guest_handoff_face_threshold", 0.50),
        max_gallery_size=cfg["reid"].get("max_gallery_size", 2000),
        guest_face_threshold=cfg["reid"].get("guest_face_threshold", 0.55),
        registered_face_stitch_threshold=cfg["reid"].get("registered_face_stitch_threshold", 0.60),
        camera_handoff_max_gap_sec=cfg["reid"].get("camera_handoff_max_gap_sec", 12.0),
        camera_adjacency=cfg.get("identity_stitching", {}).get("camera_adjacency", {}),
    )

    reid_batcher = ReIDMicroBatcher(
        max_wait_ms=cfg["reid"].get("micro_batch_max_wait_ms", 15.0),
        max_batch_size=cfg["reid"].get("micro_batch_max_size", 64),
    )

    # ── Alert system ─────────────────────────────────────────────────
    alert_cfg = cfg.get("alerts", {})
    alert_manager = AlertManager(
        cooldown_sec=alert_cfg.get("cooldown_sec", 5.0),
    )

    # Privacy gate: the CLI pipeline follows the same anonymous-by-default
    # policy as the dashboard pipeline. Face recognition is only allowed after
    # local behavior reaches the configured Suspicious tier.
    behavior_cfg = cfg.get("behavior", {})
    behavior_analyzer = BehaviorAnalyzer(
        watch_dwell_sec=behavior_cfg.get("watch_dwell_sec", 8.0),
        suspicious_dwell_sec=behavior_cfg.get("suspicious_dwell_sec", 20.0),
        high_risk_dwell_sec=behavior_cfg.get("high_risk_dwell_sec", 45.0),
        off_hours_start=behavior_cfg.get("off_hours_start", 22),
        off_hours_end=behavior_cfg.get("off_hours_end", 6),
        reentry_high_risk=behavior_cfg.get("reentry_high_risk", 3),
        zone_hop_window_sec=behavior_cfg.get("zone_hop_window_sec", 90.0),
        dwell_weight=behavior_cfg.get("dwell_weight", 30),
        reentry_weight=behavior_cfg.get("reentry_weight", 25),
        zone_weight=behavior_cfg.get("zone_weight", 20),
        off_hours_weight=behavior_cfg.get("off_hours_weight", 15),
        score_watch=behavior_cfg.get("score_watch", 30),
        score_suspicious=behavior_cfg.get("score_suspicious", 60),
        score_high=behavior_cfg.get("score_high", 80),
    )
    object_cfg = cfg.get("object_monitoring", {})
    object_monitoring_classes = set(int(c) for c in object_cfg.get("monitored_classes", [2, 24, 26, 28]))
    contextual_object_classes = set(int(c) for c in object_cfg.get("contextual_alert_classes", [24, 26, 28]))
    object_context = ObjectContextEngine(
        monitored_classes=object_monitoring_classes,
        contextual_alert_classes=contextual_object_classes,
        unattended_sec=object_cfg.get("unattended_sec", 10.0),
        stationary_speed_px_sec=object_cfg.get("stationary_speed_px_sec", 18.0),
        person_proximity_ratio=object_cfg.get("person_proximity_ratio", 1.5),
    )

    local_global_map: Dict[str, Dict[int, int]] = defaultdict(dict)
    local_name_map: Dict[str, Dict[int, str]] = defaultdict(dict)
    last_fps_time = time.time()
    frame_counter = 0
    fps = 0.0

    stream_manager.start_all()
    print("[INFO] Streams started. Press 'q' to exit.")
    print("[INFO] Alert system active — watching for threats and unknown persons.")

    try:
        while True:
            latest_packets = stream_manager.get_latest_frames()
            if not latest_packets:
                time.sleep(0.005)
                continue

            tracked_by_camera: Dict[str, Any] = {}
            frame_by_camera: Dict[str, np.ndarray] = {}
            ready_batches: List[List[ReIDCandidate]] = []

            person_class_id = cfg["reid"].get("person_class_id", 0)
            rendered_frames: Dict[str, np.ndarray] = {}

            # Tick alert manager — remove expired alerts
            alert_manager.tick()

            # ── Phase 1: detect + track per camera ───────────────────
            for camera_id, packet in latest_packets.items():
                frame = packet.frame
                detections = detector.infer(frame)
                tracked = trackers[camera_id].update(detections)
                tracked_by_camera[camera_id] = tracked
                frame_by_camera[camera_id] = frame

                track_ids = tracked.tracker_id if tracked.tracker_id is not None else np.array([], dtype=int)
                class_ids = tracked.class_id if tracked.class_id is not None else np.array([], dtype=int)
                behavior_analyzer.cleanup_local(camera_id, track_ids.tolist())

                # Object-of-interest detection is informational until contextual conditions are met.
                person_boxes = [tracked.xyxy[i] for i in range(len(tracked)) if i < len(class_ids) and int(class_ids[i]) == person_class_id]
                active_object_keys = set()
                for i in range(len(tracked)):
                    if i >= len(class_ids) or i >= len(track_ids):
                        continue
                    cls = int(class_ids[i])
                    tid = int(track_ids[i])
                    if cls == person_class_id or cls not in object_monitoring_classes or tid < 0:
                        continue
                    active_object_keys.add((camera_id, tid))
                    context = object_context.update(camera_id, tid, cls, tracked.xyxy[i], time.time(), person_boxes)
                    if context.get("context_alert"):
                        cls_name = class_map.get(cls, f"class_{cls}")
                        alert_manager.trigger(
                            alert_type=ALERT_CONTEXTUAL_OBJECT,
                            camera_id=camera_id,
                            message=f"Contextual Object Alert — {cls_name.upper()}",
                            detail=f"{cls_name} remained stationary without a nearby person for {context['duration_sec']:.1f}s on {camera_id}.",
                            entity_id=f"object:{tid}",
                        )
                object_context.cleanup(active_object_keys, camera_id)

                for i in range(len(tracked)):
                    tid = int(track_ids[i]) if i < len(track_ids) else -1
                    cls = int(class_ids[i]) if i < len(class_ids) else -1
                    if tid < 0 or cls < 0:
                        continue

                    xyxy = tracked.xyxy[i]
                    x1, y1, x2, y2 = xyxy.astype(int)
                    area = max(0, (x2 - x1)) * max(0, (y2 - y1))
                    if area < cfg["reid"].get("min_box_area", 2000):
                        continue

                    if reid_enabled and cls == person_class_id:
                        maybe_ready = reid_batcher.add((camera_id, tid, xyxy, frame, packet.timestamp))
                        if maybe_ready:
                            ready_batches.append(maybe_ready)
                    else:
                        gid = int(f"{abs(hash(camera_id)) % 9999}{tid}")
                        local_global_map[camera_id][tid] = gid
                        local_name_map[camera_id][tid] = class_map.get(cls, "Object")

            if reid_enabled:
                due_batch = reid_batcher.flush_due()
                if due_batch:
                    ready_batches.append(due_batch)

                # ── Phase 2: batch body Re-ID + face embedding ────────
                for candidate_batch in ready_batches:
                    batch_inputs = [(frame, xyxy) for _, _, xyxy, frame, _ in candidate_batch]
                    try:
                        batch_body_embeddings = feature_encoder.encode_batch(batch_inputs)
                    except Exception as exc:
                        print(f"[WARN] Batched ReID extraction failed - {exc}")
                        batch_body_embeddings = [None] * len(candidate_batch)

                    for idx, (camera_id, tid, xyxy, _frame, timestamp) in enumerate(candidate_batch):
                        body_feature = batch_body_embeddings[idx]

                        # Strict privacy gate: body Re-ID runs first, but face
                        # extraction is withheld until local behavior reaches the
                        # configured Suspicious tier. New tracks and periodic
                        # retries cannot bypass this gate.
                        escalate_to_face = behavior_analyzer.should_escalate_to_face(
                            camera_id, tid, timestamp
                        )
                        face_feature = None
                        if escalate_to_face and face_recognizer.available:
                            try:
                                face_feature = face_recognizer.get_face_embedding_from_frame(
                                    _frame, xyxy
                                )
                            except Exception as exc:
                                print(f"[WARN] Face embedding failed after behavior escalation - {exc}")

                        gid, gname = global_manager.assign_identity(
                            camera_id=camera_id,
                            local_track_id=tid,
                            body_embedding=body_feature,
                            face_embedding=face_feature,
                            timestamp=timestamp,
                            bbox_xyxy=xyxy,
                        )
                        local_global_map[camera_id][tid] = gid
                        local_name_map[camera_id][tid] = gname

                        # ── Unknown person alert ──────────────────────
                        if gname.startswith("Guest"):
                            alert_manager.trigger(
                                alert_type=ALERT_UNKNOWN_PERSON,
                                camera_id=camera_id,
                                message="Unknown Person Detected",
                                detail=f"{gname} spotted on {camera_id}",
                            )

            # ── Phase 3: render bounding boxes + labels ───────────────
            for camera_id, tracked in tracked_by_camera.items():
                frame = frame_by_camera[camera_id]
                rendered = annotate_tracked_objects(
                    frame=frame,
                    detections=tracked,
                    class_name_map=class_map,
                    global_ids=local_global_map[camera_id],
                    global_names=local_name_map[camera_id],
                    camera_id=camera_id,
                    threat_class_ids=object_monitoring_classes,
                    flash_on=False,  # alert_manager handles all flashing
                    show_fps=cfg["ui"].get("show_fps", True),
                    fps=fps,
                )
                # ── Phase 4: overlay alert visuals ────────────────────
                rendered = alert_manager.render_onto(rendered, camera_id)
                rendered_frames[camera_id] = rendered

            frame_counter += len(rendered_frames)
            now = time.time()
            elapsed = now - last_fps_time
            if elapsed >= 1.0:
                fps = frame_counter / elapsed
                frame_counter = 0
                last_fps_time = now

            grid = make_grid_with_offline(
                camera_ids=all_camera_ids,
                frames_by_camera=rendered_frames,
                max_view_width=cfg["ui"].get("max_view_width", 640),
                offline_size=tuple(cfg["ui"].get("offline_tile_size", [640, 360])),
                pulse_on=bool(int(time.time() * 2) % 2 == 0),
            )
            cv2.imshow(cfg["ui"].get("window_name", "Ghost Trail - Perimeter Defense"), grid)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

    finally:
        stream_manager.stop_all()
        db.close()
        cv2.destroyAllWindows()
        print("[INFO] Shutdown complete.")


if __name__ == "__main__":
    main()
