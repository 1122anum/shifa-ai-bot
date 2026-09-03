# Security Policy — Shifa AI

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in Shifa AI, please report it responsibly:

1. **Do NOT open a public GitHub issue** for security vulnerabilities.
2. Email the project maintainers at the contact listed in the repository.
3. Include a description of the vulnerability, steps to reproduce, and potential impact.
4. Allow reasonable time for the issue to be addressed before public disclosure.

We will acknowledge receipt within 48 hours and provide a timeline for remediation.

---

## Environment Variable Policy

### All secrets MUST come from environment variables

Shifa AI loads all credentials from `.env` files via `python-dotenv`. The following secrets are required:

| Variable | Service | Source |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini AI | [aistudio.google.com](https://aistudio.google.com/apikey) |
| `GROQ_API_KEY` or `OPENAI_API_KEY` | Whisper speech-to-text | [console.groq.com](https://console.groq.com/keys) or [platform.openai.com](https://platform.openai.com/api-keys) |
| `META_ACCESS_TOKEN` | Meta WhatsApp Business API | [developers.facebook.com](https://developers.facebook.com/apps) |
| `META_PHONE_NUMBER_ID` | Meta WhatsApp Business API | Facebook Developer Dashboard |
| `DASHBOARD_SECRET_TOKEN` | Emergency dashboard auth | Generate a random string |
| `NGROK_AUTH_TOKEN` | ngrok tunnel (dev only) | [ngrok.com](https://ngrok.com) |

### Rules

- **NEVER** hard-code credentials in source code, configuration files, or documentation.
- **NEVER** commit `.env` files to Git.
- **NEVER** share API keys in chat, email, or public channels.
- Use `.env.example` as a template — it contains only placeholder values.

---

## Secret Management

### Local Development

1. Copy `.env.example` to `.env` in each subproject:
   ```bash
   cp backend-ai/backend/.env.example backend-ai/backend/.env
   cp whatsapp-integration/.env.example whatsapp-integration/.env
   ```
2. Fill in your own credentials.
3. `.env` is listed in `.gitignore` and will not be committed.

### Production

- Use your platform's secret management (e.g., GitHub Actions Secrets, Docker secrets, cloud provider vaults).
- Rotate credentials regularly.
- Never use development credentials in production.

---

## API Key Rotation Procedure

If any credential is suspected of being compromised:

### Gemini API Key
1. Revoke the old key at [aistudio.google.com](https://aistudio.google.com/apikey).
2. Generate a new key.
3. Update `.env` with the new key.
4. Restart the backend service.

### Meta Access Token
1. Revoke the token in the Facebook Developer Dashboard.
2. Generate a new long-lived token.
3. Update `.env` with the new token.
4. Restart the WhatsApp integration service.

### Groq / OpenAI API Key
1. Revoke the key at the provider's console.
2. Generate a new key.
3. Update `.env` and restart the backend.

### Dashboard Secret Token
1. Generate a new random token.
2. Update `.env` in both backend and WhatsApp integration.
3. Restart both services.
4. Update any dashboard bookmarks with the new token.

---

## Data Privacy Principles

Shifa AI handles sensitive healthcare data. The following principles apply:

1. **Minimize data storage** — only store what the application requires.
2. **No raw audio retention** — voice messages are transcribed and immediately deleted.
3. **No raw camera frames** — camera vitals are processed in-memory; only derived estimates are stored.
4. **No patient photographs** — camera features are experimental and do not save images.
5. **Location data** — emergency geolocation is only accessible to authorized emergency workflows.
6. **Conversation data** — stored in a local SQLite database for context; not transmitted externally.

---

## Emergency Dispatch Safety

- **MOCK mode** (default): All dispatch is simulated. The dashboard clearly shows "SIMULATED" and messages state this is NOT a real ambulance.
- **PRODUCTION mode**: Requires an authorized dispatch provider, authentication, audit logging, and human oversight. AI classification alone never triggers real dispatch.

---

## Experimental Camera Vitals

Camera-derived heart rate, respiration rate, and rPPG/vPPG estimates are labeled **"Experimental Estimate"** throughout the UI and AI responses. They are NOT clinical measurements and must not be treated as such.

---

## Pre-Commit Secret Scanning

This project uses [Gitleaks](https://github.com/gitleaks/gitleaks) to scan for accidentally committed secrets. Install and configure:

```bash
# Install gitleaks
# https://github.com/gitleaks/gitleaks#installing

# Run manually
gitleaks detect --source . --verbose

# Or use the pre-commit hook (if configured)
pip install pre-commit
pre-commit install
```

---

## GitHub Actions Security

All CI/CD workflows use GitHub Repository Secrets:

```yaml
env:
  GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

Secrets are never printed in CI logs. The secret redaction filter in the logger provides an additional safety net.

---

## Responsible Disclosure

We appreciate responsible disclosure and will work with reporters to verify and address issues promptly.
