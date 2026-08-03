"""The no-hallucination check.

SCHEMA.md's contract: *every obligation must carry a verbatim quote that exists
in the source*. After the model returns obligations, the backend — not the model
— sets `verified = (verbatim_quote appears in the source text)`. Unverified
quotes are still returned, flagged, so the UI can show them with a warning
rather than as fact.

This lives on the backend on purpose: it's a deterministic, auditable guarantee
that doesn't depend on trusting the model's own claim about itself.
"""


def _normalize(s: str) -> str:
    """Collapse whitespace and lowercase so trivial formatting differences
    (line breaks, double spaces) don't cause a real quote to miss."""
    return " ".join((s or "").split()).lower()


def verify_quote(verbatim_quote: str, source_text: str) -> bool:
    """True iff the quote actually appears in the source. Empty inputs → False."""
    if not verbatim_quote or not source_text:
        return False
    return _normalize(verbatim_quote) in _normalize(source_text)


def apply_verification(obligations: list[dict], source_text: str) -> list[dict]:
    """Set `verified` on each obligation by matching its quote to the source.

    If `source_text` is empty (we have nothing to check against), every quote is
    left `verified=False` — we never mark something verified we couldn't confirm.
    """
    for ob in obligations:
        ob["verified"] = verify_quote(ob.get("verbatim_quote", ""), source_text or "")
    return obligations
