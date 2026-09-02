"""
vitals_handler.py — Handles the "📷 Check Pulse" WhatsApp flow.

Flow:
    User sends "check pulse" / "📷" / "pulse check"
        → Create a secure session via backend /api/vitals/session
        → Send camera link to user via WhatsApp
        → User opens link, completes 15s measurement in browser
        → Backend stores result in session
        → On next user message, retrieve result and include in triage context
        → Proactively send result to user via Meta API (active notification)

Multilingual triggers supported:
    English : "check pulse", "pulse check", "check vitals", "heart rate"
    Urdu    : "نبض چیک", "دل کی دھڑکن"
    Roman   : "nabd check", "pulse dekho", "pulse check karo"

Multilingual result messages:
    English, Urdu, Sindhi, Roman Urdu are all supported.
"""

import re
import os
import requests
from app.config import config
from app.services.meta_sender import send_whatsapp_message
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── Trigger patterns (case-insensitive) ──────────────────────────────────
PULSE_TRIGGER = re.compile(
    r"(check\s*pulse|pulse\s*check|check\s*vital|heart\s*rate|selfie\s*pulse|"
    r"camera\s*check|pulse\s*dekho|nabd\s*check|نبض\s*چیک|دل\s*کی\s*دھڑکن|"
    r"📷.*pulse|pulse.*📷|check.*heart|dil.*dhadkan)",
    re.IGNORECASE | re.UNICODE,
)


def is_pulse_trigger(text: str) -> bool:
    """Return True if the message is requesting a pulse/vitals check."""
    return bool(PULSE_TRIGGER.search(text.strip()))


def handle_pulse_request(from_number: str) -> None:
    """
    Create a secure vitals session and send the camera link to the user.

    Args:
        from_number: WhatsApp sender number e.g. '923001234567'
    """
    logger.info("Pulse check requested | from=%s", from_number)

    try:
        # Create session via backend — use internal URL for API call
        resp = requests.post(
            f"{config.BACKEND_BASE_URL}/api/vitals/session",
            json={"user_id": from_number},
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data       = resp.json()
        session_id = data.get("session_id", "")

        # Camera URL via Flask/ngrok — phone accessible
        ngrok_url = os.getenv("NGROK_PUBLIC_URL", config.BACKEND_PUBLIC_URL).rstrip("/")
        camera_url = f"{ngrok_url}/vitals/camera?s={session_id}"
        expires_at = data.get("expires_at", "")

        # Build WhatsApp message
        msg = (
            "📷 *Contactless Pulse Check*\n\n"
            "Open this link on your phone and follow the instructions:\n\n"
            f"👉 {camera_url}\n\n"
            "📋 *Instructions:*\n"
            "• Position your face in the oval\n"
            "• Keep phone still\n"
            "• Good lighting\n"
            "• Measurement takes ~15 seconds\n\n"
            "⚠️ This is *experimental* and not a medical device.\n"
            "Raw video is never sent to the server.\n\n"
            "After measuring, send me your symptoms and I will include the results in my assessment."
        )
        send_whatsapp_message(from_number, msg)
        logger.info("Camera link sent | from=%s | session=%s", from_number, session_id[:8])

    except requests.exceptions.ConnectionError:
        send_whatsapp_message(
            from_number,
            "Sorry, the pulse check service is temporarily unavailable.\n"
            "Please describe your symptoms as text and I will help you.",
        )
    except Exception as exc:
        logger.error("Pulse request failed | from=%s | error=%s", from_number, exc)
        send_whatsapp_message(
            from_number,
            "Sorry, I could not start the pulse check.\n"
            "Please describe your symptoms as text.",
        )


def fetch_vital_context(from_number: str) -> str:
    """
    Try to fetch the most recent completed vital measurement for a user
    and format it as a context string for Gemini.

    Returns empty string if no measurement available.
    """
    try:
        # Query the DB directly for latest vital for this user
        import sqlite3, os
        db_path = os.path.join(
            os.path.dirname(__file__), "..", "database", "..", "..", "shifa_ai.db"
        )
        db_path = os.path.normpath(db_path)
        if not os.path.exists(db_path):
            return ""

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT heart_rate, heart_rate_confidence,
                       respiration_rate, respiration_confidence,
                       signal_quality, quality_score, created_at
                FROM vital_measurements
                WHERE user_id = ?
                  AND signal_quality IN ('GOOD','FAIR')
                  AND datetime(created_at) >= datetime('now', '-30 minutes')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (from_number,),
            ).fetchone()

        if not row:
            return ""

        hr   = row["heart_rate"]
        rr   = row["respiration_rate"]
        sq   = row["signal_quality"]
        hr_c = row["heart_rate_confidence"]
        rr_c = row["respiration_confidence"]

        lines = [f"[Experimental Camera Vitals — signal_quality: {sq}]"]
        if hr:
            lines.append(f"Heart Rate: {hr} BPM (confidence: {hr_c:.2f})")
        if rr:
            lines.append(f"Respiration Rate: {rr} breaths/min (confidence: {rr_c:.2f})")
        lines.append("(Experimental estimates only — not clinically validated)")

        return "\n".join(lines)

    except Exception as exc:
        logger.debug("Could not fetch vital context: %s", exc)
        return ""


