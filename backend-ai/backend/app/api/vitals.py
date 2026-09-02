"""
vitals.py — FastAPI router for contactless vital sign estimation.

Endpoints:
  POST /api/vitals/session   — Create secure temporary measurement session
  POST /api/vitals/estimate  — Process browser-extracted RGB signal → vitals
  GET  /api/vitals/result/{session_id} — Retrieve result for WhatsApp
"""

import logging
import os
import secrets
import threading
import time
from datetime import datetime, timezone

import requests as _requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.services.vitals.signal_processor import (
    RGBFrame, process_rgb_signal, VitalResult
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vitals", tags=["vitals"])

# ── In-memory session store (survives restart is optional for prototype) ──
# Key: session_id, Value: {user_id, created_at, expires_at, result}
_sessions: dict = {}
SESSION_TTL = 600   # 10 minutes


# ── Pydantic schemas ─────────────────────────────────────────────────────

class SessionRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=256,
                         description="WhatsApp number (opaque to URL)")


class SessionResponse(BaseModel):
    session_id: str
    expires_at: str
    camera_url: str    # Full URL for WhatsApp link


class FrameData(BaseModel):
    r: float = Field(..., ge=0, le=255)
    g: float = Field(..., ge=0, le=255)
    b: float = Field(..., ge=0, le=255)
    nose_y: float | None = None
    motion:  float | None = None


class EstimateRequest(BaseModel):
    session_id: str
    fps: float = Field(default=30.0, ge=5.0, le=60.0)
    frames: list[FrameData] = Field(..., min_length=1, max_length=3600)

    @field_validator("frames")
    @classmethod
    def min_frames_check(cls, v):
        if len(v) < 60:
            raise ValueError("At least 60 frames required (2 seconds at 30fps).")
        return v


class EstimateResponse(BaseModel):
    status: str
    session_id: str
    heart_rate: dict | None = None
    respiration_rate: dict | None = None
    signal_quality: str
    quality_score: float
    measurement_duration: float
    algorithm_version: str
    disclaimer: str
    message: str = ""


# ── Helpers ──────────────────────────────────────────────────────────────

def _cleanup_expired():
    now = time.time()
    expired = [k for k, v in _sessions.items() if v["expires_at"] < now]
    for k in expired:
        del _sessions[k]


def _get_session(session_id: str) -> dict:
    _cleanup_expired()
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    if sess["expires_at"] < time.time():
        del _sessions[session_id]
        raise HTTPException(status_code=410, detail="Session has expired.")
    return sess


# ── Routes ───────────────────────────────────────────────────────────────

@router.post("/session", response_model=SessionResponse)
def create_session(req: SessionRequest):
    """
    Create a secure temporary measurement session.

    The session_id is a cryptographically random token.
    The WhatsApp number is stored server-side — NOT in the URL.
    Returns a camera URL that can be sent to the user via WhatsApp.
    """
    _cleanup_expired()

    session_id = secrets.token_urlsafe(24)
    expires_at = time.time() + SESSION_TTL
    expires_iso = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()

    _sessions[session_id] = {
        "user_id":    req.user_id,
        "created_at": time.time(),
        "expires_at": expires_at,
        "result":     None,
    }

    # The camera URL will be served by the same FastAPI server
    base_url = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")
    camera_url = f"{base_url}/vitals/camera?s={session_id}"

    logger.info("Vital session created | session_id=%s | user=%s",
                session_id, req.user_id[:6] + "***")

    return SessionResponse(
        session_id = session_id,
        expires_at = expires_iso,
        camera_url = camera_url,
    )


