"""
input_validator.py — Robust input classification and sanitisation.

Handles:
  - /reset command
  - Greetings (English + Urdu)
  - Random non-medical text
  - Empty / whitespace-only messages
  - Very long messages (length cap)
  - Special characters / emoji-only
"""

import re

MAX_INPUT_CHARS = 2000

# ─────────────────────────────────────────────
# Greeting patterns
# ─────────────────────────────────────────────
GREETING_PATTERNS = re.compile(
    r"^("
    r"hi|hello|hey|good\s*(morning|afternoon|evening|night)|"
    r"howdy|what'?s\s*up|greetings|salam|salaam|"
    r"السلام\s*علیکم|سلام|آداب|وعلیکم\s*السلام|"
    r"assalam|assalamualaikum|walaikum|"
    r"helo|hlo|hlw|hii+|heya"
    r")[\s!،.]*$",
    re.IGNORECASE | re.UNICODE,
)

# Reset commands
RESET_PATTERNS = re.compile(
    r"^(/reset|reset|new\s*conversation|naya\s*sawal|"
    r"start\s*over|clear|/new|/start|/clear)[\s.!]*$",
    re.IGNORECASE | re.UNICODE,
)

# Medical keywords — if present, treat as symptom message
MEDICAL_KEYWORDS = re.compile(
    r"bukhar|fever|dard|pain|khansi|cough|sar|head|"
    r"saans|breath|dil|heart|seena|chest|nausea|ulti|"
    r"vomit|dizzy|chakkar|fatigue|thakan|rash|wound|"
    r"injury|blood|khoon|sugar|diabetes|bp|pressure|"
    r"infection|allerg|swell|sujan|ache|hurt|symptom|"
    r"problem|takleef|bimari|mareez|patient|hospital|"
    r"doctor|dawai|medicine|tabiyat|feel|feeling|sick|"
    r"ill|unwell|weak|kamzor|emergency|urgent",
    re.IGNORECASE | re.UNICODE,
)

# Purely non-text content (emoji / special chars only)
ONLY_SPECIAL_CHARS = re.compile(
    r"^[\s\W\d_]+$",
    re.UNICODE,
)

# ─────────────────────────────────────────────
# Responses
# ─────────────────────────────────────────────
GREETING_RESPONSE = (
    "👋 Hello! I am *Shifa AI*, your medical triage assistant.\n\n"
    "Please describe your symptoms and I will help assess their urgency.\n\n"
    "Example:\n"
    "• \"Mujhe 2 din se bukhar hai\"\n"
    "• \"I have chest pain and difficulty breathing\"\n\n"
    "Type */reset* to start a new conversation."
)

GREETING_RESPONSE_URDU = (
    "👋 وعلیکم السلام! میں *Shifa AI* ہوں، آپ کا طبی مددگار۔\n\n"
    "براہ کرم اپنی علامات بتائیں تاکہ میں آپ کی مدد کر سکوں۔\n\n"
    "مثال:\n"
    "• \"مجھے دو دن سے بخار ہے\"\n"
    "• \"سینے میں درد ہے\"\n\n"
    "نیا سوال شروع کرنے کے لیے */reset* لکھیں۔"
)

EMPTY_RESPONSE = (
    "Please describe your symptoms so I can help with triage guidance.\n\n"
    "Example: \"Mujhe bukhar aur khansi hai\""
)

NON_MEDICAL_RESPONSE = (
    "I am designed to help with medical symptom assessment only.\n\n"
    "Please describe any health symptoms you are experiencing and "
    "I will provide general triage guidance.\n\n"
    "Example: \"I have a headache and fever since yesterday.\""
)

TOO_LONG_RESPONSE = (
    "Your message is too long. Please describe your main symptoms "
    "in a shorter message (under 2000 characters)."
)

SPECIAL_CHARS_RESPONSE = (
    "I could not understand your message.\n"
    "Please describe your symptoms in text.\n\n"
    "Example: \"Mujhe sir dard hai\""
)

RESET_RESPONSE = (
    "✅ Conversation reset!\n\n"
    "You can now start a fresh conversation.\n"
    "Please describe your symptoms."
)


class InputValidationResult:
    """Result of input validation."""
    __slots__ = ("action", "response", "cleaned_text")

    def __init__(self, action: str, response: str = "", cleaned_text: str = ""):
        self.action = action          # "reply" | "triage" | "reset"
        self.response = response      # pre-built reply string (if action == "reply")
        self.cleaned_text = cleaned_text  # sanitised input (if action == "triage")


def validate_input(text: str) -> InputValidationResult:
    """
    Classify and sanitise incoming user text.

    Returns an InputValidationResult with:
      action="reply"  → send pre-built response (no AI call needed)
      action="triage" → forward cleaned_text to AI triage
      action="reset"  → reset conversation, send confirmation
    """
    # 1. Empty / whitespace
    if not text or not text.strip():
        return InputValidationResult("reply", EMPTY_RESPONSE)

    stripped = text.strip()

    # 2. Reset command
    if RESET_PATTERNS.match(stripped):
        return InputValidationResult("reset", RESET_RESPONSE)

    # 3. Too long
    if len(stripped) > MAX_INPUT_CHARS:
        return InputValidationResult("reply", TOO_LONG_RESPONSE)

    # 4. Arabic/Urdu greeting
    if "السلام" in stripped or "سلام" in stripped or "آداب" in stripped:
        return InputValidationResult("reply", GREETING_RESPONSE_URDU)

    # 5. English/Roman greeting
    if GREETING_PATTERNS.match(stripped):
        return InputValidationResult("reply", GREETING_RESPONSE)

    # 6. Special characters / emoji only
    if ONLY_SPECIAL_CHARS.match(stripped):
        return InputValidationResult("reply", SPECIAL_CHARS_RESPONSE)

    # 7. Has medical keywords → always triage
    if MEDICAL_KEYWORDS.search(stripped):
        return InputValidationResult("triage", cleaned_text=stripped)

    # 8. Very short non-medical text (< 5 chars, no medical context)
    if len(stripped) < 5:
        return InputValidationResult("reply", EMPTY_RESPONSE)

    # 9. Longer non-medical text — politely redirect
    # (but still triage if it might be symptoms we didn't catch)
    words = stripped.split()
    if len(words) <= 6 and not MEDICAL_KEYWORDS.search(stripped):
        # Short random text — redirect
        return InputValidationResult("reply", NON_MEDICAL_RESPONSE)

    # 10. Default — send to triage (Gemini will handle it appropriately)
    return InputValidationResult("triage", cleaned_text=stripped)
