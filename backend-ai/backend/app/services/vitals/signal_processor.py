"""
signal_processor.py — Pure Python/NumPy/SciPy signal processing for rPPG.

Receives pre-extracted RGB signal arrays from the browser (which runs
MediaPipe Face Mesh via CDN) and computes:
  - Heart rate (POS algorithm + Welch PSD)
  - Respiration rate (low-frequency rPPG modulation + nose-tip Y motion)
  - Signal quality metric

No OpenCV or server-side MediaPipe needed.
"""

import logging
import numpy as np
from scipy.signal import butter, filtfilt, welch
from scipy.signal import correlate
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Physiological constants ─────────────────────────────────────
HR_FREQ_LOW   = 0.75    # 45 BPM
HR_FREQ_HIGH  = 3.5     # 210 BPM
RR_FREQ_LOW   = 0.1     # 6 breaths/min
RR_FREQ_HIGH  = 0.5     # 30 breaths/min
HR_MIN_BPM    = 45
HR_MAX_BPM    = 210
RR_MIN        = 6
RR_MAX        = 30
MIN_FRAMES    = 150     # ~5 seconds at 30fps minimum
MIN_DURATION  = 8.0     # seconds


# ── Input / Output schemas ───────────────────────────────────────
@dataclass
class RGBFrame:
    """Per-frame mean RGB from forehead, left cheek, right cheek."""
    r: float
    g: float
    b: float
    nose_y: Optional[float] = None      # normalised nose-tip Y (for RR)
    motion: Optional[float] = None      # per-frame motion score from browser


@dataclass
class VitalResult:
    status: str                          # "success" | "invalid"
    heart_rate: Optional[dict] = None
    respiration_rate: Optional[dict] = None
    signal_quality: str = "INVALID"
    quality_score: float = 0.0
    measurement_duration: float = 0.0
    algorithm_version: str = "v1-pos-browser"
    disclaimer: str = (
        "These are experimental camera-based estimates. "
        "They are NOT medical-grade measurements and should not "
        "replace professional medical assessment."
    )
    message: str = ""
    quality_issues: list = field(default_factory=list)


# ── Main entry point ─────────────────────────────────────────────
def process_rgb_signal(
    frames: list[RGBFrame],
    fps: float,
) -> VitalResult:
    """
    Run the full rPPG pipeline on browser-extracted RGB frames.

    Args:
        frames: List of RGBFrame — one per processed video frame
        fps:    Actual frames-per-second of the capture

    Returns:
        VitalResult with heart_rate, respiration_rate, signal_quality
    """
    n = len(frames)
    duration = n / fps

    logger.info("Signal processor started | frames=%d | fps=%.1f | duration=%.1fs",
                n, fps, duration)

    # ── Minimum data check ────────────────────────────────────────
    if n < MIN_FRAMES or duration < MIN_DURATION:
        return VitalResult(
            status="invalid",
            signal_quality="INVALID",
            message=(
                f"Insufficient data ({duration:.1f}s). "
                "Please hold still for at least 8 seconds with good lighting."
            ),
        )

    # ── Build RGB matrix ──────────────────────────────────────────
    rgb = np.array([[f.r, f.g, f.b] for f in frames], dtype=np.float32)  # (N,3)

    # ── Motion mask ───────────────────────────────────────────────
    motion_scores = [f.motion if f.motion is not None else 0.0 for f in frames]
    motion_arr    = np.array(motion_scores, dtype=np.float32)
    mean_motion   = float(motion_arr.mean())
    max_motion    = float(motion_arr.max())

    if mean_motion > 0.06:   # browser normalises 0–1
        return VitalResult(
            status="invalid",
            signal_quality="INVALID",
            message="Too much movement detected. Please keep your face still.",
        )

    # ── rPPG signal (POS algorithm) ────────────────────────────────
    raw_signal = _pos_algorithm(rgb, fps)
    if raw_signal is None or len(raw_signal) < 10:
        return VitalResult(
            status="invalid",
            signal_quality="INVALID",
            message="rPPG signal extraction failed. Please try again.",
        )

    # ── Motion artifact filter ────────────────────────────────────
    cleaned = _filter_motion_artifacts(raw_signal, motion_arr, threshold=0.04)

    # ── Heart rate ────────────────────────────────────────────────
    hr_result = _estimate_heart_rate(cleaned, fps)

    # ── Respiration rate ──────────────────────────────────────────
    nose_ys = [f.nose_y for f in frames if f.nose_y is not None]
    rr_result = _estimate_respiration_rate(cleaned, fps, nose_ys)

    # ── Signal quality ────────────────────────────────────────────
    quality = _calculate_quality(
        signal       = cleaned,
        fps          = fps,
        hr_result    = hr_result,
        rr_result    = rr_result,
        mean_motion  = mean_motion,
        valid_ratio  = 1.0 - float((motion_arr > 0.04).mean()),
    )

    if quality["signal_quality"] in ("POOR", "INVALID"):
        return VitalResult(
            status        = "invalid",
            signal_quality= quality["signal_quality"],
            quality_score = quality["quality_score"],
            message       = (
                "Unable to obtain a reliable camera-based estimate. "
                "Please try again with better lighting and keep your face still."
            ),
            quality_issues= quality["reasons"],
            measurement_duration = round(duration, 1),
        )

    return VitalResult(
        status       = "success",
        heart_rate   = {
            "value":      hr_result["value"],
            "unit":       "bpm",
            "confidence": hr_result["confidence"],
        } if hr_result["valid"] else None,
        respiration_rate = {
            "value":      rr_result["value"],
            "unit":       "breaths/minute",
            "confidence": rr_result["confidence"],
        } if rr_result["valid"] else None,
        signal_quality       = quality["signal_quality"],
        quality_score        = quality["quality_score"],
        measurement_duration = round(duration, 1),
    )


