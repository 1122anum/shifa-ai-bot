"""
emergency_messages.py — Multilingual emergency guidance templates.

Provides pre-built WhatsApp messages for:
  - Emergency detection & location request
  - Emergency guidance
  - Dispatch notification (always labelled SIMULATED)
  - Cancellation confirmation
  - Safety disclaimers

Languages: English, Urdu, Sindhi, Roman Urdu, Roman Sindhi
"""

# ── Language detection (reuse from vitals_handler) ──────────────────────

def detect_user_language(from_number: str) -> str:
    """Best-effort language detection from the user's last message in DB."""
    try:
        import sqlite3, os, re
        db_path = os.path.join(
            os.path.dirname(__file__), "..", "database", "..", "..", "shifa_ai.db"
        )
        db_path = os.path.normpath(db_path)
        if not os.path.exists(db_path):
            return "en"

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT message FROM messages "
                "WHERE role = 'user' ORDER BY created_at DESC LIMIT 1",
            ).fetchone()

        if not row:
            return "en"

        msg = row["message"] or ""

        if re.search(r'[\u0600-\u06FF]', msg):
            if any(w in msg for w in ['آهيان', 'آهي', 'مون', 'کي', 'ڀيو', 'ساهه', 'ڌڙڪن']):
                return "sd"
            return "ur"

        lower = msg.lower()
        roman_urdu_words = ['hai', 'hain', 'mujhe', 'ko', 'ki', 'ka', 'rahe',
                             'rahi', 'karo', 'dekho', 'nhi', 'nahi', 'bhi']
        roman_sindhi_words = ['aahi', 'aahe', 'mujh', 'khe', 'bhiyo']
        urdu_score = sum(1 for w in roman_urdu_words if w in lower.split())
        sindhi_score = sum(1 for w in roman_sindhi_words if w in lower.split())

        if sindhi_score > urdu_score:
            return "roman_sindhi"
        if urdu_score > 0:
            return "roman_urdu"
        return "en"
    except Exception:
        return "en"


# ── Emergency location request messages ─────────────────────────────────

def emergency_location_request(lang: str = "en") -> str:
    """Message requesting patient location after emergency detection."""
    if lang == "ur":
        return (
            "🚨 *آپ کی علامات فوری طبی امداد کی ضرورت کی نشاندہی کر سکتی ہیں۔*\n\n"
            "براہِ کرم فوراً ایمرجنسی طبی مدد حاصل کریں۔\n\n"
            "📍 *براہِ کرم اپنی موجودہ لوکیشن شیئر کریں* تاکہ ایمرجنسی "
            "رہنمائی میں مدد کی جا سکے۔\n\n"
            "اگر آپ کی حالت شدید ہے تو خود گاڑی نہ چلائیں۔\n"
            "ضرورت پڑنے پر فوراً اپنے مقامی ایمرجنسی نمبر پر رابطہ کریں۔"
        )
    elif lang == "sd":
        return (
            "🚨 *توهان جون علامتون فوري طبي مدد جي ضرورت ظاهر ڪري سگهن ٿيون.*\n\n"
            "مهرباني ڪري فوراً ايمرجنسي طبي مدد حاصل ڪريو.\n\n"
            "📍 *مهرباني ڪري پنهنجي موجوده لوڪيشن شيئر ڪريو* ته جيئن "
            "ايمرجنسي رهنمائي ۾ مدد ڪري سگهجي.\n\n"
            "جيڪڏهن توهان جي حالت شديد آهي ته پاڻ گاڏي نه هلايو.\n"
            "ضرورت پوڻ تي فوراً پنهنجي مقامي ايمرجنسي نمبر تي رابطو ڪريو."
        )
    elif lang == "roman_urdu":
        return (
            "🚨 *Aap ki alamat fori tibbi imdad ki zarurat ki nishandahi kar sakti hain.*\n\n"
            "Barah-e-karam foran emergency tibbi madad hasil karein.\n\n"
            "📍 *Barah-e-karam apni maujooda location share karein* taake "
            "emergency rehnumai mein madad ki ja sake.\n\n"
            "Agar aap ki halat shadeed hai to khud gaari na chalayein.\n"
            "Zaroorat parne par foran apne maqami emergency number par raabta karein."
        )
    elif lang == "roman_sindhi":
        return (
            "🚨 *Aanh joon alamatun fori tibbi madad ji zarurat zahir kari saghan thiyon.*\n\n"
            "Mehrban kari foran emergency tibbi madad hasil kariyo.\n\n"
            "📍 *Mehrban kari panhanji maujooda location share kariyo* ta je "
            "emergency rehnumai mein madad kari sage.\n\n"
            "Jekadhn anh ji halat shadeed aahe ta paan gaari na halayo.\n"
            "Zaroorat pokan ti foran panhanje maqami emergency number te raabto kariyo."
        )
    else:  # English
        return (
            "🚨 *Your symptoms may require urgent medical attention.*\n\n"
            "Please seek emergency medical care immediately.\n\n"
            "📍 *Please share your current location* so we can assist with "
            "emergency routing.\n\n"
            "Do not drive yourself if you are severely unwell.\n"
            "If possible, contact your local emergency service immediately."
        )


