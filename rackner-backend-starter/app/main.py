"""FastAPI app assembly for Rackner FDI.

Mounts CORS, a health route, the local-auth routes, and a protected sample
route (`/me`). The domain features — SAM.gov search, USAspending spend, the
LLM analysis gateway, contact discovery — are deliberately left as TODO stubs
for later weeks so this week's deliverable (schema + auth) stays reviewable.

Run:  uvicorn app.main:app --reload   →  http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.logging_config import AccessLogMiddleware, setup as setup_logging

setup_logging()
from app.routes import (
    analysis,
    auth,
    chat,
    contacts,
    documents,
    health,
    opportunities,
    profile,
    spend,
)

app = FastAPI(
    title="Rackner FDI — Backend API",
    description=(
        "Federal Document Intelligence: search SAM.gov opportunities, score them "
        "against your lifecycle plan, and surface cited obligations (no hallucinations)."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Outermost: every request gets an id + one JSON access line (CloudWatch-ready).
app.add_middleware(AccessLogMiddleware)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(profile.router)  # GET /profile, POST /profile/lifecycle
# Order matters: /opportunities/search and /opportunities/suggested must be
# registered BEFORE /opportunities/{id}, or FastAPI matches "search" as an id.
app.include_router(opportunities.router)
app.include_router(documents.router)  # GET /opportunities/{id}/document
app.include_router(analysis.router)  # GET /opportunities/{id}/analysis (+ /llm/*)
app.include_router(spend.router)  # GET /opportunities/{id}/spend
app.include_router(contacts.router)  # GET /opportunities/{id}/contact
app.include_router(chat.router)  # POST /opportunities/{id}/chat
