"""
rppg.py — Remote Photoplethysmography (rPPG) signal extraction.

Implements the POS (Plane-Orthogonal-to-Skin) algorithm:
    Wang, W., den Brinker, A.C., Stuijk, S., & de Haan, G. (2017).
    "Algorithmic Principles of Remote PPG."
    IEEE Transactions on Biomedical Engineering.

POS is chosen over simple green-channel or CHROM because it:
  - Better handles illumination changes
  - Works reasonably on mobile cameras
  - Has a solid mathematical basis

The output is a 1-D temporal pulse signal from which heart rate
and respiration rate are estimated by downstream modules.
"""

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

# Physiologically plausible heart-rate band (Hz)
HR_FREQ_LOW  = 0.75   # 45 BPM
HR_FREQ_HIGH = 3.5    # 210 BPM

# Physiologically plausible respiration band (Hz)
RR_FREQ_LOW  = 0.1    # 6 breaths/min
RR_FREQ_HIGH = 0.5    # 30 breaths/min


def extract_rppg_signal(roi_matrix: np.ndarray, fps: float) -> dict:
    """
    Extract rPPG pulse signal using the POS algorithm.

    Args:
        roi_matrix: (N, 3) float array — mean [R, G, B] per frame
                    (use the 'combined' output from roi.build_roi_signal_matrix)
        fps:        Frames per second of the video

    Returns:
        {
          "signal":      1-D numpy array (N,) — normalised pulse signal,
          "fps":         float,
          "n_frames":    int,
          "duration_s":  float,
        }
    """
    if roi_matrix is None or len(roi_matrix) < int(fps * 2):
        # Need at least 2 seconds of data
        logger.warning("rPPG: insufficient frames (%d)", len(roi_matrix) if roi_matrix is not None else 0)
        return {"signal": np.array([]), "fps": fps, "n_frames": 0, "duration_s": 0.0}

    signal = _pos_algorithm(roi_matrix, fps)
    signal = _normalise_signal(signal)

    return {
        "signal":     signal,
        "fps":        fps,
        "n_frames":   len(signal),
        "duration_s": len(signal) / fps,
    }


def _pos_algorithm(C: np.ndarray, fps: float) -> np.ndarray:
    """
    POS rPPG algorithm.

    C: (N, 3) array of mean [R, G, B] traces.
    """
    eps = 1e-9
    N = len(C)

    # Window length ~1.6 seconds (same as original paper)
    l = max(int(fps * 1.6), 4)

    H = np.zeros(N)

    for n in range(l, N):
        # Temporal normalisation: divide each channel by its mean over window
        C_n = C[n - l: n]                           # (l, 3)
        mean_C = C_n.mean(axis=0) + eps             # (3,)
        C_norm = C_n / mean_C                       # (l, 3)

        # Project onto POS plane
        # S1 = Rn - Gn
        # S2 = Rn + Gn - 2*Bn
        S1 = C_norm[:, 0] - C_norm[:, 1]
        S2 = C_norm[:, 0] + C_norm[:, 1] - 2.0 * C_norm[:, 2]

        alpha = _std_safe(S1) / (_std_safe(S2) + eps)
        h = S1 + alpha * S2

        # Overlap-add
        H[n - l: n] += (h - h.mean())

    return H


def _std_safe(x: np.ndarray) -> float:
    return float(np.std(x)) if len(x) > 1 else 1e-9


def _normalise_signal(signal: np.ndarray) -> np.ndarray:
    """Zero-mean unit-variance normalisation."""
    std = np.std(signal)
    if std < 1e-9:
        return signal
    return (signal - np.mean(signal)) / std
