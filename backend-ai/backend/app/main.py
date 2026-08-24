import logging
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.models.schemas import (
    SymptomRequest,
    TriageResponse,
    TranscriptionResponse,
    VoiceTriageResponse,
)
from app.services import triage_service, whisper_service
from app.services.gemini_service import GeminiServiceError
from app.services.whisper_service import SUPPORTED_AUDIO_EXTENSIONS, WhisperServiceError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024

app = FastAPI(
    title="AI Medical Triage Backend",
    description=(
        "Backend module of the AI Medical Triage WhatsApp Bot. "
        "Provides Gemini-powered text triage and Whisper voice transcription. "
        "The WhatsApp/Twilio layer consumes these endpoints; it is NOT part of this module."
    ),
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        {
            "field": ".".join(str(loc) for loc in err.get("loc", []) if loc != "body"),
            "message": err.get("msg", "invalid value"),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"status": "error", "detail": "Invalid request.", "errors": errors},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "detail": str(exc.detail)},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled internal error")
    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": "An unexpected internal error occurred."},
    )


@app.get("/")
def root():
    return {
        "service": "AI Medical Triage Backend",
        "version": "1.0.0",
        "endpoints": {
            "health": "GET /health",
            "text_triage": "POST /api/triage",
            "voice_transcription": "POST /api/transcribe",
            "voice_triage": "POST /api/voice-triage",
            "docs": "/docs",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/triage", response_model=TriageResponse)
def analyze(data: SymptomRequest):
    """Text triage endpoint used by the WhatsApp layer."""
    try:
        result = triage_service.get_triage(data.symptoms)
    except GeminiServiceError:
        raise HTTPException(
            status_code=502,
            detail="The AI medical service is temporarily unavailable. Please try again later.",
        )
    return TriageResponse(status="success", user_id=data.user_id, ai_response=result)


@app.post("/api/transcribe", response_model=TranscriptionResponse)
async def transcribe(file: UploadFile = File(...)):
    """Transcribe a WhatsApp voice note to text without running triage."""
    saved_path = await _save_upload_to_temp(file)
    try:
        transcript = whisper_service.transcribe_audio(str(saved_path))
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="Audio file is missing or unreadable.")
    except WhisperServiceError:
        raise HTTPException(
            status_code=502,
            detail="The speech-to-text service is temporarily unavailable. Please try again later.",
        )
    finally:
        saved_path.unlink(missing_ok=True)
    return TranscriptionResponse(status="success", transcript=transcript)


@app.post("/api/voice-triage", response_model=VoiceTriageResponse)
async def voice_triage(user_id: str = Form(...), file: UploadFile = File(...)):
    """Full voice pipeline: Audio -> Whisper -> Text -> Gemini -> Triage response."""
    if not user_id.strip():
        raise HTTPException(status_code=422, detail="user_id must not be empty.")

    saved_path = await _save_upload_to_temp(file)
    try:
        try:
            transcript = whisper_service.transcribe_audio(str(saved_path))
        except FileNotFoundError:
            raise HTTPException(status_code=400, detail="Audio file is missing or unreadable.")
        except WhisperServiceError:
            raise HTTPException(
                status_code=502,
                detail="The speech-to-text service is temporarily unavailable. Please try again later.",
            )

        try:
            result = triage_service.get_triage(transcript)
        except GeminiServiceError:
            raise HTTPException(
                status_code=502,
                detail="The AI medical service is temporarily unavailable. Please try again later.",
            )
    finally:
        saved_path.unlink(missing_ok=True)

    return VoiceTriageResponse(
        status="success",
        user_id=user_id.strip(),
        transcript=transcript,
        ai_response=result,
    )


async def _save_upload_to_temp(upload: UploadFile) -> Path:
    original_name = upload.filename or ""
    extension = Path(original_name).suffix.lower()
    if extension not in SUPPORTED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported audio format '{extension or 'unknown'}'. "
                   f"Supported: {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}",
        )

    total_bytes = 0
    fd, tmp_name = tempfile.mkstemp(prefix="triage_audio_", suffix=extension)
    try:
        with os.fdopen(fd, "wb") as buffer:
            while chunk := await upload.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > MAX_AUDIO_SIZE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Audio file is too large. Maximum size is 25 MB.",
                    )
                buffer.write(chunk)
    finally:
        await upload.close()

    if total_bytes == 0:
        Path(tmp_name).unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")

    return Path(tmp_name)
