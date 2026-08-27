"""
run.py — Development entry point for WhatsApp Integration server.

Usage:
    python run.py

Production:
    gunicorn -w 2 -b 0.0.0.0:5000 app.webhook:app
"""

from app.webhook import app
from app.config import config
from app.database.db import init_db
from app.utils.logger import get_logger

logger = get_logger("run")

if __name__ == "__main__":
    # Initialise database on startup
    init_db()

    logger.info("=" * 50)
    logger.info("  Shifa AI — WhatsApp Integration Server")
    logger.info("=" * 50)
    logger.info("  API        : Meta WhatsApp Business API")
    logger.info("  Host       : %s", config.INTEGRATION_HOST)
    logger.info("  Port       : %d", config.INTEGRATION_PORT)
    logger.info("  Backend    : %s", config.BACKEND_BASE_URL)
    logger.info("  Triage URL : %s", config.TRIAGE_URL)
    logger.info("=" * 50)
    logger.info("  Webhook URL (after ngrok):")
    logger.info("  <ngrok_url>/webhook/whatsapp")
    logger.info("=" * 50)

    app.run(
        host=config.INTEGRATION_HOST,
        port=config.INTEGRATION_PORT,
        debug=True,
    )
