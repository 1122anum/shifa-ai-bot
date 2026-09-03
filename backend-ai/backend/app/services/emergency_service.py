"""
emergency_service.py — Gemini-powered emergency severity classification.

Analyzes symptoms and conversation context to classify urgency:
  ROUTINE / HIGH_RISK / CRITICAL_EMERGENCY

Uses structured JSON output from Gemini to ensure machine-readable results.
Camera-derived vitals are treated as secondary context only.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.models.emergency import (
    RiskLevel,
    EmergencyCategory,
    is_valid_transition,
)

logger = logging.getLogger(__name__)

# WhatsApp-integration DB path
_DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..",
                 "..", "whatsapp-integration", "shifa_ai.db")
)

# Cooldown window to prevent duplicate emergencies
COOLDOWN_MINUTES = settings.EMERGENCY_COOLDOWN_MINUTES

EMERGENCY_SYSTEM_PROMPT = """You are the emergency triage classification component of Shifa AI.

You are NOT a diagnostic system. You do NOT diagnose diseases.

Analyze the patient's reported symptoms and conversation context.
Identify emergency red flags.

Classify urgency as exactly one of:
- ROUTINE: Minor symptoms (mild headache, mild cold, minor discomfort)
- HIGH_RISK: Concerning symptoms requiring prompt assessment (persistent fever, significant breathing difficulty, severe weakness)
- CRITICAL_EMERGENCY: Life-threatening symptoms (severe chest pain, severe difficulty breathing, loss of consciousness, stroke-like symptoms, severe uncontrolled bleeding)

Emergency categories (use when CRITICAL_EMERGENCY or HIGH_RISK):
- CHEST_PAIN
- BREATHING_EMERGENCY
- STROKE_WARNING
- LOSS_OF_CONSCIOUSNESS
- SEVERE_BLEEDING
- SEVERE_ALLERGIC_REACTION
- TRAUMA
- OTHER_CRITICAL

Rules:
1. Do not invent symptoms. Only use what the patient reports.
2. Do not diagnose the disease.
3. Camera-derived vital measurements are experimental and must NEVER override strong emergency symptoms.
4. Poor-quality camera measurements must NOT trigger an emergency by themselves.
5. If the patient's symptoms are clearly life-threatening, return CRITICAL_EMERGENCY even if vital data is unavailable or poor quality.
6. Multi-turn conversations matter — consider the full context, not just the latest message.

