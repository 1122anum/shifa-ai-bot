"""
voice_handler.py — Handles voice/audio WhatsApp message flow.

Flow:
    User sends voice note
        → download_audio(media_id, content_type)   [Meta CDN]
        → call_voice_triage(user_id, audio_path)   [Whisper + Gemini via FastAPI]
        → save turn to DB (with transcription)
        → format_triage_response(ai_response)
        → send_whatsapp_message(to, reply)
        → cleanup_audio(audio_path)
"""

from app.services.audio_handler import download_audio, cleanup_audio
from app.services.backend_client import call_voice_triage, BackendError
from app.services.meta_sender import (
    send_whatsapp_message,
    format_triage_response,
    BACKEND_UNAVAILABLE_MSG,
    VOICE_TRANSCRIPTION_FAILED_MSG,
    GENERIC_ERROR_MSG,
)
from app.database.context_manager import ConversationContext
from app.handlers.vitals_handler import fetch_vital_context
from app.handlers.emergency_handler import (
    detect_emergency_from_triage,
    handle_emergency_workflow,
    is_cancellation_request,
    handle_emergency_cancellation,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


def handle_voice_message(from_number: str, media_id: str, content_type: str) -> None:
    """
    Process an incoming voice message and send AI triage response.

    Args:
        from_number:  Sender's phone number e.g. '923001234567'
        media_id:     Meta media ID from webhook payload
        content_type: MIME type of the audio
    """
    logger.info(
        "Voice message received | from=%s | media_id=%s | type=%s",
        from_number, media_id, content_type,
    )

    audio_path: str | None = None

    try:
        # Step 1 — Download audio from Meta CDN
        audio_path = download_audio(media_id, content_type)
        logger.info("Audio downloaded | from=%s | path=%s", from_number, audio_path)

        # Step 2 — Single call: audio → Whisper → Gemini
        # Attach recent vital measurement context if available (within 30 min)
        vital_ctx = ""
        try:
            vital_ctx = fetch_vital_context(from_number)
            if vital_ctx:
                logger.info("Vital context attached to voice triage | from=%s", from_number)
        except Exception as exc:
            logger.debug("Could not fetch vital context for voice: %s", exc)

        try:
            result      = call_voice_triage(
                user_id=from_number,
                audio_path=audio_path,
                vital_context=vital_ctx,
            )
            ai_response = result["ai_response"]
            transcript  = result["transcript"]
            logger.info(
                "Voice triage done | from=%s | transcript_len=%d | urgency_detected=%s",
                from_number, len(transcript),
                "EMERGENCY" in ai_response.upper(),
            )
        except BackendError as exc:
            err_str = str(exc).lower()
            logger.error("Voice triage failed | from=%s | error=%s", from_number, exc)
            if "transcri" in err_str or "whisper" in err_str or "speech" in err_str:
                send_whatsapp_message(from_number, VOICE_TRANSCRIPTION_FAILED_MSG)
            else:
                send_whatsapp_message(from_number, BACKEND_UNAVAILABLE_MSG)
            return

        # Step 3 — Save turn to DB (with transcription)
        try:
            ctx = ConversationContext(from_number)
            ctx.save_turn(
                user_message=transcript,
                ai_response=ai_response,
                message_type="voice",
                transcription=transcript,
            )
        except Exception as exc:
            logger.error("DB save error | from=%s | error=%s", from_number, exc)

        # Step 4 — Format and send
        reply = format_triage_response(ai_response)
        send_whatsapp_message(from_number, reply)

        # Step 5 — Emergency detection post-check
        try:
            emergency = detect_emergency_from_triage(ai_response)
            if emergency and emergency.get("risk_level") == "CRITICAL_EMERGENCY":
                logger.info("Emergency detected from voice triage | from=%s", from_number)
                import threading
                threading.Thread(
                    target=handle_emergency_workflow,
                    args=(from_number, ai_response, transcript, ""),
                    daemon=True,
                ).start()
        except Exception as exc:
            logger.error("Voice emergency post-check failed: %s", exc)

    except Exception:
        logger.exception("Unexpected error in voice handler | from=%s", from_number)
        send_whatsapp_message(from_number, GENERIC_ERROR_MSG)

    finally:
        if audio_path:
            cleanup_audio(audio_path)
