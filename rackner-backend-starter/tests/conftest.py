"""Shared fixtures.

The whole suite runs against a real migrated database — `alembic upgrade head`,
not `Base.metadata.create_all`. That is deliberate: create_all would test the
models and silently skip the migration, and the migration is the thing that runs
in production.

Database selection:
    TEST_DATABASE_URL unset  -> a throwaway SQLite file (fast, no setup)
    TEST_DATABASE_URL set    -> that database (use Postgres before you ship)

Run both:
    pytest
    TEST_DATABASE_URL=postgresql+psycopg://localhost:5432/rackner_test pytest
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent

# Import app.* without installing the package.
sys.path.insert(0, str(BACKEND_ROOT))

# ---------------------------------------------------------------------------
# Environment is pinned HERE, at conftest import time — not in a fixture.
#
# app/config.py calls load_dotenv() at import, and test modules import app.*
# at module scope, which happens during COLLECTION — before any fixture runs.
# Setting these in a fixture is too late: the app would already have picked up
# the developer's real .env and the suite would run against the dev database.
# load_dotenv() does not override variables already in os.environ, so setting
# them now wins.
# ---------------------------------------------------------------------------
_TMP = Path(tempfile.mkdtemp(prefix="rackner-tests-"))

# TEST_DATABASE_URL unset -> throwaway SQLite. Set it to run on Postgres.
DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_TMP / 'test.db'}"

os.environ["DATABASE_URL"] = DATABASE_URL
os.environ["LLM_MODE"] = "mock"
os.environ["AUTH_MODE"] = "local"
# Never let a dev .env leak real Textract calls (money, latency) into the
# offline suite — the live path has its own opt-in file (test_textract_live).
os.environ["OCR_MODE"] = "off"
os.environ["STORAGE_BACKEND"] = "local"
# Never let a dev .env leak REAL keys, prod secrets, or tuned knobs into the
# offline suite (audit 2026-08-19): a placeholder SAM key (stubs override it),
# dev secrets mode, a nonexistent config secret, and default cache knobs.
os.environ["APP_ENV"] = "dev"
os.environ["SAM_GOV_API_KEY"] = "test-not-a-real-key"
os.environ["CONFIG_SECRET_NAME"] = "test-nonexistent-secret"
os.environ["SAM_SEARCH_TTL_HOURS"] = "12"
os.environ["LLM_EXTRACT_CONCURRENCY"] = "8"
# TTL 0 = attachment-fetch backoff always expired: several tests deliberately
# run a failed pass then an immediate successful retry. The backoff regression
# test opts in by monkeypatching the knob.
os.environ["ATTACHMENT_RETRY_BACKOFF_MINUTES"] = "0"
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")
os.environ.setdefault("JWT_SECRET", "test-only-secret-not-a-real-key")


@pytest.fixture(scope="session")
def database_url() -> str:
    return DATABASE_URL


def _guard_not_a_real_database(url: str) -> None:
    """Refuse to run against anything that looks like a working database.

    The suite creates, migrates and mutates tables. Pointing it at the dev DB
    would silently destroy local data.
    """
    if url.startswith("sqlite"):
        return
    name = url.rsplit("/", 1)[-1].split("?")[0]
    if not any(marker in name for marker in ("test", "ci")):
        pytest.exit(
            f"Refusing to run tests against database {name!r}: the name must "
            f"contain 'test' or 'ci'. Set TEST_DATABASE_URL to a scratch "
            f"database (e.g. .../rackner_test).",
            returncode=2,
        )


@pytest.fixture(scope="session", autouse=True)
def _migrated(database_url):
    """Run the real migration chain against a CLEAN test database.

    The downgrade matters. A persistent test database (Postgres) keeps rows
    between runs, and some records are built-once-never-reparsed by design —
    source_documents especially. A stale row can make a test pass or fail based
    on what a previous run happened to store, which is how a real ingest change
    once showed up as a Postgres-only failure. SQLite hid it by getting a fresh
    file each run. Starting from base makes both backends behave identically.
    """
    _guard_not_a_real_database(database_url)
    env = {**os.environ, "DATABASE_URL": database_url}

    def _alembic(*args) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    # Drop whatever a previous run left behind. Harmless on a fresh database.
    _alembic("downgrade", "base")

    result = _alembic("upgrade", "head")
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")
    yield


@pytest.fixture(scope="session", autouse=True)
def _no_live_gov_calls(_migrated):
    """The offline suite must never touch live government APIs (audit
    2026-08-19: search-path tests without explicit stubs were making real
    USAspending POSTs — 7 tests, 42 network attempts). Tests that need
    specific behavior monkeypatch over these; the opt-in live suites
    (RUN_GOV_TESTS=1) get the real functions."""
    if os.getenv("RUN_GOV_TESTS") == "1":
        yield
        return
    from unittest.mock import patch

    from app.services import usaspending

    real_spend = usaspending.spend_summary
    with patch.object(usaspending, "expiring_awards", lambda **kw: []), patch.object(
        usaspending,
        "spend_summary",
        lambda opportunity_id, recipient=None, **kw: real_spend(
            opportunity_id=opportunity_id, recipient=None
        ),
    ):
        yield


@pytest.fixture(scope="session")
def client(_migrated):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_search_ledger(_migrated):
    """The freshness ledger is cross-request state by design — but across
    TESTS it makes one test's live fetch silently cache-serve the next
    test's stubbed route. Each test starts with an empty ledger; stamping
    within a test still works."""
    from app.database import SessionLocal
    from app.models import SearchFetch

    db = SessionLocal()
    try:
        db.query(SearchFetch).delete()
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture(autouse=True)
def _reset_module_throttles():
    """Two process-local throttles added 2026-08-21 leak across tests if not
    reset: the JWKS miss-refetch cooldown (one test's bogus-kid miss would
    suppress another's rotation refetch) and the attachment-fetch backoff
    memo (a test that opts into a real TTL would suppress later tests that
    reuse the same opportunity id)."""
    from app import auth
    from app.routes import documents

    auth._jwks_cache["miss_refetch_at"] = None
    documents._fetch_backoff.clear()
    yield


@pytest.fixture(scope="session")
def credentials(client) -> dict:
    """A registered demo account. Anything that logs in must depend on this,
    otherwise the test passes or fails depending on collection order."""
    creds = {"email": "pytest@rackner.com", "password": "pytest-password-123"}
    client.post("/auth/register", json=creds)  # 409 on re-run is fine
    return creds


@pytest.fixture(scope="session")
def auth_headers(client, credentials) -> dict:
    """A registered, logged-in demo user's bearer header."""
    r = client.post("/auth/login", json=credentials)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --- a small, structured solicitation used across the API tests ---------------

SOLICITATION = """SECTION C — DESCRIPTION / SPECIFICATIONS
The Contractor shall provide continuous monitoring of all information systems.

C.3.1 Incident Reporting
The Contractor shall report any cyber incident to the Contracting Officer within 72 hours of discovery.

252.204-7012 Safeguarding Covered Defense Information
The Contractor shall deliver a monthly status report summarizing all safeguarding activities."""


@pytest.fixture(scope="session")
def solicitation() -> str:
    """The seeded opportunity's source text."""
    return SOLICITATION


@pytest.fixture(scope="session")
def opportunity_id(client) -> str:
    """Seed one opportunity directly in the DB and return its id."""
    from app.database import SessionLocal
    from app.models import Opportunity

    opp_id = "PYTEST-001"
    db = SessionLocal()
    try:
        if db.get(Opportunity, opp_id) is None:
            db.add(
                Opportunity(
                    id=opp_id,
                    title="Continuous Monitoring Support",
                    agency="DoD · DISA",
                    office="DISA PL83",
                    solicitation_number="HC1084-26-R-0042",
                    naics="541512",
                    set_aside="HUBZone",
                    kind="solicitation",
                    description=SOLICITATION,
                )
            )
            db.commit()
    finally:
        db.close()
    return opp_id


@pytest.fixture(scope="session")
def sample_pdfs() -> list[Path]:
    """Real federal solicitations committed as shared team fixtures."""
    return sorted((REPO_ROOT / "data" / "samples").glob("*.pdf"))
