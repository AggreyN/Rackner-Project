"""Cheap deterministic fit scoring for opportunity CARDS.

Deliberately not the LLM analysis. `GET /opportunities/{id}/analysis` runs the
full eight-factor PWin model with cited rationales, and costs a model call per
opportunity. Ranking a search page of 25 that way would be slow and expensive
for a number the UI renders as a small badge.

So `fit_score` on OpportunitySummary is a fast structural overlap score, and
`Analysis.score` is the real thing. They will not always agree, and that is
fine — the card is a sort key, the analysis is the answer. Both are 0-100 so
the UI can show them the same way.

Returns None when no lifecycle plan is on file, matching SCHEMA_v2's
"null until a plan is on file".
"""

from __future__ import annotations

# Weights mirror the emphasis of the real model without needing its evidence.
_W_NAICS = 40.0
_W_AGENCY = 25.0
_W_SET_ASIDE = 20.0
_W_CAPABILITY = 15.0


# SAM renders agencies as e.g. "DEPT OF DEFENSE" while lifecycle plans say
# "Department of Defense". Without expansion the substring match scores the
# SAME agency zero. Applied word-by-word after lowercasing.
_ABBREVIATIONS = {
    "dept": "department",
    "govt": "government",
    "admin": "administration",
    "natl": "national",
    "u.s": "us",
    "u.s.": "us",
}


def _norm(value: str) -> str:
    words = (value or "").lower().replace("&", " and ").split()
    return " ".join(
        _ABBREVIATIONS.get(w, _ABBREVIATIONS.get(w.rstrip("."), w)) for w in words
    )


def _naics_score(opp_naics: str | None, plan_codes: list[str]) -> float:
    if not opp_naics or not plan_codes:
        return 0.0
    code = str(opp_naics).strip()
    if code in {str(c).strip() for c in plan_codes}:
        return 1.0
    # NAICS is hierarchical: a shared 4-digit prefix is the same industry group,
    # 2-digit the same sector. Partial credit reflects partial relevance.
    for length, credit in ((4, 0.6), (2, 0.3)):
        prefixes = {str(c).strip()[:length] for c in plan_codes}
        if code[:length] in prefixes:
            return credit
    return 0.0


def _agency_score(opp_agency: str, targets: list[str]) -> float:
    agency = _norm(opp_agency)
    if not agency or not targets:
        return 0.0
    for target in targets:
        t = _norm(target)
        if t and (t in agency or agency in t):
            return 1.0
    return 0.0


def _set_aside_score(opp_set_aside: str | None, statuses: list[str]) -> float:
    text = _norm(opp_set_aside)
    if not text:
        return 0.0
    # Unrestricted competition is open to everyone — no eligibility risk.
    if "full" in text or "open" in text or "unrestricted" in text:
        return 1.0
    if not statuses:
        return 0.0
    return 1.0 if any(_norm(s) and _norm(s) in text for s in statuses) else 0.0


def _capability_score(text: str, capabilities: list[str]) -> float:
    haystack = _norm(text)
    if not haystack or not capabilities:
        return 0.0
    hits = sum(1 for c in capabilities if _norm(c) and _norm(c) in haystack)
    return min(1.0, hits / 2.0)  # two matching capabilities is a strong signal


def score(opportunity: dict, lifecycle: dict | None) -> float | None:
    """0-100 structural overlap, or None with no plan on file."""
    if not lifecycle:
        return None

    total = (
        _W_NAICS * _naics_score(opportunity.get("naics"), lifecycle.get("naics_codes") or [])
        + _W_AGENCY
        * _agency_score(opportunity.get("agency") or "", lifecycle.get("target_agencies") or [])
        + _W_SET_ASIDE
        * _set_aside_score(opportunity.get("set_aside"), lifecycle.get("set_asides") or [])
        + _W_CAPABILITY
        * _capability_score(
            f"{opportunity.get('title', '')} {opportunity.get('description', '')}",
            lifecycle.get("capabilities") or [],
        )
    )
    return round(total, 1)


def rank(opportunities: list[dict], lifecycle: dict | None) -> list[dict]:
    """Attach fit_score and sort best-first.

    With no plan on file every score is None, so the original order is kept
    rather than shuffled arbitrarily.
    """
    for opp in opportunities:
        opp["fit_score"] = score(opp, lifecycle)
    if lifecycle:
        opportunities.sort(key=lambda o: (o.get("fit_score") or 0.0), reverse=True)
    return opportunities
