"""The no-hallucination check.

SCHEMA_v2's contract: every obligation carries a verbatim quote that exists in
the source. After the model returns obligations, the backend — not the model —
sets `verified`. Unverified quotes are still returned, flagged, so the UI can
show them with a warning rather than as fact.

WHY THIS IS AN EXACT SUBSTRING TEST
-----------------------------------
v1 normalized both sides (lower-cased, collapsed whitespace) before comparing.
That is wrong here: the frontend highlights by calling
`section.text.indexOf(quote)` on the SAME string `GET /document` serves. A
normalized match can succeed while `indexOf` returns -1 — the quote is marked
verified and then silently fails to highlight, which is worse than not
verifying it at all.

So `verified=True` means precisely: "this quote is an exact substring of a
section we serve, and the UI's indexOf WILL find it." Nothing weaker.
"""


def verify_quote(verbatim_quote: str, source_text: str) -> bool:
    """True iff the quote is an exact substring of the source. Empty → False."""
    if not verbatim_quote or not source_text:
        return False
    return verbatim_quote in source_text


def verify_against_sections(verbatim_quote: str, sections: list) -> bool:
    """True iff the quote appears verbatim in ANY served section's text.

    Accepts section objects with a `.text` attribute or plain dicts.
    """
    if not verbatim_quote:
        return False
    for sec in sections or []:
        text = sec.get("text", "") if isinstance(sec, dict) else getattr(sec, "text", "")
        if verify_quote(verbatim_quote, text):
            return True
    return False


def apply_verification(obligations: list[dict], source_text: str) -> list[dict]:
    """Set `verified` on each obligation against one source string.

    If `source_text` is empty we have nothing to check against, so every quote
    stays `verified=False` — we never mark something verified we couldn't
    confirm.
    """
    for ob in obligations:
        ob["verified"] = verify_quote(ob.get("verbatim_quote", ""), source_text or "")
    return obligations
