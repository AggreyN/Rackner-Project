"""The no-hallucination guarantee, tested as a property rather than a demo.

Both grounding bugs found in this codebase were SILENT: `verified` came back
true while the UI's `section.text.indexOf(quote)` returned -1. The quote showed
as fact and failed to highlight. Tests written against the mock passed, because
the mock had corrupted the quote and the verifier had been taught to forgive it.

So these tests assert the invariant the FRONTEND depends on, not the one the
backend claims:

    verified == True  =>  quote is findable by indexOf in a section we serve

and they specifically pin the two regressions:
    * verify must NOT normalize (a normalized match can't be highlighted)
    * ingest must slice, never rebuild (a rebuilt string isn't in the source)
"""

from __future__ import annotations

import pytest

from app.llm import gateway, mock
from app.llm.verify import verify_quote
from app.services import ingest

# Texts chosen to break naive implementations: hard line wraps mid-sentence,
# doubled spaces, tabs, non-breaking space, unicode punctuation, form feeds.
NASTY_TEXTS = [
    "The Contractor shall report any cyber incident\nwithin 72 hours of discovery.",
    "The  Contractor   shall  deliver   a  monthly  report.",
    "The Contractor shall\tprovide\tcontinuous\tmonitoring.",
    "The Contractor shall submit the plan within 30 days.",
    "The Contractor shall comply with FAR 52.204‑21 — Basic Safeguarding.",
    "SECTION C\fThe Contractor shall maintain records.",
    "C.3.1 Reporting\nThe Contractor shall report monthly.\n\nC.3.2 Delivery\nThe Contractor shall deliver quarterly.",
]


# --- verify_quote is an EXACT substring test ---------------------------------


@pytest.mark.parametrize("text", NASTY_TEXTS)
def test_exact_substrings_verify(text):
    """Any real slice of the source must verify."""
    assert verify_quote(text[: len(text) // 2], text) is True
    assert verify_quote(text, text) is True


@pytest.mark.parametrize("text", NASTY_TEXTS)
def test_whitespace_normalized_quote_does_not_verify(text):
    """REGRESSION: v1 collapsed whitespace before comparing.

    A collapsed quote is not in the served string, so indexOf would fail. It
    must NOT be reported as verified.
    """
    collapsed = " ".join(text.split())
    if collapsed != text:  # only meaningful when normalization changes something
        assert verify_quote(collapsed, text) is False


@pytest.mark.parametrize("text", NASTY_TEXTS)
def test_case_folded_quote_does_not_verify(text):
    """REGRESSION: v1 lower-cased before comparing."""
    lowered = text.lower()
    if lowered != text:
        assert verify_quote(lowered, text) is False


def test_absent_quote_does_not_verify():
    assert verify_quote("The Contractor shall deliver a fleet of submarines.", NASTY_TEXTS[0]) is False


def test_empty_inputs_do_not_verify():
    assert verify_quote("", "anything") is False
    assert verify_quote("anything", "") is False
    assert verify_quote("", "") is False


# --- the mock must produce quotes that are real slices -----------------------


@pytest.mark.parametrize("text", NASTY_TEXTS)
def test_mock_quotes_are_exact_substrings(text):
    """REGRESSION: the mock used to build quotes with .replace('\\n', ' '),
    producing strings that were not in the source at all."""
    for ob in mock.extract(text):
        quote = ob["verbatim_quote"]
        assert quote in text, f"mock invented a quote not present in source: {quote!r}"


# --- ingest slices, never rebuilds -------------------------------------------


@pytest.mark.parametrize("text", NASTY_TEXTS)
def test_sections_are_exact_slices(text):
    for sec in ingest.split_sections(text):
        assert sec["text"] in text, "section text is not a substring of the source"


@pytest.mark.parametrize("text", NASTY_TEXTS)
def test_sections_lose_no_characters(text):
    """Concatenating sections in order must reproduce the source exactly.

    This is what stops a 'harmless' .strip() from silently dropping the
    whitespace a quote depends on.
    """
    joined = "".join(s["text"] for s in ingest.split_sections(text))
    assert joined == text


def test_section_refs_carry_no_section_sign():
    doc = ingest.split_sections("§L.2 Instructions\nThe Contractor shall respond.")
    assert all(not s["ref"].startswith("§") for s in doc), [s["ref"] for s in doc]


def test_empty_source_yields_no_sections():
    assert ingest.split_sections("") == []


# --- the end-to-end invariant ------------------------------------------------


@pytest.mark.parametrize("text", NASTY_TEXTS)
def test_verified_obligations_are_highlightable(text):
    """THE contract: verified=True must mean indexOf will find it.

    Runs the real gateway over real sections and checks every obligation it
    marks verified against the exact section its citation names.
    """
    sections = ingest.split_sections(text)
    by_ref = {s["ref"]: s["text"] for s in sections}

    for ob in gateway.extract_obligations(sections):
        if not ob["verified"]:
            continue
        cited = by_ref.get(ob["citation"]["section"])
        assert cited is not None, f"citation names an unknown section: {ob['citation']}"
        assert ob["verbatim_quote"] in cited, (
            f"verified quote is not in its cited section — the UI's indexOf "
            f"would return -1. quote={ob['verbatim_quote']!r}"
        )
        # And it must be findable in the served document as a whole.
        assert any(ob["verbatim_quote"] in s["text"] for s in sections)


def test_unverified_quotes_are_flagged_not_dropped():
    """A quote we can't confirm must still reach the UI, marked false."""
    sections = [{"ref": "1", "heading": "", "text": "Nothing quotable here.", "page": 1}]
    forged = {
        "text": "invented",
        "obligation_type": "performance",
        "time_bucket": "ongoing",
        "deadline_label": "",
        "verbatim_quote": "The Contractor shall build a submarine.",
    }
    ob = gateway._normalize_obligation(forged, ob_id=1, section=sections[0])
    assert ob["verified"] is False
    assert ob["verbatim_quote"] == "The Contractor shall build a submarine."


def test_obligations_never_claim_their_own_verification():
    """The model must not be able to assert verified=True."""
    sections = [{"ref": "1", "heading": "", "text": "Nothing quotable.", "page": 1}]
    lying = {
        "text": "x",
        "verbatim_quote": "not present in the source at all",
        "verified": True,  # the model lying
    }
    ob = gateway._normalize_obligation(lying, ob_id=1, section=sections[0])
    assert ob["verified"] is False, "model-supplied `verified` must be overwritten"


def test_time_bucket_is_sanitized():
    """An invalid bucket from the model must fall back, not break the response."""
    sections = [{"ref": "1", "heading": "", "text": "text", "page": 1}]
    ob = gateway._normalize_obligation(
        {"text": "x", "verbatim_quote": "text", "time_bucket": "next_tuesday"},
        ob_id=1,
        section=sections[0],
    )
    assert ob["time_bucket"] == "unclear"
