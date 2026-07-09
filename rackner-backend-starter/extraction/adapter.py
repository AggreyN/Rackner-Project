"""Extractor adapter — the seam between the pipeline and Kaliza's extractor.py.

Kaliza's code stays 100% hers. This adapter tries to import it; if it isn't
present (or no API key is set), a deterministic mock runs instead so the whole
app still works end-to-end for UI development. Swapping implementations never
touches the pipeline or the API.

Expected output per obligation (the locked team schema):
    {
      "plain_english_text": str, "obligation_type": str,
      "trigger_or_deadline": str|None, "responsible_party": str|None,
      "verbatim_quote": str, "confidence": float
    }
"""

from core.config import ANTHROPIC_API_KEY
from core.roles import classify_roles

# Category + time-bucket derivation (rule-based, transparent).
_CATEGORY_BY_TYPE = {
    "cyber": "security", "certification": "legal", "flow-down": "legal",
    "insurance": "financial", "report": "reporting", "deliverable": "deliverable",
    "legal": "legal", "financial": "financial", "milestone": "deliverable",
}


def _time_bucket(trigger: str | None) -> str:
    t = (trigger or "").lower()
    if any(k in t for k in ("hour", "immediately", "72", "48", "24")):
        return "immediate"
    if any(k in t for k in ("30 day", "monthly", "days")):
        return "30_days"
    if any(k in t for k in ("quarter", "90 day", "annual")):
        return "quarterly"
    if t.strip():
        return "ongoing"
    return "unclear"


def enrich(raw: dict) -> dict:
    """Add roles / category / time_bucket to one extracted obligation."""
    text = f"{raw.get('plain_english_text','')} {raw.get('verbatim_quote','')}"
    otype = raw.get("obligation_type", "legal")
    return {
        **raw,
        "roles": classify_roles(otype, text),
        "category": _CATEGORY_BY_TYPE.get(otype, "legal"),
        "time_bucket": _time_bucket(raw.get("trigger_or_deadline")),
    }


def _mock_extract(chunk_text: str) -> list[dict]:
    """Keyword-driven stand-in so the app runs without an API key."""
    out = []
    lowered = chunk_text.lower()
    if "shall" in lowered or "must" in lowered:
        sentence = next(
            (s.strip() for s in chunk_text.split(".") if "shall" in s.lower() or "must" in s.lower()),
            chunk_text[:200],
        )
        out.append({
            "plain_english_text": f"Obligation detected: {sentence[:160]}",
            "obligation_type": "cyber" if "cyber" in lowered or "incident" in lowered else "report",
            "trigger_or_deadline": "72 hours" if "72" in lowered else None,
            "responsible_party": "Contractor",
            "verbatim_quote": sentence[:300],
            "confidence": 0.55,  # mock output is clearly marked low-confidence
        })
    return out


def extract_obligations(chunk_text: str) -> list[dict]:
    """Route to the real extractor when available, else the mock."""
    try:
        from extraction.extractor import extract as kaliza_extract  # type: ignore[import-not-found]  # Kaliza's module (added later)
        if ANTHROPIC_API_KEY:
            return [enrich(o) for o in kaliza_extract(chunk_text)]
    except ImportError:
        pass
    return [enrich(o) for o in _mock_extract(chunk_text)]
