"""
audio_handler.py — Downloads voice messages from Meta WhatsApp Cloud API.

Meta stores media at a URL that requires Bearer token auth.
Flow:
  1. Get media URL from:  GET /v19.0/{media_id}
  2. Download binary from the returned URL with Bearer token
"""

import os
import uuid
import requests

from app.config import config
from app.utils.logger import get_logger

logger = get_logger(__name__)

AUDIO_MIME_TYPES: dict[str, str] = {
    "audio/ogg": ".ogg",
    "audio/ogg; codecs=opus": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/amr": ".amr",
    "audio/3gpp": ".3gp",
    "audio/webm": ".webm",
}

META_MEDIA_URL = "https://graph.facebook.com/v19.0/{media_id}"


def is_audio_message(content_type: str) -> bool:
    """Return True if the content type is a recognised audio type."""
    if not content_type:
        return False
    base_type = content_type.split(";")[0].strip().lower()
    return base_type.startswith("audio/")


def download_audio(media_id: str, content_type: str) -> str:
    """
    Download a voice message from Meta Cloud API.

    Args:
        media_id:     The media ID from the webhook payload.
        content_type: MIME type of the audio file.

    Returns:
        Local file path of the downloaded audio file.
    """
    os.makedirs(config.AUDIO_TEMP_DIR, exist_ok=True)

    base_type = content_type.split(";")[0].strip().lower()
    ext = AUDIO_MIME_TYPES.get(base_type, ".ogg")
    filename = f"{uuid.uuid4().hex}{ext}"
    local_path = os.path.join(config.AUDIO_TEMP_DIR, filename)

    headers = {"Authorization": f"Bearer {config.META_ACCESS_TOKEN}"}

    # Step 1 — Get the actual download URL from Meta
    logger.info("Getting media URL | media_id=%s", media_id)
    meta_url = META_MEDIA_URL.format(media_id=media_id)
    resp = requests.get(meta_url, headers=headers, timeout=config.REQUEST_TIMEOUT)
    resp.raise_for_status()
    download_url = resp.json().get("url")

    if not download_url:
        raise ValueError(f"No download URL returned for media_id={media_id}")

    # Step 2 — Download the audio binary
    logger.info("Downloading audio | url=%s | ext=%s", download_url[:60], ext)
    audio_resp = requests.get(
        download_url,
        headers=headers,
        timeout=config.REQUEST_TIMEOUT,
        stream=True,
    )
    audio_resp.raise_for_status()

    with open(local_path, "wb") as f:
        for chunk in audio_resp.iter_content(chunk_size=8192):
            f.write(chunk)

    logger.info("Audio downloaded | path=%s | size=%d bytes",
                local_path, os.path.getsize(local_path))
    return local_path


def cleanup_audio(file_path: str) -> None:
    """Remove a temporary audio file. Silently ignores missing files."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.debug("Cleaned up audio file | path=%s", file_path)
    except OSError as exc:
        logger.warning("Could not clean up audio | path=%s | error=%s", file_path, exc)
