"""One place for outbound HTTP to government APIs.

Ground rule: an upstream outage returns a clean 503 — never a silent empty
panel (which reads as "no data exists") and never a 500 that takes the whole
analysis down with it.

So every call here has a connect+read timeout, bounded retries with backoff on
the failures that are actually transient (timeouts, 5xx, 429), and no retry on
the ones that never fix themselves (400, 401, 403, 404). Failures surface as
UpstreamError, which routes translate to 503 with the service named.
"""

from __future__ import annotations

import logging
import re

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

# (connect, read). Government APIs are slow; SAM's description endpoint has been
# measured taking >60s, so callers that can degrade should pass a shorter read.
DEFAULT_TIMEOUT = (5, 30)

# 5xx are transient; retry with backoff. 429 is deliberately NOT here: SAM.gov
# 429s mean the key's DAILY quota is spent, which a 4-second backoff cannot
# fix — retrying it three times turned a fast failure into a measured 47-51s
# hang before the same error. Fail fast and let the route degrade.
_RETRY_STATUS = {500, 502, 503, 504}


# requests exceptions embed the full URL — including ?api_key=… — and those
# strings flow into UpstreamError.detail, which reaches 503 response bodies
# and logs. Secret NAMES may appear in logs; secret VALUES must never.
_KEY_PARAM = re.compile(r"(api_key=)[^&\s'\"]+", re.IGNORECASE)


def redact(text: str) -> str:
    return _KEY_PARAM.sub(r"\1[redacted]", text or "")


class UpstreamError(RuntimeError):
    """An external service failed in a way we cannot paper over.

    `service` names it so the 503 tells the user which dependency is down
    rather than "something went wrong".
    """

    def __init__(self, service: str, detail: str):
        super().__init__(f"{service}: {detail}")
        self.service = service
        self.detail = detail


class _Retryable(RuntimeError):
    """Internal marker for a transient failure worth another attempt."""


@retry(
    retry=retry_if_exception_type(_Retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    reraise=True,
)
def _request(method: str, url: str, *, service: str, timeout, **kwargs):
    try:
        response = requests.request(method, url, timeout=timeout, **kwargs)
    except requests.Timeout as exc:
        raise _Retryable(f"timeout after {timeout}s") from exc
    except requests.RequestException as exc:
        raise _Retryable(redact(str(exc))) from exc

    if response.status_code in _RETRY_STATUS:
        raise _Retryable(f"HTTP {response.status_code}")
    return response


def _call(method: str, url: str, *, service: str, timeout=DEFAULT_TIMEOUT, **kwargs) -> dict:
    try:
        response = _request(method, url, service=service, timeout=timeout, **kwargs)
    except _Retryable as exc:
        log.warning("%s unavailable: %s", service, exc)
        raise UpstreamError(service, redact(str(exc))) from exc

    if not response.ok:
        # Non-retryable: a bad key, a bad query, a missing record, a spent quota.
        log.warning("%s returned HTTP %s: %s", service, response.status_code, response.text[:200])
        detail = f"HTTP {response.status_code}"
        if response.status_code == 429:
            detail += " (rate limited — the API key's request quota is spent)"
        raise UpstreamError(service, detail)

    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamError(service, "response was not JSON") from exc


def get_json(url: str, *, service: str, params=None, timeout=DEFAULT_TIMEOUT) -> dict:
    return _call("GET", url, service=service, params=params, timeout=timeout)


def get_bytes(
    url: str,
    *,
    service: str,
    params=None,
    timeout=DEFAULT_TIMEOUT,
    max_bytes: int,
) -> bytes:
    """Download a file, streamed, with a hard size cap.

    Single attempt, no retry: callers fetch attachments in a loop and degrade
    per-file, so a retry here would just multiply a dead endpoint's latency.
    The cap aborts mid-stream — a 500 MB upload can't exhaust task memory.
    """
    try:
        with requests.get(url, params=params, timeout=timeout, stream=True) as response:
            if not response.ok:
                detail = f"HTTP {response.status_code}"
                if response.status_code == 429:
                    detail += " (rate limited — the API key's request quota is spent)"
                raise UpstreamError(service, detail)
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=65536):
                total += len(chunk)
                if total > max_bytes:
                    raise UpstreamError(
                        service, f"file exceeds the {max_bytes // (1024 * 1024)} MB cap"
                    )
                chunks.append(chunk)
            return b"".join(chunks)
    except requests.RequestException as exc:
        raise UpstreamError(service, redact(str(exc))) from exc


def post_json(url: str, *, service: str, json=None, timeout=DEFAULT_TIMEOUT) -> dict:
    return _call("POST", url, service=service, json=json, timeout=timeout)
