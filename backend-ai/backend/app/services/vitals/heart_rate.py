"""
heart_rate.py — Heart rate estimation from rPPG signal.

Pipeline:
    Raw rPPG signal
        ↓
    Band-pass filter (0.75 – 3.5 Hz → 45–210 BPM)
        ↓
    FFT frequency analysis
        ↓
    Dominant frequency → BPM
        ↓
    Confidence score
"""

import logging
import numpy as np
from scipy.signal import butter, filtfilt, welch
from app.services.vitals.rppg import HR_FREQ_LOW, HR_FREQ_HIGH

logger = logging.getLogger(__name__)

# Physiologically plausible HR range for confidence check
HR_MIN_BPM = 45
HR_MAX_BPM = 210


def estimate_heart_rate(signal: np.ndarray, fps: float) -> dict:
    """
    Estimate heart rate from an rPPG signal.

    Args:
        signal: 1-D numpy array — normalised rPPG signal
        fps:    Frames per second

    Returns:
        {
          "value":      int   — heart rate in BPM  (or None if invalid),
          "unit":       "bpm",
          "confidence": float — 0.0–1.0,
          "valid":      bool,
        }
    """
    invalid = {"value": None, "unit": "bpm", "confidence": 0.0, "valid": False}

    if signal is None or len(signal) < int(fps * 5):
        logger.warning("HR: signal too short (%d frames)", len(signal) if signal is not None else 0)
        return invalid

    try:
        # 1. Band-pass filter
        filtered = _bandpass_filter(signal, fps, HR_FREQ_LOW, HR_FREQ_HIGH)

        # 2. Welch power spectral density — more robust than plain FFT on short signals
        freqs, psd = welch(filtered, fs=fps, nperseg=min(len(filtered), int(fps * 8)))

        # 3. Restrict to HR band
        mask = (freqs >= HR_FREQ_LOW) & (freqs <= HR_FREQ_HIGH)
        if not mask.any():
            return invalid

        band_freqs = freqs[mask]
        band_psd   = psd[mask]

        # 4. Dominant frequency
        peak_idx  = int(np.argmax(band_psd))
        peak_freq = band_freqs[peak_idx]
        hr_bpm    = int(round(peak_freq * 60))

        # 5. Confidence — ratio of peak power to total band power
        total_power = band_psd.sum()
        peak_power  = band_psd[peak_idx]
        spectral_purity = float(peak_power / (total_power + 1e-9))
        confidence = min(spectral_purity * 1.5, 1.0)   # scale to 0–1 range

        # 6. Plausibility check
        if not (HR_MIN_BPM <= hr_bpm <= HR_MAX_BPM):
            logger.warning("HR estimate outside plausible range: %d BPM", hr_bpm)
            return invalid

        logger.info("HR estimated: %d BPM | confidence=%.2f", hr_bpm, confidence)
        return {
            "value":      hr_bpm,
            "unit":       "bpm",
            "confidence": round(confidence, 3),
            "valid":      confidence > 0.3,
        }

    except Exception as exc:
        logger.error("Heart rate estimation failed: %s", exc)
        return invalid


def _bandpass_filter(signal: np.ndarray,
                     fps: float,
                     low_hz: float,
                     high_hz: float,
                     order: int = 4) -> np.ndarray:
    """Apply Butterworth band-pass filter."""
    nyq = fps / 2.0
    low  = low_hz  / nyq
    high = high_hz / nyq
    low  = max(low,  1e-4)
    high = min(high, 0.9999)
    b, a = butter(order, [low, high], btype="band")
    return filtfilt(b, a, signal)
