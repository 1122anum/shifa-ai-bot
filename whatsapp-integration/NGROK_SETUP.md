# ngrok Setup Guide

This guide connects your local WhatsApp integration server to Twilio over the internet using ngrok.

---

## Why ngrok?

Twilio needs a **public HTTPS URL** to deliver WhatsApp messages to your webhook.
ngrok creates a secure tunnel from the internet to your local machine.

---

## Step 1 — Install ngrok

### Option A: Direct download
Go to https://ngrok.com/download and download the binary for your OS.

### Option B: Windows (winget)
```powershell
winget install ngrok
```

### Option C: npm
```bash
npm install -g ngrok
```

---

## Step 2 — Create a free ngrok account

1. Sign up at https://dashboard.ngrok.com/signup
2. Copy your **Auth Token** from https://dashboard.ngrok.com/get-started/your-authtoken
3. Configure ngrok with your token:

```powershell

```
ngrok config add-authtoken YOUR_AUTH_TOKEN_HERE
---

## Step 3 — Start the backend (team member's FastAPI)

In a **separate terminal**, run:

```powershell
uvicorn app.main:app --reload --port 8000
```

Verify it is running:
```
http://localhost:8000/docs
```

---

## Step 4 — Start the WhatsApp integration server

In another terminal, from the `whatsapp-integration/` folder:

```powershell
python run.py
```

This starts Flask on port **5000**.

Verify it is running:
```
http://localhost:5000/health
```

Expected response:
```json
{"status": "ok", "service": "whatsapp-integration"}
```

---

## Step 5 — Start ngrok tunnel

In a **third terminal**:

```powershell
ngrok http 5000
```

You will see output like:

```
Session Status    online
Account           your@email.com
Forwarding        https://a1b2c3d4.ngrok-free.app -> http://localhost:5000
```

Copy the **https** forwarding URL. Example:
```
https://a1b2c3d4.ngrok-free.app
```

---

## Step 6 — Update your .env

Open `.env` and set:

```env
NGROK_PUBLIC_URL=https://a1b2c3d4.ngrok-free.app
```

---

## Step 7 — Configure Twilio Webhook

1. Log in to https://console.twilio.com
2. Go to **Messaging → Try it out → Send a WhatsApp message**
3. In the **Sandbox Settings** (or phone number settings), find:

   > **WHEN A MESSAGE COMES IN**

4. Set it to:
   ```
   https://a1b2c3d4.ngrok-free.app/webhook/whatsapp
   ```
5. Set the method to **HTTP POST**
6. Click **Save**

---

## Step 8 — Join the WhatsApp Sandbox (Twilio Testing)

Send the join code from your WhatsApp to the Twilio sandbox number:

```
whatsapp:+14155238886
```

Twilio will give you a join phrase like:
```
join <word>-<word>
```

Send that from WhatsApp to activate your sandbox session.

---

## Step 9 — Test the connection

Send a WhatsApp message to the Twilio sandbox number.

You should see:
- A log line in the Flask terminal
- An AI triage response back in WhatsApp

---

## Keeping ngrok Running

The free ngrok URL **changes every time you restart ngrok**.
Each restart requires:
1. Copying the new URL
2. Updating `.env`
3. Updating the Twilio webhook URL

For a stable URL, upgrade to ngrok's paid plan and use a **static domain**.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `ERR_NGROK_105` — auth token | Run `ngrok config add-authtoken <token>` |
| Twilio shows "11200 HTTP retrieval failure" | Check Flask is running on port 5000 |
| 403 Forbidden on webhook | Set `TWILIO_VALIDATE_SIGNATURE=false` in `.env` for local dev |
| ngrok session expired (free tier) | Restart ngrok and update Twilio webhook URL |
| Voice message not transcribed | Check the backend Whisper service is running on port 8000 |
| No response in WhatsApp | Check Twilio logs at https://console.twilio.com/us1/monitor/logs/sms |
