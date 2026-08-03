"""Quote realignment: recover true citations without weakening the guarantee.

The measured problem: against the live model on a real federal PDF, 4 of 8
quotes failed an exact match. They were not hallucinations — they were real
passages the model re-wrapped across line breaks.

There are two wrong fixes and one right one:
  WRONG  loosen verify_quote() to a normalized compare -> `indexOf` breaks,
         quotes show as fact and fail to highlight (this was the original bug)
  WRONG  drop unverified quotes -> true citations silently disappear
  RIGHT  normalize to LOCATE, then return the SOURCE's text for that span

So the invariant under test is unchanged and absolute: whatever
realign_quote() returns must be an exact substring of the source. These tests
spend most of their effort on the REFUSAL cases, because the danger of repair
is attaching an obligation to the wrong passage.
"""

from __future__ import annotations

import pytest

from app.llm import gateway
from app.llm.verify import realign_quote, verify_quote
from app.services.ingest import canonicalize

SOURCE = """C.3.1 Incident Reporting
The Contractor shall report any cyber incident to the
Contracting Officer within 72 hours of discovery.

C.3.2 Client Reference Information
Name:
Title:
Phone Number:
Email Address:"""


# --- recovery ----------------------------------------------------------------


def test_exact_quote_is_returned_unchanged():
    quote = "The Contractor shall report any cyber incident"
    assert realign_quote(quote, SOURCE) == quote


def test_rewrapped_quote_is_repaired():
    """The exact failure seen against the live model: line break -> space."""
    rewrapped = "The Contractor shall report any cyber incident to the Contracting Officer"
    assert rewrapped not in SOURCE  # precondition: it really is broken
    repaired = realign_quote(rewrapped, SOURCE)
    assert repaired is not None
    assert repaired in SOURCE, "a repair MUST be an exact substring"
    assert "\n" in repaired, "the repair should restore the source's real line break"


def test_multiline_form_quote_is_repaired():
    """The other live failure: a run of form fields the model reflowed."""
    reflowed = "Client Reference Information Name: Title: Phone Number:"
    assert reflowed not in SOURCE
    repaired = realign_quote(reflowed, SOURCE)
    assert repaired is not None and repaired in SOURCE


def test_collapsed_double_spaces_are_repaired():
    source = "The  Contractor   shall  deliver  a  report."
    repaired = realign_quote("The Contractor shall deliver a report.", source)
    assert repaired is not None and repaired in source


def test_repaired_quote_then_verifies():
    """The end of the chain: repair -> verify_quote passes -> UI can highlight."""
    rewrapped = "cyber incident to the Contracting Officer within 72 hours"
    repaired = realign_quote(rewrapped, SOURCE)
    assert repaired is not None
    assert verify_quote(repaired, SOURCE) is True
    assert SOURCE.find(repaired) != -1


# --- refusals (the safety half) ----------------------------------------------


def test_absent_quote_is_refused():
    """A hallucination must stay unverified. This is the whole point."""
    assert realign_quote("The Contractor shall deliver a fleet of submarines.", SOURCE) is None


def test_partially_invented_quote_is_refused():
    assert realign_quote(
        "The Contractor shall report any cyber incident to the Space Force", SOURCE
    ) is None


def test_ambiguous_quote_is_refused():
    """Two identical passages: refuse rather than cite the wrong one.

    A wrong citation is worse than a missing one — it points the reviewer at
    the wrong clause while looking confirmed.
    """
    source = "A.1 The Contractor shall report.\n\nB.1 The Contractor shall report."
    assert realign_quote("The Contractor  shall report.", source) is None


def test_empty_inputs_are_refused():
    assert realign_quote("", SOURCE) is None
    assert realign_quote("anything", "") is None
    assert realign_quote("   ", SOURCE) is None


def test_repair_cannot_swallow_a_much_larger_span():
    """The length guard: a repair restores a passage, it does not invent one."""
    source = "A" + (" " * 5000) + "B"
    assert realign_quote("A B", source) is None


# --- the invariant, over many inputs -----------------------------------------


@pytest.mark.parametrize(
    "quote",
    [
        "The Contractor shall report any cyber incident",
        "The Contractor shall report any cyber incident to the Contracting Officer",
        "Client Reference Information Name: Title:",
        "within 72 hours of discovery.",
        "totally absent text",
        "",
        "   ",
        "Contractor",
    ],
)
def test_any_repair_is_always_an_exact_substring(quote):
    """The one rule that must never break, whatever the input."""
    repaired = realign_quote(quote, SOURCE)
    if repaired is not None:
        assert repaired in SOURCE
        assert verify_quote(repaired, SOURCE) is True