# ── Emergency guidance messages ─────────────────────────────────────────

def emergency_guidance(lang: str = "en", category: str = "") -> str:
    """Concise emergency guidance message."""
    cat_text = f"\nCategory: {category.replace('_', ' ').title()}" if category else ""

    if lang == "ur":
        return (
            "🚨 *ایمرجنسی ہدایات*\n\n"
            "آپ کی علامات سنگین ہو سکتی ہیں۔\n\n"
            "✅ فوراً ایمرجنسی سروسز سے رابطہ کریں\n"
            "✅ آرام کریں اور حرکت کم کریں\n"
            "❌ خود گاڑی نہ چلائیں\n"
            "❌ اکیلے نہ رہیں اگر ممکن ہو\n\n"
            "⚠️ یہ AI معاون ٹریج ہے — طبی تشخیص نہیں۔"
        )
    elif lang == "sd":
        return (
            "🚨 *ايمرجنسي هدايتون*\n\n"
            "توهان جون علامتون سنگين ٿي سگهن ٿيون.\n\n"
            "✅ فوراً ايمرجنسي سروسز سان رابطو ڪريو\n"
            "✅ آرام ڪريو ۽ حرڪت گهٽ ڪريو\n"
            "❌ پاڻ گاڏي نه هلايو\n"
            "❌ اڪيلا نه رهو جيڪڏهن ممڪن هجي\n\n"
            "⚠️ هي AI مددگار ٽريج آهي — طبي تشخيص نه."
        )
    elif lang in ("roman_urdu", "roman_sindhi"):
        return (
            "🚨 *Emergency Hidayat*\n\n"
            "Aap ki alamat sangeen ho sakti hain.\n\n"
            "✅ Foran emergency services se raabta karein\n"
            "✅ Aaram karein aur harkat kam karein\n"
            "❌ Khud gaari na chalayein\n"
            "❌ Akele na rahein agar mumkin ho\n\n"
            "⚠️ Yeh AI madadgar triage hai — tibbi tashkhees nahi."
        )
    else:
        return (
            "🚨 *Emergency Guidance*\n\n"
            "Your symptoms may be serious.\n\n"
            "✅ Contact emergency services immediately\n"
            "✅ Rest and minimise movement\n"
            "❌ Do not drive yourself\n"
            "❌ Do not stay alone if possible\n\n"
            "⚠️ This is AI-assisted triage — NOT a medical diagnosis."
        )


# ── Dispatch notification ───────────────────────────────────────────────