@router.post("/estimate", response_model=EstimateResponse)
def estimate_vitals(req: EstimateRequest):
    """
    Process browser-extracted RGB signal and return vital estimates.

    The browser (running MediaPipe via CDN) extracts per-frame mean RGB
    from facial ROIs and sends the raw signal here.
    This endpoint runs POS rPPG + Welch PSD entirely in Python.
    Raw video is never sent — only extracted signal values.
    """
    sess = _get_session(req.session_id)

    frames = [
        RGBFrame(
            r      = f.r,
            g      = f.g,
            b      = f.b,
            nose_y = f.nose_y,
            motion = f.motion,
        )
        for f in req.frames
    ]

    logger.info("Vital estimate request | session=%s | frames=%d | fps=%.1f",
                req.session_id, len(frames), req.fps)

    result: VitalResult = process_rgb_signal(frames, req.fps)

    # Save result in session (for polling)
    _sessions[req.session_id]["result"] = result

    # Save to DB (best-effort)
    try:
        _save_to_db(sess["user_id"], req.session_id, result)
    except Exception as exc:
        logger.warning("DB save failed (non-fatal): %s", exc)

    # Send WhatsApp message directly via Meta API
    try:
        _send_whatsapp_result(sess["user_id"], result)
    except Exception as exc:
        logger.warning("WhatsApp notification failed (non-fatal): %s", exc)

    # Notify WhatsApp integration so result is pushed proactively (best-effort)
    try:
        _notify_whatsapp(sess["user_id"], req.session_id, result)
    except Exception as exc:
        logger.warning("WhatsApp notification failed (non-fatal): %s", exc)

    return EstimateResponse(
        status               = result.status,
        session_id           = req.session_id,
        heart_rate           = result.heart_rate,
        respiration_rate     = result.respiration_rate,
        signal_quality       = result.signal_quality,
        quality_score        = result.quality_score,
        measurement_duration = result.measurement_duration,
        algorithm_version    = result.algorithm_version,
        disclaimer           = result.disclaimer,
        message              = result.message,
    )


@router.get("/result/{session_id}")
def get_result(session_id: str):
    """
    Retrieve a previously computed vital result.
    Used by the WhatsApp integration layer to fetch and forward the result.
    """
    sess = _get_session(session_id)
    result = sess.get("result")
    if result is None:
        raise HTTPException(status_code=202, detail="Measurement not yet completed.")
    return {
        "user_id":    sess["user_id"],
        "session_id": session_id,
        "result":     result.__dict__,
    }


# ── DB persistence ───────────────────────────────────────────────────────

