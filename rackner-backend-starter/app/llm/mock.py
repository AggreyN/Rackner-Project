"""Deterministic, no-AWS stand-in for the LLM (LLM_MODE=mock, the default).

Everything it returns is schema-valid and clearly marked `[MOCK]` with low
confidence, so the whole app — upload → analyze → render → verify — runs end to
end with no Anthropic/AWS credentials and no cost. Flip LLM_MODE=bedrock to swap
in real Claude; nothing else changes.

For obligations, the mock pulls its `verbatim_quote` straight from the input
text, so the backend's no-hallucination check passes and the "verified" path is
exercised in demos.
"""

from app.schemas import FACTOR_WEIGHTS


def _first_sentence_with(text: str, keywords: tuple[str, ...]) -> str:
    for sentence in (text or "").replace("\n", " ").split("."):
        low = sentence.lower()
        if any(k in low for k in keywords):
            return sentence.strip()
    return ""


def extract(chunk_text: str) -> list[dict]:
    """Keyword-driven obligation extraction. Returns obligation dicts WITHOUT
    the `verified` field (the gateway/verify layer sets that)."""
    text = chunk_text or ""
    low = text.lower()
    out: list[dict] = []

    if "shall" in low or "must" in low:
        sentence = _first_sentence_with(text, ("shall", "must")) or text[:200]
        is_cyber = any(k in low for k in ("cyber", "incident", "72 hours", "cui", "nist"))
        out.append(
            {
                "plain_english_text": f"[MOCK] The contractor is required to: {sentence[:180]}",
                "obligation_type": "cyber" if is_cyber else "report",
                "trigger_or_deadline": "within 72 hours" if "72" in low else None,
                "responsible_party": "Contractor",
                "time_bucket": "immediate" if "72" in low else "ongoing",
                "verbatim_quote": sentence[:300],
                "source_page": 1,
                "source_ref": None,
                "confidence": 0.5,  # clearly-marked low confidence for mock output
            }
        )

    if "report" in low or "deliver" in low:
        sentence = _first_sentence_with(text, ("report", "deliver")) or text[:160]
        out.append(
            {
                "plain_english_text": f"[MOCK] Deliverable/reporting requirement: {sentence[:180]}",
                "obligation_type": "deliverable",
                "trigger_or_deadline": "monthly" if "month" in low else None,
                "responsible_party": "Contractor",
                "time_bucket": "30_days" if "month" in low else "ongoing",
                "verbatim_quote": sentence[:300],
                "source_page": 1,
                "source_ref": None,
                "confidence": 0.5,
            }
        )
    return out


def analyze_factors(opportunity: dict, lifecycle_profile: dict) -> dict:
    """Return {summary, factors} — the 8 canonical factors with plausible,
    deterministic scores derived from simple profile/opportunity overlap."""
    naics = opportunity.get("naics") or ""
    profile_naics = set(lifecycle_profile.get("naics_codes") or [])
    set_aside = (opportunity.get("set_aside") or "").lower()
    statuses = [s.lower() for s in (lifecycle_profile.get("set_aside_status") or [])]

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
            "name": name,
            "weight": FACTOR_WEIGHTS[name],
            "score": score,
            "rationale": f"[MOCK] {name.replace('_', ' ')} derived from profile/opportunity overlap.",
        }
        for name, score in scores.items()
    ]
    summary = (
        "[MOCK] Deterministic stand-in analysis. Set LLM_MODE=bedrock (with AWS "
        "credentials + Claude Sonnet 4.5 model access) for real scoring."
    )
    return {"summary": summary, "factors": factors}
