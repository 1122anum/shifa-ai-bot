"""
test_twilio_sender.py — Tests for format_triage_response (meta_sender).

Note: twilio_sender.py is dead code (Twilio replaced by Meta API).
These tests now cover the Meta sender formatter only.
"""

from app.services.meta_sender import format_triage_response, _is_emergency


class TestIsEmergency:
    def test_urgency_label_emergency(self):
        assert _is_emergency("Urgency Level: EMERGENCY\nCall 1122.") is True

    def test_triage_label_emergency(self):
        assert _is_emergency("Triage Level: EMERGENCY\nSeek help.") is True

    def test_routine_is_not_emergency(self):
        assert _is_emergency("Triage Level: ROUTINE\nRest.") is False

    def test_urgent_is_not_emergency(self):
        assert _is_emergency("Urgency Level: URGENT\nSee doctor.") is False

    def test_educational_emergency_not_triggered(self):
        """EMERGENCY mentioned in educational context must NOT trigger header."""
        text = (
            "*Urgency Level: ROUTINE*\n"
            "### When to seek EMERGENCY care:\n"
            "- Sudden severe headache"
        )
        assert _is_emergency(text) is False

    def test_case_insensitive(self):
        assert _is_emergency("urgency level: emergency\nseek help.") is True


class TestFormatTriageResponse:
    def test_emergency_adds_header(self):
        resp = format_triage_response("Urgency Level: EMERGENCY\nCall now.")
        assert "⚠️" in resp
        assert "*EMERGENCY*" in resp
        assert "immediately" in resp.lower()

    def test_routine_unchanged(self):
        resp = format_triage_response("Triage Level: ROUTINE\nDrink water.")
        assert resp == "Triage Level: ROUTINE\nDrink water."

    def test_emergency_preserves_original(self):
        ai = "Urgency Level: EMERGENCY\nGo to ER."
        resp = format_triage_response(ai)
        assert ai in resp
