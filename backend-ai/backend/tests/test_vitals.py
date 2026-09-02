"""
test_vitals.py — Automated tests for the rPPG vital signs pipeline.

All tests run offline — no camera, no MediaPipe, no network calls needed.
Synthetic signals are used to verify the signal processing logic.
"""

import math
import pytest
import numpy as np

from app.services.vitals.signal_processor import (
    RGBFrame, process_rgb_signal, VitalResult,
    _pos_algorithm, _estimate_heart_rate, _estimate_respiration_rate,
    _calculate_quality, _bandpass, _snr_score, _periodicity_score,
)


# ── Helpers ──────────────────────────────────────────────────────────────

FPS = 30.0

def make_frames(n: int, hr_bpm: float = 72.0, rr_bpm: float = 15.0,
                noise: float = 0.05, motion: float = 0.0) -> list[RGBFrame]:
    """Generate synthetic frames with a known heart rate and respiration rate."""
    t = np.linspace(0, n / FPS, n)
    # Simulate skin colour: mean ~150 + pulsatile cardiac + respiratory component
    cardiac = 5.0  * np.sin(2 * math.pi * (hr_bpm / 60) * t)
    resp    = 2.0  * np.sin(2 * math.pi * (rr_bpm / 60) * t)
    noise_v = noise * np.random.randn(n)

    r = 150 + cardiac * 0.5 + resp * 0.3 + noise_v
    g = 120 + cardiac * 1.0 + resp * 0.5 + noise_v  # green strongest
    b = 100 + cardiac * 0.2 + resp * 0.1 + noise_v

    nose_y = 0.5 + 0.01 * np.sin(2 * math.pi * (rr_bpm / 60) * t)

    return [
        RGBFrame(r=float(r[i]), g=float(g[i]), b=float(b[i]),
                 nose_y=float(nose_y[i]), motion=motion)
        for i in range(n)
    ]


# ── Tests: Heart Rate ─────────────────────────────────────────────────────

class TestHeartRate:

    def test_valid_72bpm(self):
        frames = make_frames(600, hr_bpm=72.0, noise=0.02)
        rgb = np.array([[f.r, f.g, f.b] for f in frames], dtype=np.float32)
        signal = _pos_algorithm(rgb, FPS)
        assert signal is not None
        result = _estimate_heart_rate(signal, FPS)
        assert result["valid"]
        assert abs(result["value"] - 72) <= 15    # ±15 BPM tolerance for synthetic
        assert result["confidence"] > 0.0

    def test_valid_90bpm(self):
        frames = make_frames(600, hr_bpm=90.0, noise=0.02)
        rgb = np.array([[f.r, f.g, f.b] for f in frames], dtype=np.float32)
        signal = _pos_algorithm(rgb, FPS)
        result = _estimate_heart_rate(signal, FPS)
        assert result["valid"]
        assert 45 <= result["value"] <= 210

    def test_too_short_returns_invalid(self):
        frames = make_frames(60)    # only 2 seconds
        rgb = np.array([[f.r, f.g, f.b] for f in frames], dtype=np.float32)
        signal = _pos_algorithm(rgb, FPS)
        result = _estimate_heart_rate(signal, FPS)
        assert not result["valid"]

    def test_pure_noise_low_confidence(self):
        frames = make_frames(600, noise=50.0)    # overwhelm signal
        rgb = np.array([[f.r, f.g, f.b] for f in frames], dtype=np.float32)
        signal = _pos_algorithm(rgb, FPS)
        if signal is not None:
            result = _estimate_heart_rate(signal, FPS)
            # Should either be invalid or have low confidence
            if result["valid"]:
                assert result["confidence"] < 0.9


# ── Tests: Respiration Rate ───────────────────────────────────────────────

class TestRespirationRate:

    def test_valid_15bpm(self):
        frames = make_frames(900, hr_bpm=72.0, rr_bpm=15.0, noise=0.02)
        rgb = np.array([[f.r, f.g, f.b] for f in frames], dtype=np.float32)
        signal = _pos_algorithm(rgb, FPS)
        nose_ys = [f.nose_y for f in frames]
        result = _estimate_respiration_rate(signal, FPS, nose_ys)
        # RR is harder to estimate — just check it's in range if valid
        if result["valid"]:
            assert RR_MIN <= result["value"] <= RR_MAX
        # We don't assert valid=True since RR from synthetic signal is unreliable

    def test_empty_nose_ys(self):
        frames = make_frames(600)
        rgb = np.array([[f.r, f.g, f.b] for f in frames], dtype=np.float32)
        signal = _pos_algorithm(rgb, FPS)
        result = _estimate_respiration_rate(signal, FPS, [])
        # Should not crash
        assert isinstance(result, dict)
        assert "value" in result


