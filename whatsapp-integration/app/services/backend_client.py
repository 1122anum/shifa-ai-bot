"""
backend_client.py — HTTP client for the FastAPI backend.

Exposes:
  call_triage(user_id, symptoms)          -> str
  call_voice_triage(user_id, audio_path)  -> dict {transcript, ai_response}

Dead code removed — call_transcribe() was unreachable after call_voice_triage return.
"""

import requests
from app.config import config
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BackendError(Exception):
    """Raised when the FastAPI backend returns an error or is unreachable."""
    pass


def call_triage(user_id: str, symptoms: str) -> str:
    """
    POST /api/triage

    Args:
        user_id:  WhatsApp sender number
        symptoms: Symptom text — may include conversation history prefix

    Returns:
        AI triage response string.

    Raises:
        BackendError: on connection failure or non-2xx response.
    """
    payload = {"user_id": user_id, "symptoms": symptoms}
    logger.info("Calling triage API | user=%s | symptoms_len=%d", user_id, len(symptoms))

    try:
        response = requests.post(
            config.TRIAGE_URL,
            json=payload,
            timeout=config.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise BackendError(f"Cannot connect to backend at {config.TRIAGE_URL}") from exc
    except requests.exceptions.Timeout as exc:
        raise BackendError("Backend triage request timed out") from exc
    except requests.exceptions.HTTPError as exc:
        raise BackendError(
            f"Backend returned HTTP {response.status_code}: {response.text}"
        ) from exc

    data = response.json()
    ai_response = data.get("ai_response") or data.get("response") or ""
    if not ai_response:
        raise BackendError("Backend returned empty ai_response")

    logger.info("Triage response received | user=%s | len=%d", user_id, len(ai_response))
    return ai_response


def call_voice_triage(user_id: str, audio_path: str, vital_context: str = "") -> dict:
    """
    POST /api/voice-triage

    Sends audio file, gets back transcript + ai_response in one call.

    Args:
        user_id:       WhatsApp sender number
        audio_path:    Local path to downloaded audio file
        vital_context: Optional experimental camera-vital context string
                       that will be prepended to the transcript before
                       Gemini triage on the backend.

    Returns:
        dict with keys: transcript, ai_response

    Raises:
        BackendError: on failure
    """
    logger.info("Calling voice-triage API | user=%s | file=%s | vital_ctx=%s",
                user_id, audio_path, bool(vital_context))

    form_data = {"user_id": user_id}
    if vital_context and vital_context.strip():
        form_data["vital_context"] = vital_context.strip()

    try:
        with open(audio_path, "rb") as audio_file:
            response = requests.post(
                f"{config.BACKEND_BASE_URL}/api/voice-triage",
                files={"file": audio_file},
                data=form_data,
                timeout=config.REQUEST_TIMEOUT,
            )
        response.raise_for_status()
    except FileNotFoundError as exc:
        raise BackendError(f"Audio file not found: {audio_path}") from exc
    except requests.exceptions.ConnectionError as exc:
        raise BackendError("Cannot connect to backend") from exc
    except requests.exceptions.Timeout as exc:
        raise BackendError("Voice triage request timed out") from exc
    except requests.exceptions.HTTPError as exc:
        raise BackendError(
            f"Backend returned HTTP {response.status_code}: {response.text}"
        ) from exc

    result = response.json()
    ai_response = result.get("ai_response", "")
    transcript  = result.get("transcript", "")

    if not ai_response:
        raise BackendError("Voice triage returned empty ai_response")

    logger.info(
        "Voice triage done | user=%s | transcript_len=%d",
        user_id, len(transcript),
    )
    return {"transcript": transcript, "ai_response": ai_response}


def call_emergency_analyze(
    user_id: str,
    symptoms: str,
    conversation_history: str = "",
    vital_data: dict | None = None,
) -> dict:
    """
    POST /api/emergency/analyze

    Args:
        user_id: WhatsApp sender number
        symptoms: Symptom text with conversation context
        conversation_history: Previous conversation turns
        vital_data: Optional camera vital measurements

    Returns:
        dict with emergency analysis result

    Raises:
        BackendError on failure
    """
    payload = {
        "user_id": user_id,
        "symptoms": symptoms,
        "conversation_history": conversation_history,
    }
    if vital_data:
        payload["vital_data"] = vital_data

    logger.info("Calling emergency analyze API | user=%s", user_id)

    try:
        response = requests.post(
            f"{config.BACKEND_BASE_URL}/api/emergency/analyze",
            json=payload,
            timeout=config.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise BackendError("Cannot connect to backend") from exc
    except requests.exceptions.Timeout as exc:
        raise BackendError("Emergency analyze request timed out") from exc
    except requests.exceptions.HTTPError as exc:
        raise BackendError(
            f"Backend returned HTTP {response.status_code}: {response.text}"
        ) from exc

    return response.json()
