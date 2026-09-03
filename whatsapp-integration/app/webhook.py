"""
webhook.py — Flask app for Meta WhatsApp Business API webhook.

Meta uses TWO types of requests:
  1. GET  /webhook/whatsapp — Verification challenge (one time setup)
  2. POST /webhook/whatsapp — Incoming messages

Also serves:
  GET /vitals/camera — Mobile camera page (proxied from backend static)
"""

import hashlib
import hmac
import os
from flask import Flask, request, Response, jsonify

from app.config import config
from app.services.audio_handler import is_audio_message
from app.handlers.text_handler import handle_text_message
from app.handlers.voice_handler import handle_voice_message
from app.handlers.location_handler import handle_location_message
from app.handlers.vitals_handler import send_vital_result_to_user
from app.services.meta_sender import send_whatsapp_message
from app.utils.logger import get_logger

logger = get_logger(__name__)

app = Flask(__name__)


# ─────────────────────────────────────────────
# Meta Webhook Signature Validation
# ─────────────────────────────────────────────
def _verify_meta_signature() -> bool:
    """Verify the X-Hub-Signature-256 header from Meta.

    Meta signs every webhook POST with the app secret using HMAC-SHA256.
    If META_APP_SECRET is not configured, skip validation (dev mode).
    """
    app_secret = os.getenv("META_APP_SECRET", "")
    if not app_secret:
        # Dev mode — no app secret configured, skip validation
        return True

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature:
        logger.warning("Missing X-Hub-Signature-256 header")
        return False

    expected = (
        "sha256="
        + hmac.new(
            app_secret.encode("utf-8"),
            request.get_data(),
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(signature, expected)


# ─────────────────────────────────────────────
# Webhook Verification (GET)
# ─────────────────────────────────────────────
@app.route("/webhook/whatsapp", methods=["GET"])
def verify_webhook():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    logger.info("Webhook verification | mode=%s | token_match=%s",
                mode, token == config.META_VERIFY_TOKEN)

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
    # Validate Meta webhook signature in production
    if not _verify_meta_signature():
        logger.warning("Webhook signature validation failed — rejecting request")
        return jsonify({"status": "error", "detail": "Invalid signature"}), 401

    data = request.get_json(silent=True)

    if not data:
        logger.warning("Empty or non-JSON payload received")
        return jsonify({"status": "ok"}), 200

    try:
        entry = data.get("entry", [])
        if not entry:
            return jsonify({"status": "ok"}), 200

        changes = entry[0].get("changes", [])
        if not changes:
            return jsonify({"status": "ok"}), 200

        value    = changes[0].get("value", {})
        messages = value.get("messages", [])

        if not messages:
            logger.debug("No messages in payload — likely a status update")
            return jsonify({"status": "ok"}), 200

        message     = messages[0]
        from_number = message.get("from", "")
        msg_type    = message.get("type", "")
        msg_id      = message.get("id", "")

        logger.info("Message received | id=%s | from=%s | type=%s",
                    msg_id, from_number, msg_type)

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

        # ── LOCATION ─────────────────────────
        elif msg_type == "location":
            location_data = message.get("location", {})
            handle_location_message(from_number=from_number, location_data=location_data)

        # ── UNSUPPORTED MEDIA ─────────────────
        else:
            logger.info("Unsupported message type | type=%s | from=%s",
                        msg_type, from_number)
            send_whatsapp_message(
                from_number,
                "I can only process text messages and voice notes.\n"
                "Please describe your symptoms in text or send a voice message.",
            )

    except Exception:
        logger.exception("Unexpected error processing webhook payload")

    return jsonify({"status": "ok"}), 200


# ─────────────────────────────────────────────
# Emergency Alert Callback
# ─────────────────────────────────────────────
@app.route("/webhook/emergency-alert", methods=["POST"])
def emergency_alert():
    """
    POST /webhook/emergency-alert

    Callback from the backend when an emergency event occurs.
    """
    data = request.get_json(silent=True)

    if not data:
        logger.warning("Emergency alert: empty or non-JSON payload")
        return jsonify({"status": "error", "detail": "Empty or invalid payload."}), 400

    user_id = data.get("user_id", "")
    if not user_id:
        logger.warning("Emergency alert: missing user_id")
        return jsonify({"status": "error", "detail": "user_id is required."}), 400

    event = data.get("event", "")
    logger.info("Emergency alert received | user=%s | event=%s", user_id, event)

    return jsonify({"status": "ok"}), 200


# ─────────────────────────────────────────────
# Vital Result Callback
# ─────────────────────────────────────────────
@app.route("/webhook/vital-result", methods=["POST"])
def vital_result():
    """
    POST /webhook/vital-result

    Callback from the backend when a vital measurement completes.
    Forwards the result to the user via WhatsApp.
    """
    data = request.get_json(silent=True)

    if not data:
        logger.warning("Vital result: empty or non-JSON payload")
        return jsonify({"status": "error", "detail": "Empty or invalid payload."}), 400

    user_id = data.get("user_id", "")
    if not user_id:
        logger.warning("Vital result: missing user_id")
        return jsonify({"status": "error", "detail": "user_id is required."}), 400

    logger.info("Vital result received | user=%s | status=%s",
                user_id, data.get("status"))
    send_vital_result_to_user(data)

    return jsonify({"status": "ok"}), 200


# ─────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "service": "whatsapp-integration",
                    "api": "meta"}), 200


