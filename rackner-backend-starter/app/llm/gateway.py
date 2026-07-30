"""The LLM gateway — the single seam between the backend and the model.

Two public functions match SCHEMA.md's handoff contract:

    extract_obligations(chunk_text, *, source_text=None) -> list[Obligation dict]
    analyze(opportunity, lifecycle_profile, *, source_text=None) -> Analysis dict

Both route to Bedrock (LLM_MODE=bedrock) or the mock (default) and then run the
shared assembly: normalize obligations to the schema, apply the no-hallucination
verify check, and — for analyze — derive compatibility_score and verdict on the
backend (never trusting the model to compute them). Swapping mock↔Bedrock, or
editing a prompt, never changes this file's callers.
"""

import json

from app import config
from app.llm import mock, prompts
from app.llm.verify import apply_verification
from app.schemas import CompatibilityFactor, compatibility_score, verdict_for

# Schema defaults so a sparse model response still produces a valid Obligation.
_OBLIGATION_DEFAULTS = {
    "plain_english_text": "",
    "obligation_type": "legal",
    "trigger_or_deadline": None,
    "responsible_party": None,
    "time_bucket": "unclear",
    "verbatim_quote": "",
    "source_page": None,
    "source_ref": None,
    "confidence": 0.0,
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


def _normalize_obligation(raw: dict) -> dict:
    ob = dict(_OBLIGATION_DEFAULTS)
    for k in _OBLIGATION_DEFAULTS:
        if k in raw and raw[k] is not None:
            ob[k] = raw[k]
    ob["verified"] = False  # set for real by apply_verification()
    return ob


def _score(factors: list[dict]) -> float:
    try:
        return compatibility_score([CompatibilityFactor(**f) for f in factors])
    except Exception:
        return 0.0


def extract_obligations(chunk_text: str, *, source_text: str | None = None) -> list[dict]:
    """Extract obligations from a chunk, then verify each quote against the
    source (defaults to the chunk itself when no wider source is given)."""
    if config.LLM_MODE == "bedrock":
        from app.llm import bedrock_client

        parsed = _parse_json(
            bedrock_client.invoke(
                prompts.EXTRACT_SYSTEM, prompts.extract_user_prompt(chunk_text)
            )
        )
        raw = parsed if isinstance(parsed, list) else parsed.get("obligations", [])
    else:
        raw = mock.extract(chunk_text)

    obligations = [_normalize_obligation(o) for o in raw]
    effective_source = source_text if source_text is not None else chunk_text
    return apply_verification(obligations, effective_source)


def analyze(
    opportunity: dict, lifecycle_profile: dict, *, source_text: str | None = None
) -> dict:
    """Produce a full Analysis: model gives summary + factors, obligations come
    from extract (grounded + verified), and the backend derives score + verdict."""
    if config.LLM_MODE == "bedrock":
        from app.llm import bedrock_client

        parsed = _parse_json(
            bedrock_client.invoke(
                prompts.ANALYZE_SYSTEM,
                prompts.analyze_user_prompt(opportunity, lifecycle_profile),
            )
        )
        parsed = parsed if isinstance(parsed, dict) else {}
        summary = parsed.get("summary", "")
        factors = parsed.get("factors", [])
    else:
        result = mock.analyze_factors(opportunity, lifecycle_profile)
        summary, factors = result["summary"], result["factors"]

    grounding = source_text if source_text is not None else opportunity.get("description", "")
    obligations = extract_obligations(grounding or "", source_text=grounding)

    score = _score(factors)
    return {
        "opportunity_id": opportunity.get("id"),
        "compatibility_score": score,
        "verdict": verdict_for(score),
        "summary": summary,
        "factors": factors,
        "obligations": obligations,
        "spend": None,  # filled by USAspending later
        "contact": None,  # filled by contact discovery later
        "generated_at": None,  # stamped when persisted
    }
