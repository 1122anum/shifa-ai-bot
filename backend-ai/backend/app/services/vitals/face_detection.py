"""
face_detection.py — Face detection and landmark extraction using MediaPipe.

Uses MediaPipe Face Mesh for:
  - Face presence detection
  - 468 facial landmarks
  - Face bounding box
  - Quality pre-checks (size, centering, lighting)
"""

import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy import mediapipe — allows module to load even if mp not installed yet
_mp = None
_mp_face_mesh = None
_face_mesh = None


def _get_face_mesh():
    global _mp, _mp_face_mesh, _face_mesh
    if _face_mesh is None:
        import mediapipe as mp
        _mp = mp
        _mp_face_mesh = mp.solutions.face_mesh
        _face_mesh = _mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=2,          # detect up to 2 to flag multiple-face condition
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
    return _face_mesh


@dataclass
class FaceDetectionResult:
    face_detected: bool = False
    multiple_faces: bool = False
    landmarks: Optional[np.ndarray] = None   # shape (468, 2) — normalised x,y
    bbox: Optional[tuple] = None             # (x1, y1, x2, y2) pixel coords
    face_size_ok: bool = False
    centered_ok: bool = False
    lighting_ok: bool = False
    quality_message: str = ""


# Landmark indices for key skin ROI regions
FOREHEAD_INDICES = [10, 338, 297, 332, 284, 251, 389, 356, 454,
                    323, 361, 288, 397, 365, 379, 378, 400, 377,
                    152, 148, 176, 149, 150, 136, 172, 58, 132,
                    93, 234, 127, 162, 21, 54, 103, 67, 109]

LEFT_CHEEK_INDICES  = [234, 93, 132, 58, 172, 136, 150, 149, 176,
                       148, 152, 377, 400, 378, 379, 365, 397, 288]

RIGHT_CHEEK_INDICES = [454, 323, 361, 288, 397, 365, 379, 378, 400,
                       377, 152, 148, 176, 149, 150, 136, 172, 58]

# Subset for forehead-only (more stable)
FOREHEAD_TOP_INDICES = [10, 338, 297, 332, 284, 251, 389, 356,
                        109, 67, 103, 54, 21, 162, 127, 234]


def detect_face(frame: np.ndarray) -> FaceDetectionResult:
    """
    Run face detection and landmark extraction on a single BGR frame.

    Args:
        frame: BGR numpy array (H, W, 3)

    Returns:
        FaceDetectionResult with all quality checks populated.
    """
    result = FaceDetectionResult()
    h, w = frame.shape[:2]

    try:
        import mediapipe as mp
        face_mesh = _get_face_mesh()
        rgb = frame[:, :, ::-1]  # BGR → RGB
        mp_result = face_mesh.process(rgb)
    except Exception as exc:
        logger.error("MediaPipe face detection failed: %s", exc)
        result.quality_message = "Face detection unavailable."
        return result

    if not mp_result.multi_face_landmarks:
        result.quality_message = "Face not detected. Please position your face inside the frame."
        return result

    if len(mp_result.multi_face_landmarks) > 1:
        result.face_detected = True
        result.multiple_faces = True
        result.quality_message = "Please make sure only one person is visible."
        return result

    # Single face found
    result.face_detected = True
    face_lm = mp_result.multi_face_landmarks[0]

    # Convert normalised landmarks → pixel coords (store normalised for ROI)
    lm_array = np.array([[lm.x, lm.y] for lm in face_lm.landmark])
    result.landmarks = lm_array  # normalised [0,1]

    # Bounding box in pixels
    xs = lm_array[:, 0] * w
    ys = lm_array[:, 1] * h
    x1, y1 = int(xs.min()), int(ys.min())
    x2, y2 = int(xs.max()), int(ys.max())
    result.bbox = (x1, y1, x2, y2)

    face_w = x2 - x1
    face_h = y2 - y1

    # ── Quality checks ──────────────────────────────────

    # 1. Face size (must occupy at least 15% of frame width)
    min_face_fraction = 0.15
    result.face_size_ok = (face_w / w) >= min_face_fraction
    if not result.face_size_ok:
        result.quality_message = "Please move closer to the camera."
        return result

    # 2. Face centering (centre of face within middle 60% of frame)
    cx = (x1 + x2) / 2 / w
    cy = (y1 + y2) / 2 / h
    result.centered_ok = (0.2 < cx < 0.8) and (0.1 < cy < 0.9)
    if not result.centered_ok:
        result.quality_message = "Please centre your face in the frame."
        return result

    # 3. Lighting check — mean brightness of forehead ROI
    result.lighting_ok = _check_lighting(frame, lm_array, w, h)
    if not result.lighting_ok:
        result.quality_message = "Lighting is too low. Please move to a brighter location."
        return result

    result.quality_message = "OK"
    return result


def _check_lighting(frame: np.ndarray,
                    landmarks: np.ndarray,
                    w: int, h: int) -> bool:
    """Return True if mean brightness of forehead region is acceptable."""
    try:
        import cv2
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        pts = _get_roi_pixels(landmarks, FOREHEAD_TOP_INDICES, w, h)
        if len(pts) == 0:
            return True  # can't check, assume ok
        brightness = float(gray[pts[:, 1], pts[:, 0]].mean())
        return 40 < brightness < 230   # reject very dark or over-exposed
    except Exception:
        return True  # don't block on lighting check failure


def _get_roi_pixels(landmarks: np.ndarray,
                    indices: list[int],
                    w: int, h: int) -> np.ndarray:
    """Return Nx2 pixel coordinate array for given landmark indices."""
    pts = landmarks[indices] * np.array([w, h])
    return pts.astype(int)


def extract_landmarks(frame: np.ndarray) -> Optional[np.ndarray]:
    """
    Quick landmark extraction returning normalised (468, 2) array or None.
    Used by motion filter to track inter-frame displacement.
    """
    result = detect_face(frame)
    return result.landmarks if result.face_detected and not result.multiple_faces else None
