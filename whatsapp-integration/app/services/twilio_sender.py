"""
twilio_sender.py — Sends WhatsApp messages back to the user via Twilio.

Responsibilities:
  - Send plain text replies
  - Format emergency responses with visual prominence
  - Keep messages WhatsApp-friendly (no heavy markdown, short lines)
"""

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from app.config import config
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Lazy-initialised Twilio client (avoids import-time credential check in tests)
_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    return _client


def send_whatsapp_message(to: str, body: str) -> str:
    """
    Send a WhatsApp message to `to` via Twilio.

    Args:
        to:   Recipient identifier in Twilio format — 'whatsapp:+923001234567'
        body: Message text to send.

    Returns:
        Twilio message SID on success.

    Raises:
        TwilioRestException: if the Twilio API call fails.
    """
    # Ensure the 'whatsapp:' prefix is present
    if not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"

    logger.info("Sending WhatsApp message | to=%s | len=%d", to, len(body))

    try:
        message = _get_client().messages.create(
            from_=config.TWILIO_WHATSAPP_NUMBER,
            to=to,
            body=body,
        )
        logger.info("Message sent | sid=%s", message.sid)
        return message.sid
    except TwilioRestException as exc:
        logger.error("Twilio send failed | to=%s | error=%s", to, str(exc))
        raise


def format_triage_response(ai_response: str) -> str:
    """
    Format the AI triage response for WhatsApp delivery.

    - Detects EMERGENCY and adds a prominent header.
    - Otherwise returns the response as-is (the backend already formats it).
    """
    upper = ai_response.upper()

    if "EMERGENCY" in upper:
        return (
            "⚠️ *EMERGENCY*\n\n"
            "Your symptoms may require *immediate medical attention*.\n\n"
            f"{ai_response}\n\n"
            "🚨 Please seek emergency medical care immediately.\n"
            "Do not rely on this chatbot for emergency medical decisions."
        )

    return ai_response


# -------------------------------------------------------------------
# Pre-built error messages (never expose internals to the user)
# -------------------------------------------------------------------

BACKEND_UNAVAILABLE_MSG = (
    "Sorry, the system is temporarily unavailable.\n"
    "Please try again later or seek professional medical help "
    "if your symptoms are serious."
)

VOICE_TRANSCRIPTION_FAILED_MSG = (
    "Sorry, I could not understand the voice message.\n"
    "Please try again or send your symptoms as text."
)

GENERIC_ERROR_MSG = (
    "Something went wrong while processing your request.\n"
    "Please try again in a moment."
)
