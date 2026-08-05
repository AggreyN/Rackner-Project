"""Database failures must be clean, NAMED 503s — never bare 500s.

The two messages make the two real deployment incidents distinguishable from
outside, without CloudWatch access: wrong credentials / unreachable host
("unreachable") vs. migrations-never-ran ("schema is not ready"). Both have
now happened in production; the bare 500 they used to produce was opaque.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.database import get_db
from app.main import app


def _raising_db(exc: Exception):
    def dep():
        raise exc
        yield  # pragma: no cover

    return dep


@pytest.fixture()
def rigged_db():
    """Override get_db to raise; always restore."""

    def rig(exc: Exception):
        app.dependency_overrides[get_db] = _raising_db(exc)

    yield rig
    app.dependency_overrides.pop(get_db, None)


def test_unreachable_database_is_a_named_503(client, auth_headers, rigged_db):
    rigged_db(
        OperationalError(
            "SELECT 1", {}, Exception("password authentication failed for user")
        )
    )
    r = client.get("/me", headers=auth_headers)
    assert r.status_code == 503
    assert "unreachable" in r.json()["detail"]


def test_missing_schema_is_a_named_503(client, auth_headers, rigged_db):
    rigged_db(
        ProgrammingError(
            "SELECT * FROM users", {}, Exception('relation "users" does not exist')
        )
    )
    r = client.get("/me", headers=auth_headers)
    assert r.status_code == 503
    assert "migrations" in r.json()["detail"]


def test_healthy_db_is_unaffected(client, auth_headers):
    assert client.get("/me", headers=auth_headers).status_code == 200
