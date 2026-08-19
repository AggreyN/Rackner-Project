"""The single-JSON config secret (rackner-fdi-config) — offline, boto3 faked.

Prod resolution order: JSON blob -> per-key secret -> environment. Dev never
touches AWS. The blob is fetched at most once per process even when absent.
"""

from __future__ import annotations

import json
import sys
import types

import pytest

from app.services import secrets


@pytest.fixture(autouse=True)
def reset_module_state():
    secrets._cache.clear()
    secrets._blob = secrets._UNFETCHED
    yield
    secrets._cache.clear()
    secrets._blob = secrets._UNFETCHED


class _FakeSM:
    def __init__(self, store: dict[str, str]):
        self.store = store
        self.calls: list[str] = []

    def get_secret_value(self, *, SecretId):
        self.calls.append(SecretId)
        if SecretId not in self.store:
            raise RuntimeError("ResourceNotFound")
        return {"SecretString": self.store[SecretId]}


def _rig(monkeypatch, store: dict[str, str]) -> _FakeSM:
    fake = _FakeSM(store)
    module = types.ModuleType("boto3")
    module.client = lambda name, **kw: fake
    monkeypatch.setitem(sys.modules, "boto3", module)
    return fake


def test_dev_mode_never_calls_aws(monkeypatch):
    fake = _rig(monkeypatch, {})
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("SOME_KEY", "from-env")
    assert secrets.get_secret("SOME_KEY") == "from-env"
    assert fake.calls == []


def test_prod_reads_the_json_blob_first(monkeypatch):
    fake = _rig(
        monkeypatch,
        {secrets._CONFIG_SECRET: json.dumps({"DATABASE_URL": "postgresql://from-blob"})},
    )
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("DATABASE_URL", "postgresql://from-env")
    assert secrets.get_secret("DATABASE_URL") == "postgresql://from-blob"
    assert fake.calls == [secrets._CONFIG_SECRET]


def test_blob_is_fetched_once_even_across_keys(monkeypatch):
    fake = _rig(
        monkeypatch,
        {secrets._CONFIG_SECRET: json.dumps({"A": "1", "B": "2"})},
    )
    monkeypatch.setenv("APP_ENV", "prod")
    assert secrets.get_secret("A") == "1"
    assert secrets.get_secret("B") == "2"
    assert fake.calls.count(secrets._CONFIG_SECRET) == 1


def test_key_missing_from_blob_falls_back_to_per_key_secret(monkeypatch):
    fake = _rig(
        monkeypatch,
        {
            secrets._CONFIG_SECRET: json.dumps({"OTHER": "x"}),
            "rackner-fdi/JWT_SECRET": "per-key-value",
        },
    )
    monkeypatch.setenv("APP_ENV", "prod")
    assert secrets.get_secret("JWT_SECRET") == "per-key-value"


def test_missing_blob_falls_back_to_env_without_crashing_boot(monkeypatch):
    _rig(monkeypatch, {})
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("JWT_SECRET", "from-ecs-env")
    assert secrets.get_secret("JWT_SECRET") == "from-ecs-env"


def test_malformed_blob_is_ignored_not_fatal(monkeypatch):
    _rig(monkeypatch, {secrets._CONFIG_SECRET: "not json at all"})
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SOME_KEY", "from-env")
    assert secrets.get_secret("SOME_KEY") == "from-env"


def test_non_string_blob_values_are_coerced(monkeypatch):
    _rig(monkeypatch, {secrets._CONFIG_SECRET: json.dumps({"PORT_LIKE": 5432})})
    monkeypatch.setenv("APP_ENV", "prod")
    assert secrets.get_secret("PORT_LIKE") == "5432"


def test_null_blob_value_falls_through_instead_of_becoming_the_string_None(monkeypatch):
    _rig(monkeypatch, {secrets._CONFIG_SECRET: json.dumps({"SAM_GOV_API_KEY": None})})
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SAM_GOV_API_KEY", "from-env")
    assert secrets.get_secret("SAM_GOV_API_KEY") == "from-env"


def test_empty_string_blob_value_does_not_shadow_the_env(monkeypatch):
    _rig(monkeypatch, {secrets._CONFIG_SECRET: json.dumps({"JWT_SECRET": ""})})
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("JWT_SECRET", "from-env")
    assert secrets.get_secret("JWT_SECRET") == "from-env"
