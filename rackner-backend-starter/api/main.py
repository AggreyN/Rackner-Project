"""App assembly — REPLACES the starter api/main.py (which was a stub).

Everything is a module mounted here; removing one router never breaks the
others. Startup creates tables, purges expired documents, and schedules an
hourly retention sweep.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import documents, obligations
from core.config import ALLOWED_ORIGINS, AUTH_ENABLED, RETENTION_DAYS
from core.retention import purge_expired
from db.database import Base, engine, SessionLocal


async def _retention_loop():
    while True:
        with SessionLocal() as session:
            purge_expired(session)
        await asyncio.sleep(3600)  # hourly


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)      # dev convenience; Alembic owns prod
    with SessionLocal() as session:
        purge_expired(session)                 # sweep on boot
    task = asyncio.create_task(_retention_loop())
    yield
    task.cancel()


app = FastAPI(
    title="Team Anvil — Federal Document Intelligence Layer",
    description=f"One document, read once — every team gets its answers. "
                f"Documents auto-delete after {RETENTION_DAYS} days.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(obligations.router)

if AUTH_ENABLED:                               # feature flag — off for demo
    from api.routes import auth
    app.include_router(auth.router)


@app.get("/")
def health():
    return {"status": "ok", "service": "team-anvil-intelligence-layer"}