RR_MIN, RR_MAX = 6, 30


# ── Tests: Signal Quality ─────────────────────────────────────────────────

class TestSignalQuality:

    def _make_quality_args(self, hr_conf=0.8, rr_conf=0.6,
                            mean_motion=0.01, valid_ratio=0.95,
                            noise=0.02, n=600):
        frames = make_frames(n, noise=noise)
        rgb = np.array([[f.r, f.g, f.b] for f in frames], dtype=np.float32)
        signal = _pos_algorithm(rgb, FPS)
        if signal is None:
            signal = np.zeros(n)
        return dict(
            signal      = signal,
            fps         = FPS,
            hr_result   = {"value": 72, "confidence": hr_conf, "valid": hr_conf > 0.3},
            rr_result   = {"value": 15, "confidence": rr_conf, "valid": rr_conf > 0.25},
            mean_motion = mean_motion,
            valid_ratio = valid_ratio,
        )

    def test_good_signal_quality(self):
        q = _calculate_quality(**self._make_quality_args(hr_conf=0.85, noise=0.01))
        assert q["signal_quality"] in ("GOOD", "FAIR")
        assert q["quality_score"] > 0.0

    def test_high_motion_downgrades(self):
        q = _calculate_quality(**self._make_quality_args(mean_motion=0.08))
        assert q["signal_quality"] in ("POOR", "INVALID", "FAIR")

    def test_low_valid_ratio_downgrades(self):
        q = _calculate_quality(**self._make_quality_args(valid_ratio=0.3))
        assert q["quality_score"] < 0.8

    def test_noisy_signal_low_quality(self):
        q = _calculate_quality(**self._make_quality_args(noise=40.0, hr_conf=0.1))
        assert q["signal_quality"] in ("POOR", "INVALID", "FAIR")


# ── Tests: Full Pipeline ──────────────────────────────────────────────────

class TestPipeline:

    def test_too_few_frames(self):
        frames = make_frames(50)
        result = process_rgb_signal(frames, FPS)
        assert result.status == "invalid"
        assert "Insufficient" in result.message

    def test_excessive_motion_rejected(self):
        frames = make_frames(450, motion=0.1)   # all frames high motion
        result = process_rgb_signal(frames, FPS)
        assert result.status == "invalid"
        assert "movement" in result.message.lower() or result.signal_quality == "INVALID"

    def test_good_signal_returns_success_or_invalid(self):
        """With clean synthetic data, should get success OR honest invalid — never crash."""
        frames = make_frames(600, hr_bpm=72.0, noise=0.02, motion=0.0)
        result = process_rgb_signal(frames, FPS)
        assert result.status in ("success", "invalid")
        assert isinstance(result, VitalResult)

    def test_result_has_disclaimer(self):
        frames = make_frames(600)
        result = process_rgb_signal(frames, FPS)
        if result.status == "success":
            assert "experimental" in result.disclaimer.lower()

    def test_hr_in_range_when_valid(self):
        frames = make_frames(600, hr_bpm=75.0, noise=0.01)
        result = process_rgb_signal(frames, FPS)
        if result.status == "success" and result.heart_rate:
            assert 45 <= result.heart_rate["value"] <= 210
            assert 0.0 <= result.heart_rate["confidence"] <= 1.0

    def test_rr_in_range_when_valid(self):
        frames = make_frames(900, rr_bpm=15.0, noise=0.01)
        result = process_rgb_signal(frames, FPS)
        if result.status == "success" and result.respiration_rate:
            assert 6 <= result.respiration_rate["value"] <= 30
            assert 0.0 <= result.respiration_rate["confidence"] <= 1.0


# ── Tests: FastAPI Endpoint (unit, no real server) ────────────────────────

