"""Secrets — AWS Secrets Manager in prod, plain environment in dev.

    get_secret("JWT_SECRET", default="dev-only")

One call site pattern for both environments, so promoting a value to Secrets
Manager is an infra change, not a code change:

  * APP_ENV=dev  (default): read os.environ — which load_dotenv() has already
    populated from .env in development.
  * APP_ENV=prod: try Secrets Manager first (cached per process), fall back to
    the environment. The fallback matters for ECS: task definitions commonly
    inject secrets AS environment variables from Secrets Manager ARNs, in which
    case the value is already in the environment and no API call is needed.

This module deliberately reads APP_ENV straight from the environment rather
than importing app.config — config.py calls get_secret() at import time, so an
import in the other direction would be circular.

Secret NAMES may appear in logs; secret VALUES must never. Nothing here logs a
value, and errors are reported by name only.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

# Prefix for Secrets Manager lookups so one AWS account can hold several
# environments: rackner-fdi/JWT_SECRET, rackner-fdi/DATABASE_URL, ...
_PREFIX = os.getenv("SECRETS_PREFIX", "rackner-fdi")

_cache: dict[str, str] = {}


def _app_env() -> str:
    return os.getenv("APP_ENV", "dev").lower()


def _from_secrets_manager(name: str) -> str | None:
    """One cached Secrets Manager lookup. Returns None on any failure —
    the caller falls back to the environment rather than crashing boot."""
    if name in _cache:
        return _cache[name]
    try:
        import boto3

        client = boto3.client(
            "secretsmanager", region_name=os.getenv("AWS_REGION", "us-east-2")
        )
        value = client.get_secret_value(SecretId=f"{_PREFIX}/{name}")["SecretString"]
    except Exception as exc:  # missing secret, no creds, no network — all fall back
        log.warning("Secrets Manager lookup failed for %s/%s: %s", _PREFIX, name, type(exc).__name__)
        return None
    _cache[name] = value
    return value


def get_secret(name: str, default: str = "") -> str:
    """The one accessor. Name is the plain env-var-style key, e.g. "JWT_SECRET"."""
    if _app_env() == "prod":
        value = _from_secrets_manager(name)
        if value is not None:
            return value
        # ECS injects Secrets Manager values as env vars via the task
        # definition; that path lands here.
    return os.getenv(name, default)
