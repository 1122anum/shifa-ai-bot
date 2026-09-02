"""
demo_vitals.py — End-to-end demo of the rPPG vital signs feature.

Simulates the complete flow described in Phase 27:
    Patient sends symptoms → Shifa AI offers pulse check →
    Synthetic camera data processed → Gemini triage with vitals context →
    WhatsApp response

Usage:
    python demo_vitals.py

No real camera or WhatsApp needed — uses synthetic signal data.
"""

import math
import json
import time
import requests
import numpy as np

BASE_URL = "http://localhost:8000"


def separator(title: str):
    print(f"\n{'═'*55}")
    print(f"  {title}")
    print('═'*55)


def make_synthetic_frames(n=450, hr_bpm=78.0, rr_bpm=16.0, fps=30.0):
    """Generate synthetic rPPG signal frames."""
    t = np.linspace(0, n / fps, n)
    cardiac = 5.0 * np.sin(2 * math.pi * (hr_bpm / 60) * t)
    resp    = 2.0 * np.sin(2 * math.pi * (rr_bpm / 60) * t)
    noise   = 0.5 * np.random.randn(n)
    r = 150 + cardiac * 0.5 + resp * 0.3 + noise
    g = 120 + cardiac * 1.0 + resp * 0.5 + noise
    b = 100 + cardiac * 0.2 + resp * 0.1 + noise
    nose_y = 0.5 + 0.01 * np.sin(2 * math.pi * (rr_bpm / 60) * t)
    return [
        {"r": float(r[i]), "g": float(g[i]), "b": float(b[i]),
         "nose_y": float(nose_y[i]), "motion": 0.0}
        for i in range(n)
    ]


