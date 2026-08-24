# Shifa AI — WhatsApp Integration

> **Part 2 of 2** — WhatsApp / Twilio integration layer for the AI Medical Triage Bot.  
> Part 1 (FastAPI + Gemini + Whisper backend) is maintained by the backend team on the `backend-ai` branch.

---

## What This Module Does

This module connects WhatsApp users to the AI triage backend via Twilio.

```
WhatsApp User
     │
     ▼
Twilio WhatsApp
     │
     ▼
POST /webhook/whatsapp     ← This module
     │
     ├─── TEXT ────────────► POST /api/triage (FastAPI)
     │                               │
     └─── VOICE ──► Download Audio   │
                         │           │
                         ▼           │
                   POST /api/transcribe (Whisper)
                         │           │
                         ▼           │
                       Text ─────────┘
                                     │
                                     ▼
                               Gemini AI
                                     │
                                     ▼
                             Triage Response
                                     │
                                     ▼
                           Twilio → WhatsApp → User
```

---

## Project Structure

```
whatsapp-integration/
├── app/
│   ├── __init__.py
│   ├── config.py               # All env vars, centralised
│   ├── webhook.py              # Flask app — POST /webhook/whatsapp
│   ├── handlers/
│   │   ├── text_handler.py     # Text message flow
│   │   └── voice_handler.py    # Voice message flow
│   ├── services/
│   │   ├── backend_client.py   # HTTP client → FastAPI /api/triage + /api/transcribe
│   │   ├── twilio_sender.py    # Sends WhatsApp replies via Twilio REST API
│   │   └── audio_handler.py    # Downloads Twilio voice media
│   └── utils/
│       └── logger.py           # Shared logger
├── tests/
│   ├── conftest.py             # Shared fixtures, env stubs
│   ├── test_webhook.py         # Webhook routing tests
│   ├── test_text_handler.py    # All 5 spec test scenarios
│   ├── test_voice_handler.py   # Voice flow + error cases
│   ├── test_backend_client.py  # HTTP client mocking
│   ├── test_twilio_sender.py   # Formatter + sender tests
│   └── test_audio_handler.py  # Audio download + MIME detection
├── audio_temp/                 # Temporary audio files (git-ignored)
├── .env.example                # Template — copy to .env and fill in
├── .gitignore
├── requirements.txt
├── run.py                      # Development entry point
├── NGROK_SETUP.md              # Step-by-step ngrok + Twilio config guide
└── README.md                   # This file
```

---

## Quick Start

### 1. Clone and set up environment

```powershell
# From the repo root
cd whatsapp-integration

# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure credentials

```powershell
Copy-Item .env.example .env
```

Edit `.env` and fill in:

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
BACKEND_BASE_URL=http://localhost:8000
```

### 3. Start the backend (team member's service)

```powershell
# In a separate terminal, from the backend-ai folder:
uvicorn app.main:app --reload --port 8000
```

### 4. Start the WhatsApp integration server

```powershell
python run.py
```

### 5. Start ngrok

```powershell
ngrok http 5000
```

Copy the `https://xxxxx.ngrok-free.app` URL.

See [NGROK_SETUP.md](NGROK_SETUP.md) for the full Twilio configuration walkthrough.

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `TWILIO_ACCOUNT_SID` | ✅ | — | Twilio Account SID (starts with AC) |
| `TWILIO_AUTH_TOKEN` | ✅ | — | Twilio Auth Token |
| `TWILIO_WHATSAPP_NUMBER` | ✅ | — | Your Twilio WhatsApp number (whatsapp:+1...) |
| `BACKEND_BASE_URL` | ✅ | `http://localhost:8000` | Base URL of the FastAPI backend |
| `WHISPER_ENDPOINT` | ❌ | `/api/transcribe` | Transcription endpoint path |
| `INTEGRATION_PORT` | ❌ | `5000` | Port for this Flask server |
| `AUDIO_TEMP_DIR` | ❌ | `audio_temp` | Directory for temporary audio files |
| `LOG_LEVEL` | ❌ | `INFO` | Logging verbosity (DEBUG/INFO/WARNING/ERROR) |
| `TWILIO_VALIDATE_SIGNATURE` | ❌ | `true` | Set to `false` for local dev/testing |

---

## API Endpoints

### `POST /webhook/whatsapp`
Receives all incoming WhatsApp messages from Twilio.

**Twilio payload fields used:**
| Field | Description |
|---|---|
| `From` | Sender's WhatsApp number |
| `Body` | Text message content |
| `NumMedia` | Number of media attachments |
| `MediaUrl0` | URL of the first media item |
| `MediaContentType0` | MIME type of the first media item |
| `MessageSid` | Unique message identifier |

**Returns:** Empty TwiML 200 response (replies are sent via REST API, not TwiML verbs).

### `GET /health`
Health check endpoint. Returns:
```json
{"status": "ok", "service": "whatsapp-integration"}
```

---

## Message Flows

### Text Message

