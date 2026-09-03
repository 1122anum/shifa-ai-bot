"""
logger.py — Shared logger used across the integration layer.
Configured once and imported everywhere else.

Includes a secret-redacting filter to prevent accidental credential leaks.
"""

import logging
import re
import sys
from app.config import config


# ── Secret Redaction Filter ────────────────────────────────────────────
# Patterns that look like API keys, tokens, passwords, etc.
_SECRET_PATTERNS = [
    # OpenAI / generic sk- keys
    (re.compile(r'sk-[A-Za-z0-9]{20,}'), '[REDACTED:sk-key]'),
    # Groq keys
    (re.compile(r'gsk_[A-Za-z0-9]{20,}'), '[REDACTED:groq-key]'),
    # Gemini / Google AI keys
    (re.compile(r'AIza[A-Za-z0-9_-]{20,}'), '[REDACTED:gemini-key]'),
    # Meta / Facebook access tokens
    (re.compile(r'EAA[A-Za-z0-9]{50,}'), '[REDACTED:meta-token]'),
    # Twilio Account SIDs
    (re.compile(r'AC[a-f0-9]{32}'), '[REDACTED:twilio-sid]'),
    # Twilio Auth Tokens (32 hex chars)
    (re.compile(r'[a-f0-9]{32}(?="|\'|\s|$)'), '[REDACTED:auth-token]'),
    # Generic key=value patterns for secrets
    (re.compile(r'(password|secret|token|api_key|auth_token)\s*[=:]\s*\S+', re.IGNORECASE),
     '\\1=[REDACTED]'),
    # Bearer tokens in headers
    (re.compile(r'Bearer\s+[A-Za-z0-9._-]{20,}', re.IGNORECASE), 'Bearer [REDACTED]'),
]


class SecretRedactionFilter(logging.Filter):
    """Redact anything that looks like a secret from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in _SECRET_PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        if record.args:
            record.args = tuple(
                self._redact(arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True

    @staticmethod
    def _redact(value: str) -> str:
        for pattern, replacement in _SECRET_PATTERNS:
            value = pattern.sub(replacement, value)
        return value


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with a consistent format and secret redaction."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SecretRedactionFilter())
        logger.addHandler(handler)

    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)
    return logger
