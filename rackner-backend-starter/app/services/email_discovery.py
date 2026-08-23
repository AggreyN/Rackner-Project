"""Contact discovery, human-in-the-loop.

Two tiers, in order:

  1. SAM.gov's `pointOfContact`. Real, published contracting-officer addresses
     ride along with the notice, so guessing is usually unnecessary. Confidence
     is high because the government published it.

  2. Pattern inference, when SAM has no POC. Candidate syntaxes are generated
     from the name and the agency's mail domain and scored by how common each
     pattern is in federal practice. By DEFAULT these are UNVERIFIED guesses:
     no SMTP probing, no third-party lookups. When EMAIL_VERIFY_PROVIDER is
     set (deliberate, disclosed — see services/email_verify.py), the top
     candidates are checked against that provider: invalid ones are dropped,
     a confirmed one may rise to confidence 0.75 — still visibly below the
     published tier (0.85/0.95) so the UI can always tell them apart.
     Verification never runs on Tier 1 and never blocks discovery.

PROCUREMENT INTEGRITY
---------------------
`active_solicitation` is the Procurement Integrity Act guard. While a
solicitation is open, contact is constrained — discussions outside the official
channel can taint the competition. The flag is set from the opportunity's own
state, and the UI is required to surface it and keep a human in the loop. This
module never sends anything; it only proposes an address.
"""

from __future__ import annotations

import datetime
import re

from app import config
from app.services import email_verify

# Generational suffixes are not surnames — "Doe Jr." must guess doe@, not jr@.
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

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
    # SAM POCs frequently arrive as "Last, First [Middle]" — swap to natural
    # order before splitting, or every guessed pattern flips (doe.jane@ for
    # Jane Doe was the shipped behavior).
    if "," in cleaned:
        last_part, _, first_part = cleaned.partition(",")
        cleaned = f"{first_part.strip()} {last_part.strip()}"
    parts = [_NON_NAME.sub("", p.lower()) for p in cleaned.split()]
    parts = [p for p in parts if p]
    # Trailing position only: "Patel, V" must keep its single-letter first
    # initial — stripping any 'v' anywhere threw away real names.
    while len(parts) > 2 and parts[-1] in _SUFFIXES:
        parts.pop()
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


def _solicitation_open(opportunity: dict) -> bool:
    """Is this an OPEN solicitation (outreach constrained under the PIA)?

    The old check was `bool(close_date)` — a notice whose deadline passed
    months ago still flagged "active solicitation" forever. A close date in
    the past no longer constrains; an unparseable one stays conservative.
    """
    if opportunity.get("kind") == "expiring_award":
        return False
    raw = opportunity.get("close_date")
    if not raw:
        return False
    if isinstance(raw, datetime.datetime):
        close = raw.date()
    elif isinstance(raw, datetime.date):
        close = raw
    else:
        try:
            close = datetime.date.fromisoformat(str(raw)[:10])
        except ValueError:
            return True  # dated but unreadable — keep the outreach warning
    return close >= datetime.date.today()


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
    active = _solicitation_open(opportunity)

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
    # Hard ceiling: a pattern guess must not be presentable as equal to a
    # published contact.
    confidence = round(min(prior, 0.5), 2)
    verification = None
    if config.EMAIL_VERIFY_PROVIDER != "none":
        email, confidence, verification = _verified_choice(guesses)
        if email is None:
            # Every top candidate came back provably nonexistent. Serving one
            # anyway would be fabrication with extra steps — empty panel wins.
            # The marker (vs plain None) lets the route CACHE the negative
            # result: without it every read re-spends provider credits re-
            # proving the same invalidity.
            return {"none_valid": True}

    return {
        "opportunity_id": opp_id,
        "name": _TITLE_IN_PARENS.sub("", name_source).strip(),
        "title": _title_from(name_source, "Contracting Officer"),
        "office": office or agency,
        "email": email,
        "confidence": confidence,
        "active_solicitation": active,
        "verification": verification,
    }


def _verified_choice(
    guesses: list[tuple[str, float]],
) -> tuple[str | None, float, dict | None]:
    """Run the top candidates through the configured verifier, in rank order.

    invalid → drop and try the next; valid → serve at confidence ≤ 0.75
    (below Tier 1's 0.85/0.95, above an unchecked guess); anything else
    (accept_all, unknown, unverified, …) → serve at today's ≤ 0.5 cap.
    All top candidates invalid → (None, …): no contact at all.

    Confidence is always derived from the SERVED candidate's own pattern
    prior — a fall-through survivor must not inherit the dropped front-
    runner's higher number (audit finding: jdoe@ at jane.doe@'s 0.45).
    """
    for candidate, prior in guesses[:3]:
        own = round(min(prior, 0.5), 2)
        result = email_verify.verify(candidate)
        if result["status"] == "invalid":
            continue
        if result["status"] == "valid":
            return candidate, round(min(max(own, 0.6) + 0.15, 0.75), 2), result
        # A real provider answer (accept_all, unknown, …) is worth reporting;
        # "unverified" (timeout, cap, outage — provider None) is not an answer.
        return candidate, own, (result if result.get("provider") else None)
    return None, 0.0, None
