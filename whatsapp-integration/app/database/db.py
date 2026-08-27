"""
db.py — SQLite database setup using the built-in sqlite3 module.

Schema:
  users            — one row per WhatsApp number
  conversations    — one per session (resets on /reset or 30-min inactivity)
  messages         — every user + bot turn
  triage_results   — urgency + summary per conversation

No external ORM needed — sqlite3 is part of the Python standard library.
Parameterised queries used throughout to prevent SQL injection.
"""

import sqlite3
import os
from contextlib import contextmanager
from app.config import config
from app.utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "shifa_ai.db"
)

# ─────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    whatsapp_number   TEXT    NOT NULL UNIQUE,
    created_at        DATETIME DEFAULT (datetime('now')),
    updated_at        DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER  NOT NULL REFERENCES users(id),
    started_at   DATETIME DEFAULT (datetime('now')),
    ended_at     DATETIME,
    status       TEXT     DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER  PRIMARY KEY AUTOINCREMENT,
    conversation_id  INTEGER  NOT NULL REFERENCES conversations(id),
    role             TEXT     NOT NULL CHECK(role IN ('user','assistant')),
    message          TEXT     NOT NULL,
    message_type     TEXT     DEFAULT 'text' CHECK(message_type IN ('text','voice')),
    transcription    TEXT,
    created_at       DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS triage_results (
    id               INTEGER  PRIMARY KEY AUTOINCREMENT,
    conversation_id  INTEGER  NOT NULL REFERENCES conversations(id),
    urgency          TEXT,
    summary          TEXT,
    created_at       DATETIME DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_conv_user   ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_msg_conv    ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_triage_conv ON triage_results(conversation_id);
"""


def init_db() -> None:
    """Create tables if they do not exist. Called once at startup."""
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    with _connect() as conn:
        conn.executescript(SCHEMA)
    logger.info("Database initialised | path=%s", os.path.abspath(DB_PATH))


@contextmanager
def _connect():
    """Yield a connection with row_factory and WAL mode enabled."""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────
# Users
# ─────────────────────────────────────────────────────────

def get_or_create_user(whatsapp_number: str) -> int:
    """Return the user row id, creating one if needed."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE whatsapp_number = ?",
            (whatsapp_number,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET updated_at = datetime('now') WHERE id = ?",
                (row["id"],)
            )
            return row["id"]
        cur = conn.execute(
            "INSERT INTO users (whatsapp_number) VALUES (?)",
            (whatsapp_number,)
        )
        logger.info("New user created | number=%s", whatsapp_number)
        return cur.lastrowid


# ─────────────────────────────────────────────────────────
# Conversations
# ─────────────────────────────────────────────────────────

SESSION_TIMEOUT_MINUTES = 30


def get_active_conversation(user_id: int) -> int | None:
    """
    Return the active conversation id for a user if it exists
    and was active within SESSION_TIMEOUT_MINUTES. Else None.
    """
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, started_at
            FROM conversations
            WHERE user_id = ?
              AND status  = 'active'
              AND datetime(started_at, '+' || ? || ' minutes') > datetime('now')
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (user_id, SESSION_TIMEOUT_MINUTES)
        ).fetchone()
        return row["id"] if row else None


def create_conversation(user_id: int) -> int:
    """Open a new conversation for a user."""
    with _connect() as conn:
        # Close any stale active conversations first
        conn.execute(
            "UPDATE conversations SET status='ended', ended_at=datetime('now') "
            "WHERE user_id=? AND status='active'",
            (user_id,)
        )
        cur = conn.execute(
            "INSERT INTO conversations (user_id) VALUES (?)",
            (user_id,)
        )
        logger.info("New conversation | user_id=%d | conv_id=%d", user_id, cur.lastrowid)
        return cur.lastrowid


def close_conversation(conversation_id: int) -> None:
    """Mark a conversation as ended (e.g. on /reset)."""
    with _connect() as conn:
        conn.execute(
            "UPDATE conversations SET status='ended', ended_at=datetime('now') WHERE id=?",
            (conversation_id,)
        )
    logger.info("Conversation closed | conv_id=%d", conversation_id)


def get_or_create_conversation(user_id: int) -> int:
    """Get active conversation or create a new one."""
    conv_id = get_active_conversation(user_id)
    if conv_id is None:
        conv_id = create_conversation(user_id)
    return conv_id


# ─────────────────────────────────────────────────────────
# Messages
# ─────────────────────────────────────────────────────────

def save_message(
    conversation_id: int,
    role: str,
    message: str,
    message_type: str = "text",
    transcription: str | None = None,
) -> int:
    """Persist a message and return its id."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO messages
                (conversation_id, role, message, message_type, transcription)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, role, message, message_type, transcription)
        )
        return cur.lastrowid


def get_conversation_history(conversation_id: int, limit: int = 10) -> list[dict]:
    """
    Return the last `limit` messages for a conversation, oldest first.
    Used to build context for Gemini.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT role, message, message_type, transcription
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (conversation_id, limit)
        ).fetchall()
    # Reverse to get chronological order
    return [dict(r) for r in reversed(rows)]


# ─────────────────────────────────────────────────────────
# Triage Results
# ─────────────────────────────────────────────────────────

def save_triage_result(
    conversation_id: int,
    urgency: str,
    summary: str,
) -> None:
    """Persist a triage result."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO triage_results (conversation_id, urgency, summary) VALUES (?,?,?)",
            (conversation_id, urgency, summary)
        )
    logger.debug("Triage result saved | conv_id=%d | urgency=%s", conversation_id, urgency)


def extract_urgency(ai_response: str) -> str:
    """Extract urgency level from Gemini response text."""
    import re
    m = re.search(
        r'(?:urgency|triage|priority)(?:\s+level)?\s*[:\-–]\s*\*{0,2}(\w+)\*{0,2}',
        ai_response,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).upper()
    for level in ("EMERGENCY", "URGENT", "ROUTINE"):
        if level in ai_response.upper():
            return level
    return "UNKNOWN"