def dispatch_notification(lang: str = "en", dispatch_id: str = "",
                          eta_minutes: float = 0, facility: str = "") -> str:
    """Notify patient about mock dispatch — always clearly labelled SIMULATED."""
    eta_text = f"{eta_minutes:.0f} minutes" if eta_minutes else "N/A"
    fac_text = f"Nearest Facility: {facility}" if facility else ""

    if lang == "ur":
        return (
            "🚑 *ایمرجنسی ڈسپیچ — سمولیٹڈ*\n\n"
            f"ڈسپیچ آئی ڈی: {dispatch_id}\n"
            f"موقع: {fac_text}\n"
            f"موقع تک پہنچنے کا اندازہ وقت: {eta_text} (تخمینہ)\n\n"
            "⚠️ *یہ ایک ڈیمو/سمولیٹڈ ڈسپیچ ہے۔*\n"
            "*یہ کوئی حقیقی ایمبولینس نہیں ہے۔*\n"
            "حقیقی ایمرجنسی میں اپنے مقامی ایمرجنسی نمبر پر کال کریں۔"
        )
    elif lang == "sd":
        return (
            "🚑 *ايمرجنسي ڊسپيچ — سيموليٽيڊ*\n\n"
            f"ڊسپيچ آئي ڊي: {dispatch_id}\n"
            f"ويجهي سهولت: {fac_text}\n"
            f"اندازي وقت: {eta_text} (تخمينو)\n\n"
            "⚠️ *هي هڪ ڊيمو/سيموليٽيڊ ڊسپيچ آهي.*\n"
            "*هي ڪا حقيقي ايمبولينس نه آهي.*\n"
            "حقيقي ايمرجنسي ۾ پنهنجي مقامي ايمرجنسي نمبر تي ڪال ڪريو."
        )
    elif lang in ("roman_urdu", "roman_sindhi"):
        return (
            "🚑 *Emergency Dispatch — SIMULATED*\n\n"
            f"Dispatch ID: {dispatch_id}\n"
            f"Nearest Facility: {fac_text}\n"
            f"Estimated Time: {eta_text} (Estimated)\n\n"
            "⚠️ *Yeh ek DEMO/SIMULATED dispatch hai.*\n"
            "*Yeh koi haqiqi ambulance nahi hai.*\n"
            "Haqiqi emergency mein apne maqami emergency number par call karein."
        )
    else:
        return (
            "🚑 *Emergency Dispatch — SIMULATED*\n\n"
            f"Dispatch ID: {dispatch_id}\n"
            f"Nearest Facility: {fac_text}\n"
            f"Estimated Time: {eta_text} (Estimated)\n\n"
            "⚠️ *This is a DEMO/SIMULATED dispatch.*\n"
            "*This is NOT a real ambulance.*\n"
            "In a real emergency, call your local emergency number immediately."
        )


# ── Cancellation confirmation ───────────────────────────────────────────

def cancellation_confirmation(lang: str = "en") -> str:
    """Confirm emergency cancellation with safety reminder."""
    if lang == "ur":
        return (
            "ℹ️ *ایمرجنسی منسوخ کر دی گئی*\n\n"
            "ایمرجنسی ورک فلو منسوخ کر دیا گیا ہے۔\n\n"
            "⚠️ اگر آپ کی علامات اب بھی سنگین ہیں تو براہ کرم فوراً "
            "ایمرجنسی طبی مدد حاصل کریں۔\n"
            "منسوخی آپ کو طبی مشورہ حاصل کرنے سے نہیں روکتی۔"
        )
    elif lang == "sd":
        return (
            "ℹ️ *ايمرجنسي منسوخ ڪئي وئي*\n\n"
            "ايمرجنسي ورڪ فلو منسوخ ڪيو ويو آهي.\n\n"
            "⚠️ جيڪڏهن توهان جون علامتون اڃا به سنگين آهن ته مهرباني ڪري "
            "فوراً ايمرجنسي طبي مدد حاصل ڪريو.\n"
            "منسوخي توهان کي طبي صلاح حاصل ڪرڻ کان نه روڪي ٿي."
        )
    elif lang in ("roman_urdu", "roman_sindhi"):
        return (
            "ℹ️ *Emergency Cancel kar di gayi*\n\n"
            "Emergency workflow cancel kar diya gaya hai.\n\n"
            "⚠️ Agar aap ki alamat ab bhi sangeen hain to barah-e-karam "
            "foran emergency tibbi madad hasil karein.\n"
            "Cancellation aap ko tibbi mashwara hasil karne se nahi rokti."
        )
    else:
        return (
            "ℹ️ *Emergency Cancelled*\n\n"
            "The emergency workflow has been cancelled.\n\n"
            "⚠️ If your symptoms remain potentially serious, please seek "
            "emergency medical care immediately.\n"
            "Cancellation does not prevent you from seeking medical advice."
        )


