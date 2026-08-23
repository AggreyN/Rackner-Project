"""Third-party verification of INFERRED contact emails. Feature-flagged.

Scope guard: this runs ONLY on Tier-2 pattern guesses in email_discovery —
never on SAM-published addresses (SAM is authoritative; second-guessing it
spends credits to add nothing). With EMAIL_VERIFY_PROVIDER=none (the default)
this module is never called and discovery behaves exactly as before.

Normalized statuses, provider-independent:
    valid       the mailbox exists (confidence may rise, capped below Tier 1)
    invalid     the mailbox does not exist (candidate is dropped)
    accept_all  domain accepts anything — existence unknowable
    webmail     personal-mail domain (Hunter only)
    disposable  throwaway domain (Hunter only)
    unknown     provider could not determine
    unverified  we never got an answer (flag off, timeout, error, daily cap)

Fail-soft is the contract: a verification failure must NEVER surface an error
to the contact endpoint — the worst outcome is today's unverified behavior.
No email addresses in logs (no-PII rule): only status and credit charge.
"""

from __future__ import annotations

import datetime
import logging
import threading

import requests

from app import config

log = logging.getLogger(__name__)

UNVERIFIED = {"status": "unverified", "score": None, "provider": None}

# Outbound-call budget: a hard daily stop so a bug (or a scrape-shaped burst)
# cannot drain the account. Process-local, resets at UTC midnight.
_cap_lock = threading.Lock()
_cap_state = {"day": None, "count": 0}


def _under_daily_cap() -> bool:
    today = datetime.datetime.now(datetime.timezone.utc).date()
    with _cap_lock:
        if _cap_state["day"] != today:
            _cap_state["day"] = today
            _cap_state["count"] = 0
        if _cap_state["count"] >= config.EMAIL_VERIFY_DAILY_CAP:
            return False
        _cap_state["count"] += 1
        return True


def verify(email: str) -> dict:
    """Normalized verification result for one address. Never raises."""
    provider = config.EMAIL_VERIFY_PROVIDER
    if provider == "none" or not email:
        return dict(UNVERIFIED)
    if not _under_daily_cap():
        log.info("email verification skipped: daily cap reached")
        return dict(UNVERIFIED)
    try:
        if provider == "generect":
            result = _generect(email)
        elif provider == "hunter":
            result = _hunter(email)
        else:
            log.warning("unknown EMAIL_VERIFY_PROVIDER %r", provider)
            return dict(UNVERIFIED)
    except Exception as exc:  # noqa: BLE001 — fail-soft is the contract
        log.warning("email verification failed (%s): %s", provider, type(exc).__name__)
        return dict(UNVERIFIED)
    result["provider"] = provider
    log.info(
        "email verified",
        extra={"provider": provider, "status": result["status"]},
    )
    return result


def _generect(email: str) -> dict:
    """POST /api/v1/email/validate/ — result: valid|invalid|catch_all|unknown."""
    resp = requests.post(
        "https://api.generect.com/api/v1/email/validate/",
        json={"emails": [email]},
        headers={"Authorization": f"Token {config.GENERECT_API_KEY}"},
        timeout=config.EMAIL_VERIFY_TIMEOUT_S,
    )
    resp.raise_for_status()
    body = resp.json()
    row = (body.get("data") or [{}])[0]
    status = {
        "valid": "valid",
        "invalid": "invalid",
        "catch_all": "accept_all",
        "unknown": "unknown",
    }.get(row.get("result"), "unknown")
    return {"status": status, "score": None, "raw_result": row.get("result")}


def _hunter(email: str) -> dict:
    """GET /v2/email-verifier — status: valid|invalid|accept_all|webmail|disposable|unknown."""
    resp = requests.get(
        "https://api.hunter.io/v2/email-verifier",
        params={"email": email, "api_key": config.HUNTER_API_KEY},
        timeout=config.EMAIL_VERIFY_TIMEOUT_S,
    )
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    status = data.get("status")
    if status not in {"valid", "invalid", "accept_all", "webmail", "disposable", "unknown"}:
        status = "unknown"
    return {"status": status, "score": data.get("score"), "raw_result": data.get("status")}
