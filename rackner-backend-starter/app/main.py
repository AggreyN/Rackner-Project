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
from app.routes import analyses, auth, health

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

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(analyses.router)  # LLM gateway (mock by default; Bedrock via LLM_MODE)

# TODO(week2+): mount remaining domain routers as they land —
#   - routes/opportunities.py  → SAM.gov search + cache (Opportunity)
#   - routes/spend.py           → USAspending.gov lookups (SpendSummary)
#   - routes/contacts.py        → contact discovery (Contact, human-in-the-loop)
