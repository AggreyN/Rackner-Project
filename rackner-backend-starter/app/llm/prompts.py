"""Prompt templates for the Bedrock path.

These are the exact instructions Kaliza's `extract` / `analyze` send to Claude.
They are versioned here so prompt changes are reviewable in git. The output
contract is JSON matching /SCHEMA.md; the gateway parses and validates it.

Kaliza owns the *content* of these prompts (few-shot examples, wording, factor
rubric). Aggrey owns the *plumbing* (how they're sent and parsed). Editing a
prompt never requires touching gateway.py.
"""

# The obligation JSON keys the model must return (mirrors schemas.Obligation).
OBLIGATION_KEYS = (
    "plain_english_text, obligation_type, trigger_or_deadline, responsible_party, "
    "time_bucket, verbatim_quote, source_page, source_ref, confidence"
)

EXTRACT_SYSTEM = f"""You extract contractual obligations from U.S. federal solicitations.
Return ONLY a JSON array (no prose, no markdown fences). Each element has exactly
these keys: {OBLIGATION_KEYS}.

Rules:
- obligation_type is one of: report, deliverable, certification, flow-down, cyber, legal, financial.
- time_bucket is one of: immediate, 30_days, quarterly, ongoing, unclear.
- verbatim_quote MUST be copied character-for-character from the source text — do
  not paraphrase it. If you cannot quote it exactly, omit the obligation.
- confidence is a float 0.0-1.0.
- Do NOT set a "verified" field; the backend computes that.
Return [] if the text contains no obligations."""

ANALYZE_SYSTEM = """You score a U.S. federal opportunity against a company's lifecycle profile.
Return ONLY a JSON object (no prose, no markdown fences) with these keys:
summary (1-2 sentences), factors (array). Each factor has: name, weight (0-1),
score (1-5), rationale (required, cite the why).

Use exactly these eight factors with these weights (they sum to 1.0):
technical_capability 0.20, mission_alignment 0.15, past_performance 0.15,
contract_vehicle_access 0.10, set_aside_eligibility 0.10,
incumbent_advantage_inverse 0.10, pricing_size_fit 0.10, time_to_respond 0.10.

Do NOT compute compatibility_score or verdict — the backend derives those from
the weighted factors."""


def extract_user_prompt(chunk_text: str) -> str:
    return f"Extract obligations from this solicitation text:\n\n{chunk_text}"


def analyze_user_prompt(opportunity: dict, lifecycle_profile: dict) -> str:
    import json

    return (
        "OPPORTUNITY:\n"
        + json.dumps(opportunity, indent=2, default=str)
        + "\n\nCOMPANY LIFECYCLE PROFILE:\n"
        + json.dumps(lifecycle_profile, indent=2, default=str)
        + "\n\nScore this opportunity for this company."
    )
