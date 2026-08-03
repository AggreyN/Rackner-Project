"""Uploaded Opportunity Lifecycle plan → LifecycleProfile.

The plan is a prose PDF; the scoring model needs structured lists. This asks the
LLM gateway to pull them out, then coerces the result into the v2 wire shape.

Two things stay server-side (SCHEMA_v2.md "DB ↔ wire"): `past_performance`,
`contract_vehicles` and the size range are parsed and persisted because they
feed scoring, but v2's LifecycleProfile does not serialize them.
"""

from __future__ import annotations

import json
import re

from app import config
from app.llm import prompts  # noqa: F401  (kept so prompt edits stay reviewable here)

_PARSE_SYSTEM = """You read a company's "Opportunity Lifecycle" capture plan and
extract its structured profile. Return ONLY a JSON object (no prose, no markdown
fences) with these keys:
  capabilities        array of strings — technical/domain strengths
  naics_codes         array of NAICS code strings
  target_agencies     array of agency names
  set_asides          array of set-aside statuses, e.g. ["HUBZone", "8(a)"]
  past_performance    array of strings — prior relevant work
  contract_vehicles   array of vehicles the company can use
  size_min            number — smallest contract value they target, USD, or null
  size_max            number — largest, USD, or null
Use only what the document actually says. Return an empty array for anything the
document does not state. Never invent capabilities, agencies, or certifications."""

_LIST_KEYS = (
    "capabilities",
    "naics_codes",
    "target_agencies",
    "set_asides",
    "past_performance",
    "contract_vehicles",
)

# Cheap, dependency-free fallbacks used when LLM_MODE=mock, so the upload path
# is demoable with no AWS. Deliberately conservative: it is better to return an
# empty profile than a hallucinated one.
_NAICS_RE = re.compile(r"\b\d{6}\b")
_SET_ASIDES = (
    "HUBZone",
    "8(a)",
    "SDVOSB",
    "WOSB",
    "EDWOSB",
    "Small Business",
    "Full and Open",
)


def _coerce(raw: dict) -> dict:
    out: dict = {k: [] for k in _LIST_KEYS}
    for k in _LIST_KEYS:
        value = raw.get(k)
        if isinstance(value, list):
            out[k] = [str(v).strip() for v in value if str(v).strip()]
        elif isinstance(value, str) and value.strip():
            out[k] = [value.strip()]
    for k in ("size_min", "size_max"):
        try:
            out[k] = float(raw[k]) if raw.get(k) is not None else None
        except (TypeError, ValueError):
            out[k] = None
    return out


def _mock_parse(text: str) -> dict:
    """Deterministic keyword scrape — no model, no AWS, no cost."""
    found_naics = sorted(set(_NAICS_RE.findall(text)))[:10]
    found_set_asides = [s for s in _SET_ASIDES if s.lower() in text.lower()]
    return {
        "capabilities": [],
        "naics_codes": found_naics,
        "target_agencies": [],
        "set_asides": found_set_asides,
        "past_performance": [],
        "contract_vehicles": [],
        "size_min": None,
        "size_max": None,
    }


def parse(plan_text: str) -> dict:
    """Plan text → the full parsed profile (wire fields + server-side extras)."""
    text = (plan_text or "").strip()
    if not text:
        return _coerce({})

    if config.LLM_MODE == "bedrock":
        from app.llm import bedrock_client

        try:
            raw = bedrock_client.invoke(_PARSE_SYSTEM, text[:100_000])
            body = raw.strip()
            if body.startswith("```"):
                body = body.strip("`")
                body = body[body.find("\n") + 1 :] if "\n" in body else body
            parsed = json.loads(body)
        except Exception:
            # A parse failure must not lose the upload — fall back to the scrape.
            parsed = _mock_parse(text)
    else:
        parsed = _mock_parse(text)

    return _coerce(parsed if isinstance(parsed, dict) else {})
