"""
webhook.py — Flask app for Meta WhatsApp Business API webhook.

Meta uses TWO types of requests:
  1. GET  /webhook/whatsapp — Verification challenge (one time setup)
  2. POST /webhook/whatsapp — Incoming messages

Meta Webhook Payload docs:
  https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks
"""

import hashlib
import hmac
from flask import Flask, request, Response, jsonify

from app.config import config
from app.services.audio_handler import is_audio_message
from app.handlers.text_handler import handle_text_message
from app.handlers.voice_handler import handle_voice_message
from app.services.meta_sender import send_whatsapp_message
from app.utils.logger import get_logger

logger = get_logger(__name__)

app = Flask(__name__)


# ─────────────────────────────────────────────
# Webhook Verification (GET) — Meta calls this
# once when you register the webhook URL
# ─────────────────────────────────────────────
@app.route("/webhook/whatsapp", methods=["GET"])
def verify_webhook():
    """
    Meta sends a GET request to verify the webhook URL.
    We must return the hub.challenge value if the token matches.
    """
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    logger.info("Webhook verification | mode=%s | token_match=%s", mode, token == config.META_VERIFY_TOKEN)

    if mode == "subscribe" and token == config.META_VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return Response(challenge, status=200, mimetype="text/plain")

    logger.warning("Webhook verification failed — token mismatch")
    return Response("Forbidden", status=403)


# ─────────────────────────────────────────────
# Incoming Messages (POST)
# ─────────────────────────────────────────────
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    """
    POST /webhook/whatsapp

    Receives all incoming WhatsApp messages from Meta.
    Parses the payload and routes to text or voice handler.
    """
    data = request.get_json(silent=True)

    if not data:
        logger.warning("Empty or non-JSON payload received")
        return jsonify({"status": "ok"}), 200

    logger.debug("Webhook payload: %s", data)

    try:
        # Meta payload structure:
        # data.entry[0].changes[0].value.messages[0]
        entry   = data.get("entry", [])
        if not entry:
            return jsonify({"status": "ok"}), 200

        changes = entry[0].get("changes", [])
        if not changes:
            return jsonify({"status": "ok"}), 200

        value    = changes[0].get("value", {})
        messages = value.get("messages", [])

        if not messages:
            # Could be a status update (delivered, read) — ignore
            logger.debug("No messages in payload — likely a status update")
            return jsonify({"status": "ok"}), 200

        message     = messages[0]
        from_number = message.get("from", "")   # e.g. "923001234567"
        msg_type    = message.get("type", "")   # "text" | "audio" | "image" etc.
        msg_id      = message.get("id", "")

        logger.info("Message received | id=%s | from=%s | type=%s", msg_id, from_number, msg_type)

        # ── TEXT ──────────────────────────────
        if msg_type == "text":
            body = message.get("text", {}).get("body", "")
            handle_text_message(from_number=from_number, body=body)

        # ── AUDIO / VOICE ─────────────────────
        elif msg_type == "audio":
            audio_info = message.get("audio", {})
            media_id   = audio_info.get("id", "")
            mime_type  = audio_info.get("mime_type", "audio/ogg")
            handle_voice_message(
                from_number=from_number,
                media_id=media_id,
                content_type=mime_type,
            )

        # ── UNSUPPORTED MEDIA ─────────────────
        else:
            logger.info("Unsupported message type | type=%s | from=%s", msg_type, from_number)
            send_whatsapp_message(
                from_number,
                "I can only process text messages and voice notes.\n"
                "Please describe your symptoms in text or send a voice message.",
            )

    except Exception as exc:
        logger.exception("Unexpected error processing webhook payload")

    # Always return 200 — Meta retries on non-200
    return jsonify({"status": "ok"}), 200


# ─────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "service": "whatsapp-integration", "api": "meta"}), 200
