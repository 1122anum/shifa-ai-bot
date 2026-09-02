import logging
import os

import google.genai as genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.6-flash"

TRIAGE_SYSTEM_PROMPT = """You are Shifa AI, an AI medical triage assistant.

You must NOT diagnose diseases.

Analyze the symptoms provided by the user and provide general triage guidance.

Classify urgency as:
- EMERGENCY
- URGENT
- ROUTINE

If potentially life-threatening symptoms are present, clearly recommend immediate professional emergency care.

Do not prescribe medication or unsafe dosages.

Ask follow-up questions when necessary.

Use simple language.

If the user speaks Urdu, respond in Urdu.
If the user speaks English, respond in English.
If the user uses Roman Urdu, respond in Roman Urdu/Urdu style.
If the user speaks Sindhi, respond in Sindhi.
If the user uses Roman Sindhi, respond in Roman Sindhi where possible.

Always include an appropriate medical disclaimer.

--- EXPERIMENTAL CAMERA VITALS ---

The system may provide camera-derived physiological estimates alongside the symptoms.
These values are EXPERIMENTAL and may contain measurement errors.

Rules for using camera-derived values:
1. NEVER treat them as confirmed or clinical measurements.
2. Always prioritise the patient's reported symptoms over camera estimates.
3. If signal_quality is POOR or INVALID, ignore the camera values entirely.
4. If signal_quality is GOOD or FAIR, you may use them as supporting context only.
5. Do not base an EMERGENCY classification solely on camera values.
6. Always communicate the experimental nature of these estimates to the user.
7. Use language like: "The experimental camera check suggests..." not "Your heart rate is..."

Example camera context format you may receive:
[Experimental Camera Vitals — signal_quality: GOOD]
Heart Rate: 102 BPM (confidence: 0.81)
Respiration Rate: 21 breaths/min (confidence: 0.72)

When presenting results to patients in Urdu:
"تجرباتی کیمرہ چیک: دل کی دھڑکن تقریباً 102 BPM"

In Sindhi:
"تجرباتي وائٽل: دل جي ڌڙڪن لڳ ڀڳ 102 BPM"

Always add:
"⚠️ یہ تجرباتی اندازے ہیں — طبی پیمائش نہیں۔"
"""


class GeminiServiceError(Exception):
    """Raised when the Gemini AI service fails or is unavailable."""


_client = None
_model_name = None


def _get_client():
    global _client, _model_name
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise GeminiServiceError("Gemini API key is not configured.")

        # Remove any conflicting GOOGLE_API_KEY from environment
        os.environ.pop("GOOGLE_API_KEY", None)
        timeout_ms = int(float(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")) * 1000)
        try:
            _client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=timeout_ms,
                    api_version="v1",
                ),
            )
        except Exception as exc:
            logger.error("Failed to initialize Gemini client: %s", exc)
            raise GeminiServiceError("Gemini client could not be initialized.") from exc
        _model_name = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    return _client


def reset_client() -> None:
    global _client, _model_name
    _client = None
    _model_name = None


def get_triage(symptoms: str) -> str:
    """Send a symptoms message to Gemini and return triage guidance text.

    Integration contract for the WhatsApp layer:
        reply = gemini_service.get_triage(user_message_text)
    """
    text = (symptoms or "").strip()
    if not text:
        raise ValueError("Symptoms must not be empty.")

    reply = _generate_reply(text)
    if not reply:
        raise GeminiServiceError("Gemini returned an empty response.")
    return reply


def _generate_reply(symptoms: str) -> str:
    try:
        client = _get_client()
    except GeminiServiceError:
        raise

    try:
        response = client.models.generate_content(
            model=_model_name,
            contents=symptoms,
            config=types.GenerateContentConfig(
                system_instruction=TRIAGE_SYSTEM_PROMPT,
                temperature=0.3,
                max_output_tokens=1024,
            ),
        )
    except Exception as exc:
        logger.error("Gemini request failed: %s", exc)
        raise GeminiServiceError("Gemini request failed or timed out.") from exc

    try:
        return (response.text or "").strip()
    except Exception as exc:
        logger.error("Gemini returned no usable text (possibly safety-blocked): %s", exc)
        raise GeminiServiceError("Gemini could not generate a safe response.") from exc
