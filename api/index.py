"""
Vercel serverless entry point for Shifa AI FastAPI backend.
Routes all requests to the FastAPI application.
"""

import sys
import os

# Add backend to Python path so imports work in serverless environment
_backend_path = os.path.join(os.path.dirname(__file__), "..", "backend-ai", "backend")
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

# Load environment variables (Vercel sets these as actual env vars, not .env)
from dotenv import load_dotenv
load_dotenv(os.path.join(_backend_path, ".env"))

# Import the FastAPI app
from app.main import app

# Vercel serverless handler
handler = app