# ── Transport options ───────────────────────────────────────────────────

def transport_options_message(lang: str = "en") -> str:
    """Message offering transport choices: Ambulance, InDrive, Uber."""
    if lang == "ur":
        return (
            "🚗 *ایمرجنسی ٹرانسپورٹ منتخب کریں*\n\n"
            "براہِ کرم نیچے دیے گئے آپشنز میں سے اپنا ذریعہ سفر منتخب کریں:\n\n"
            "🚑 *1. ایمبولینس* — قریب ترین ایمرجنسی ایمبولینس بُلائی جائے\n"
            "🚕 *2. ان ڈرائیو (InDrive)* — فوری رائیڈ بک کریں\n"
            "🚙 *3. اوبر (Uber)* — فوری رائیڈ بک کریں\n\n"
            "براہِ کرم *1*، *2*، یا *3* ٹائپ کریں۔"
        )
    elif lang == "sd":
        return (
            "🚗 *ايمرجنسي ٽرانسپورٽ چونڊيو*\n\n"
            "مهرباني ڪري هيٺ ڏنل آپشنز مان پنهنجو سفر جو ذريعو چونڊيو:\n\n"
            "🚑 *1. ايمبولينس* — ويجهي ايمرجنسي ايمبولينس گهرايو\n"
            "🚕 *2. ان ڊرائيو (InDrive)* — فوري رائيڊ بڪ ڪريو\n"
            "🚙 *3. اوبر (Uber)* — فوري رائيڊ بڪ ڪريو\n\n"
            "مهرباني ڪري *1*، *2*، يا *3* ٽائپ ڪريو."
        )
    elif lang == "roman_urdu":
        return (
            "🚗 *Emergency Transport Select Karein*\n\n"
            "Barah-e-karam neeche diye gaye options mein se apna zariya-e-safar select karein:\n\n"
            "🚑 *1. Ambulance* — Qareebi emergency ambulance bulayein\n"
            "🚕 *2. InDrive* — Fauri ride book karein\n"
            "🚙 *3. Uber* — Fauri ride book karein\n\n"
            "Barah-e-karam *1*, *2*, ya *3* type karein."
        )
    elif lang == "roman_sindhi":
        return (
            "🚗 *Emergency Transport Select Kariyo*\n\n"
            "Mehrban kari heath diye optionan mein panhanje safar jo zareeo select kariyo:\n\n"
            "🚑 *1. Ambulance* — Veenhi emergency ambulance ghareyo\n"
            "🚕 *2. InDrive* — Fauri ride book kariyo\n"
            "🚙 *3. Uber* — Fauri ride book kariyo\n\n"
            "Mehrban kari *1*, *2*, ya *3* type kariyo."
        )
    else:  # English
        return (
            "🚗 *Choose Emergency Transport*\n\n"
            "Please select your mode of transport from the options below:\n\n"
            "🚑 *1. Ambulance* — Call the nearest emergency ambulance\n"
            "🚕 *2. InDrive* — Book an immediate ride\n"
            "🚙 *3. Uber* — Book an immediate ride\n\n"
            "Please type *1*, *2*, or *3*."
        )


