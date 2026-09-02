"""
quality.py — Signal Quality Metric (SQM) calculation.

Aggregates multiple quality signals into a single score and label.

Inputs considered:
  - Face tracking stability (% valid frames)
  - Motion level (LOW / MEDIUM / HIGH)
  - Signal-to-noise ratio of rPPG
  - Signal periodicity (autocorrelation peak)
  - Cross-ROI consistency (do ROIs agree?)
  - HR physiological plausibility
  - RR physiological plausibility
  - Lighting stability
"""

import logging
import numpy as np
from scipy.signal import correlate

logger = logging.getLogger(__name__)


def calculate_signal_quality(
    signal: np.ndarray,
    fps: float,
    hr_result: dict,
    rr_result: dict,
    motion_stats: dict,
    roi_signals: dict,
    valid_frame_ratio: float,
) -> dict:
    """
    Compute a Signal Quality Metric.

    Returns:
        {
          "signal_quality": "GOOD" | "FAIR" | "POOR" | "INVALID",
          "quality_score":  float 0.0–1.0,
          "reasons":        list[str],   — reasons for downgrade
        }
    """
    reasons = []
    scores  = []

    # ── 1. Valid frame ratio ────────────────────────────
    scores.append(min(valid_frame_ratio, 1.0))
    if valid_frame_ratio < 0.7:
        reasons.append("Too many dropped frames.")

    # ── 2. Motion ───────────────────────────────────────
    motion_level = motion_stats.get("motion_level", "HIGH")
    motion_score = {"LOW": 1.0, "MEDIUM": 0.6, "HIGH": 0.1}[motion_level]
    scores.append(motion_score)
    if motion_level == "HIGH":
        reasons.append("Excessive head movement.")
    elif motion_level == "MEDIUM":
        reasons.append("Moderate movement detected.")

    # ── 3. Signal SNR (ratio of band power to total power) ─
    snr_score = _compute_snr_score(signal, fps)
    scores.append(snr_score)
    if snr_score < 0.3:
        reasons.append("Weak rPPG signal.")

    # ── 4. Signal periodicity (autocorrelation) ─────────
    period_score = _compute_periodicity_score(signal, fps)
    scores.append(period_score)
    if period_score < 0.3:
        reasons.append("Signal lacks periodic structure.")

    # ── 5. Cross-ROI consistency ─────────────────────────
    roi_score = _compute_roi_consistency(roi_signals, fps)
    scores.append(roi_score)
    if roi_score < 0.4:
        reasons.append("ROI signals inconsistent.")

    # ── 6. HR confidence ────────────────────────────────
    hr_conf = hr_result.get("confidence", 0.0) if hr_result.get("valid") else 0.0
    scores.append(hr_conf)
    if hr_conf < 0.3:
        reasons.append("Low heart rate confidence.")

    # ── 7. RR confidence ────────────────────────────────
    rr_conf = rr_result.get("confidence", 0.0) if rr_result.get("valid") else 0.0
    scores.append(rr_conf * 0.7)   # weight RR lower (harder to estimate)

    # ── Aggregate ────────────────────────────────────────
    quality_score = float(np.mean(scores))

    if quality_score >= 0.65:
        label = "GOOD"
    elif quality_score >= 0.45:
        label = "FAIR"
    elif quality_score >= 0.25:
        label = "POOR"
    else:
        label = "INVALID"

    logger.info("SQM: %s (%.2f) | reasons: %s", label, quality_score, reasons)

    return {
        "signal_quality": label,
        "quality_score":  round(quality_score, 3),
        "reasons":        reasons,
    }


def _compute_snr_score(signal: np.ndarray, fps: float) -> float:
    """Ratio of power in HR band to total signal power."""
    if signal is None or len(signal) < 10:
        return 0.0
    try:
        from scipy.signal import welch
        from app.services.vitals.rppg import HR_FREQ_LOW, HR_FREQ_HIGH
        freqs, psd = welch(signal, fs=fps,
                           nperseg=min(len(signal), int(fps * 8)))
        mask = (freqs >= HR_FREQ_LOW) & (freqs <= HR_FREQ_HIGH)
        if not mask.any():
            return 0.0
        band_power  = psd[mask].sum()
        total_power = psd.sum()
        return float(min(band_power / (total_power + 1e-9) * 3.0, 1.0))
    except Exception:
        return 0.0


def _compute_periodicity_score(signal: np.ndarray, fps: float) -> float:
    """
    Measure signal periodicity via normalised autocorrelation.
    A periodic pulse signal has a strong secondary peak at lag ~1/HR.
    """
    if signal is None or len(signal) < 20:
        return 0.0
    try:
        s = signal - signal.mean()
        ac = correlate(s, s, mode="full")
        ac = ac[len(ac) // 2:]           # positive lags only
        ac_norm = ac / (ac[0] + 1e-9)

        # Look for peak in lag range corresponding to 45–210 BPM
        lag_min = int(fps * 60 / 210)
        lag_max = int(fps * 60 / 45)
        lag_min = max(lag_min, 1)
        lag_max = min(lag_max, len(ac_norm) - 1)

        if lag_max <= lag_min:
            return 0.0

        peak_val = float(ac_norm[lag_min:lag_max].max())
        return max(0.0, min(peak_val, 1.0))
    except Exception:
        return 0.0


def _compute_roi_consistency(roi_signals: dict, fps: float) -> float:
    """
    Compare G-channel traces across ROIs.
    High correlation = consistent signal = higher quality.
    """
    if not roi_signals or len(roi_signals) < 2:
        return 0.5   # neutral if can't compare

    try:
        traces = []
        for key in ("forehead", "left_cheek", "right_cheek"):
            arr = roi_signals.get(key)
            if arr is not None and len(arr) > 10:
                g = arr[:, 1]   # green channel
                g = (g - g.mean()) / (g.std() + 1e-9)
                traces.append(g)

        if len(traces) < 2:
            return 0.5

        # Mean pairwise correlation
        n = len(traces)
        cors = []
        for i in range(n):
            for j in range(i + 1, n):
                min_len = min(len(traces[i]), len(traces[j]))
                c = float(np.corrcoef(traces[i][:min_len],
                                      traces[j][:min_len])[0, 1])
                cors.append(c)
        mean_cor = float(np.mean(cors))
        return max(0.0, min(mean_cor, 1.0))
    except Exception:
        return 0.5


def is_measurement_reliable(quality: dict) -> bool:
    """Return True if quality is GOOD or FAIR."""
    return quality.get("signal_quality") in ("GOOD", "FAIR")