Return structured JSON with exactly these fields:
{
    "risk_level": "ROUTINE" | "HIGH_RISK" | "CRITICAL_EMERGENCY",
    "category": string or null,
    "confidence": float between 0.0 and 1.0,
    "red_flags": [list of strings],
    "requires_emergency_workflow": boolean
}
"""


def analyze_emergency(
    symptoms: str,
    conversation_history: str = "",
    vital_data: Optional[dict] = None,
    user_id: str = "",
) -> dict:
    """
    Analyze symptoms for emergency classification using Gemini.

    Args:
        symptoms: Current user message / symptom description
        conversation_history: Previous conversation turns
        vital_data: Optional camera-derived vital signs (experimental)
        user_id: User identifier for duplicate prevention

    Returns:
        dict with risk_level, category, confidence, red_flags,
        requires_emergency_workflow, emergency_id
    """
    # ── Check for duplicate emergency ─────────────────────
    if user_id:
        existing = _find_active_emergency(user_id)
        if existing:
            logger.info("Active emergency exists for user %s — updating", user_id[:6])
            return _update_existing_emergency(existing, symptoms, conversation_history)

    # ── Build Gemini prompt ───────────────────────────────
    prompt_parts = []

    if conversation_history:
        prompt_parts.append(f"Conversation history:\n{conversation_history}")

    prompt_parts.append(f"Current patient message:\n{symptoms}")

    if vital_data:
        sq = vital_data.get("signal_quality", "UNKNOWN")
        prompt_parts.append(
            f"\n[Experimental Camera Vitals — signal_quality: {sq}]"
        )
        if vital_data.get("heart_rate"):
            prompt_parts.append(
                f"Heart Rate: {vital_data['heart_rate']} BPM "
                f"(confidence: {vital_data.get('heart_rate_confidence', 0):.2f})"
            )
        if vital_data.get("respiration_rate"):
            prompt_parts.append(
                f"Respiration Rate: {vital_data['respiration_rate']} breaths/min "
                f"(confidence: {vital_data.get('respiration_confidence', 0):.2f})"
            )
        prompt_parts.append(
            "(EXPERIMENTAL — do not base emergency classification solely on these values)"
        )

    full_prompt = "\n\n".join(prompt_parts)

    # ── Call Gemini ───────────────────────────────────────
    try:
        result = _call_gemini_emergency(full_prompt)
    except Exception as exc:
        logger.error("Gemini emergency analysis failed: %s", exc)
        # Fallback: keyword-based emergency detection
        result = _keyword_fallback(symptoms)

    # ── Create incident record ────────────────────────────
    emergency_id = f"emg_{secrets.token_hex(8)}"

    # Create record in DB
    _create_incident(
        emergency_id=emergency_id,
        user_id=user_id,
        risk_level=result["risk_level"],
        category=result.get("category"),
        confidence=result.get("confidence", 0.0),
        red_flags=result.get("red_flags", []),
        vital_context=json.dumps(vital_data) if vital_data else None,
    )

    result["emergency_id"] = emergency_id
    result["requires_emergency_workflow"] = (
        result["risk_level"] == "CRITICAL_EMERGENCY"
    )

    return result


def _call_gemini_emergency(prompt: str) -> dict:
    """Call Gemini with the emergency analysis prompt."""
    import google.genai as genai
    from google.genai import types

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")

    model_name = settings.GEMINI_MODEL
    timeout_ms = int(settings.REQUEST_TIMEOUT_SECONDS * 1000)

    os.environ.pop("GOOGLE_API_KEY", None)
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=timeout_ms),
    )

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=EMERGENCY_SYSTEM_PROMPT,
            temperature=0.2,
            max_output_tokens=512,
        ),
    )

    text = (response.text or "").strip()

    # Try to parse structured JSON
    try:
        # Handle markdown code blocks
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Gemini emergency response was not valid JSON: %s", text[:200])
        return _parse_fallback(text)


def _parse_fallback(text: str) -> dict:
    """Attempt to extract risk level from free-form text."""
    upper = text.upper()
    if "CRITICAL_EMERGENCY" in upper or "CRITICAL EMERGENCY" in upper:
        return {
            "risk_level": "CRITICAL_EMERGENCY",
            "category": "OTHER_CRITICAL",
            "confidence": 0.7,
            "red_flags": ["Emergency keywords detected in response"],
        }
    if "HIGH_RISK" in upper or "HIGH RISK" in upper:
        return {
            "risk_level": "HIGH_RISK",
            "category": "OTHER_CRITICAL",
            "confidence": 0.6,
            "red_flags": ["High-risk keywords detected"],
        }
    return {
        "risk_level": "ROUTINE",
        "category": None,
        "confidence": 0.5,
        "red_flags": [],
    }


def _keyword_fallback(symptoms: str) -> dict:
    """Very basic keyword-based emergency detection if Gemini fails."""
    text = symptoms.lower()

    critical_keywords = [
        "severe chest pain", "chest pain", "difficulty breathing",
        "can't breathe", "unconscious", "passed out", "stroke",
        "severe bleeding", "not responding", "cardiac arrest",
    ]

    for kw in critical_keywords:
        if kw in text:
            return {
                "risk_level": "CRITICAL_EMERGENCY",
                "category": "CHEST_PAIN" if "chest" in kw else "OTHER_CRITICAL",
                "confidence": 0.5,
                "red_flags": [kw],
            }

    high_risk_keywords = [
        "high fever", "breathing difficult", "severe weakness",
        "persistent pain", "very weak",
    ]

    for kw in high_risk_keywords:
        if kw in text:
            return {
                "risk_level": "HIGH_RISK",
                "category": "OTHER_CRITICAL",
                "confidence": 0.4,
                "red_flags": [kw],
            }

    return {
        "risk_level": "ROUTINE",
        "category": None,
        "confidence": 0.5,
        "red_flags": [],
    }


# ── Database helpers ────────────────────────────────────────────────────

def _create_incident(
    emergency_id: str,
    user_id: str,
    risk_level: str,
    category: Optional[str],
    confidence: float,
    red_flags: list[str],
    vital_context: Optional[str],
) -> None:
    """Create a new emergency incident record."""
    try:
        if not os.path.exists(_DB_PATH):
            return
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            # Look up conversation_id
            conv_id = None
            if user_id:
                user_row = conn.execute(
                    "SELECT id FROM users WHERE whatsapp_number = ?",
                    (user_id,),
                ).fetchone()
                if user_row:
                    conv_row = conn.execute(
                        "SELECT id FROM conversations WHERE user_id = ? AND status = 'active' "
                        "ORDER BY started_at DESC LIMIT 1",
                        (user_row["id"],),
                    ).fetchone()
                    if conv_row:
                        conv_id = conv_row["id"]

            conn.execute(
                """INSERT INTO emergency_incidents
                   (id, user_id, conversation_id, risk_level, category,
                    confidence, red_flags, status, vital_context)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'ASSESSING', ?)""",
                (emergency_id, user_id, conv_id, risk_level,
                 category, confidence, json.dumps(red_flags), vital_context),
            )
            conn.execute(
                """INSERT INTO emergency_events
                   (emergency_id, event_type, event_data)
                   VALUES (?, 'EMERGENCY_DETECTED', ?)""",
                (emergency_id, json.dumps({
                    "risk_level": risk_level,
                    "category": category,
                    "confidence": confidence,
                    "red_flags": red_flags,
                })),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Failed to create emergency incident: %s", exc)


def _find_active_emergency(user_id: str) -> Optional[dict]:
    """Check for an existing active emergency within the cooldown window."""
    try:
        if not os.path.exists(_DB_PATH):
            return None
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT id, risk_level, category, confidence, status
               FROM emergency_incidents
               WHERE user_id = ?
                 AND status NOT IN ('RESOLVED', 'CANCELLED')
                 AND datetime(created_at, '+' || ? || ' minutes') > datetime('now')
               ORDER BY created_at DESC
               LIMIT 1""",
            (user_id, COOLDOWN_MINUTES),
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def _update_existing_emergency(
    existing: dict,
    symptoms: str,
    conversation_history: str,
) -> dict:
    """Update an existing active emergency instead of creating a duplicate."""
    return {
        "emergency_id": existing["id"],
        "risk_level": existing["risk_level"],
        "category": existing.get("category"),
        "confidence": existing.get("confidence", 0.0),
        "red_flags": [],
        "requires_emergency_workflow": existing["risk_level"] == "CRITICAL_EMERGENCY",
        "message": "Existing active emergency updated.",
    }


