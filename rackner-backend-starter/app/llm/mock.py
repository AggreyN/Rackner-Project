"""Deterministic, no-AWS stand-in for the LLM (LLM_MODE=mock, the default).

Everything it returns is SCHEMA_v2-valid and clearly marked `[MOCK]`, so the
whole app — upload → analyze → render → verify — runs end to end with no AWS
credentials and no cost. Flip LLM_MODE=bedrock to swap in real Claude; nothing
else changes.

GROUNDING INVARIANT: every `verbatim_quote` this module emits is produced by
slicing the input string by index (`text[a:b]`) and is therefore an exact
substring of it. Nothing is lower-cased, whitespace-collapsed, or newline-
stripped on the way out. That is what lets the UI's `text.indexOf(quote)`
highlight succeed for every verified quote.
"""

import re

from app.schemas import FACTOR_LABELS, FACTOR_WEIGHTS

# A "sentence" is a run of characters between sentence terminators. Matching on
# the ORIGINAL string (no normalization) keeps every span index meaningful.
_SENTENCE_RE = re.compile(r"[^.\n]+")

# Word splitter for the chat keyword fallback.
_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")

_MAX_QUOTE = 300


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence-ish run, trimmed of surrounding whitespace
    but still expressed as indices INTO THE ORIGINAL STRING."""
    spans: list[tuple[int, int]] = []
    for m in _SENTENCE_RE.finditer(text or ""):
        start, end = m.start(), m.end()
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end > start:
            spans.append((start, end))
    return spans


def _quote_with(text: str, keywords: tuple[str, ...]) -> str:
    """First sentence containing any keyword, sliced verbatim from `text`."""
    for start, end in _sentence_spans(text):
        if any(k in text[start:end].lower() for k in keywords):
            return text[start : min(end, start + _MAX_QUOTE)]
    return ""


def _first_quote(text: str) -> str:
    spans = _sentence_spans(text)
    if not spans:
        return ""
    start, end = spans[0]
    return text[start : min(end, start + _MAX_QUOTE)]


def extract(section_text: str) -> list[dict]:
    """Keyword-driven obligation extraction for ONE source section.

    Returns partial obligation dicts — no `id`, `citation`, or `verified`; the
    gateway assembles those so the citation always names the section the quote
    was actually taken from.
    """
    text = section_text or ""
    low = text.lower()
    out: list[dict] = []

    if "shall" in low or "must" in low:
        quote = _quote_with(text, ("shall", "must")) or _first_quote(text)
        if quote:
            urgent = "72 hour" in low or "72 hours" in low
            out.append(
                {
                    "text": f"[MOCK] The contractor is required to: {quote[:180]}",
                    "obligation_type": "cyber"
                    if any(k in low for k in ("cyber", "incident", "cui", "nist"))
                    else "performance",
                    "time_bucket": "immediate" if urgent else "ongoing",
                    "deadline_label": "Immediate · 72 hours" if urgent else "Ongoing",
                    "verbatim_quote": quote,
                }
            )

    if "report" in low or "deliver" in low:
        quote = _quote_with(text, ("report", "deliver")) or _first_quote(text)
        if quote:
            monthly = "month" in low
            out.append(
                {
                    "text": f"[MOCK] Deliverable/reporting requirement: {quote[:180]}",
                    "obligation_type": "reporting",
                    "time_bucket": "30_days" if monthly else "ongoing",
                    "deadline_label": "Within 30 days" if monthly else "Ongoing",
                    "verbatim_quote": quote,
                }
            )
    return out


def analyze_factors(opportunity: dict, lifecycle_profile: dict) -> dict:
    """Return {verdict_note, factors} — the 8 canonical factors with plausible,
    deterministic scores derived from simple profile/opportunity overlap."""
    naics = opportunity.get("naics") or ""
    profile_naics = set(lifecycle_profile.get("naics_codes") or [])
    set_aside = (opportunity.get("set_aside") or "").lower()
    statuses = [s.lower() for s in (lifecycle_profile.get("set_asides") or [])]

    scores = {
        "technical_capability": 4.0,
        "mission_alignment": 3.0,
        "past_performance": 3.0,
        "contract_vehicle_access": 3.0,
        "set_aside_eligibility": 5.0
        if (any(s in set_aside for s in statuses) or "full" in set_aside)
        else 2.0,
        "incumbent_advantage_inverse": 3.0,
        "pricing_size_fit": 3.0,
        "time_to_respond": 3.0,
    }
    if naics and naics in profile_naics:
        scores["technical_capability"] = 5.0
        scores["mission_alignment"] = 4.0

    factors = [
        {
            "key": key,
            "label": FACTOR_LABELS[key],
            "weight": FACTOR_WEIGHTS[key],
            "score": score,
            "rationale": (
                f"[MOCK] {FACTOR_LABELS[key]} derived from profile/opportunity overlap."
            ),
            "citation": None,
        }
        for key, score in scores.items()
    ]
    note = (
        "[MOCK] Deterministic stand-in analysis. Set LLM_MODE=bedrock (with AWS "
        "credentials + Claude Sonnet 4.5 model access) for real scoring."
    )
    return {"verdict_note": note, "factors": factors}


def answer_question(question: str, sections: list) -> dict:
    """Deterministic grounded answer for LLM_MODE=mock.

    Scores each section by how many question words it contains and quotes the
    best match. Cites only sections it actually used, and returns no citations
    when nothing matches — the same "say so plainly" behaviour the real prompt
    demands, so the ungrounded path is exercised in demos too.
    """
    words = {w for w in _NORMALIZE_RE.split((question or "").lower()) if len(w) > 3}
    scored = []
    for section in sections or []:
        if isinstance(section, dict):
            ref, page, text = section.get("ref"), section.get("page"), section.get("text", "")
        else:
            ref, page, text = (
                getattr(section, "ref", ""),
                getattr(section, "page", None),
                getattr(section, "text", ""),
            )
        low = (text or "").lower()
        hits = sum(1 for w in words if w in low)
        if hits:
            scored.append((hits, ref, page, text))

    if not scored:
        return {
            "answer": (
                "[MOCK] The provided sections do not answer that question. "
                "Set LLM_MODE=bedrock for a real answer."
            ),
            "citations": [],
        }

    scored.sort(key=lambda s: s[0], reverse=True)
    top = scored[:3]
    # The ANSWER is prose — normalizing it is fine. Each citation's
    # verbatim_quote is NOT prose: it is sliced by index from the section text
    # so the exact-substring check (and the UI's indexOf) holds, same
    # invariant as extract().
    excerpt = " ".join((top[0][3] or "").split())[:240]
    citations = []
    for _, ref, page, text in top:
        quote = _quote_with(text, tuple(words)) or _first_quote(text)
        citations.append(
            {"section": ref, "page": page, "verbatim_quote": quote}
        )
    return {
        "answer": f"[MOCK] Based on section {top[0][1]}: {excerpt}",
        "citations": citations,
    }
