"""
respiration_rate.py — Respiration rate estimation.

Uses TWO complementary approaches and picks the more confident result:

1. rPPG-derived RR — respiratory modulation causes low-frequency
   amplitude/frequency modulation of the cardiac signal (RSA effect).

2. Landmark-based RR — vertical displacement of the nose tip or chin
   correlates with chest/head movement during breathing.
   This is independent of rPPG and works when the cardiac signal is weak.
"""

import logging
import numpy as np
from scipy.signal import butter, filtfilt, welch, find_peaks
from app.services.vitals.rppg import RR_FREQ_LOW, RR_FREQ_HIGH
from app.services.vitals.heart_rate import _bandpass_filter

logger = logging.getLogger(__name__)

RR_MIN = 6    # breaths/min
RR_MAX = 30   # breaths/min

# Nose tip landmark index in MediaPipe Face Mesh
NOSE_TIP_IDX = 4
CHIN_IDX     = 152


def estimate_respiration_rate(signal: np.ndarray,
                               fps: float,
                               landmark_history: list = None) -> dict:
    """
    Estimate respiration rate using rPPG + optional landmark motion.

    Args:
        signal:            1-D rPPG signal
        fps:               Frames per second
        landmark_history:  Optional list of (468,2) landmark arrays

    Returns:
        {
          "value":      int   — breaths/min (or None if invalid),
          "unit":       "breaths/minute",
          "confidence": float,
          "valid":      bool,
          "method":     "rppg" | "landmark" | "combined",
        }
    """
    invalid = {"value": None, "unit": "breaths/minute",
               "confidence": 0.0, "valid": False, "method": "none"}

    rppg_result     = _rr_from_rppg(signal, fps)
    landmark_result = _rr_from_landmarks(landmark_history, fps) if landmark_history else invalid

    # Pick the more confident result
    if (rppg_result["confidence"] >= landmark_result["confidence"] and
            rppg_result["valid"]):
        best = rppg_result
        best["method"] = "rppg"
    elif landmark_result["valid"]:
        best = landmark_result
        best["method"] = "landmark"
    else:
        return invalid

    logger.info("RR estimated: %d breaths/min | confidence=%.2f | method=%s",
                best["value"], best["confidence"], best["method"])
    return best


def _rr_from_rppg(signal: np.ndarray, fps: float) -> dict:
    """Extract respiratory component from rPPG signal via low-pass spectral analysis."""
    invalid = {"value": None, "unit": "breaths/minute", "confidence": 0.0, "valid": False}

    if signal is None or len(signal) < int(fps * 8):
        return invalid

    try:
        filtered = _bandpass_filter(signal, fps, RR_FREQ_LOW, RR_FREQ_HIGH)
        freqs, psd = welch(filtered, fs=fps,
                           nperseg=min(len(filtered), int(fps * 16)))

        mask = (freqs >= RR_FREQ_LOW) & (freqs <= RR_FREQ_HIGH)
        if not mask.any():
            return invalid

        band_psd  = psd[mask]
        band_freq = freqs[mask]
        peak_idx  = int(np.argmax(band_psd))
        rr_hz     = band_freq[peak_idx]
        rr_bpm    = int(round(rr_hz * 60))

        total = band_psd.sum()
        conf  = min(float(band_psd[peak_idx] / (total + 1e-9)) * 2.0, 1.0)

        if not (RR_MIN <= rr_bpm <= RR_MAX):
            return invalid

        return {"value": rr_bpm, "unit": "breaths/minute",
                "confidence": round(conf, 3), "valid": conf > 0.25}
    except Exception as exc:
        logger.error("RR from rPPG failed: %s", exc)
        return invalid


def _rr_from_landmarks(landmark_history: list, fps: float) -> dict:
    """Estimate respiration from nose-tip vertical displacement."""
    invalid = {"value": None, "unit": "breaths/minute", "confidence": 0.0, "valid": False}

    if not landmark_history or len(landmark_history) < int(fps * 8):
        return invalid

    try:
        # Extract nose-tip Y coordinate over time
        ys = []
        for lm in landmark_history:
            if lm is not None and len(lm) > NOSE_TIP_IDX:
                ys.append(float(lm[NOSE_TIP_IDX, 1]))
            else:
                ys.append(float("nan"))

        y_arr = np.array(ys)
        # Interpolate missing frames
        nans = np.isnan(y_arr)
        if nans.mean() > 0.5:
            return invalid
        good = np.where(~nans)[0]
        y_arr[nans] = np.interp(np.where(nans)[0], good, y_arr[good])

        filtered = _bandpass_filter(y_arr, fps, RR_FREQ_LOW, RR_FREQ_HIGH)
        freqs, psd = welch(filtered, fs=fps,
                           nperseg=min(len(filtered), int(fps * 16)))

        mask = (freqs >= RR_FREQ_LOW) & (freqs <= RR_FREQ_HIGH)
        if not mask.any():
            return invalid

        band_psd  = psd[mask]
        band_freq = freqs[mask]
        peak_idx  = int(np.argmax(band_psd))
        rr_hz     = band_freq[peak_idx]
        rr_bpm    = int(round(rr_hz * 60))

        total = band_psd.sum()
        conf  = min(float(band_psd[peak_idx] / (total + 1e-9)) * 2.0, 1.0)

        if not (RR_MIN <= rr_bpm <= RR_MAX):
            return invalid

        return {"value": rr_bpm, "unit": "breaths/minute",
                "confidence": round(conf, 3), "valid": conf > 0.25}
    except Exception as exc:
        logger.error("RR from landmarks failed: %s", exc)
        return invalid