def transition_state(emergency_id: str, new_state: str) -> bool:
    """
    Transition an emergency incident to a new state.
    Validates against the state machine before applying.

    Returns True if transition was valid and applied.
    """
    try:
        if not os.path.exists(_DB_PATH):
            return False
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            row = conn.execute(
                "SELECT status FROM emergency_incidents WHERE id = ?",
                (emergency_id,),
            ).fetchone()
            if not row:
                return False

            current = row["status"]
            if not is_valid_transition(current, new_state):
                logger.warning(
                    "Invalid state transition: %s -> %s for %s",
                    current, new_state, emergency_id,
                )
                return False

            now = datetime.now(tz=timezone.utc).isoformat()
            resolved_at = now if new_state in ("RESOLVED", "CANCELLED") else None
            conn.execute(
                """UPDATE emergency_incidents
                   SET status=?, updated_at=?, resolved_at=?
                   WHERE id=?""",
                (new_state, now, resolved_at, emergency_id),
            )
            conn.execute(
                """INSERT INTO emergency_events
                   (emergency_id, event_type, event_data)
                   VALUES (?, ?, ?)""",
                (emergency_id, f"STATE_{new_state}",
                 json.dumps({"from": current, "to": new_state})),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as exc:
        logger.error("State transition failed: %s", exc)
        return False
