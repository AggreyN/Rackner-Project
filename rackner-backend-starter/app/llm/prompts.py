"""Prompt templates for the Bedrock path.

These are the exact instructions Kaliza's `extract` / `analyze` send to Claude.
They are versioned here so prompt changes are reviewable in git. The output
contract is JSON matching /SCHEMA_v2.md; the gateway parses and validates it.

Kaliza owns the *content* of these prompts (few-shot examples, wording, factor
rubric). Aggrey owns the *plumbing* (how they're sent and parsed). Editing a
prompt never requires touching gateway.py.
"""

# The obligation JSON keys the model must return (mirrors schemas.Obligation).
# `id`, `citation` and `verified` are deliberately NOT requested — the gateway
# assigns the id, builds the citation from the section it fed the model, and
# computes `verified` itself. See SCHEMA_v2.md.
OBLIGATION_KEYS = (
    "text, obligation_type, time_bucket, deadline_label, verbatim_quote"
)

EXTRACT_SYSTEM = f"""You extract contractual obligations from U.S. federal solicitations.
Return ONLY a JSON array (no prose, no markdown fences). Each element has exactly
these keys: {OBLIGATION_KEYS}.

Rules:
- text is a plain-English statement of what the contractor must do.
- obligation_type is a short lowercase label, e.g. submission, performance,
  certification, reporting, cyber, legal, financial.
- time_bucket is one of: immediate, 30_days, at_award, quarterly, ongoing, unclear.
- deadline_label is a short display string, e.g. "Immediate · 21 days".
- verbatim_quote MUST be copied character-for-character from the source text —
  same capitalization, punctuation and internal line breaks. Do not paraphrase,
  re-wrap, or tidy it. If you cannot quote it exactly, omit the obligation.
- Do NOT set "id", "citation" or "verified"; the backend computes those.
Return [] if the text contains no obligations."""

ANALYZE_SYSTEM = """You score a U.S. federal opportunity against a company's lifecycle profile.
Return ONLY a JSON object (no prose, no markdown fences) with these keys:
verdict (a one-sentence plain-English take), factors (array). Each factor has:
key, label, weight (0-1), score (1-5), rationale (required, cite the why).

Use exactly these eight factors with these weights (they sum to 1.0):
technical_capability 0.20, mission_alignment 0.15, past_performance 0.15,
contract_vehicle_access 0.10, set_aside_eligibility 0.10,
incumbent_advantage_inverse 0.10, pricing_size_fit 0.10, time_to_respond 0.10.

Score each factor 1-5 using these anchors (1 = poor fit, 5 = excellent fit):
- technical_capability: 1 = required scope outside our capabilities; 5 = proven, mature capability for this exact scope.
- mission_alignment: 1 = outside our target agencies/mission; 5 = squarely a target agency and a core mission area.
- past_performance: 1 = no relevant, recent, or similar-size past performance; 5 = directly relevant, recent, comparable-size past performance.
- contract_vehicle_access: 1 = requires a vehicle we cannot access; 5 = we hold the required vehicle, or it is open competition.
- set_aside_eligibility: 1 = a set-aside we do not qualify for; 5 = fully eligible (or full-and-open, no restriction).
- incumbent_advantage_inverse: INVERSE — 1 = strong, entrenched, long-tenured incumbent; 5 = weak or no incumbent, or recompete churn.
- pricing_size_fit: 1 = estimated value far outside our size sweet spot; 5 = value squarely in our sweet spot.
- time_to_respond: 1 = deadline too soon to prepare a strong proposal; 5 = ample runway to respond well.

Base every score ONLY on evidence actually present in the inputs, and cite that
evidence in the rationale. Never invent facts, competitors, prices, or
relationships. If a factor has no supporting evidence, score it conservatively
(2-3) and say so in the rationale.

Use the factor name as BOTH `key` (snake_case, exactly as listed above) and
`label` (human-readable, e.g. "Technical capability").

Do NOT compute `score` or `band` — the backend derives those from the weighted
factors."""


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


CHAT_SYSTEM = """You answer questions about a U.S. federal solicitation using ONLY
the numbered sections provided. Return ONLY a JSON object (no prose, no markdown
fences) with these keys:
  answer     a direct, plain-English answer
  citations  array of {"section": "<the ref exactly as given>",
                       "page": <number|null>,
                       "verbatim_quote": "<the supporting passage>"}

Rules:
- Ground every claim in the provided sections and cite the section it came from.
- verbatim_quote MUST be copied character-for-character from that section —
  same capitalization, punctuation and internal line breaks. Do not paraphrase,
  re-wrap, or tidy it. If you cannot quote it exactly, omit that citation.
- If the sections do not answer the question, say so plainly in `answer` and
  return an empty citations array. Never fill the gap from general knowledge
  about federal contracting.
- Do not speculate about price, competitors, or the government's intent.
- Cite section refs EXACTLY as they appear in the input (no "§" prefix).
- Do NOT set a "verified" field; the backend computes that.
- A CONVERSATION SO FAR may be included. Use it ONLY to resolve what the
  question refers to ("that clause", "the deadline you mentioned"). It is
  conversation, not source material: every factual claim must still come from
  the sections, and citations may only reference the sections."""


def chat_user_prompt(question: str, sections: list, history: list | None = None) -> str:
    """Render the grounding sections, any prior turns, then the question.

    History renders BETWEEN sections and question: context for reading the
    question, positioned so the model never mistakes it for source text.
    """
    blocks = []
    for section in sections:
        if isinstance(section, dict):
            ref, page, text = section.get("ref"), section.get("page"), section.get("text")
        else:
            ref, page, text = (
                getattr(section, "ref", ""),
                getattr(section, "page", None),
                getattr(section, "text", ""),
            )
        blocks.append(f"[section {ref} | page {page}]\n{text}")

    prompt = "SOLICITATION SECTIONS:\n\n" + "\n\n".join(blocks)

    if history:
        turns = []
        for turn in history:
            role = turn.get("role") if isinstance(turn, dict) else getattr(turn, "role", "")
            text = turn.get("text") if isinstance(turn, dict) else getattr(turn, "text", "")
            if role and text:
                turns.append(f"{role}: {text}")
        if turns:
            prompt += "\n\nCONVERSATION SO FAR:\n" + "\n".join(turns)

    return prompt + f"\n\nQUESTION: {question}"