def _send_whatsapp_result(user_id: str, result: VitalResult) -> None:
    """Send vital measurement result directly to user via Meta WhatsApp API."""
    import requests as req

    meta_token    = os.getenv("META_ACCESS_TOKEN", "")
    phone_id      = os.getenv("META_PHONE_NUMBER_ID", "")

    if not meta_token or not phone_id:
        logger.warning("META credentials not set — skipping WhatsApp notification")
        return

    # Clean phone number
    to = user_id.replace("whatsapp:", "").replace("+", "").replace(" ", "").strip()

    # Build message
    if result.status == "success":
        hr = result.heart_rate or {}
        rr = result.respiration_rate or {}
        sq = result.signal_quality

        quality_emoji = {"GOOD": "🟢", "FAIR": "🟡", "POOR": "🔴"}.get(sq, "⚪")

        msg = (
            f"📊 *Experimental Vital Check Results*\n\n"
            f"❤️ Heart Rate: *{hr.get('value', '--')} BPM*\n"
            f"🫁 Breathing Rate: *{rr.get('value', '--')} breaths/min*\n"
            f"📶 Signal Quality: {quality_emoji} {sq}\n"
            f"⏱ Duration: {result.measurement_duration}s\n\n"
            f"⚠️ *Important:* These are experimental camera-based estimates. "
            f"They are NOT a substitute for professional medical measurement.\n\n"
            f"Please describe your symptoms and I will provide a full triage assessment."
        )
    else:
        msg = (
            f"⚠️ *Vital Check Incomplete*\n\n"
            f"{result.message}\n\n"
            f"Please try again or describe your symptoms as text."
        )

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": msg},
    }

    r = req.post(
        f"https://graph.facebook.com/v19.0/{phone_id}/messages",
        headers={"Authorization": f"Bearer {meta_token}",
                 "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )

    if r.status_code == 200:
        logger.info("Vital result sent to WhatsApp | user=%s | status=%s",
                    user_id[:6] + "***", result.status)
    else:
        logger.warning("WhatsApp notification HTTP %d | user=%s",
                       r.status_code, user_id[:6] + "***")


def _save_to_db(user_id: str, session_id: str, result: VitalResult):
    """Save vital measurement to the WhatsApp integration SQLite DB.

    Also attempts to link the measurement to the user's active conversation
    by looking up the users/conversations tables.  If no active conversation
    is found, conversation_id is stored as NULL (the schema allows it).
    """
    import sqlite3
    db_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..",
        "whatsapp-integration", "shifa_ai.db"
    )
    if not os.path.exists(db_path):
        return   # DB not initialised yet — skip

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vital_measurements (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id                 TEXT,
                conversation_id         INTEGER,
                measurement_session_id  TEXT,
                heart_rate              INTEGER,
                heart_rate_confidence   REAL,
                respiration_rate        INTEGER,
                respiration_confidence  REAL,
                signal_quality          TEXT,
                quality_score           REAL,
                measurement_duration    REAL,
                algorithm_version       TEXT,
                created_at              DATETIME DEFAULT (datetime('now'))
            )
        """)

        # Look up active conversation_id for this user (best-effort)
        conversation_id = None
        try:
            conn.row_factory = sqlite3.Row
            user_row = conn.execute(
                "SELECT id FROM users WHERE whatsapp_number = ?",
                (user_id,),
            ).fetchone()
            if user_row:
                conv_row = conn.execute(
                    "SELECT id FROM conversations "
                    "WHERE user_id = ? AND status = 'active' "
                    "ORDER BY started_at DESC LIMIT 1",
                    (user_row["id"],),
                ).fetchone()
                if conv_row:
                    conversation_id = conv_row["id"]
        except Exception:
            pass  # non-fatal — conversation_id stays NULL

        hr  = result.heart_rate or {}
        rr  = result.respiration_rate or {}
        conn.execute("""
            INSERT INTO vital_measurements
              (user_id, conversation_id, measurement_session_id,
               heart_rate, heart_rate_confidence,
               respiration_rate, respiration_confidence,
               signal_quality, quality_score,
               measurement_duration, algorithm_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            user_id, conversation_id, session_id,
            hr.get("value"), hr.get("confidence"),
            rr.get("value"), rr.get("confidence"),
            result.signal_quality, result.quality_score,
            result.measurement_duration, result.algorithm_version,
        ))
        conn.commit()
        logger.info("Vital measurement saved to DB | session=%s | conv=%s",
                    session_id, conversation_id)
    finally:
        conn.close()


# ── WhatsApp proactive notification ─────────────────────────────────────

def _notify_whatsapp(user_id: str, session_id: str, result: VitalResult):
    """Best-effort POST of the vital result to the WhatsApp integration server.

    The integration server will format the result in the user's language and
    send it via Meta API so the user receives the measurement proactively
    without having to send another message first.

    This runs in a daemon thread so it never blocks the estimate response.
    """
    wa_url = os.getenv("WHATSAPP_INTEGRATION_URL", "").strip()
    if not wa_url:
        return   # notification disabled

    payload = {
        "user_id":    user_id,
        "session_id": session_id,
        "status":     result.status,
        "heart_rate": result.heart_rate,
        "respiration_rate": result.respiration_rate,
        "signal_quality":   result.signal_quality,
        "quality_score":    result.quality_score,
        "measurement_duration": result.measurement_duration,
        "message":    result.message,
        "disclaimer": result.disclaimer,
    }

    def _fire():
        try:
            resp = _requests.post(
                f"{wa_url}/webhook/vital-result",
                json=payload,
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("WhatsApp vital-result notification sent | user=%s | session=%s",
                            user_id[:6] + "***", session_id[:8])
            else:
                logger.warning("WhatsApp notification HTTP %d | user=%s",
                               resp.status_code, user_id[:6] + "***")
        except Exception as exc:
            logger.debug("WhatsApp notification network error: %s", exc)

    threading.Thread(target=_fire, daemon=True).start()
