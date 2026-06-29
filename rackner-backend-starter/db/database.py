"""
Database connection setup (SQLAlchemy).

This file gives the rest of the project a shared way to talk to Postgres.
You'll import `engine` and `SessionLocal` from here in your pipeline and API.

Learn more: https://docs.sqlalchemy.org/
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Load DATABASE_URL (and other settings) from your .env file
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://localhost:5432/rackner",
)

# The engine is the core connection to Postgres.
# echo=True prints the SQL it runs — handy while learning; set False later.
engine = create_engine(DATABASE_URL, echo=False)

# A SessionLocal() is a short-lived workspace for reading/writing rows.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# All your table classes (in models.py) will inherit from this Base.
Base = declarative_base()