```
User sends: "Mujhe bukhar aur khansi hai"
    │
    ▼
webhook.py extracts Body + From
    │
    ▼
text_handler.py → backend_client.call_triage(user_id, symptoms)
    │
    ▼
FastAPI /api/triage → Gemini AI
    │
    ▼
ai_response → format_triage_response()
    │
    ▼
twilio_sender.send_whatsapp_message(from, formatted_response)
```

### Voice Message

```
User sends voice note
    │
    ▼
webhook.py detects NumMedia > 0 AND audio/* content type
    │
    ▼
voice_handler.py
    │
    ├─ 1. audio_handler.download_audio(media_url, content_type)
    │       └─ Authenticated GET to Twilio CDN → saves to audio_temp/
    │
    ├─ 2. backend_client.call_transcribe(audio_path)
    │       └─ POST /api/transcribe → Whisper → transcript text
    │
    ├─ 3. backend_client.call_triage(user_id, transcript)
    │       └─ POST /api/triage → Gemini → ai_response
    │
    ├─ 4. twilio_sender.send_whatsapp_message(from, formatted_response)
    │
    └─ 5. audio_handler.cleanup_audio(audio_path)   [always runs]
```

---

## Error Handling

| Scenario | User Receives |
|---|---|
| Backend / Gemini unavailable | "Sorry, the system is temporarily unavailable..." |
| Voice transcription fails | "Sorry, I could not understand the voice message..." |
| Non-audio media (image, doc) | "I can only process text messages and voice notes..." |
| Empty text message | Prompt to describe symptoms |
| Any unexpected error | Generic "Something went wrong" message |

Internal errors, stack traces, and API keys are **never** sent to the user.

---

## Emergency Detection

If the AI response contains the word **EMERGENCY** (case-insensitive), the reply is automatically formatted with a prominent warning:

```
⚠️ *EMERGENCY*

Your symptoms may require *immediate medical attention*.

[AI response here]

🚨 Please seek emergency medical care immediately.
Do not rely on this chatbot for emergency medical decisions.
```

---

## Running Tests

```powershell
# From whatsapp-integration/ with venv active
pytest tests/ -v
```

All tests run **fully offline** — no Twilio account or running backend needed.

### Test Scenarios Covered

| # | Scenario | Test File |
|---|---|---|
| 1 | Normal Urdu text (halki khansi) | `test_text_handler.py` |
| 2 | Urdu — 2-day fever | `test_text_handler.py` |
| 3 | English — headache | `test_text_handler.py` |
| 4 | Emergency — chest pain + breathing | `test_text_handler.py` |
| 5 | Urdu voice note | `test_voice_handler.py` |
| + | Backend unavailable | `test_text_handler.py` |
| + | Voice transcription failure | `test_voice_handler.py` |
| + | Triage failure after transcription | `test_voice_handler.py` |
| + | Emergency in voice flow | `test_voice_handler.py` |
| + | Webhook routing (text/voice/image/empty) | `test_webhook.py` |
| + | HTTP client error handling | `test_backend_client.py` |
| + | MIME type detection | `test_audio_handler.py` |

---

## Git Branch Strategy

```
main
 ├── backend-ai        ← Team member's Gemini + FastAPI + Whisper
 └── whatsapp-integration  ← This module
```

Do not modify files under `backend-ai/` directly. Coordinate through the shared API contract:

- `POST /api/triage` — `{"user_id": "...", "symptoms": "..."}` → `{"ai_response": "..."}`
- `POST /api/transcribe` — multipart file upload → `{"text": "..."}`

---

## Integration Checklist

Before merging to `main`:

- [ ] FastAPI backend is running on port 8000
- [ ] `GET /health` returns 200
- [ ] Text message reaches `/api/triage` and reply arrives in WhatsApp
- [ ] Voice message is downloaded, transcribed, and response sent to WhatsApp
- [ ] Emergency message shows ⚠️ header in WhatsApp
- [ ] Backend-down scenario sends safe error message
- [ ] Voice transcription failure sends safe error message
- [ ] All `pytest tests/` pass
- [ ] `.env` is not committed (check `.gitignore`)
- [ ] `audio_temp/` is not committed
- [ ] Twilio webhook URL updated to current ngrok URL
- [ ] Twilio signature validation enabled in production (`TWILIO_VALIDATE_SIGNATURE=true`)

---

## Production Deployment Notes

For production (instead of ngrok):

1. Deploy this Flask app behind **gunicorn**:
   ```bash
   gunicorn -w 2 -b 0.0.0.0:5000 app.webhook:app
   ```
2. Put it behind **nginx** or a cloud load balancer with a real TLS certificate.
3. Set a **static Twilio webhook URL** (no more ngrok URL changes).
4. Keep `TWILIO_VALIDATE_SIGNATURE=true` to reject spoofed requests.
5. Set `LOG_LEVEL=WARNING` in production to reduce noise.

---

## Team Contacts

| Module | Owner | Branch |
|---|---|---|
| FastAPI + Gemini + Whisper | Backend team | `backend-ai` |
| WhatsApp + Twilio + Webhook | This module | `whatsapp-integration` |