# ── Multilingual result formatting ─────────────────────────────────────

def _detect_user_language(from_number: str) -> str:
    """Best-effort language detection from the user's last message in DB.

    Returns one of: 'en', 'ur', 'sd', 'roman_urdu', 'roman_sindhi'.
    Defaults to 'en' if detection fails.
    """
    try:
        import sqlite3, os
        db_path = os.path.join(
            os.path.dirname(__file__), "..", "database", "..", "..", "shifa_ai.db"
        )
        db_path = os.path.normpath(db_path)
        if not os.path.exists(db_path):
            return "en"

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT message FROM messages "
                "WHERE role = 'user' "
                "ORDER BY created_at DESC LIMIT 1",
            ).fetchone()

        if not row:
            return "en"

        msg = row["message"] or ""

        # Simple heuristic: check for Urdu/Sindhi script characters
        import re
        if re.search(r'[\u0600-\u06FF]', msg):
            # Arabic-script — distinguish Urdu vs Sindhi by common words
            if any(w in msg for w in ['آهيان', 'آهي', 'مون', 'کي', 'ڀيو', 'ساهه', 'ڌڙڪن']):
                return "sd"
            return "ur"

        # Roman check
        lower = msg.lower()
        roman_urdu_words = ['hai', 'hain', 'mujhe', 'ko', 'ki', 'ka', 'rahe',
                             'rahi', 'karo', 'dekho', 'nhi', 'nahi', 'bhi']
        roman_sindhi_words = ['aahi', 'aahe', 'mujh', 'khe', 'bhiyo']
        urdu_score = sum(1 for w in roman_urdu_words if w in lower.split())
        sindhi_score = sum(1 for w in roman_sindhi_words if w in lower.split())

        if sindhi_score > urdu_score:
            return "roman_sindhi"
        if urdu_score > 0:
            return "roman_urdu"
        return "en"

    except Exception:
        return "en"


