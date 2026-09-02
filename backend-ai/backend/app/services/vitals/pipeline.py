"""
pipeline.py — Complete rPPG vital signs estimation pipeline.

Orchestrates:
    Video frames
        → Face detection (per frame)
        → ROI extraction
        → Motion scoring
        → rPPG signal (POS algorithm)
        → Motion artifact filtering
        → Heart rate estimation
        → Respiration rate estimation
        → Signal quality metric
        → Final result dict

Entry point: process_video(video_path, expected_fps)
"""

import logging
import os
import tempfile
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

# Maximum video duration accepted (seconds)
MAX_DURATION_S  = 30
# Target FPS for processing (downsample if camera FPS is higher)
TARGET_FPS      = 30
# Minimum duration needed for valid measurement
MIN_DURATION_S  = 8


def process_video(video_path: str) -> dict:
    """
    Run the full vital signs pipeline on a video file.

    Args:
        video_path: Path to the uploaded video (mp4/webm/ogg)

    Returns:
        Full result dict — see _build_result() for schema.
    """
    import cv2
    from app.services.vitals.face_detection import detect_face, extract_landmarks
    from app.services.vitals.roi import extract_skin_rois, build_roi_signal_matrix
    from app.services.vitals.motion_filter import calculate_motion_score, filter_motion_artifacts, check_motion_validity
    from app.services.vitals.rppg import extract_rppg_signal
    from app.services.vitals.heart_rate import estimate_heart_rate
    from app.services.vitals.respiration_rate import estimate_respiration_rate
    from app.services.vitals.quality import calculate_signal_quality, is_measurement_reliable

    logger.info("Vital pipeline starting | file=%s", video_path)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return _error_result("Could not open video file.")

    video_fps  = cap.get(cv2.CAP_PROP_FPS) or 30.0
    fps        = min(video_fps, TARGET_FPS)
    frame_skip = max(1, int(video_fps / fps))

    roi_history       = []
    landmark_history  = []
    frame_idx         = 0
    valid_face_frames = 0
    quality_issues    = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1

        # Only process every Nth frame to hit target fps
        if frame_idx % frame_skip != 0:
            continue

        # Duration cap
        elapsed = len(roi_history) / fps
        if elapsed > MAX_DURATION_S:
            break

        # Face detection
        face_result = detect_face(frame)
        if not face_result.face_detected:
            landmark_history.append(None)
            roi_history.append(None)
            if face_result.quality_message and face_result.quality_message != "OK":
                if face_result.quality_message not in quality_issues:
                    quality_issues.append(face_result.quality_message)
            continue

        if face_result.multiple_faces:
            landmark_history.append(None)
            roi_history.append(None)
            continue

        # ROI extraction
        rois = extract_skin_rois(frame, face_result.landmarks)
        if rois is None:
            landmark_history.append(None)
            roi_history.append(None)
            continue

        valid_face_frames += 1
        landmark_history.append(face_result.landmarks)
        roi_history.append(rois)

    cap.release()
    logger.info("Frames processed: %d | valid face: %d", len(roi_history), valid_face_frames)

    total_frames = len(roi_history)
    valid_ratio  = valid_face_frames / max(total_frames, 1)
    duration_s   = total_frames / fps

    # Minimum data check
    if duration_s < MIN_DURATION_S or valid_face_frames < int(fps * MIN_DURATION_S * 0.5):
        return _error_result(
            "Insufficient data. Please ensure your face is visible "
            "for at least 8 seconds with good lighting.",
            quality_issues=quality_issues,
        )

    # Build ROI signal matrix (skip None frames)
    valid_rois = [r for r in roi_history if r is not None]
    roi_matrix_dict = build_roi_signal_matrix(valid_rois)
    roi_combined = roi_matrix_dict["combined"]   # (N, 3)

    # Motion scoring
    motion_stats = calculate_motion_score(landmark_history)
    motion_valid, motion_msg = check_motion_validity(motion_stats)
    if not motion_valid:
        return _error_result(motion_msg, quality_issues=quality_issues)

    # rPPG signal extraction
    rppg_result = extract_rppg_signal(roi_combined, fps)
    raw_signal  = rppg_result["signal"]

    if len(raw_signal) == 0:
        return _error_result("rPPG signal extraction failed. Please try again.",
                             quality_issues=quality_issues)

    # Motion artifact filtering
    motion_scores = motion_stats["per_frame_motion"]
    # Align motion scores to valid frames
    valid_motion = [motion_scores[i] for i, r in enumerate(roi_history)
                    if r is not None and i < len(motion_scores)]
    cleaned_signal = filter_motion_artifacts(raw_signal, valid_motion)

    # Heart rate
    hr_result = estimate_heart_rate(cleaned_signal, fps)

    # Respiration rate
    valid_landmarks = [l for l in landmark_history if l is not None]
    rr_result = estimate_respiration_rate(cleaned_signal, fps, valid_landmarks)

    # Signal quality
    quality = calculate_signal_quality(
        signal            = cleaned_signal,
        fps               = fps,
        hr_result         = hr_result,
        rr_result         = rr_result,
        motion_stats      = motion_stats,
        roi_signals       = roi_matrix_dict,
        valid_frame_ratio = valid_ratio,
    )

    # Build final result
    if not is_measurement_reliable(quality):
        return {
            "status":          "invalid",
            "signal_quality":  quality["signal_quality"],
            "quality_score":   quality["quality_score"],
            "message":         "Unable to obtain a reliable camera-based estimate. "
                               "Please try again with better lighting and keep your face still.",
            "quality_issues":  quality["reasons"] + quality_issues,
            "measurement_duration": round(duration_s, 1),
            "algorithm_version":    "v1-pos",
        }

    return {
        "status": "success",
        "heart_rate": {
            "value":      hr_result["value"],
            "unit":       "bpm",
            "confidence": hr_result["confidence"],
        },
        "respiration_rate": {
            "value":      rr_result["value"],
            "unit":       "breaths/minute",
            "confidence": rr_result["confidence"],
        },
        "signal_quality":        quality["signal_quality"],
        "quality_score":         quality["quality_score"],
        "measurement_duration":  round(duration_s, 1),
        "algorithm_version":     "v1-pos",
        "disclaimer": (
            "These are experimental camera-based estimates. "
            "They are NOT medical-grade measurements and should not "
            "replace professional medical assessment."
        ),
    }


def _error_result(message: str, quality_issues: list = None) -> dict:
    return {
        "status":         "invalid",
        "signal_quality": "INVALID",
        "quality_score":  0.0,
        "message":        message,
        "quality_issues": quality_issues or [],
        "measurement_duration": 0.0,
        "algorithm_version":    "v1-pos",
    }
