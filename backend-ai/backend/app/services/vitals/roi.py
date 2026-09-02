"""
roi.py — Region of Interest extraction from facial landmarks.

Extracts mean RGB values from forehead, left cheek, and right cheek.
These time-series RGB traces are the raw input to rPPG algorithms.
"""

import logging
import numpy as np
from typing import Optional
from app.services.vitals.face_detection import (
    FOREHEAD_TOP_INDICES,
    LEFT_CHEEK_INDICES,
    RIGHT_CHEEK_INDICES,
    _get_roi_pixels,
)

logger = logging.getLogger(__name__)


def extract_skin_rois(frame: np.ndarray,
                      landmarks: np.ndarray) -> Optional[dict]:
    """
    Extract mean RGB values from three facial skin ROIs.

    Args:
        frame:     BGR numpy array (H, W, 3)
        landmarks: Normalised (468, 2) landmark array from MediaPipe

    Returns:
        dict with keys: forehead, left_cheek, right_cheek
        Each value is a 3-element array [R, G, B] (float32)
        Returns None if extraction fails.
    """
    if landmarks is None or len(landmarks) == 0:
        return None

    h, w = frame.shape[:2]
    rgb = frame[:, :, ::-1].astype(np.float32)   # BGR → RGB

    try:
        forehead   = _mean_roi_rgb(rgb, landmarks, FOREHEAD_TOP_INDICES, w, h)
        left_cheek = _mean_roi_rgb(rgb, landmarks, LEFT_CHEEK_INDICES,   w, h)
        right_cheek= _mean_roi_rgb(rgb, landmarks, RIGHT_CHEEK_INDICES,  w, h)

        if forehead is None or left_cheek is None or right_cheek is None:
            return None

        return {
            "forehead":    forehead,
            "left_cheek":  left_cheek,
            "right_cheek": right_cheek,
        }
    except Exception as exc:
        logger.error("ROI extraction failed: %s", exc)
        return None


def _mean_roi_rgb(rgb_frame: np.ndarray,
                  landmarks: np.ndarray,
                  indices: list[int],
                  w: int, h: int) -> Optional[np.ndarray]:
    """Return mean [R, G, B] of pixels in the given landmark region."""
    pts = _get_roi_pixels(landmarks, indices, w, h)

    # Clamp to frame bounds
    pts[:, 0] = np.clip(pts[:, 0], 0, w - 1)
    pts[:, 1] = np.clip(pts[:, 1], 0, h - 1)

    if len(pts) < 5:
        return None

    pixels = rgb_frame[pts[:, 1], pts[:, 0]]   # (N, 3)
    return pixels.mean(axis=0)                   # [R_mean, G_mean, B_mean]


def build_roi_signal_matrix(roi_history: list[dict]) -> dict:
    """
    Convert a list of per-frame ROI dicts into channel arrays.

    Args:
        roi_history: list of dicts, each {"forehead": [R,G,B], ...}

    Returns:
        {
          "forehead":    ndarray shape (N, 3),
          "left_cheek":  ndarray shape (N, 3),
          "right_cheek": ndarray shape (N, 3),
          "combined":    ndarray shape (N, 3)   # mean of 3 ROIs
        }
    """
    forehead    = np.array([r["forehead"]    for r in roi_history], dtype=np.float32)
    left_cheek  = np.array([r["left_cheek"]  for r in roi_history], dtype=np.float32)
    right_cheek = np.array([r["right_cheek"] for r in roi_history], dtype=np.float32)
    combined    = (forehead + left_cheek + right_cheek) / 3.0

    return {
        "forehead":    forehead,
        "left_cheek":  left_cheek,
        "right_cheek": right_cheek,
        "combined":    combined,
    }
