"""Contact discovery, human-in-the-loop.

Two tiers, in order:

  1. SAM.gov's `pointOfContact`. Real, published contracting-officer addresses
     ride along with the notice, so guessing is usually unnecessary. Confidence
     is high because the government published it.

  2. Pattern inference, when SAM has no POC. Candidate syntaxes are generated
     from the name and the agency's mail domain and scored by how common each
     pattern is in federal practice. These are UNVERIFIED guesses: no SMTP
     probing, no third-party verification service. Confidence is capped well
     below the published tier so the UI can tell them apart.

PROCUREMENT INTEGRITY
---------------------
`active_solicitation` is the Procurement Integrity Act guard. While a
solicitation is open, contact is constrained — discussions outside the official
channel can taint the competition. The flag is set from the opportunity's own
state, and the UI is required to surface it and keep a human in the loop. This
module never sends anything; it only proposes an address.
"""

from __future__ import annotations

import re

# Federal address patterns, most→least common. The score is a prior, not a
# measurement — nothing here has been verified against a mail server.
_PATTERNS: list[tuple[str, float]] = [
    ("{first}.{last}", 0.45),
    ("{first}.{middle}.{last}", 0.20),
    ("{f}{last}", 0.15),
    ("{first}{last}", 0.10),
    ("{last}.{first}", 0.05),
    ("{f}.{last}", 0.05),
]

# Mail domains by agency keyword. Federal mail domains rarely match the
# organization path in SAM, so this is an explicit lookup, not a guess.
_DOMAINS: list[tuple[tuple[str, ...], str]] = [
    (("army",), "army.mil"),
    (("navy", "naval"), "navy.mil"),
    (("air force", "usaf"), "us.af.mil"),
    (("marine",), "usmc.mil"),
    (("space force",), "spaceforce.mil"),
    (("defense health",), "health.mil"),
    (("disa", "defense information systems"), "disa.mil"),
    (("defense logistics", "dla"), "dla.mil"),
    (("defense",), "mail.mil"),
    (("veterans", "va "), "va.gov"),
    (("homeland", "dhs"), "hq.dhs.gov"),
    (("energy",), "hq.doe.gov"),
    (("health and human", "hhs"), "hhs.gov"),
    (("transportation",), "dot.gov"),
    (("interior",), "ios.doi.gov"),
    (("agriculture",), "usda.gov"),
    (("commerce",), "doc.gov"),
    (("justice",), "usdoj.gov"),
    (("treasury",), "treasury.gov"),
    (("state",), "state.gov"),
    (("general services", "gsa"), "gsa.gov"),
    (("nasa",), "nasa.gov"),
]

_TITLE_IN_PARENS = re.compile(r"\(([^)]*)\)")
_NON_NAME = re.compile(r"[^a-z]+")


def domain_for_agency(agency: str, office: str | None = None) -> str | None:
    haystack = f"{agency or ''} {office or ''}".lower()
    for keywords, domain in _DOMAINS:
        if any(k in haystack for k in keywords):
            return domain
    return None


def _split_name(full_name: str) -> tuple[str, str, str]:
    """('Argenies Gonzalez (Contracting Officer)') -> ('argenies', '', 'gonzalez')."""
    cleaned = _TITLE_IN_PARENS.sub("", full_name or "").strip()
    parts = [_NON_NAME.sub("", p.lower()) for p in cleaned.split()]
    parts = [p for p in parts if p]
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    first, last = parts[0], parts[-1]
    middle = parts[1] if len(parts) > 2 else ""
    return first, middle, last


def _title_from(full_name: str, fallback: str = "") -> str:
    match = _TITLE_IN_PARENS.search(full_name or "")
    return match.group(1).strip() if match else fallback


def candidates(full_name: str, domain: str) -> list[tuple[str, float]]:
    """Ranked (email, confidence) guesses. Never verified — priors only."""
    first, middle, last = _split_name(full_name)
    if not first or not last or not domain:
        return []
    out: list[tuple[str, float]] = []
    for pattern, prior in _PATTERNS:
        if "{middle}" in pattern and not middle:
            continue
        local = pattern.format(first=first, middle=middle, last=last, f=first[0])
        out.append((f"{local}@{domain}", prior))
    return out


def discover(opportunity: dict) -> dict | None:
    """Best contact for an opportunity, as a ContactResult-shaped dict.

    Returns None when there is neither a published POC nor enough information
    to infer one — better an empty panel the UI can explain than a fabricated
    contact.
    """
    opp_id = opportunity.get("id") or ""
    agency = opportunity.get("agency") or ""
    office = opportunity.get("office") or ""
    # Open solicitations constrain outreach (Procurement Integrity Act).
    active = bool(opportunity.get("close_date")) and opportunity.get("kind") != "expiring_award"

    # Tier 1: SAM published it.
    for poc in opportunity.get("_point_of_contact") or []:
        email = (poc.get("email") or "").strip()
        if not email:
            continue
        full_name = (poc.get("fullName") or "").strip()
        primary = (poc.get("type") or "").lower() == "primary"
        return {
            "opportunity_id": opp_id,
            "name": _TITLE_IN_PARENS.sub("", full_name).strip() or email.split("@")[0],
            "title": _title_from(full_name, "Contracting Officer" if primary else "Point of Contact"),
            "office": office or agency,
            "email": email,
            # Published by the government, but people move and notices go stale.
            "confidence": 0.95 if primary else 0.85,
            "active_solicitation": active,
        }

    # Tier 2: infer. Needs a name to work from.
    name_source = ""
    for poc in opportunity.get("_point_of_contact") or []:
        if poc.get("fullName"):
            name_source = poc["fullName"]
            break
    domain = domain_for_agency(agency, office)
    if not name_source or not domain:
        return None

    guesses = candidates(name_source, domain)
    if not guesses:
        return None
    email, prior = guesses[0]
    return {
        "opportunity_id": opp_id,
        "name": _TITLE_IN_PARENS.sub("", name_source).strip(),
        "title": _title_from(name_source, "Contracting Officer"),
        "office": office or agency,
        "email": email,
        # Hard ceiling: this is a pattern guess, never a verified address. It
        # must not be presentable as equal to a published contact.
        "confidence": round(min(prior, 0.5), 2),
        "active_solicitation": active,
    }
