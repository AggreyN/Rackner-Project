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


# --------------------------------------------------------------------------- #
# Realignment
#
# Measured against the live model on a real federal PDF, only 4 of 8 quotes
# were character-exact. The misses were not hallucinations — they were real
# passages the model re-wrapped across form-field line breaks. Discarding them
# loses true citations; loosening verify_quote() to accept them would break the
# UI's indexOf and is the bug this module exists to prevent.
#
# So: normalize to LOCATE, never to ASSERT. Find where the quote lives in the
# source, then return the source's own text for that span. The caller replaces
# the model's quote with that slice, after which it verifies exactly and
# highlights correctly. The guarantee is unchanged; only recall improves.
# --------------------------------------------------------------------------- #

_MAX_LEN_RATIO = 3.0  # a repair may not silently swallow a much larger span


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Whitespace-collapsed text plus, for each output char, its source index.

    The map is what makes repair possible: it turns a match in normalized space
    back into an exact (start, end) slice of the original string.
    """
    out: list[str] = []
    index: list[int] = []
    prev_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            index.append(i)
            prev_space = True
        else:
            out.append(ch)
            index.append(i)
            prev_space = False
    return "".join(out), index


def _normalize(text: str) -> str:
    return " ".join((text or "").split())


def realign_quote(verbatim_quote: str, source_text: str) -> str | None:
    """Return the source's own text for the span this quote refers to.

    Returns the input unchanged when it is already exact, a corrected slice when
    the quote differs from the source only in whitespace, and None when the
    quote cannot be placed safely.

    Refuses to repair (returns None) when:
      * the quote is absent from the source even after normalization,
      * the normalized quote occurs MORE THAN ONCE — an ambiguous span could
        attach the obligation to the wrong part of the document, and a wrong
        citation is worse than a missing one,
      * the recovered slice is disproportionately longer than the quote, which
        would mean we are inventing text rather than restoring it.
    """
    if not verbatim_quote or not source_text:
        return None

    # Fast path: already exact.
    if verbatim_quote in source_text:
        return verbatim_quote

    nq = _normalize(verbatim_quote)
    if not nq:
        return None

    ns, index = _normalize_with_map(source_text)

    first = ns.find(nq)
    if first == -1:
        return None  # genuinely not in the source — a hallucination stays unverified
    if ns.find(nq, first + 1) != -1:
        return None  # ambiguous: refuse rather than guess

    start = index[first]
    end = index[first + len(nq) - 1] + 1
    candidate = source_text[start:end]

    # Guardrail: the repair must be the SAME passage, not a bigger one.
    if len(candidate) > max(len(verbatim_quote), len(nq)) * _MAX_LEN_RATIO:
        return None

    # Backstop. Unreachable while _normalize_with_map is correct (verified by
    # a 200k-case fuzz: it never fires), and kept precisely because that is an
    # assumption about ANOTHER function. If someone changes the offset mapping
    # and gets it subtly wrong, this is what stops a mis-sliced span from being
    # returned and then marked verified. tests/test_realignment.py breaks the
    # mapper on purpose to prove this still catches it.
    if _normalize(candidate) != nq:
        return None
    return candidate


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
