"""
meta_sender.py — Sends WhatsApp messages via Meta WhatsApp Business API.

Replaces twilio_sender.py — no Twilio needed.

Meta API endpoint:
  POST https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages
"""

import requests
from app.config import config
from app.utils.logger import get_logger

logger = get_logger(__name__)

META_API_URL = "https://graph.facebook.com/v19.0/{phone_number_id}/messages"


def send_whatsapp_message(to: str, body: str) -> bool:
    """
    Send a WhatsApp text message via Meta API.

    Args:
        to:   Recipient phone number with country code — '923001234567'
              (no +, no whatsapp: prefix)
        body: Message text to send.

    Returns:
        True on success, False on failure.
    """
    # Clean the number — remove +, spaces, whatsapp: prefix
    to_clean = to.replace("whatsapp:", "").replace("+", "").replace(" ", "").strip()

    url = META_API_URL.format(phone_number_id=config.META_PHONE_NUMBER_ID)

    headers = {
        "Authorization": f"Bearer {config.META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_clean,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": body,
        },
    }

    logger.info("Sending Meta WhatsApp message | to=%s | len=%d", to_clean, len(body))

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=config.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        msg_id = data.get("messages", [{}])[0].get("id", "unknown")
        logger.info("Message sent | id=%s", msg_id)
        return True

    except requests.exceptions.HTTPError as exc:
        logger.error("Meta API HTTP error | to=%s | status=%d | body=%s",
                     to_clean, response.status_code, response.text)
        return False
    except requests.exceptions.ConnectionError as exc:
        logger.error("Meta API connection error | %s", exc)
        return False
    except requests.exceptions.Timeout:
        logger.error("Meta API request timed out")
        return False


def _is_emergency(ai_response: str) -> bool:
    """
    Detect if the AI classified urgency as EMERGENCY.

    Only matches when EMERGENCY is the actual urgency classification,
    NOT when it appears in educational context like "when to seek emergency care".

    Looks for patterns like:
      - "Urgency Level: EMERGENCY"
      - "Urgency: EMERGENCY"
      - "URGENCY LEVEL: EMERGENCY"
      - "*EMERGENCY*" at start of response
      - "Triage Level: EMERGENCY"
    """
    import re
    text = ai_response

    # Pattern 1: Urgency label followed by EMERGENCY
    urgency_pattern = re.search(
        r'(?:urgency|triage|priority|level)\s*(?:level)?\s*[:\-–]\s*\*{0,2}EMERGENCY\*{0,2}',
        text,
        re.IGNORECASE,
    )
    if urgency_pattern:
        return True

    # Pattern 2: Response starts with EMERGENCY (first 30 chars)
    if re.match(r'^\s*\*{0,2}EMERGENCY\*{0,2}', text.strip(), re.IGNORECASE):
        return True

    return False


def format_triage_response(ai_response: str) -> str:
    """
    Format AI triage response for WhatsApp delivery.
    Adds emergency header only if EMERGENCY is the actual urgency level.
    """
    if _is_emergency(ai_response):
        return (
            "⚠️ *EMERGENCY*\n\n"
            "Your symptoms may require *immediate medical attention*.\n\n"
            f"{ai_response}\n\n"
            "🚨 Please seek emergency medical care immediately.\n"
            "Do not rely on this chatbot for emergency medical decisions."
        )
    return ai_response


# -------------------------------------------------------------------
# Pre-built error messages
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