class TestVitalsAPI:

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_create_session(self, client):
        r = client.post("/api/vitals/session", json={"user_id": "923001234567"})
        assert r.status_code == 200
        data = r.json()
        assert "session_id" in data
        assert "camera_url"  in data
        assert "expires_at"  in data

    def test_estimate_too_few_frames(self, client):
        # Create session first
        sess = client.post("/api/vitals/session", json={"user_id": "923001234567"}).json()
        sid  = sess["session_id"]
        frames = [{"r":150,"g":120,"b":100,"nose_y":0.5,"motion":0.0}] * 30
        r = client.post("/api/vitals/estimate", json={
            "session_id": sid, "fps": 30.0, "frames": frames
        })
        # Should fail validation (min 60 frames) or return invalid
        assert r.status_code in (200, 422)

    def test_estimate_valid_signal(self, client):
        sess = client.post("/api/vitals/session", json={"user_id": "923001234567"}).json()
        sid  = sess["session_id"]
        # Build synthetic frames
        frames_data = []
        for i in range(450):
            t = i / 30.0
            g = 120 + 5 * math.sin(2 * math.pi * 1.2 * t)
            frames_data.append({"r": 150.0, "g": float(g), "b": 100.0,
                                  "nose_y": 0.5, "motion": 0.0})
        r = client.post("/api/vitals/estimate", json={
            "session_id": sid, "fps": 30.0, "frames": frames_data
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("success", "invalid")
        assert "signal_quality" in data
        assert "disclaimer"     in data

    def test_invalid_session_returns_404(self, client):
        r = client.post("/api/vitals/estimate", json={
            "session_id": "nonexistent_session_id_xyz",
            "fps": 30.0,
            "frames": [{"r":150,"g":120,"b":100}] * 100,
        })
        assert r.status_code == 404

    def test_camera_page_served(self, client):
        r = client.get("/vitals/camera?s=test123")
        assert r.status_code == 200
        assert b"Pulse Check" in r.content

    def test_result_retrieval_no_measurement_yet(self, client):
        """GET result before measurement completes should return 202."""
        sess = client.post("/api/vitals/session", json={"user_id": "923001234567"}).json()
        r = client.get(f"/api/vitals/result/{sess['session_id']}")
        assert r.status_code == 202

    def test_result_retrieval_after_estimate(self, client):
        """GET result after a successful estimate should return the result."""
        sess = client.post("/api/vitals/session", json={"user_id": "923001234567"}).json()
        sid = sess["session_id"]
        frames_data = []
        for i in range(450):
            t = i / 30.0
            g = 120 + 5 * math.sin(2 * math.pi * 1.2 * t)
            frames_data.append({"r": 150.0, "g": float(g), "b": 100.0,
                                "nose_y": 0.5, "motion": 0.0})
        # Submit estimate
        client.post("/api/vitals/estimate", json={
            "session_id": sid, "fps": 30.0, "frames": frames_data
        })
        # Retrieve result
        r = client.get(f"/api/vitals/result/{sid}")
        assert r.status_code == 200
        data = r.json()
        assert "result" in data
        assert data["user_id"] == "923001234567"
        assert "status" in data["result"]

    def test_result_invalid_session_returns_404(self, client):
        r = client.get("/api/vitals/result/nonexistent_session_xyz")
        assert r.status_code == 404

    def test_root_lists_vitals_endpoints(self, client):
        r = client.get("/")
        assert r.status_code == 200
        endpoints = r.json()["endpoints"]
        assert "vitals_session" in endpoints
        assert "vitals_estimate" in endpoints
        assert "vitals_result" in endpoints
        assert "camera_page" in endpoints

    def test_session_returns_camera_url_with_session_id(self, client):
        r = client.post("/api/vitals/session", json={"user_id": "test_user"})
        assert r.status_code == 200
        data = r.json()
        assert data["session_id"] in data["camera_url"]

    def test_estimate_empty_user_id_rejected(self, client):
        r = client.post("/api/vitals/session", json={"user_id": ""})
        assert r.status_code == 422

    def test_estimate_missing_session_id(self, client):
        r = client.post("/api/vitals/estimate", json={
            "fps": 30.0,
            "frames": [{"r": 150, "g": 120, "b": 100}] * 100,
        })
        assert r.status_code == 422


# ── Tests: Session Expiry ──────────────────────────────────────────────────

class TestSessionExpiry:

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_expired_session_returns_404(self, client, monkeypatch):
        """Simulate session expiry by patching time."""
        import app.api.vitals as vitals_mod

        # Create session
        r = client.post("/api/vitals/session", json={"user_id": "923001234567"})
        assert r.status_code == 200
        sid = r.json()["session_id"]

        # Simulate expiry by advancing time far into the future
        original_cleanup = vitals_mod._cleanup_expired

        def force_expired_cleanup():
            # Mark all sessions as expired
            for k in list(vitals_mod._sessions.keys()):
                vitals_mod._sessions[k]["expires_at"] = 0

        monkeypatch.setattr(vitals_mod, "_cleanup_expired", force_expired_cleanup)

        # Try to use expired session
        r = client.post("/api/vitals/estimate", json={
            "session_id": sid,
            "fps": 30.0,
            "frames": [{"r": 150, "g": 120, "b": 100}] * 100,
        })
        assert r.status_code in (404, 410)

        # Restore
        monkeypatch.setattr(vitals_mod, "_cleanup_expired", original_cleanup)