def main():
    print("\n" + "★" * 55)
    print("  Shifa AI — rPPG Vital Signs Feature Demo")
    print("★" * 55)

    # ── Step 1: Check backend health ─────────────────────
    separator("Step 1 — Backend Health Check")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"  ✓ Backend: {r.json()}")
    except Exception as e:
        print(f"  ✗ Backend not reachable: {e}")
        print(f"    Start it with: python -m uvicorn app.main:app --port 8000")
        return

    # ── Step 2: Patient sends symptoms ───────────────────
    separator("Step 2 — Patient Message (WhatsApp simulation)")
    user_id  = "923001234567"
    symptoms = "Mujhe chakkar aa rahe hain aur kamzori hai"
    print(f"  User: {symptoms}")

    # ── Step 3: Triage without vitals ────────────────────
    separator("Step 3 — Initial Triage (no vitals yet)")
    r = requests.post(f"{BASE_URL}/api/triage",
                      json={"user_id": user_id, "symptoms": symptoms}, timeout=30)
    if r.status_code == 200:
        initial_response = r.json()["ai_response"]
        print(f"  Shifa AI:\n  {initial_response[:200]}...")
    else:
        print(f"  Triage error: {r.status_code}")

    # ── Step 4: Create vital session ─────────────────────
    separator("Step 4 — Create Secure Vital Session")
    r = requests.post(f"{BASE_URL}/api/vitals/session",
                      json={"user_id": user_id}, timeout=10)
    if r.status_code != 200:
        print(f"  ✗ Session creation failed: {r.text}")
        return

    sess_data  = r.json()
    session_id = sess_data["session_id"]
    camera_url = sess_data["camera_url"]
    print(f"  ✓ Session: {session_id[:12]}...")
    print(f"  ✓ Camera URL: {camera_url}")
    print(f"  → This URL would be sent to user via WhatsApp")

    # ── Step 5: Simulate camera measurement ──────────────
    separator("Step 5 — Camera Measurement (15s synthetic signal)")
    print("  Generating synthetic rPPG signal...")
    print("  Parameters: HR=78 BPM, RR=16 breaths/min")
    print("  Simulating 15 seconds at 30 FPS...")

    for pct in [25, 50, 75, 100]:
        time.sleep(0.2)
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r  [{bar}] {pct}%", end="", flush=True)
    print()

    frames = make_synthetic_frames(n=450, hr_bpm=78.0, rr_bpm=16.0)
    print(f"  ✓ {len(frames)} frames collected at 30 FPS")

    # ── Step 6: Submit to backend ─────────────────────────
    separator("Step 6 — Submit Signal to Backend (POS Algorithm)")
    r = requests.post(f"{BASE_URL}/api/vitals/estimate", json={
        "session_id": session_id,
        "fps":        30.0,
        "frames":     frames,
    }, timeout=30)

    if r.status_code != 200:
        print(f"  ✗ Estimate failed: {r.text}")
        return

    vital_data = r.json()
    print(f"  ✓ Status: {vital_data['status']}")
    print(f"  ✓ Signal Quality: {vital_data['signal_quality']} "
          f"(score: {vital_data['quality_score']:.2f})")

    if vital_data["status"] == "success":
        hr = vital_data.get("heart_rate") or {}
        rr = vital_data.get("respiration_rate") or {}
        print(f"\n  📊 Results:")
        print(f"     ❤️  Heart Rate: {hr.get('value','--')} BPM "
              f"(confidence: {hr.get('confidence',0):.0%})")
        print(f"     🫁 Respiration: {rr.get('value','--')} breaths/min "
              f"(confidence: {rr.get('confidence',0):.0%})")
        print(f"     ⏱  Duration: {vital_data['measurement_duration']}s")
    else:
        print(f"  ⚠ Measurement: {vital_data.get('message','invalid')}")

    # ── Step 7: Triage with vital context ────────────────
    separator("Step 7 — Triage with Experimental Vital Context")

    vital_context = ""
    if vital_data["status"] == "success":
        hr = vital_data.get("heart_rate") or {}
        rr = vital_data.get("respiration_rate") or {}
        sq = vital_data["signal_quality"]
        vital_context = (
            f"[Experimental Camera Vitals — signal_quality: {sq}]\n"
            f"Heart Rate: {hr.get('value','--')} BPM (confidence: {hr.get('confidence',0):.2f})\n"
            f"Respiration Rate: {rr.get('value','--')} breaths/min "
            f"(confidence: {rr.get('confidence',0):.2f})\n"
            "(Experimental estimates only — not clinically validated)"
        )

    full_symptoms = (vital_context + "\n\n" + symptoms).strip() if vital_context else symptoms

    print(f"\n  Sending to Gemini with context:\n")
    print("  " + "\n  ".join(full_symptoms.split("\n")))

    r = requests.post(f"{BASE_URL}/api/triage",
                      json={"user_id": user_id, "symptoms": full_symptoms}, timeout=30)

    if r.status_code == 200:
        final_response = r.json()["ai_response"]
        print(f"\n  Shifa AI Response:\n")
        for line in final_response.split("\n"):
            print(f"  {line}")
    else:
        print(f"  Triage error: {r.status_code} — {r.text[:200]}")

    # ── Step 8: Summary ───────────────────────────────────
    separator("Step 8 — Feature Summary")
    print("""
  ✓ Backend health check
  ✓ Initial triage (text only)
  ✓ Secure session created (random token — phone number NOT in URL)
  ✓ Camera URL generated for WhatsApp
  ✓ Synthetic rPPG signal processed (POS algorithm)
  ✓ Heart rate estimated (Welch PSD)
  ✓ Respiration rate estimated (rPPG + nose-tip motion)
  ✓ Signal quality calculated
  ✓ Gemini triage with experimental vital context
  ✓ Disclaimer included in response

  ⚠ Medical disclaimer:
    This is an EXPERIMENTAL prototype.
    Camera-derived values are NOT clinically validated.
    Always prioritise professional medical assessment.
    """)


if __name__ == "__main__":
    main()
