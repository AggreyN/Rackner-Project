"""Central configuration — one place to change behavior without touching code.

Every module reads from here, so swapping a value (model, upload limit, allowed
origins) never requires edits elsewhere. Values come from .env first.

This file grows a section per week: retention lands in Week 4, auth in Week 6.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- Database ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://localhost:5432/rackner")

# --- Claude / extraction ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "claude-sonnet-4-5")

# --- File storage ---
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "data/uploads")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))

# --- CORS: the deployed frontend + local dev ---
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,https://main.d3rvrftm36ntnq.amplifyapp.com",
    ).split(",")
]
