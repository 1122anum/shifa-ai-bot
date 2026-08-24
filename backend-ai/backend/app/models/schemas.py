from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SymptomRequest(BaseModel):
    user_id: str = Field(
        ...,
        min_length=1,
        max_length=256,
        examples=["whatsapp:+923001234567"],
        description="Unique identifier of the user (e.g. WhatsApp number).",
    )
    symptoms: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Symptoms or health message written by the user (English, Urdu or Roman Urdu).",
    )

    @field_validator("user_id", "symptoms")
    @classmethod
    def value_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty or whitespace only")
        return value


class TriageResponse(BaseModel):
    status: Literal["success"] = "success"
    user_id: str
    ai_response: str


class TranscriptionResponse(BaseModel):
    status: Literal["success"] = "success"
    transcript: str


class VoiceTriageResponse(BaseModel):
    status: Literal["success"] = "success"
    user_id: str
    transcript: str
    ai_response: str


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    detail: str
