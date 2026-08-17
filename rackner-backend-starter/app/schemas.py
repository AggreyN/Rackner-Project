"""Rackner FDI — shared schema v2 (backend, Pydantic v2).

MIRRORS SCHEMA_v2.md, which is derived from Remy's frontend/src/lib/types.ts.
If a field disagrees, types.ts wins — change it there, then SCHEMA_v2.md, then
here. See SCHEMA_v2.md's "v1 → v2 changes" table for the renames.

Note the two things that most often get written back to v1 by mistake:
  * Analysis has BOTH `band` (the enum) and `verdict` (a free-text one-liner).
    `verdict` was NOT renamed to `band`; v2 has both, meaning different things.
  * Analysis.score, not compatibility_score.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# --- enums -------------------------------------------------------------------

OpportunityKind = Literal[
    "solicitation", "baa", "sources_sought", "presolicitation", "expiring_award"
]
FitBand = Literal["pursue", "conditional", "no_bid"]
TimeBucket = Literal[
    "immediate", "30_days", "at_award", "quarterly", "ongoing", "unclear"
]


# --- auth & profile ----------------------------------------------------------


class User(BaseModel):
    email: str
    org: str = ""
    initials: str = ""


class LifecycleProfile(BaseModel):
    """The wire shape. The DB table keeps extra scoring columns (past_performance,
    contract_vehicles, size_min/size_max) that v2 deliberately does not expose."""

    filename: str = ""
    uploaded_at: Optional[str] = None
    capabilities: list[str] = Field(default_factory=list)
    naics_codes: list[str] = Field(default_factory=list)
    target_agencies: list[str] = Field(default_factory=list)
    set_asides: list[str] = Field(default_factory=list)


class Profile(BaseModel):
    user: User
    lifecycle: Optional[LifecycleProfile] = None


# --- opportunities -----------------------------------------------------------


class OpportunitySummary(BaseModel):
    id: str
    title: str
    agency: str
    office: Optional[str] = None
    solicitation_number: Optional[str] = None
    naics: Optional[str] = None
    set_aside: Optional[str] = None
    kind: OpportunityKind = "solicitation"
    description: str = ""
    # Live solicitations only; null on expiring_award rows.
    close_date: Optional[str] = None
    days_to_close: Optional[int] = None
    est_value: Optional[str] = None  # display string, e.g. "$8–12M / 5yr"
    incumbent: Optional[str] = None
    fit_score: Optional[float] = None  # 0–100; null with no lifecycle plan on file
    # Where fit_score came from: "analysis" = the user's cached full analysis
    # (the researched number — card and analysis screen agree); "estimate" =
    # a pre-screen from card metadata only (AI-batched or heuristic). The UI
    # renders estimates as approximate ("~72 est."), never as verdicts.
    fit_source: Optional[Literal["estimate", "analysis"]] = None
    # expiring_award only; null on live solicitations.
    expiry_date: Optional[str] = None
    months_to_expiry: Optional[int] = None
    current_award_value: Optional[float] = None


# --- analysis ----------------------------------------------------------------


class Citation(BaseModel):
    section: str  # matches a SourceSection.ref — stored WITHOUT the "§" prefix
    page: Optional[int] = None


class FitFactor(BaseModel):
    key: str
    label: str
    weight: float = Field(ge=0.0, le=1.0)
    score: float = Field(ge=1.0, le=5.0)
    rationale: str
    citation: Optional[Citation] = None


class Obligation(BaseModel):
    id: int
    text: str
    obligation_type: str = ""
    time_bucket: TimeBucket = "unclear"
    deadline_label: str = ""
    verbatim_quote: str
    citation: Citation
    verified: bool = False


class Analysis(BaseModel):
    opportunity_id: str
    score: float = Field(ge=0.0, le=100.0)
    band: FitBand
    verdict: str = ""  # free-text one-liner for humans, NOT the enum
    factors: list[FitFactor] = Field(default_factory=list)
    obligations: list[Obligation] = Field(default_factory=list)


# --- source document ---------------------------------------------------------


class SourceSection(BaseModel):
    ref: str
    heading: str = ""
    text: str  # the canonical string quotes are matched against
    page: int = 1


class SourceDocument(BaseModel):
    opportunity_id: str
    label: str = ""
    sections: list[SourceSection] = Field(default_factory=list)


# --- spend -------------------------------------------------------------------


class Incumbent(BaseModel):
    name: str
    uei: str = ""


class SpendYear(BaseModel):
    fiscal_year: str  # "FY25"
    amount: float


class SpendSummary(BaseModel):
    opportunity_id: str
    years: list[SpendYear] = Field(default_factory=list)
    total_obligated: float = 0.0
    incumbent: Optional[Incumbent] = None
    trend_pct: Optional[float] = None


# --- contact -----------------------------------------------------------------


class ContactResult(BaseModel):
    opportunity_id: str
    name: str
    title: str = ""
    office: str = ""
    email: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    active_solicitation: bool = False


# --- assistant ---------------------------------------------------------------


class ChatCitation(BaseModel):
    """Chat citations carry the same grounding fields as obligations, so the
    UI can highlight them through the identical indexOf path.

    `verbatim_quote`/`verified` are an ADDITIVE extension over types.ts's
    {section, page} — extra JSON keys are harmless to the current frontend, so
    this ships backend-first; Remy syncs types.ts when he picks it up. The
    backend computes `verified`, never the model (same rule as obligations).
    """

    section: str
    page: Optional[int] = None
    verbatim_quote: str = ""
    verified: bool = False


class ChatAnswer(BaseModel):
    answer: str
    citations: list[ChatCitation] = Field(default_factory=list)


class ChatTurn(BaseModel):
    """One prior turn, as the frontend's ChatMessage minus citations —
    citations are display state, not conversational context."""

    role: Literal["user", "assistant"]
    text: str


class ChatRequest(BaseModel):
    question: str
    # Optional so pre-history clients keep working (additive, like ChatCitation).
    history: list[ChatTurn] = Field(default_factory=list)


# Server-side history caps — a long conversation must never blow the model's
# context or the request size. Most recent turns win.
CHAT_HISTORY_MAX_TURNS = 12
CHAT_HISTORY_MAX_CHARS = 6000


def trim_history(history: list[ChatTurn]) -> list[ChatTurn]:
    """Keep the most recent turns within both caps. Oldest are dropped first —
    silently, because a trimmed follow-up degrades to a first question, which
    is exactly the pre-history behaviour."""
    kept: list[ChatTurn] = []
    chars = 0
    for turn in reversed(history[-CHAT_HISTORY_MAX_TURNS:]):
        chars += len(turn.text)
        if chars > CHAT_HISTORY_MAX_CHARS:
            break
        kept.append(turn)
    kept.reverse()
    return kept


# --- scoring -----------------------------------------------------------------

FACTOR_WEIGHTS: dict[str, float] = {
    "technical_capability": 0.20,
    "mission_alignment": 0.15,
    "past_performance": 0.15,
    "contract_vehicle_access": 0.10,
    "set_aside_eligibility": 0.10,
    "incumbent_advantage_inverse": 0.10,
    "pricing_size_fit": 0.10,
    "time_to_respond": 0.10,
}

FACTOR_LABELS: dict[str, str] = {
    "technical_capability": "Technical capability",
    "mission_alignment": "Mission alignment",
    "past_performance": "Past performance",
    "contract_vehicle_access": "Contract vehicle access",
    "set_aside_eligibility": "Set-aside eligibility",
    "incumbent_advantage_inverse": "Incumbent advantage (inverse)",
    "pricing_size_fit": "Pricing / size fit",
    "time_to_respond": "Time to respond",
}

TIME_BUCKET_LABELS: dict[str, str] = {
    "immediate": "Immediate",
    "30_days": "Within 30 days",
    "at_award": "At award",
    "quarterly": "Quarterly / monthly",
    "ongoing": "Ongoing",
    "unclear": "Timing unclear",
}


def compatibility_score(factors: list[FitFactor]) -> float:
    """Weighted 1–5 factor scores → a 0–100 compatibility score.

    A straight weighted mean lands in [1,5]; (x-1)/4 rescales that to [0,1].
    Derived on the backend — the model is never asked to compute it.
    """
    weighted = sum(f.weight * f.score for f in factors)
    return round((weighted - 1) / 4 * 100, 1)


def band_for(score: float) -> FitBand:
    """SCHEMA_v2: ≥70 pursue · 50–69 conditional · <50 no_bid."""
    return "pursue" if score >= 70 else "conditional" if score >= 50 else "no_bid"


def verdict_for(score: float) -> str:
    """The human-readable one-liner that rides alongside `band`."""
    if score >= 70:
        return "Strong fit — recommend pursue"
    if score >= 50:
        return "Conditional fit — pursue only if gaps can be closed"
    return "Weak fit — recommend no-bid"
