"""
text_handler.py — Handles plain-text WhatsApp message flow.

Flow:
    User sends text
        → input_validator classifies message
        → if reset: close conversation, confirm
        → if greeting/invalid: send pre-built response
        → if triage: build context from DB history
        → call_triage(user_id, context_enriched_symptoms)
        → save turn to DB
        → format_triage_response()
        → send_whatsapp_message()
"""

from app.services.backend_client import call_triage, BackendError
from app.services.meta_sender import (
    send_whatsapp_message,
    format_triage_response,
    BACKEND_UNAVAILABLE_MSG,
    GENERIC_ERROR_MSG,
)
from app.database.context_manager import ConversationContext
from app.utils.input_validator import validate_input
from app.utils.logger import get_logger

logger = get_logger(__name__)


def handle_text_message(from_number: str, body: str) -> None:
    """
    Process an incoming text message and send AI triage response.

    Args:
        from_number: Sender's phone number e.g. '923001234567'
        body:        Raw message text from the user.
    """
    logger.info("Text message | from=%s | len=%d", from_number, len(body))

    # ── 1. Input validation ──────────────────────────────
    validation = validate_input(body)

    if validation.action == "reply":
        # Greeting, random text, empty, too long, special chars
        logger.info("Input classified: non-triage | from=%s | action=reply", from_number)
        send_whatsapp_message(from_number, validation.response)
        return

    if validation.action == "reset":
        # /reset command — close conversation, confirm
        logger.info("Reset requested | from=%s", from_number)
        try:
            ctx = ConversationContext(from_number)
            ctx.reset()
        except Exception as exc:
            logger.error("Reset failed | from=%s | error=%s", from_number, exc)
        send_whatsapp_message(from_number, validation.response)
        return

    # ── 2. Load conversation context from DB ────────────
    try:
        ctx = ConversationContext(from_number)
        symptoms_with_context = ctx.get_context_for_triage(validation.cleaned_text)
    except Exception as exc:
        logger.error("DB context error | from=%s | error=%s", from_number, exc)
        # Fall back to stateless triage if DB fails
        ctx = None
        symptoms_with_context = validation.cleaned_text

    # ── 3. Call triage API ───────────────────────────────
    try:
        ai_response = call_triage(user_id=from_number, symptoms=symptoms_with_context)
        reply = format_triage_response(ai_response)

    except BackendError as exc:
        logger.error("Backend error | from=%s | error=%s", from_number, exc)
        send_whatsapp_message(from_number, BACKEND_UNAVAILABLE_MSG)
        return

    except Exception:
        logger.exception("Unexpected error | from=%s", from_number)
        send_whatsapp_message(from_number, GENERIC_ERROR_MSG)
        return

    # ── 4. Save turn to DB ───────────────────────────────
    if ctx:
        try:
            ctx.save_turn(
                user_message=validation.cleaned_text,
                ai_response=ai_response,
                message_type="text",
            )
        except Exception as exc:
            logger.error("DB save error | from=%s | error=%s", from_number, exc)

    # ── 5. Send reply ────────────────────────────────────
    send_whatsapp_message(from_number, reply)
