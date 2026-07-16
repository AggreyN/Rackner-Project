"""App assembly.

Everything is a module mounted here; removing one router never breaks the
others. Startup creates tables (dev convenience — Alembic owns production).

Grows each week: the retention sweep lands in Week 4, the obligations router in
Week 5, auth in Week 6.

Run it:
    uvicorn api.main:app --reload     # http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import documents
from core.config import ALLOWED_ORIGINS
from db.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)      # dev convenience; Alembic owns prod
    yield


app = FastAPI(
    title="Team Anvil — Federal Document Intelligence Layer",
    description="One document, read once — every team gets its answers.",
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


@app.get("/")
def health():
    return {"status": "ok", "service": "team-anvil-intelligence-layer"}
