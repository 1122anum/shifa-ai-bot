import logging
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.models.schemas import (
    SymptomRequest,
    TriageResponse,
    TranscriptionResponse,
    VoiceTriageResponse,
)
from app.services import triage_service, whisper_service
from app.services.gemini_service import GeminiServiceError
from app.services.whisper_service import SUPPORTED_AUDIO_EXTENSIONS, WhisperServiceError
from app.services.websocket_manager import ws_manager, verify_dashboard_token
from app.api.vitals import router as vitals_router
from app.api.emergency import router as emergency_router

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

# CORS — required so the browser camera page (opened via WhatsApp link)
# can POST to /api/vitals/estimate on this backend.
# Session tokens provide authorisation; cookies are not used.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(vitals_router)
app.include_router(emergency_router, prefix="/api/emergency")

# Serve camera web page static files
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

@app.get("/vitals/camera")
def camera_page(s: str = ""):
    """Serve the mobile camera page for vital sign measurement."""
    page = os.path.join(os.path.dirname(__file__), "..", "static", "vitals", "camera.html")
    if not os.path.exists(page):
        raise HTTPException(status_code=404, detail="Camera page not found.")
    return FileResponse(page, media_type="text/html")


@app.get("/dashboard/emergencies")
def dashboard_page(token: str = ""):
    """Serve the real-time emergency dashboard page."""
    page = os.path.join(os.path.dirname(__file__), "..", "static", "dashboard", "index.html")
    if not os.path.exists(page):
        raise HTTPException(status_code=404, detail="Dashboard page not found.")
    return FileResponse(page, media_type="text/html")


@app.websocket("/ws/emergencies")
async def websocket_emergencies(websocket: WebSocket, token: str = ""):
    """WebSocket endpoint for real-time emergency dashboard updates."""
    if not verify_dashboard_token(token):
        await websocket.close(code=4003)
        return
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive — dashboard is read-only via WS
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


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
            "vitals_session": "POST /api/vitals/session",
            "vitals_estimate": "POST /api/vitals/estimate",
            "vitals_result": "GET /api/vitals/result/{session_id}",
            "camera_page": "GET /vitals/camera",
            "emergency_analyze": "POST /api/emergency/analyze",
            "emergency_active": "GET /api/emergency/active",
            "emergency_detail": "GET /api/emergency/{emergency_id}",
            "emergency_location": "POST /api/emergency/{emergency_id}/location",
            "emergency_acknowledge": "POST /api/emergency/{emergency_id}/acknowledge",
            "emergency_resolve": "POST /api/emergency/{emergency_id}/resolve",
            "emergency_cancel": "POST /api/emergency/{emergency_id}/cancel",
            "nearest_facility": "GET /api/emergency/facilities/nearest",
            "dispatch_mock": "POST /api/emergency/dispatch/mock",
            "dashboard": "GET /dashboard/emergencies",
            "websocket": "WS /ws/emergencies",
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
async def voice_triage(
    user_id: str = Form(...),
    file: UploadFile = File(...),
    vital_context: str = Form(default=""),
):
    """Full voice pipeline: Audio -> Whisper -> Text -> Gemini -> Triage response.

    If ``vital_context`` is provided it is prepended to the transcript so that
    Gemini receives recent experimental camera-vital estimates alongside the
    user's spoken symptoms.
    """
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

        # Attach experimental vital context (if any) before sending to Gemini
        symptoms_for_triage = transcript
        if vital_context and vital_context.strip():
            symptoms_for_triage = vital_context.strip() + "\n\n" + transcript

        try:
            result = triage_service.get_triage(symptoms_for_triage)
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
