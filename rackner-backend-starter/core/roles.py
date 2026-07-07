"""Role definitions — the heart of the 'document intelligence layer' pivot.

One document, read once; each corporate team gets the view that matters to
them (per Lauren Hiles' BD feedback). Adding a new role = adding one entry
here. Nothing else in the codebase changes.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Role:
    key: str
    label: str
    question: str                      # the question this team asks of a document
    obligation_types: tuple[str, ...]  # which extracted types are most relevant
    keywords: tuple[str, ...] = field(default_factory=tuple)  # boosts relevance


ROLES: dict[str, Role] = {
    "contracts": Role(
        key="contracts",
        label="Contracts",
        question="What are we legally on the hook for?",
        obligation_types=("flow-down", "certification", "insurance", "legal", "report"),
        keywords=("shall", "clause", "far", "dfars", "compliance", "flow down"),
    ),
    "proposal": Role(
        key="proposal",
        label="Proposal & Capture",
        question="What must the proposal address, and how will we be evaluated?",
        obligation_types=("deliverable", "report", "certification"),
        keywords=("evaluation", "criteria", "submit", "proposal", "volume", "past performance"),
    ),
    "program": Role(
        key="program",
        label="Program Management",
        question="What do we have to deliver, and when?",
        obligation_types=("deliverable", "report", "milestone"),
        keywords=("deliverable", "schedule", "milestone", "monthly", "quarterly", "cdrl"),
    ),
    "security": Role(
        key="security",
        label="Security & Compliance",
        question="Which security and data-handling clauses apply to us?",
        obligation_types=("cyber", "certification", "legal"),
        keywords=("cyber", "incident", "cui", "nist", "safeguarding", "72 hours", "clearance"),
    ),
    "leadership": Role(
        key="leadership",
        label="Leadership",
        question="Where is the risk, and can we meet what we're signing up for?",
        obligation_types=("legal", "insurance", "cyber", "financial"),
        keywords=("penalty", "termination", "liability", "damages", "audit"),
    ),
}


def classify_roles(obligation_type: str, text: str) -> list[str]:
    """Tag an obligation with every role it matters to (rule-based v1).

    Deliberately simple and transparent — Kaliza's extractor output is not
    modified; this is a post-processing layer. v2 can swap in an LLM
    classifier behind the same function signature.
    """
    text_l = (text or "").lower()
    matched = []
    for role in ROLES.values():
        type_hit = obligation_type in role.obligation_types
        kw_hit = any(k in text_l for k in role.keywords)
        if type_hit or kw_hit:
            matched.append(role.key)
    return matched or ["contracts"]  # every obligation matters to Contracts at minimum