def test_guard_catches_a_broken_offset_mapper(monkeypatch):
    """The backstop in realign_quote(), made load-bearing.

    Mutation testing showed nothing failed when this check was deleted, and a
    200k-case fuzz showed it never fires while _normalize_with_map is correct.
    It is kept because it encodes an assumption about a DIFFERENT function. So
    break that function and prove the guard still holds the line: a wrong
    offset map must yield a refusal, never a mis-sliced span reported verified.
    """
    from app.llm import verify

    real = verify._normalize_with_map

    def skewed(text: str):
        norm, index = real(text)
        return norm, [max(0, i - 3) for i in index]  # shift every offset

    monkeypatch.setattr(verify, "_normalize_with_map", skewed)

    rewrapped = "The Contractor shall report any cyber incident to the Contracting Officer"
    result = verify.realign_quote(rewrapped, SOURCE)

    # "Is it a substring?" is too weak to catch this: a mis-sliced span is
    # still a slice, so it is still a substring. The property that actually
    # breaks is passage identity — the repair must be the SAME text as the
    # quote, modulo whitespace.
    assert result is None or verify._normalize(result) == verify._normalize(rewrapped), (
        f"a broken offset map produced a repair for a DIFFERENT passage: {result!r}"
    )


def test_repairs_are_always_substrings_under_fuzz():
    """Property test over randomized messy whitespace.

    Seeded, so a failure is reproducible rather than a flake.
    """
    import random
    import string

    rng = random.Random(1234)
    whitespace = [" ", "\n", "\t", "  ", "\n\n", " \t "]

    for _ in range(2000):
        words = [
            "".join(rng.choices(string.ascii_letters, k=rng.randint(1, 6)))
            for _ in range(rng.randint(2, 8))
        ]
        source = "".join(w + rng.choice(whitespace) for w in words)
        # A quote the model might emit: the right words, the wrong whitespace.
        span = words[rng.randrange(len(words)) :][: rng.randint(1, 4)]
        quote = " ".join(span)

        repaired = realign_quote(quote, source)
        if repaired is not None:
            assert repaired in source, f"repair not a substring: {repaired!r}"
            assert verify_quote(repaired, source) is True


# --- gateway integration ------------------------------------------------------


def test_gateway_repairs_and_verifies_a_rewrapped_quote():
    section = {"ref": "C.3.1", "heading": "", "text": SOURCE, "page": 1}
    raw = {
        "text": "Report cyber incidents promptly.",
        "verbatim_quote": (
            "The Contractor shall report any cyber incident to the Contracting Officer"
        ),
    }
    ob = gateway._normalize_obligation(raw, ob_id=1, section=section)
    assert ob["verified"] is True
    assert ob["verbatim_quote"] in SOURCE, "the stored quote must be the repaired one"


def test_gateway_leaves_hallucinations_unverified_and_unmodified():
    section = {"ref": "C.3.1", "heading": "", "text": SOURCE, "page": 1}
    forged = "The Contractor shall deliver a fleet of submarines."
    ob = gateway._normalize_obligation(
        {"text": "x", "verbatim_quote": forged}, ob_id=1, section=section
    )
    assert ob["verified"] is False
    assert ob["verbatim_quote"] == forged, "unrepairable quotes are shown as-is, not dropped"


def test_realignment_did_not_weaken_verify_quote():
    """verify_quote itself must remain an exact test — no normalization crept in."""
    assert verify_quote("the contractor shall report", SOURCE) is False
    assert verify_quote(
        "The Contractor shall report any cyber incident to the Contracting Officer", SOURCE
    ) is False


# --- canonicalization ---------------------------------------------------------


def test_canonicalize_unifies_smart_punctuation():
    assert canonicalize("Client Reference’s Signature:") == "Client Reference's Signature:"
    assert canonicalize("“quoted”") == '"quoted"'
    assert canonicalize("FAR 52.204‑21") == "FAR 52.204-21"


def test_canonicalize_removes_invisible_characters():
    assert canonicalize("soft­hyphen") == "softhyphen"
    assert canonicalize("zero​width") == "zerowidth"
    assert canonicalize("non breaking") == "non breaking"


def test_canonicalize_normalizes_line_endings():
    assert canonicalize("a\r\nb\rc") == "a\nb\nc"


def test_canonicalize_is_idempotent():
    for s in ["Client Reference’s Signature:", "a\r\nb", "soft­hyphen", "plain text", ""]:
        assert canonicalize(canonicalize(s)) == canonicalize(s)


def test_canonicalize_preserves_whitespace_shape():
    """It must NOT collapse whitespace — that would move every offset and
    destroy the document's structure. Whitespace drift is realignment's job."""
    text = "Line one\n\n  indented\ttabbed"
    assert canonicalize(text) == text


def test_canonicalized_smart_quote_now_matches_the_model():
    """The second live failure mode: the model emits a straight apostrophe for
    a source that had a curly one. Canonicalizing at ingest closes that gap."""
    raw_from_pdf = "Client Reference’s Signature:"
    served = canonicalize(raw_from_pdf)
    assert verify_quote("Client Reference's Signature:", served) is True
