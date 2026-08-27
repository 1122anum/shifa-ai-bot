"""
context_manager.py — Per-user conversation context for Gemini.

Builds the conversation history list that is sent to the backend
alongside each new message so Gemini understands prior turns.

Strategy:
  - Last 10 messages from the active conversation
  - If conversation is long, the oldest messages are dropped
    (backend enforces 4000-char symptoms cap so context is bounded)
  - Each user is isolated — no cross-user leakage
"""

from app.database.db import (
    get_or_create_user,
    get_or_create_conversation,
    get_active_conversation,
    create_conversation,
    close_conversation,
    get_conversation_history,
    save_message,
    save_triage_result,
    extract_urgency,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

HISTORY_LIMIT = 10          # max turns sent to Gemini
MAX_SYMPTOMS_CHARS = 3800   # stay under backend 4000-char cap


def build_context_prompt(history: list[dict], current_message: str) -> str:
    """
    Combine conversation history + current message into a single
    symptoms string that the backend /api/triage endpoint accepts.

    Format:
        [Previous conversation]
        User: ...
        Assistant: ...
        User: ...

        [Current message]
        <current_message>
    """
    if not history:
        return current_message

    lines = ["[Previous conversation]"]
    for turn in history:
        role_label = "User" if turn["role"] == "user" else "Assistant"
        lines.append(f"{role_label}: {turn['message']}")

    lines.append("")
    lines.append("[Current message]")
    lines.append(current_message)

    full = "\n".join(lines)

    # Truncate if over backend limit — keep current message intact
    if len(full) > MAX_SYMPTOMS_CHARS:
        overhead = len(full) - MAX_SYMPTOMS_CHARS
        # Remove oldest history lines first
        while overhead > 0 and len(lines) > 3:
            removed = lines.pop(1)  # remove oldest history line
            overhead -= len(removed) + 1
        full = "\n".join(lines)

    return full


class ConversationContext:
    """
    High-level interface for managing a single user's conversation.

    Usage:
        ctx = ConversationContext("923001234567")
        symptoms = ctx.get_context_for_triage("Mujhe bukhar hai")
        ctx.save_turn("Mujhe bukhar hai", ai_response, message_type="text")
    """

    def __init__(self, whatsapp_number: str):
        self.whatsapp_number = whatsapp_number
        self.user_id = get_or_create_user(whatsapp_number)
        self.conversation_id = get_or_create_conversation(self.user_id)
        logger.debug(
            "Context loaded | number=%s | user_id=%d | conv_id=%d",
            whatsapp_number, self.user_id, self.conversation_id,
        )

    def get_context_for_triage(self, current_message: str) -> str:
        """
        Return a context-enriched symptoms string to send to /api/triage.
        Includes recent conversation history.
        """
        history = get_conversation_history(self.conversation_id, limit=HISTORY_LIMIT)
        context = build_context_prompt(history, current_message)
        logger.debug(
            "Context built | conv_id=%d | history_turns=%d | total_len=%d",
            self.conversation_id, len(history), len(context),
        )
        return context

    def save_turn(
        self,
        user_message: str,
        ai_response: str,
        message_type: str = "text",
        transcription: str | None = None,
    ) -> None:
        """Persist user message + AI response to the database."""
        save_message(
            conversation_id=self.conversation_id,
            role="user",
            message=user_message,
            message_type=message_type,
            transcription=transcription,
        )
        save_message(
            conversation_id=self.conversation_id,
            role="assistant",
            message=ai_response,
            message_type="text",
        )
        # Save triage result
        urgency = extract_urgency(ai_response)
        save_triage_result(
            conversation_id=self.conversation_id,
            urgency=urgency,
            summary=ai_response[:500],
        )
        logger.info(
            "Turn saved | conv_id=%d | urgency=%s | type=%s",
            self.conversation_id, urgency, message_type,
        )

    def reset(self) -> None:
        """Close the current conversation — next message starts fresh."""
        close_conversation(self.conversation_id)
        self.conversation_id = create_conversation(self.user_id)
        logger.info(
            "Conversation reset | user_id=%d | new_conv_id=%d",
            self.user_id, self.conversation_id,
        )