# ── POS Algorithm ────────────────────────────────────────────────
def _pos_algorithm(C: np.ndarray, fps: float) -> Optional[np.ndarray]:
    """Plane-Orthogonal-to-Skin (Wang et al. 2017)."""
    eps = 1e-9
    N = len(C)
    l = max(int(fps * 1.6), 4)
    H = np.zeros(N, dtype=np.float64)

    for n in range(l, N):
        Cn     = C[n - l: n]
        mean_C = Cn.mean(axis=0) + eps
        Cn     = Cn / mean_C
        S1     = Cn[:, 0] - Cn[:, 1]
        S2     = Cn[:, 0] + Cn[:, 1] - 2.0 * Cn[:, 2]
        std2   = float(np.std(S2)) + eps
        alpha  = float(np.std(S1)) / std2
        h      = S1 + alpha * S2
        H[n - l: n] += (h - h.mean())

    std_H = np.std(H)
    if std_H < 1e-9:
        return None
    return (H - H.mean()) / std_H


# ── Butterworth band-pass ─────────────────────────────────────────
def _bandpass(signal: np.ndarray, fps: float,
              low: float, high: float, order: int = 4) -> np.ndarray:
    nyq  = fps / 2.0
    b, a = butter(order, [max(low / nyq, 1e-4), min(high / nyq, 0.9999)], btype="band")
    return filtfilt(b, a, signal)


# ── Motion artifact filter ────────────────────────────────────────
def _filter_motion_artifacts(signal: np.ndarray,
                              motion: np.ndarray,
                              threshold: float = 0.04) -> np.ndarray:
    cleaned  = signal.copy()
    bad      = motion > threshold
    good_idx = np.where(~bad)[0]
    bad_idx  = np.where(bad)[0]
    if len(good_idx) >= 2 and len(bad_idx) > 0:
        cleaned[bad_idx] = np.interp(bad_idx, good_idx, cleaned[good_idx])
    return cleaned


# ── Heart rate ────────────────────────────────────────────────────
def _estimate_heart_rate(signal: np.ndarray, fps: float) -> dict:
    invalid = {"value": None, "unit": "bpm", "confidence": 0.0, "valid": False}
    if len(signal) < int(fps * 5):
        return invalid
    try:
        filt  = _bandpass(signal, fps, HR_FREQ_LOW, HR_FREQ_HIGH)
        freqs, psd = welch(filt, fs=fps, nperseg=min(len(filt), int(fps * 8)))
        mask  = (freqs >= HR_FREQ_LOW) & (freqs <= HR_FREQ_HIGH)
        if not mask.any():
            return invalid
        bf, bp  = freqs[mask], psd[mask]
        pi      = int(np.argmax(bp))
        hr_bpm  = int(round(bf[pi] * 60))
        conf    = min(float(bp[pi] / (bp.sum() + 1e-9)) * 1.5, 1.0)
        if not (HR_MIN_BPM <= hr_bpm <= HR_MAX_BPM):
            return invalid
        logger.info("HR: %d BPM | conf=%.2f", hr_bpm, conf)
        return {"value": hr_bpm, "unit": "bpm",
                "confidence": round(conf, 3), "valid": conf > 0.3}
    except Exception as e:
        logger.error("HR estimation error: %s", e)
        return invalid


