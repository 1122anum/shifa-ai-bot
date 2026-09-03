import logging
from pathlib import Path

from openai import OpenAI, OpenAIError
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_EXTENSIONS = {
    ".mp3", ".mpeg", ".mpga", ".m4a", ".mp4",
    ".wav", ".webm", ".ogg", ".oga", ".amr", ".opus",
}
MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024

TRANSCRIPTION_HINT_PROMPT = (
    "The speaker may talk in Urdu, English, or Roman Urdu. "
    "Transcribe exactly what is said."
)


class WhisperServiceError(Exception):
    """Raised when the speech-to-text service fails or is unavailable."""


_client = None
_model_name = None


def _get_client():
    global _client, _model_name
    if _client is None:
        provider = settings.WHISPER_PROVIDER
        if provider == "groq":
            api_key = settings.GROQ_API_KEY
            base_url = "https://api.groq.com/openai/v1"
            default_model = settings.GROQ_WHISPER_MODEL
        else:
            api_key = settings.OPENAI_API_KEY
            base_url = None
            default_model = settings.OPENAI_WHISPER_MODEL

        if not api_key:
            raise WhisperServiceError("Speech-to-text API key is not configured.")

        timeout_seconds = float(settings.REQUEST_TIMEOUT_SECONDS)
        try:
            if base_url:
                _client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_seconds)
            else:
                _client = OpenAI(api_key=api_key, timeout=timeout_seconds)
        except Exception as exc:
            logger.error("Failed to initialize speech-to-text client: %s", exc)
            raise WhisperServiceError("Speech-to-text client could not be initialized.") from exc
        _model_name = default_model
    return _client


def reset_client() -> None:
    global _client, _model_name
    _client = None
    _model_name = None


def transcribe_audio(audio_path: str) -> str:
    """Transcribe a voice recording (Urdu / English / Roman Urdu) to text.

    Integration contract for the WhatsApp layer:
        transcript = whisper_service.transcribe_audio(downloaded_audio_path)
    """
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file does not exist: {path.name}")

    extension = path.suffix.lower()
    if extension not in SUPPORTED_AUDIO_EXTENSIONS:
        raise WhisperServiceError(f"Unsupported audio format: {extension or 'unknown'}")

    if path.stat().st_size == 0:
        raise WhisperServiceError("Audio file is empty.")

    transcript = _request_transcription(path)
    if not transcript:
        raise WhisperServiceError("Speech-to-text returned an empty transcript.")
    return transcript


def _request_transcription(path: Path) -> str:
    try:
        with path.open("rb") as audio_file:
            result = _get_client().audio.transcriptions.create(
                model=_model_name,
                file=(path.name, audio_file),
                prompt=TRANSCRIPTION_HINT_PROMPT,
            )
    except FileNotFoundError:
        raise
    except (OpenAIError, httpx.HTTPError) as exc:
        logger.error("Speech-to-text request failed: %s", exc)
        raise WhisperServiceError("Speech-to-text request failed or timed out.") from exc
    except Exception as exc:
        logger.error("Unexpected speech-to-text error: %s", exc)
        raise WhisperServiceError("Speech-to-text service failed unexpectedly.") from exc

    text = getattr(result, "text", "") or ""
    return text.strip()
