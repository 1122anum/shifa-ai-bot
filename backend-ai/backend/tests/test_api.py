import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import gemini_service, triage_service, whisper_service
from app.services.gemini_service import GeminiServiceError
from app.services.whisper_service import WhisperServiceError

FAKE_TRIAGE_REPLY = (
    "Urgency: URGENT\n"
    "Please visit a doctor within 24 hours.\n"
    "Disclaimer: This is general guidance, not a medical diagnosis."
)

FAKE_EMERGENCY_REPLY = (
    "Urgency: EMERGENCY\n"
    "Chest pain can be life-threatening. Go to the nearest emergency room immediately.\n"
    "Disclaimer: This is general guidance, not a medical diagnosis."
)


@pytest.fixture(autouse=True)
def reset_ai_clients():
    gemini_service.reset_client()
    whisper_service.reset_client()
    yield
    gemini_service.reset_client()
    whisper_service.reset_client()


@pytest.fixture()
def client():
    return TestClient(app)


class _FakeResponse:
    text = FAKE_TRIAGE_REPLY


class _FakeGeminiClient:
    class models:
        @staticmethod
        def generate_content(**kwargs):
            return _FakeResponse()


class _FailingGeminiClient:
    class models:
        @staticmethod
        def generate_content(**kwargs):
            raise TimeoutError("simulated network timeout")


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "AI Medical Triage Backend"
    assert "text_triage" in body["endpoints"]


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_triage_success(client, monkeypatch):
    monkeypatch.setattr(triage_service, "get_triage", lambda symptoms: FAKE_TRIAGE_REPLY)
    response = client.post(
        "/api/triage",
        json={"user_id": "user123", "symptoms": "I have fever and cough"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "user_id": "user123",
        "ai_response": FAKE_TRIAGE_REPLY,
    }


def test_triage_invalid_missing_fields(client):
    response = client.post("/api/triage", json={"symptoms": "fever"})
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "error"
    assert any(e["field"] == "user_id" for e in body["errors"])


def test_triage_empty_symptoms_rejected(client):
    payloads = [
        {"user_id": "u1", "symptoms": ""},
        {"user_id": "u1", "symptoms": "   "},
        {"user_id": "", "symptoms": "fever"},
    ]
    for payload in payloads:
        response = client.post("/api/triage", json=payload)
        assert response.status_code == 422, f"expected 422 for payload {payload}"
        assert response.json()["status"] == "error"


def test_triage_emergency_symptoms(client, monkeypatch):
    captured = {}

    def fake_get_triage(symptoms):
        captured["symptoms"] = symptoms
        return FAKE_EMERGENCY_REPLY

    monkeypatch.setattr(triage_service, "get_triage", fake_get_triage)
    emergency_text = "severe chest pain and shortness of breath"
    response = client.post("/api/triage", json={"user_id": "wa-42", "symptoms": emergency_text})

    assert response.status_code == 200
    body = response.json()
    assert "EMERGENCY" in body["ai_response"]
    assert captured["symptoms"] == emergency_text


def test_triage_gemini_failure_returns_502(client, monkeypatch):
    def failing(symptoms):
        raise GeminiServiceError("Gemini request failed or timed out.")

    monkeypatch.setattr(triage_service, "get_triage", failing)
    response = client.post("/api/triage", json={"user_id": "u1", "symptoms": "headache"})
    assert response.status_code == 502
    body = response.json()
    assert body["status"] == "error"
    assert "temporarily unavailable" in body["detail"]
    assert "Gemini" not in body["detail"]


def test_gemini_success_with_mocked_api(monkeypatch):
    monkeypatch.setattr(gemini_service, "_get_client", lambda: _FakeGeminiClient())
    reply = gemini_service.get_triage("I have fever and cough")
    assert reply.startswith("Urgency:")


def test_gemini_failure_is_wrapped(monkeypatch):
    monkeypatch.setattr(gemini_service, "_get_client", lambda: _FailingGeminiClient())
    with pytest.raises(GeminiServiceError) as exc_info:
        gemini_service.get_triage("I have a headache")
    assert not isinstance(exc_info.value, ValueError)


def test_gemini_missing_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    gemini_service.reset_client()
    with pytest.raises(GeminiServiceError):
        gemini_service.get_triage("headache")


def test_gemini_empty_symptoms_rejected():
    with pytest.raises(ValueError):
        gemini_service.get_triage("   ")
    with pytest.raises(ValueError):
        triage_service.get_triage("")


def test_whisper_missing_file():
    with pytest.raises(FileNotFoundError):
        whisper_service.transcribe_audio("does_not_exist.ogg")


def test_whisper_unsupported_format(tmp_path):
    bad_file = tmp_path / "notes.txt"
    bad_file.write_text("hello")
    with pytest.raises(WhisperServiceError):
        whisper_service.transcribe_audio(str(bad_file))


def test_transcribe_success(client, monkeypatch):
    monkeypatch.setattr(whisper_service, "transcribe_audio", lambda path: "Mujhe bukhar hai")
    response = client.post(
        "/api/transcribe",
        files={"file": ("voice_note.ogg", io.BytesIO(b"fake-audio-bytes"), "audio/ogg")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["transcript"] == "Mujhe bukhar hai"


def test_voice_triage_pipeline(client, monkeypatch):
    monkeypatch.setattr(
        whisper_service, "transcribe_audio", lambda path: "Mujhe seene mein dard ho raha hai"
    )
    monkeypatch.setattr(triage_service, "get_triage", lambda symptoms: FAKE_EMERGENCY_REPLY)
    response = client.post(
        "/api/voice-triage",
        data={"user_id": "wa-42"},
        files={"file": ("voice_note.ogg", io.BytesIO(b"fake-audio-bytes"), "audio/ogg")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["user_id"] == "wa-42"
    assert body["transcript"].startswith("Mujhe")
    assert "EMERGENCY" in body["ai_response"]


def test_transcribe_unsupported_extension(client):
    response = client.post(
        "/api/transcribe",
        files={"file": ("notes.txt", io.BytesIO(b"x"), "text/plain")},
    )
    assert response.status_code == 415


def test_transcribe_empty_file(client):
    response = client.post(
        "/api/transcribe",
        files={"file": ("voice.ogg", io.BytesIO(b""), "audio/ogg")},
    )
    assert response.status_code == 400


def test_whisper_failure_returns_502(client, monkeypatch):
    def failing(path):
        raise WhisperServiceError("Speech-to-text request failed or timed out.")

    monkeypatch.setattr(whisper_service, "transcribe_audio", failing)
    response = client.post(
        "/api/transcribe",
        files={"file": ("voice.ogg", io.BytesIO(b"data"), "audio/ogg")},
    )
    assert response.status_code == 502
    body = response.json()
    assert body["status"] == "error"
    assert "temporarily unavailable" in body["detail"]
