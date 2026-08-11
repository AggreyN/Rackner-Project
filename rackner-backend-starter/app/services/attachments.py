"""SAM.gov attachment downloads — the full solicitation package.

A notice's `resourceLinks` point at the real documents (SOW, instructions,
clause sets); the description is only a summary. This module turns those URLs
into bytes for ingest.build_source_document, with the failure discipline the
rest of the stack uses:

  * per-file degradation — one dead link never blocks the rest;
  * a 429 stops ALL further fetching immediately (the key's daily quota is
    spent; every additional attempt is a wasted call) and reports the pass as
    NOT exhausted, so a later request retries once quota returns;
  * a 404/unsupported-format link is permanently resolved — the pass still
    counts as exhausted, so callers stop retrying links that will never work;
  * only content the PDF pipeline can honestly ingest is kept: PDFs by magic
    number, or text-looking bytes. Binary formats we can't parse (docx, zip)
    are skipped and logged — garbage in the grounding text would poison
    citations.

Downloads bill the SAM.gov key (roughly one call per file). Build-once caching
upstream means each opportunity pays that price exactly once.
"""

from __future__ import annotations

import logging

from app import config
from app.services import http
from app.services.http import UpstreamError

log = logging.getLogger(__name__)

SERVICE = "SAM.gov"


def _is_rate_limited(exc: UpstreamError) -> bool:
    return exc.detail.startswith("HTTP 429")


def _looks_ingestible(blob: bytes) -> bool:
    """PDF by magic number, or plausibly text (UTF-8 aware — a non-ASCII SOW
    is still text). Everything else is skipped."""
    if blob[:5] == b"%PDF-":
        return True
    sample = blob[:4096]
    if not sample:
        return False
    try:
        decoded = sample.decode("utf-8")
    except UnicodeDecodeError:
        printable = sum(1 for b in sample if 32 <= b < 127 or b in (9, 10, 13))
        return printable / len(sample) > 0.9
    good = sum(1 for ch in decoded if ch.isprintable() or ch in "\t\n\r")
    return good / len(decoded) > 0.9


def fetch_all(links: list[str] | None) -> tuple[list[bytes], bool]:
    """Download attachments in link order.

    Returns (blobs, exhausted): the successful blobs, and whether every link
    was RESOLVED — downloaded, or failed for a reason retrying won't fix.
    exhausted=False means the pass stopped on a spent quota and a later
    attempt may do better. Order is preserved and failures are skipped, so
    the assembled document is deterministic for a given set of successes.
    """
    if not links:
        return [], True
    if not config.SAM_GOV_API_KEY:
        return [], False  # can't know what's behind the links without a key

    capped = links[: config.SAM_MAX_ATTACHMENTS]
    if len(links) > len(capped):
        log.warning(
            "attachment fetch capped at %d of %d files", len(capped), len(links)
        )

    total_cap = config.SAM_ATTACHMENTS_TOTAL_MB * 1024 * 1024
    blobs: list[bytes] = []
    total = 0
    for url in capped:
        if total >= total_cap:
            log.warning("attachment total size cap reached; remaining files skipped")
            break  # resolved-by-policy: retrying won't shrink the files
        try:
            blob = http.get_bytes(
                url,
                service=SERVICE,
                params={"api_key": config.SAM_GOV_API_KEY},
                timeout=(5, 60),
                max_bytes=config.SAM_ATTACHMENT_MAX_MB * 1024 * 1024,
            )
        except UpstreamError as exc:
            if _is_rate_limited(exc):
                log.warning("SAM quota spent mid-fetch; stopping attachment downloads")
                return blobs, False
            log.info("attachment skipped (%s): %s", exc.detail, url[:120])
            continue
        if not _looks_ingestible(blob):
            log.info("attachment skipped (unsupported format): %s", url[:120])
            continue
        blobs.append(blob)
        total += len(blob)
    return blobs, True
