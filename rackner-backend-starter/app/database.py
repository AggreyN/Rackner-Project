"""SQLAlchemy engine, session factory, declarative Base, and the get_db dependency.

Everything that talks to Postgres imports from here. `Base` is the parent of
all ORM models (models.py); `get_db` is the FastAPI dependency that hands a
request-scoped session to a route and closes it afterward.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL


def _engine_kwargs(url: str) -> dict:
    """Backend-appropriate engine options.

    Postgres/RDS: pre-ping (RDS failovers and idle timeouts silently kill
    pooled connections; pre-ping replaces a dead one instead of erroring the
    request) and env-tunable pool sizing for ECS. TLS needs no code — append
    `?sslmode=require` to DATABASE_URL and psycopg honors it; the prod URL in
    Secrets Manager carries it.

    SQLite (tests/smoke only): no pooling knobs apply.
    """
    if url.startswith("sqlite"):
        return {}
    return {
        "pool_pre_ping": True,
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        "pool_recycle": 1800,  # under RDS's default idle-connection timeout
    }


# `future=True` opts into SQLAlchemy 2.0 behavior. echo=False keeps logs quiet.
engine = create_engine(DATABASE_URL, echo=False, future=True, **_engine_kwargs(DATABASE_URL))

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()


def get_db():
    """Yield a database session, guaranteed to close after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
