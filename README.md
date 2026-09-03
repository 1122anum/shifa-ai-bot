# Shifa AI — AI-Powered Medical Triage & Emergency Assistant

An AI-powered healthcare assistant that supports multi-language symptom triage, voice messages, experimental camera-based vital estimation, emergency severity detection, geofencing, and real-time emergency dashboards — all accessible via WhatsApp.

---

## Features

- **AI Symptom Triage** — Gemini-powered urgency classification (EMERGENCY / HIGH_RISK / ROUTINE)
- **Multi-Language Support** — English, Urdu, Roman Urdu, Sindhi, Roman Sindhi
- **Voice Messages** — Whisper speech-to-text via Groq or OpenAI
- **WhatsApp Integration** — Meta WhatsApp Business API
- **Experimental Camera Vitals** — rPPG/vPPG heart rate and respiration rate estimation
- **Emergency Engine** — Severity classification, geofencing, facility lookup
- **Real-Time Dashboard** — WebSocket-powered emergency monitoring
- **Mock Dispatch** — Simulated ambulance dispatch for development
- **Conversation Context** — Multi-turn conversation memory
- **Secret Scanning** — Pre-commit hooks with Gitleaks

---

## Architecture

```
WhatsApp User
     │
     ▼
Meta WhatsApp Business API
     │
     ▼
WhatsApp Integration (Flask)          Backend (FastAPI)
  ├── Text → /api/triage ──────────────► Gemini AI
  ├── Voice → Whisper ─────────────────► Speech-to-Text
  │         → /api/triage ─────────────► Gemini AI
  ├── Emergency Analysis ──────────────► Gemini (severity classification)
  ├── Camera Vitals (rPPG) ───────────► Signal Processing
  └── Dashboard (WebSocket) ──────────► Real-time Updates
```

---

## Project Structure

```
shifa-ai/
│
├── backend-ai/backend/          # FastAPI backend (Gemini + Whisper + Vitals)
│   ├── app/
│   │   ├── core/config.py       # Centralised configuration
│   │   ├── api/                 # Emergency & vitals routers
│   │   ├── models/              # Pydantic schemas
│   │   ├── services/            # Gemini, Whisper, Emergency, Dispatch, etc.
│   │   └── main.py              # FastAPI application
│   ├── static/                  # Camera page & dashboard HTML
│   ├── tests/
│   ├── .env.example
│   └── requirements.txt
│
├── whatsapp-integration/        # Flask webhook layer (Meta WhatsApp API)
│   ├── app/
│   │   ├── config.py            # Centralised configuration
│   │   ├── handlers/            # Text, voice, location, vitals, emergency
│   │   ├── services/            # Meta sender, backend client, audio handler
│   │   ├── utils/               # Logger with secret redaction
│   │   └── webhook.py           # Flask webhook endpoints
│   ├── tests/
│   ├── .env.example
│   └── requirements.txt
│
├── .gitignore
├── .pre-commit-config.yaml      # Gitleaks + pre-commit hooks
├── SECURITY.md                  # Security policy
└── README.md                    # This file
```

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/your-org/shifa-ai.git
cd shifa-ai
```

### 2. Set up the Backend

```bash
cd backend-ai/backend

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and fill in your API keys
```

### 3. Set up the WhatsApp Integration

```bash
cd whatsapp-integration

# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1    # Windows
# source venv/bin/activate      # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and fill in your Meta API credentials
```

### 4. Run the Services

```bash
# Terminal 1 — Backend
cd backend-ai/backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 — WhatsApp Integration
cd whatsapp-integration
python run.py
```

---

## Environment Variables

All secrets are loaded from `.env` files. **Never commit `.env` to Git.**

### Backend (`backend-ai/backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Google Gemini API key |
| `GROQ_API_KEY` or `OPENAI_API_KEY` | Yes | Speech-to-text provider key |
| `DASHBOARD_SECRET_TOKEN` | Yes | Dashboard authentication token |
| `META_ACCESS_TOKEN` | Optional | Meta WhatsApp token (for vital notifications) |
| `EMERGENCY_DISPATCH_MODE` | No | `MOCK` (default) or `PRODUCTION` |
| `ENVIRONMENT` | No | `development` (default) or `production` |

### WhatsApp Integration (`whatsapp-integration/.env`)

| Variable | Required | Description |
|---|---|---|
| `META_ACCESS_TOKEN` | Yes | Meta WhatsApp Business API token |
| `META_PHONE_NUMBER_ID` | Yes | Phone number ID from Facebook |
| `META_VERIFY_TOKEN` | Yes | Custom verification token |
| `NGROK_AUTH_TOKEN` | Dev | ngrok authentication token |
| `DASHBOARD_SECRET_TOKEN` | Yes | Must match backend |

See `.env.example` in each subproject for the full list.

---

## Security

- All credentials loaded from environment variables
- Secret redaction in logs
- Webhook signature validation (Meta X-Hub-Signature-256)
- Pre-commit secret scanning with Gitleaks
- CORS restricted in production
- Constant-time token comparison for dashboard auth
- No secrets in source code, tests, or documentation

See [SECURITY.md](SECURITY.md) for the full security policy.

---

## Testing

```bash
# Backend tests
cd backend-ai/backend
pytest -v

# WhatsApp integration tests
cd whatsapp-integration
pytest -v
```

All tests run offline — no API keys required.

---

## Medical Safety Disclaimer

Shifa AI is a **triage assistant, not a doctor**. It classifies symptom urgency and provides general guidance. It does NOT diagnose diseases or prescribe treatment. For any medical emergency, contact your local emergency services immediately.

Camera-derived vital estimates (heart rate, respiration rate) are **experimental** and must not be treated as clinical measurements.

---

## License

This project is provided for educational and development purposes. See [SECURITY.md](SECURITY.md) for responsible disclosure information.
