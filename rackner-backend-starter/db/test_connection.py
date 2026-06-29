"""
Week 1 deliverable: prove Python can connect to your Postgres database.

Run it from the project root with your venv active:
    python db/test_connection.py

Expected output:
    ✅ Connected to PostgreSQL!
    PostgreSQL 16.x ...
"""

from sqlalchemy import text

from db.database import engine, DATABASE_URL


def main() -> None:
    print(f"Connecting to: {DATABASE_URL}")
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version();")).scalar_one()
        print("✅ Connected to PostgreSQL!")
        print(version)
    except Exception as exc:  # noqa: BLE001  (broad catch is fine for a smoke test)
        print("❌ Could not connect.")
        print(f"Error: {exc}")
        print("\nChecklist:")
        print("  1. Is Postgres running?   brew services start postgresql@16")
        print("  2. Did you create the db?  createdb rackner")
        print("  3. Is your venv active?    source venv/bin/activate")
        print("  4. Did you copy .env?      cp .env.example .env")


if __name__ == "__main__":
    # Allow running as `python db/test_connection.py` from the project root.
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    main()
