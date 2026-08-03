"""SQLAlchemy engine, session factory, declarative Base, and the get_db dependency.

Everything that talks to Postgres imports from here. `Base` is the parent of
all ORM models (models.py); `get_db` is the FastAPI dependency that hands a
request-scoped session to a route and closes it afterward.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

# `future=True` opts into SQLAlchemy 2.0 behavior. echo=False keeps logs quiet.
engine = create_engine(DATABASE_URL, echo=False, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()


def get_db():
    """Yield a database session, guaranteed to close after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
