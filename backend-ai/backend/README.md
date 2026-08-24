# AI Medical Triage Bot — Backend (Part 1)

FastAPI backend for the **AI Medical Triage WhatsApp Bot**. This module handles all AI work
(Gemini triage + Whisper voice transcription) and exposes clean HTTP endpoints.
The WhatsApp/Twilio layer (built separately by another team member) simply calls this API.

> This module does NOT contain any Twilio / WhatsApp / ngrok code.

---

## 1. Architecture

```
WhatsApp user message (text or voice)
        |
        v
[WhatsApp/Twilio layer — separate module]
        |                        |
        |  POST /api/triage      |  POST /api/voice-triage
        v                        v
+--------------------------------------------------+
|                FastAPI backend                    |
|                                                  |
|  Text:   symptoms ──> triage_service ──> Gemini  |
|  Voice:  audio    ──> whisper_service            |
|                       | transcript               |
|                       v                          |
|                   triage_service ──> Gemini      |
+--------------------------------------------------+
        |
        v
{ "status": "success", "user_id": "...", "ai_response": "..." }
```

## 2. Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app + endpoints + error handling
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py           # Pydantic request/response models
│   └── services/
│       ├── __init__.py
│       ├── gemini_service.py    # Gemini AI + medical triage prompt
│       ├── whisper_service.py   # Whisper voice transcription (OpenAI or Groq)
│       └── triage_service.py    # Orchestrates the triage workflow
├── tests/
│   ├── __init__.py
│   └── test_api.py              # API + service tests (AI APIs are mocked)
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## 3. Installation

Requires **Python 3.11+**.

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## 4. Configuration (`.env`)

```bash
# Windows
copy .env.example .env
# macOS/Linux
cp .env.example .env
```

Then fill in your keys:

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Yes (for triage) | Get from https://aistudio.google.com/apikey |
| `GEMINI_MODEL` | No | Defaults to `gemini-2.0-flash` |
| `OPENAI_API_KEY` | Yes for voice (OpenAI Whisper) | Get from https://platform.openai.com/api-keys |
| `OPENAI_WHISPER_MODEL` | No | Defaults to `whisper-1` |
| `WHISPER_PROVIDER` | No | `openai` (default) or `groq` |
| `GROQ_API_KEY` | Only if provider is `groq` | Groq key; model defaults to `whisper-large-v3` |
| `REQUEST_TIMEOUT_SECONDS` | No | AI call timeout, default `30` |

`.env` is git-ignored — never commit it.

## 5. Run the Server

```bash
uvicorn app.main:app --reload --port 8000
```

- Swagger UI: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## 6. Endpoints

### `GET /` — service info
### `GET /health` — returns `{"status": "ok"}`

### `POST /api/triage` — text triage (main endpoint)

Request:

```json
{
    "user_id": "user123",
    "symptoms": "I have fever and cough"
}
```

Success response (`200`):

```json
{
    "status": "success",
    "user_id": "user123",
    "ai_response": "Urgency: ROUTINE ... Disclaimer: ..."
}
```

The AI replies in the user's language automatically:
English → English, Urdu script → Urdu, Roman Urdu → Roman Urdu/Urdu style.

Errors:

| Status | Meaning |
|---|---|
| `422` | Missing fields / empty symptoms (`status: error`) |
| `502` | Gemini unavailable or timed out (safe generic message) |
| `500` | Unexpected internal error (no stack trace exposed) |

### `POST /api/transcribe` — voice note to text only

`multipart/form-data`: `file` = audio file (.ogg/.oga/.mp3/.m4a/.wav/.webm/.amr, max 25 MB).

Response:

```json
{ "status": "success", "transcript": "Mujhe bukhar hai" }
```

### `POST /api/voice-triage` — full voice pipeline (Audio → Whisper → Text → Gemini)

`multipart/form-data`: `user_id` (form field) + `file` (audio).

Response:

```json
{
    "status": "success",
    "user_id": "wa-42",
    "transcript": "Mujhe seene mein dard ho raha hai",
    "ai_response": "Urgency: EMERGENCY ..."
}
```

Voice errors: `400` empty/unreadable file · `413` >25 MB · `415` unsupported format · `502` Whisper/Gemini failure.

## 7. Testing the API

**Swagger (easiest):** open http://localhost:8000/docs → try `POST /api/triage` with the JSON above.

**curl:**

```bash
curl -X POST http://localhost:8000/api/triage ^
  -H "Content-Type: application/json" ^
  -d "{\"user_id\": \"user123\", \"symptoms\": \"I have fever and cough\"}"
```

Try an emergency case to verify the safety prompt:

```json
{ "user_id": "user123", "symptoms": "severe chest pain and shortness of breath" }
```

Expected: response contains `EMERGENCY` plus a recommendation to seek immediate professional care.

## 8. Automated Tests

External AI APIs are fully mocked — no keys needed to run tests.

```bash
pytest -v
```

Covered: `/health`, `/api/triage` success, invalid request, empty symptoms,
emergency symptoms, Gemini failure (→502), Whisper failure (→502),
unsupported audio format, empty upload, full voice pipeline.

## 9. Integration Guide for the WhatsApp/Twilio Developer

You do **not** need to touch any AI code. Two options:

### Option A — call the HTTP API (recommended)

Text messages — forward the user's text to:

```
POST http://<host>:8000/api/triage
Content-Type: application/json

{
    "user_id": "<whatsapp_user_id>",   // e.g. sender's wa number
    "symptoms": "<user message>"
}
```

Then send `ai_response` from the JSON reply back to the WhatsApp user verbatim.
Handle non-200 responses by sending a fallback message such as
"Service is temporarily unavailable, please try again."

Voice notes — download the Twilio media file locally, then either:
1. `POST /api/voice-triage` with `multipart/form-data` fields `user_id` + `file`
   (get the final triage answer in one call), or
2. `POST /api/transcribe` if you want only the transcript first.

Twilio WhatsApp voice notes arrive as `.ogg/.oga` — both are accepted.

### Option B — import the service functions directly

If the integration runs inside this same project/virtualenv:

```python
from app.services.triage_service import get_triage
from app.services.whisper_service import transcribe_audio

reply = get_triage("I have fever and cough")          # -> str (Gemini answer)

text = transcribe_audio(r"C:\tmp\voice_note.ogg")     # -> str (Urdu/English/Roman Urdu)
reply = get_triage(text)                              # voice -> text -> triage
```

Contract: `get_triage(symptoms: str) -> str`, `transcribe_audio(audio_path: str) -> str`.
These raise `GeminiServiceError` / `WhisperServiceError` on failure and never leak API keys.
They contain zero Twilio coupling.

## 10. Error Handling & Security Summary

- Empty/whitespace symptoms and invalid payloads → `422` before any AI call.
- Gemini/Whisper outages and network timeouts → `502` with a safe generic message;
  real errors are logged server-side only.
- Stack traces and API keys are never returned to clients.
- Audio uploads are validated (extension, emptiness, 25 MB cap) and written to temp files that are always deleted.

## 11. Medical Safety Rules (enforced via system prompt)

The Gemini model is instructed to act strictly as a **triage assistant, not a doctor**:
classify urgency as `EMERGENCY` / `URGENT` / `ROUTINE`, recommend immediate professional
care for life-threatening symptoms, never prescribe medication or dosages, ask follow-up
questions when needed, use simple language, mirror the user's language
(English / Urdu / Roman Urdu), and always include a medical disclaimer.