def transport_booked_confirmation(lang: str = "en", transport_type: str = "",
                                   facility: str = "", lat: float = 0,
                                   lng: float = 0) -> str:
    """Confirmation message after user selects a transport option."""
    type_labels = {
        "ambulance": "🚑 Ambulance",
        "indrive": "🚕 InDrive",
        "uber": "🚙 Uber",
    }
    label = type_labels.get(transport_type, transport_type)

    if lang == "ur":
        return (
            f"✅ *{label} منتخب ہو گیا*\n\n"
            f"منزل: {facility or 'قریب ترین ایمرجنسی سہولت'}\n\n"
            "⚠️ *یہ ایک ڈیمو/سمولیٹڈ بکنگ ہے۔*\n"
            "حقیقی ایمرجنسی میں اپنے مقامی ایمرجنسی نمبر پر کال کریں۔"
        )
    elif lang == "sd":
        return (
            f"✅ *{label} چونڊيو ويو*\n\n"
            f"منزل: {facility or 'ويجهي ايمرجنسي سهولت'}\n\n"
            "⚠️ *هي هڪ ڊيمو/سيموليٽيڊ بکنگ آهي.*\n"
            "حقيقي ايمرجنسي ۾ پنهنجي مقامي ايمرجنسي نمبر تي ڪال ڪريو."
        )
    elif lang in ("roman_urdu", "roman_sindhi"):
        return (
            f"✅ *{label} select ho gaya*\n\n"
            f"Manzil: {facility or 'Qareebi emergency facility'}\n\n"
            "⚠️ *Yeh ek DEMO/SIMULATED booking hai.*\n"
            "Haqiqi emergency mein apne maqami emergency number par call karein."
        )
    else:
        return (
            f"✅ *{label} Selected*\n\n"
            f"Destination: {facility or 'Nearest Emergency Facility'}\n\n"
            "⚠️ *This is a DEMO/SIMULATED booking.*\n"
            "In a real emergency, call your local emergency number immediately."
        )


# ── Location received confirmation ──────────────────────────────────────

def location_received_confirmation(lang: str = "en", distance_km: float = 0,
                                   facility: str = "", eta: float = 0) -> str:
    """Confirm location received with nearest facility info."""
    dist_text = f"{distance_km:.1f} km" if distance_km else "N/A"
    eta_text = f"{eta:.0f} min (Estimated)" if eta else "N/A"

    if lang == "ur":
        return (
            "📍 *لوکیشن موصول ہوئی*\n\n"
            f"قریب ترین سہولت: {facility or 'N/A'}\n"
            f"فاصلہ: {dist_text}\n"
            f"اندازی وقت: {eta_text}\n\n"
            "ایمرجنسی ٹیم کو آگاہ کر دیا گیا ہے۔\n"
            "⚠️ یہ تجرباتی رہنمائی ہے — حقیقی ایمرجنسی سروس نہیں۔"
        )
    elif lang == "sd":
        return (
            "📍 *لوڪيشن ملي وئي*\n\n"
            f"ويجهي سهولت: {facility or 'N/A'}\n"
            f"فاصلو: {dist_text}\n"
            f"اندازي وقت: {eta_text}\n\n"
            "ايمرجنسي ٽيم کي آگاهه ڪيو ويو آهي.\n"
            "⚠️ هي تجرباتي رهنمائي آهي — حقيقي ايمرجنسي سروس نه."
        )
    elif lang in ("roman_urdu", "roman_sindhi"):
        return (
            "📍 *Location wasil hui*\n\n"
            f"Qareeb tareen sahulat: {facility or 'N/A'}\n"
            f"Faasla: {dist_text}\n"
            f"Andazi waqt: {eta_text}\n\n"
            "Emergency team ko aagah kar diya gaya hai.\n"
            "⚠️ Yeh tajurbati rehnumai hai — haqiqi emergency service nahi."
        )
    else:
        return (
            "📍 *Location Received*\n\n"
            f"Nearest Facility: {facility or 'N/A'}\n"
            f"Distance: {dist_text}\n"
            f"ETA: {eta_text}\n\n"
            "Emergency team has been alerted.\n"
            "⚠️ This is experimental guidance — NOT a real emergency service."
        )