# ─────────────────────────────────────────────
# Camera Page (served via Flask — single ngrok URL)
# ─────────────────────────────────────────────
@app.route("/vitals/camera", methods=["GET"])
def vitals_camera():
    """
    Serve the mobile camera page.
    Served by Flask (port 5000 via ngrok) so phone can open it.
    Injects the backend API URL so browser can call /api/vitals/estimate.
    """
    page_path = os.path.normpath(os.path.join(
        os.path.dirname(__file__), "..", "..",
        "backend-ai", "backend", "static", "vitals", "camera.html"
    ))

    if not os.path.exists(page_path):
        return jsonify({"error": "Camera page not found", "path": page_path}), 404

    with open(page_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Replace API_BASE so browser POST goes to backend via Flask proxy
    ngrok_url = config.NGROK_PUBLIC_URL.rstrip("/") if hasattr(config, 'NGROK_PUBLIC_URL') else ""
    if not ngrok_url:
        from dotenv import load_dotenv
        load_dotenv()
        import os as _os
        ngrok_url = _os.getenv("NGROK_PUBLIC_URL", "").rstrip("/")

    html = html.replace(
        "const API_BASE       = window.location.origin;",
        f"const API_BASE       = '{ngrok_url}';"
    )

    return Response(html, status=200, mimetype="text/html")


# ─────────────────────────────────────────────
# Vitals API Proxy (Flask → FastAPI backend)
# Browser on phone cannot reach localhost:8000
# So Flask proxies /api/vitals/* to backend
# ─────────────────────────────────────────────
@app.route("/api/vitals/<path:subpath>", methods=["GET", "POST"])
def vitals_proxy(subpath):
    """Proxy /api/vitals/* requests to FastAPI backend."""
    import requests as req

    backend_url = f"{config.BACKEND_BASE_URL}/api/vitals/{subpath}"
    if request.query_string:
        backend_url += "?" + request.query_string.decode()

    try:
        if request.method == "POST":
            resp = req.post(
                backend_url,
                json=request.get_json(silent=True),
                timeout=60,
            )
        else:
            resp = req.get(backend_url, timeout=10)

        return Response(
            resp.content,
            status=resp.status_code,
            content_type=resp.headers.get("Content-Type", "application/json"),
        )
    except req.exceptions.ConnectionError:
        return jsonify({"status": "error",
                        "detail": "Backend unavailable"}), 503