# ── Respiration rate ──────────────────────────────────────────────
def _estimate_respiration_rate(signal: np.ndarray, fps: float,
                                nose_ys: list) -> dict:
    invalid = {"value": None, "unit": "breaths/minute",
               "confidence": 0.0, "valid": False}

    best = invalid

    # Method 1: rPPG low-frequency modulation
    if len(signal) >= int(fps * 8):
        try:
            filt = _bandpass(signal, fps, RR_FREQ_LOW, RR_FREQ_HIGH)
            freqs, psd = welch(filt, fs=fps,
                               nperseg=min(len(filt), int(fps * 16)))
            mask = (freqs >= RR_FREQ_LOW) & (freqs <= RR_FREQ_HIGH)
            if mask.any():
                bf, bp = freqs[mask], psd[mask]
                pi     = int(np.argmax(bp))
                rr     = int(round(bf[pi] * 60))
                conf   = min(float(bp[pi] / (bp.sum() + 1e-9)) * 2.0, 1.0)
                if RR_MIN <= rr <= RR_MAX and conf > best["confidence"]:
                    best = {"value": rr, "unit": "breaths/minute",
                            "confidence": round(conf, 3), "valid": conf > 0.25}
        except Exception:
            pass

    # Method 2: nose-tip Y displacement
    if len(nose_ys) >= int(fps * 8):
        try:
            y = np.array(nose_ys, dtype=np.float64)
            nans = np.isnan(y)
            if nans.mean() < 0.5:
                good = np.where(~nans)[0]
                y[nans] = np.interp(np.where(nans)[0], good, y[good])
                filt = _bandpass(y, fps, RR_FREQ_LOW, RR_FREQ_HIGH)
                freqs, psd = welch(filt, fs=fps,
                                   nperseg=min(len(filt), int(fps * 16)))
                mask = (freqs >= RR_FREQ_LOW) & (freqs <= RR_FREQ_HIGH)
                if mask.any():
                    bf, bp = freqs[mask], psd[mask]
                    pi     = int(np.argmax(bp))
                    rr     = int(round(bf[pi] * 60))
                    conf   = min(float(bp[pi] / (bp.sum() + 1e-9)) * 2.0, 1.0)
                    if RR_MIN <= rr <= RR_MAX and conf > best["confidence"]:
                        best = {"value": rr, "unit": "breaths/minute",
                                "confidence": round(conf, 3), "valid": conf > 0.25}
        except Exception:
            pass

    if best["valid"]:
        logger.info("RR: %d breaths/min | conf=%.2f", best["value"], best["confidence"])
    return best


# ── Signal quality ─────────────────────────────────────────────────
def _calculate_quality(signal, fps, hr_result, rr_result,
                        mean_motion, valid_ratio) -> dict:
    reasons = []
    scores  = []

    # 1. Valid frame ratio
    scores.append(min(valid_ratio, 1.0))
    if valid_ratio < 0.7:
        reasons.append("Too many high-motion frames.")

    # 2. Motion
    ms = 1.0 - min(mean_motion / 0.06, 1.0)
    scores.append(ms)
    if mean_motion > 0.03:
        reasons.append("Moderate movement detected.")

    # 3. SNR
    snr = _snr_score(signal, fps)
    scores.append(snr)
    if snr < 0.3:
        reasons.append("Weak rPPG signal.")

    # 4. Periodicity
    per = _periodicity_score(signal, fps)
    scores.append(per)
    if per < 0.3:
        reasons.append("Signal lacks periodic structure.")

    # 5. HR confidence
    hr_c = hr_result.get("confidence", 0.0) if hr_result.get("valid") else 0.0
    scores.append(hr_c)

    # 6. RR confidence (lower weight)
    rr_c = rr_result.get("confidence", 0.0) if rr_result.get("valid") else 0.0
    scores.append(rr_c * 0.7)

    qs = float(np.mean(scores))
    if qs >= 0.65:   label = "GOOD"
    elif qs >= 0.45: label = "FAIR"
    elif qs >= 0.25: label = "POOR"
    else:            label = "INVALID"

    return {"signal_quality": label, "quality_score": round(qs, 3),
            "reasons": reasons}


def _snr_score(signal, fps):
    try:
        freqs, psd = welch(signal, fs=fps,
                           nperseg=min(len(signal), int(fps * 8)))
        mask = (freqs >= HR_FREQ_LOW) & (freqs <= HR_FREQ_HIGH)
        if not mask.any():
            return 0.0
        return float(min(psd[mask].sum() / (psd.sum() + 1e-9) * 3.0, 1.0))
    except Exception:
        return 0.0


def _periodicity_score(signal, fps):
    try:
        s  = signal - signal.mean()
        ac = correlate(s, s, mode="full")[len(s) - 1:]
        ac = ac / (ac[0] + 1e-9)
        l1 = max(int(fps * 60 / 210), 1)
        l2 = min(int(fps * 60 / 45), len(ac) - 1)
        if l2 <= l1:
            return 0.0
        return float(max(0.0, min(ac[l1:l2].max(), 1.0)))
    except Exception:
        return 0.0
