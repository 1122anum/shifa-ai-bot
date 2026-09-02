"""
motion_filter.py — Motion artifact detection and filtering.

Estimates head/facial movement from landmark displacement between frames.
Excessive motion degrades rPPG signal quality and should be flagged.
"""

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

# Max acceptable mean landmark displacement per frame (normalised 0–1 coords)
# ~0.01 = roughly 1% of frame width — allows minor natural movement
MOTION_THRESHOLD_SOFT = 0.008   # FAIR quality flag
MOTION_THRESHOLD_HARD = 0.025   # POOR/invalid flag


def calculate_motion_score(landmark_history: list[Optional[np.ndarray]]) -> dict:
    """
    Calculate per-frame motion scores and overall motion statistics.

    Args:
        landmark_history: list of (468,2) arrays or None for missing frames

    Returns:
        {
          "per_frame_motion": list of floats,
          "mean_motion": float,
          "max_motion": float,
          "motion_level": "LOW" | "MEDIUM" | "HIGH",
          "valid_frames": int,
          "total_frames": int,
        }
    """
    per_frame = []
    valid_count = 0

    for i in range(1, len(landmark_history)):
        prev = landmark_history[i - 1]
        curr = landmark_history[i]

        if prev is None or curr is None:
            per_frame.append(float("nan"))
            continue

        valid_count += 1
        # Mean Euclidean displacement across all 468 landmarks
        displacement = np.linalg.norm(curr - prev, axis=1).mean()
        per_frame.append(float(displacement))

    valid_scores = [s for s in per_frame if not np.isnan(s)]
    mean_motion = float(np.mean(valid_scores)) if valid_scores else 1.0
    max_motion  = float(np.max(valid_scores))  if valid_scores else 1.0

    if mean_motion < MOTION_THRESHOLD_SOFT:
        level = "LOW"
    elif mean_motion < MOTION_THRESHOLD_HARD:
        level = "MEDIUM"
    else:
        level = "HIGH"

    return {
        "per_frame_motion": per_frame,
        "mean_motion":      mean_motion,
        "max_motion":       max_motion,
        "motion_level":     level,
        "valid_frames":     valid_count,
        "total_frames":     len(landmark_history),
    }


def filter_motion_artifacts(signal: np.ndarray,
                             motion_scores: list,
                             threshold: float = MOTION_THRESHOLD_HARD) -> np.ndarray:
    """
    Replace high-motion frames with linearly interpolated values.

    Args:
        signal:        1-D rPPG signal array (N,)
        motion_scores: per-frame motion scores (length N or N-1)
        threshold:     motion above this value → frame marked bad

    Returns:
        Cleaned signal with artifact frames interpolated.
    """
    if len(signal) == 0:
        return signal

    cleaned = signal.copy().astype(np.float64)
    bad_mask = np.zeros(len(cleaned), dtype=bool)

    # Align motion scores with signal length
    for i, score in enumerate(motion_scores):
        if i < len(cleaned) and not np.isnan(score) and score > threshold:
            bad_mask[i] = True

    # Interpolate bad frames
    good_idx = np.where(~bad_mask)[0]
    if len(good_idx) < 2:
        return cleaned  # not enough good frames to interpolate

    bad_idx = np.where(bad_mask)[0]
    cleaned[bad_idx] = np.interp(bad_idx, good_idx, cleaned[good_idx])

    removed = int(bad_mask.sum())
    if removed > 0:
        logger.debug("Motion filter: %d/%d frames cleaned", removed, len(signal))

    return cleaned


def check_motion_validity(motion_stats: dict) -> tuple[bool, str]:
    """
    Determine if motion level is acceptable for valid measurement.

    Returns:
        (is_valid: bool, reason: str)
    """
    level = motion_stats.get("motion_level", "HIGH")
    valid_ratio = (motion_stats.get("valid_frames", 0) /
                   max(motion_stats.get("total_frames", 1), 1))

    if valid_ratio < 0.5:
        return False, "Too many frames lost during tracking. Please keep your face visible."

    if level == "HIGH":
        return False, "Too much movement detected. Please keep your face still."

    return True, "OK"
