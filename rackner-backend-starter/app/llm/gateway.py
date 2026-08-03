"""The LLM gateway — the single seam between the backend and the model.

Two public functions:

    extract_obligations(sections)                      -> list[Obligation dict]
    analyze(opportunity, lifecycle_profile, sections)  -> Analysis dict

Both route to Bedrock (LLM_MODE=bedrock) or the mock (default) and then run the
shared assembly: normalize to SCHEMA_v2, attach a citation naming the section
the quote came from, apply the no-hallucination check, and — for analyze —
derive `score`, `band` and `verdict` on the backend. The model is never trusted
to compute the score or to declare its own quote verified.

Extraction is done PER SECTION rather than over one concatenated blob. That is
what makes `citation.section` truthful: an obligation's quote is verified
against the exact section its citation names, so the UI's
`section.text.indexOf(quote)` is guaranteed to succeed when verified=True.
"""

import json

from app import config
from app.llm import mock, prompts
from app.llm.verify import verify_quote
from app.schemas import FitFactor, band_for, compatibility_score, verdict_for

# Schema defaults so a sparse model response still produces a valid Obligation.
_OBLIGATION_DEFAULTS = {
    "text": "",
    "obligation_type": "",
    "time_bucket": "unclear",
    "deadline_label": "",
    "verbatim_quote": "",
}

_VALID_TIME_BUCKETS = {
    "immediate",
    "30_days",
    "at_award",
    "quarterly",
    "ongoing",
    "unclear",
}


def _parse_json(text: str):
    """Best-effort JSON parse of a model response (tolerates ``` fences / prose)."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1 :] if "\n" in text else text
    try:
        return json.loads(text)
    except Exception:
        for open_c, close_c in (("[", "]"), ("{", "}")):
            i, j = text.find(open_c), text.rfind(close_c)
            if i != -1 and j != -1 and j > i:
                try:
                    return json.loads(text[i : j + 1])
                except Exception:
                    continue
        return []


def _section_field(section, name: str, default=""):
    """Sections may arrive as ORM rows or plain dicts."""
    if isinstance(section, dict):
        return section.get(name, default)
    return getattr(section, name, default)


def _normalize_obligation(raw: dict, *, ob_id: int, section) -> dict:
    ob = dict(_OBLIGATION_DEFAULTS)
    for k in _OBLIGATION_DEFAULTS:
        if raw.get(k) is not None:
            ob[k] = raw[k]
    if ob["time_bucket"] not in _VALID_TIME_BUCKETS:
        ob["time_bucket"] = "unclear"

    ref = _section_field(section, "ref", "") or ""
    ob["id"] = ob_id
    # Citation names THIS section — the one the quote was verified against.
    # Refs are stored without the "§" prefix (SCHEMA_v2).
    ob["citation"] = {
        "section": ref.lstrip("§").strip(),
        "page": _section_field(section, "page", None),
    }
    # Set by code against the exact served text, never by the model.
    ob["verified"] = verify_quote(
        ob["verbatim_quote"], _section_field(section, "text", "") or ""
    )
    return ob


def _raw_obligations_for(section_text: str) -> list[dict]:
    if config.LLM_MODE == "bedrock":
        from app.llm import bedrock_client

        parsed = _parse_json(
            bedrock_client.invoke(
                prompts.EXTRACT_SYSTEM, prompts.extract_user_prompt(section_text)
            )
        )
        if isinstance(parsed, list):
            return parsed
        return parsed.get("obligations", []) if isinstance(parsed, dict) else []
    return mock.extract(section_text)


def extract_obligations(sections: list) -> list[dict]:
    """Extract obligations from each section, cited and verified against it.

    Unverified quotes are kept with verified=False — never dropped.
    """
    obligations: list[dict] = []
    next_id = 1
    for section in sections or []:
        text = _section_field(section, "text", "") or ""
        if not text.strip():
            continue
        for raw in _raw_obligations_for(text):
            obligations.append(
                _normalize_obligation(raw, ob_id=next_id, section=section)
            )
            next_id += 1
    return obligations


def _normalize_factor(raw: dict) -> dict | None:
    """Coerce a model factor into a FitFactor, or drop it if unusable."""
    try:
        return FitFactor(**raw).model_dump()
    except Exception:
        return None


def _score(factors: list[dict]) -> float:
    valid = [FitFactor(**f) for f in factors if _normalize_factor(f) is not None]
    return compatibility_score(valid) if valid else 0.0


def analyze(opportunity: dict, lifecycle_profile: dict, sections: list) -> dict:
    """Produce a full SCHEMA_v2 Analysis.

    The model supplies the factor scores and rationales; obligations come from
    the grounded per-section extraction; the backend derives score/band/verdict.
    """
    if config.LLM_MODE == "bedrock":
        from app.llm import bedrock_client

        parsed = _parse_json(
            bedrock_client.invoke(
                prompts.ANALYZE_SYSTEM,
                prompts.analyze_user_prompt(opportunity, lifecycle_profile),
            )
        )
        parsed = parsed if isinstance(parsed, dict) else {}
        raw_factors = parsed.get("factors", [])
        verdict_note = parsed.get("verdict", "") or parsed.get("summary", "")
    else:
        result = mock.analyze_factors(opportunity, lifecycle_profile)
        raw_factors = result["factors"]
        verdict_note = result["verdict_note"]

    factors = [f for f in (_normalize_factor(r) for r in raw_factors) if f]
    obligations = extract_obligations(sections)
    score = _score(factors)

    return {
        "opportunity_id": opportunity.get("id"),
        "score": score,
        "band": band_for(score),
        # `verdict` is prose in v2; prefer the model's line, else a derived one.
        "verdict": verdict_note or verdict_for(score),
        "factors": factors,
        "obligations": obligations,
    }
