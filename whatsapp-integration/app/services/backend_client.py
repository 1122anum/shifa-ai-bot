"""
backend_client.py — HTTP client for the team member's FastAPI backend.

Responsibilities:
  - POST /api/triage   → get AI triage response for a symptom text
  - POST /api/transcribe → send audio file, receive transcribed text

All network errors are caught here and re-raised as BackendError so
callers never have to handle raw requests exceptions.
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
        user_id:  WhatsApp sender identifier (e.g. 'whatsapp:+923001234567')
        symptoms: The symptom text (plain text, any language)

    Returns:
        AI triage response string.

    Raises:
        BackendError: on connection failure or non-2xx response.
    """
    payload = {
        "user_id": user_id,
        "symptoms": symptoms,
    }
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

    # Expected response shape: {"status": "success", "user_id": "...", "ai_response": "..."}
    ai_response = data.get("ai_response") or data.get("response") or ""
    if not ai_response:
        raise BackendError("Backend returned empty ai_response")

    logger.info("Triage response received | user=%s | len=%d", user_id, len(ai_response))
    return ai_response


def call_voice_triage(user_id: str, audio_path: str) -> dict:
    """
    POST /api/voice-triage

    Single call — sends audio file, gets back transcript + ai_response.
    This is more efficient than calling /api/transcribe + /api/triage separately.

    Args:
        user_id:    WhatsApp sender number
        audio_path: Local path to downloaded audio file

    Returns:
        dict with keys: transcript, ai_response

    Raises:
        BackendError: on failure
    """
    logger.info("Calling voice-triage API | user=%s | file=%s", user_id, audio_path)

    try:
        with open(audio_path, "rb") as audio_file:
            files = {"file": audio_file}
            data  = {"user_id": user_id}
            response = requests.post(
                f"{config.BACKEND_BASE_URL}/api/voice-triage",
                files=files,
                data=data,
                timeout=config.REQUEST_TIMEOUT,
            )
        response.raise_for_status()
    except FileNotFoundError as exc:
        raise BackendError(f"Audio file not found: {audio_path}") from exc
    except requests.exceptions.ConnectionError as exc:
        raise BackendError(f"Cannot connect to backend") from exc
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

    logger.info("Voice triage done | user=%s | transcript_len=%d", user_id, len(transcript))
    return {"transcript": transcript, "ai_response": ai_response}
    """
    POST /api/transcribe

    Sends the downloaded audio file to the backend's Whisper endpoint
    and returns the transcribed text.

    Args:
        audio_path: Absolute or relative path to the local audio file.

    Returns:
        Transcribed text string.

    Raises:
        BackendError: on connection failure, non-2xx response, or empty transcript.
    """
    logger.info("Calling transcribe API | file=%s", audio_path)

    try:
        with open(audio_path, "rb") as audio_file:
            files = {"file": audio_file}
            response = requests.post(
                config.TRANSCRIBE_URL,
                files=files,
                timeout=config.REQUEST_TIMEOUT,
            )
        response.raise_for_status()
    except FileNotFoundError as exc:
        raise BackendError(f"Audio file not found: {audio_path}") from exc
    except requests.exceptions.ConnectionError as exc:
        raise BackendError(
            f"Cannot connect to transcription service at {config.TRANSCRIBE_URL}"
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise BackendError("Transcription request timed out") from exc
    except requests.exceptions.HTTPError as exc:
        raise BackendError(
            f"Transcription service returned HTTP {response.status_code}: {response.text}"
        ) from exc

    data = response.json()

    # Backend returns: {"status": "success", "transcript": "..."}
    transcript = data.get("transcript") or data.get("text") or ""
    if not transcript:
        raise BackendError("Transcription returned empty text")

    logger.info("Transcription received | len=%d", len(transcript))
    return transcript.strip()
