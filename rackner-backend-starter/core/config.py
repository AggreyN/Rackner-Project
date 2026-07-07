"""Central configuration — one place to change behavior without touching code.

Every module reads from here, so swapping a value (retention window, roles,
feature flags) never requires edits elsewhere. Values come from .env first.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- Database ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://localhost:5432/rackner")

# --- Claude / extraction ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "claude-sonnet-4-5")

# --- Document retention (security requirement) ---
# Contracts live in the system for 3 days, then are hard-deleted.
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "3"))

# --- File storage ---
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "data/uploads")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))

# --- Auth (feature-flagged so the demo works without accounts) ---
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "12"))

# --- CORS: the deployed frontend + local dev ---
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,https://main.d3rvrftm36ntnq.amplifyapp.com",
    ).split(",")
]
