"""FastAPI app assembly for Rackner FDI.

Mounts CORS, a health route, the local-auth routes, and a protected sample
route (`/me`). The domain features — SAM.gov search, USAspending spend, the
LLM analysis gateway, contact discovery — are deliberately left as TODO stubs
for later weeks so this week's deliverable (schema + auth) stays reviewable.

Run:  uvicorn app.main:app --reload   →  http://localhost:8000/docs
"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError

from app import config
from app.logging_config import AccessLogMiddleware, setup as setup_logging

setup_logging()
from app.routes import (
    analysis,
    auth,
    bookmarks,
    chat,
    contacts,
    documents,
    health,
    imports,
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

_log = logging.getLogger(__name__)


# Fail-soft ground rule applies to our own database too: a DB failure is a
# clean, NAMED 503 — never a bare 500. The distinct messages make the two
# deployment failure modes diagnosable from outside without CloudWatch access
# (bad credentials/unreachable vs. migrations-never-ran).
@app.exception_handler(OperationalError)
async def _db_unreachable(request: Request, exc: OperationalError):
    _log.error("database unreachable: %s", exc.orig, exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "The database is unreachable right now. Try again shortly."},
    )


@app.exception_handler(ProgrammingError)
async def _db_schema_broken(request: Request, exc: ProgrammingError):
    _log.error("database schema error: %s", exc.orig, exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "The database schema is not ready — have migrations run "
            "against this database?"
        },
    )

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(profile.router)  # GET /profile, POST+DELETE /profile/lifecycle
app.include_router(bookmarks.router)  # /profile/bookmarks (the saved drawer)
# /opportunities/import must register BEFORE the {id} routes.
app.include_router(imports.router)
# Order matters: /opportunities/search and /opportunities/suggested must be
# registered BEFORE /opportunities/{id}, or FastAPI matches "search" as an id.
app.include_router(opportunities.router)
app.include_router(documents.router)  # GET /opportunities/{id}/document
app.include_router(analysis.router)  # GET /opportunities/{id}/analysis (+ /llm/*)
app.include_router(spend.router)  # GET /opportunities/{id}/spend
app.include_router(contacts.router)  # GET /opportunities/{id}/contact
app.include_router(chat.router)  # POST /opportunities/{id}/chat