def format_vital_result_message(data: dict, lang: str = "en") -> str:
    """Format a vital result dict into a multilingual WhatsApp message.

    Args:
        data: dict with keys status, heart_rate, respiration_rate,
              signal_quality, quality_score, measurement_duration,
              message, disclaimer
        lang: one of 'en', 'ur', 'sd', 'roman_urdu', 'roman_sindhi'

    Returns:
        Formatted message string ready for WhatsApp delivery.
    """
    status = data.get("status", "invalid")
    sq     = data.get("signal_quality", "INVALID")

    # ── Unreliable measurement ────────────────────────────────────
    if status != "success" or sq in ("POOR", "INVALID"):
        if lang == "ur":
            return (
                "⚠️ *پیمائش غیر معتبر*\n\n"
                "ہم کیمرے سے قابل اعتماد اندازہ حاصل نہیں کر سکے۔\n\n"
                "براہ کرم دوبارہ کوشش کریں:\n"
                "• بہتر روشنی\n"
                "• کم حرکت\n"
                "• چہرہ واضح طور پر فریم میں\n\n"
                "آپ عام ٹیکسٹ یا وائس ٹریج بھی استعمال کر سکتے ہیں۔"
            )
        elif lang == "sd":
            return (
                "⚠️ *ماپ غير معتبر*\n\n"
                "اسان ڪئميرا ذريعي قابل اعتماد اندازو حاصل نه ڪري سگهياسين.\n\n"
                "مهرباني ڪري ٻيهر ڪوشش ڪريو:\n"
                "• بهتر روشني\n"
                "• گهٽ حرڪت\n"
                "• چهرو فريم ۾ واضح هجي\n\n"
                "توهان عام ٽيڪسٽ يا وائس ٽريج به استعمال ڪري سگهو ٿا."
            )
        elif lang == "roman_urdu":
            return (
                "⚠️ *Measurement Unreliable*\n\n"
                "Camera se reliable estimate nahi mil saka.\n\n"
                "Dobara koshish karein:\n"
                "• Behtar roshni\n"
                "• Kam harkat\n"
                "• Chehra frame mein saaf nazar aaye\n\n"
                "Aap normal text ya voice triage bhi use kar sakte hain."
            )
        else:
            return (
                "⚠️ *Measurement Unreliable*\n\n"
                "We could not obtain a reliable camera-based estimate.\n\n"
                "Please try again with:\n"
                "• Better lighting\n"
                "• Less movement\n"
                "• Your face clearly visible in the frame\n\n"
                "You can continue using normal text or voice triage."
            )

    # ── Successful measurement ─────────────────────────────────────
    hr = data.get("heart_rate") or {}
    rr = data.get("respiration_rate") or {}
    hr_val = hr.get("value", "--")
    rr_val = rr.get("value", "--")
    duration = data.get("measurement_duration", 0)

    if lang == "ur":
        sq_label = {"GOOD": "اچھی", "FAIR": "ٹھیک"}.get(sq, sq)
        return (
            "📊 *تجرباتی وائٹل چیک*\n\n"
            f"❤️ *دل کی دھڑکن:* {hr_val} BPM\n\n"
            f"🫁 *سانس کی رفتار:* {rr_val} فی منٹ\n\n"
            f"📶 *سگنل کوالٹی:* {sq_label}\n\n"
            f"⏱ *دورانیہ:* {duration} سیکنڈ\n\n"
            "⚠️ یہ کیمرے سے حاصل کیے گئے تجرباتی اندازے ہیں،\n"
            "طبی پیمائش کا متبادل نہیں۔\n"
            "اگر علامات سنگین ہیں تو براہ کرم ڈاکٹر سے رجوع کریں۔"
        )
    elif lang == "sd":
        sq_label = {"GOOD": "سٺي", "FAIR": "ٺيڪ"}.get(sq, sq)
        return (
            "📊 *تجرباتي وائٽل چيڪ*\n\n"
            f"❤️ *دل جي ڌڙڪن:* {hr_val} BPM\n\n"
            f"🫁 *ساهه جي رفتار:* {rr_val} في منٽ\n\n"
            f"📶 *سگنل ڪوالٽي:* {sq_label}\n\n"
            f"⏱ *مدو:* {duration} سيڪنڊ\n\n"
            "⚠️ هي ڪئميرا ذريعي حاصل ڪيل تجرباتي اندازا آهن،\n"
            "طبي ماپ جو متبادل نه آهن.\n"
            "جيڪڏهن علامات سنگين آهن ته ڊاڪٽر سان رجوع ڪريو."
        )
    elif lang == "roman_urdu":
        sq_label = {"GOOD": "Achi", "FAIR": "Theek"}.get(sq, sq)
        return (
            "📊 *Experimental Vital Check*\n\n"
            f"❤️ *Dil ki dhadkan:* {hr_val} BPM\n\n"
            f"🫁 *Saans ki raftaar:* {rr_val} per minute\n\n"
            f"📶 *Signal Quality:* {sq_label}\n\n"
            f"⏱ *Duration:* {duration} seconds\n\n"
            "⚠️ Yeh camera se hasil kiye gaye experimental andazay hain,\n"
            "tibbi paimaish ka mutabadil nahi.\n"
            "Agar alamaat sangeen hain to doctor se rabta karein."
        )
    elif lang == "roman_sindhi":
        sq_label = {"GOOD": "Suthi", "FAIR": "Theek"}.get(sq, sq)
        return (
            "📊 *Experimental Vital Check*\n\n"
            f"❤️ *Dil ji dhadkan:* {hr_val} BPM\n\n"
            f"🫁 *Sahh ji raftar:* {rr_val} per minute\n\n"
            f"📶 *Signal Quality:* {sq_label}\n\n"
            f"⏱ *Duration:* {duration} seconds\n\n"
            "⚠️ Hiyaa camera zariye hasil kiyal experimental andaza aahin,\n"
            "tibbi paimaish jo mutabadil na aahin.\n"
            "Jekadhin alamaat sangeen aahin ta doctor saan rabto karyo."
        )
    else:
        return (
            "📊 *Experimental Vital Check*\n\n"
            f"❤️ *Heart Rate:* {hr_val} BPM\n\n"
            f"🫁 *Respiration Rate:* {rr_val} breaths/minute\n\n"
            f"📶 *Signal Quality:* {sq}\n\n"
            f"⏱ *Duration:* {duration} seconds\n\n"
            "⚠️ These are experimental camera-based estimates.\n"
            "They are NOT medical-grade measurements and should not\n"
            "replace professional medical assessment.\n"
            "If your symptoms are serious, please consult a doctor."
        )


def send_vital_result_to_user(data: dict) -> None:
    """Format and proactively send a vital result to the user via WhatsApp.

    Called by the /webhook/vital-result callback from the backend after
    a measurement completes.

    Args:
        data: dict with keys user_id, session_id, status, heart_rate,
              respiration_rate, signal_quality, quality_score,
              measurement_duration, message, disclaimer
    """
    from_number = data.get("user_id", "")
    if not from_number:
        logger.warning("send_vital_result_to_user: no user_id in data")
        return

    lang = _detect_user_language(from_number)
    msg  = format_vital_result_message(data, lang)

    try:
        send_whatsapp_message(from_number, msg)
        logger.info("Vital result sent to user | from=%s | lang=%s | status=%s",
                    from_number, lang, data.get("status"))
    except Exception as exc:
        logger.error("Failed to send vital result | from=%s | error=%s",
                     from_number, exc)
