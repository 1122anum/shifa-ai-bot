# Meta WhatsApp Business API — Setup Guide

## Step 1 — Facebook Developer Account

1. Jao: **https://developers.facebook.com**
2. Top right: **"Get Started"** ya **"My Apps"**
3. Facebook account se login karo

---

## Step 2 — New App Banao

1. **My Apps → Create App**
2. App type: **"Business"** select karo → Next
3. App name: `Shifa AI` likho
4. Business account: apna ya create new
5. **Create App** click karo

---

## Step 3 — WhatsApp Product Add Karo

1. App dashboard mein neeche scroll karo
2. **"WhatsApp"** product dhundo → **"Set up"** click karo
3. Business portfolio select karo (ya new banao)

---

## Step 4 — Credentials Copy Karo

WhatsApp → Getting Started page pe:

```
Phone Number ID   → META_PHONE_NUMBER_ID
Access Token      → META_ACCESS_TOKEN  (temporary, 24hr)
```

Inhe `.env` file mein paste karo:
```env
META_ACCESS_TOKEN=EAAxxxxxxxxxxxxxxx
META_PHONE_NUMBER_ID=1234567890123456
META_VERIFY_TOKEN=shifa_verify_token
```

---

## Step 5 — Test Number Configure Karo

1. **"To"** field mein apna WhatsApp number daalo
2. **"Send message"** click karo — test message aayega
3. Iska matlab API kaam kar rahi hai ✓

---

## Step 6 — ngrok Start Karo

**Terminal 1:**
```powershell
cd "c:\Users\Tech Trends\Desktop\shifa ai\whatsapp-integration"
python run.py
```

**Terminal 2:**
```powershell
cd "c:\Users\Tech Trends\Desktop\shifa ai\whatsapp-integration"
python start_ngrok.py
```

URL copy karo, jaise:
```
https://abc123.ngrok-free.app
```

---

## Step 7 — Webhook Configure Karo

1. Meta App Dashboard → **WhatsApp → Configuration**
2. **Webhook** section mein:
   - **Callback URL:**
     ```
     https://abc123.ngrok-free.app/webhook/whatsapp
     ```
   - **Verify Token:**
     ```
     shifa_verify_token
     ```
3. **"Verify and Save"** click karo
4. ✓ Green checkmark aayega — webhook verified!

---

## Step 8 — Webhook Fields Subscribe Karo

Webhook verified hone ke baad:

1. **"Webhook fields"** section mein
2. **"messages"** ke saamne **"Subscribe"** click karo

---

## Step 9 — Test Karo

Browser mein health check:
```
https://abc123.ngrok-free.app/health
```
Response:
```json
{"status": "ok", "service": "whatsapp-integration", "api": "meta"}
```

Phir apne WhatsApp se test number pe message bhejo:
```
Mujhe bukhar hai
```

---

## Permanent Access Token (Important!)

Default token sirf **24 ghante** valid hota hai.

Permanent token ke liye:
1. **Meta Business Suite → System Users**
2. New system user banao (Admin role)
3. **"Generate New Token"** → WhatsApp permissions select karo
4. Ye token permanent rahega

---

## Credentials Summary

| Variable | Kahan Milega |
|---|---|
| `META_ACCESS_TOKEN` | WhatsApp → Getting Started → Temporary token |
| `META_PHONE_NUMBER_ID` | WhatsApp → Getting Started → Phone Number ID |
| `META_VERIFY_TOKEN` | Aap khud set karo (`.env` mein `shifa_verify_token`) |
