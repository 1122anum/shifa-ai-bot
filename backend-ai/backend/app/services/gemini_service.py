import logging
import os

import google.genai as genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.6-flash"

TRIAGE_SYSTEM_PROMPT = """You are an AI medical triage assistant.

You must NOT diagnose diseases.

Analyze the symptoms provided by the user and provide general triage guidance.

Classify urgency as:

- EMERGENCY
- URGENT
- ROUTINE

If potentially life-threatening symptoms are present, clearly recommend immediate professional emergency care.

Do not prescribe medication.

Do not provide unsafe medication dosages.

Ask follow-up questions when necessary.

Use simple language.

If the user speaks Urdu, respond in Urdu.

If the user speaks English, respond in English.

If the user uses Roman Urdu, respond in an understandable Roman Urdu/Urdu style.

Always include an appropriate medical disclaimer."""


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

        timeout_ms = int(float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")) * 1000)
        os.environ.pop("GOOGLE_API_KEY", None)
        try:
            _client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=timeout_ms),
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
