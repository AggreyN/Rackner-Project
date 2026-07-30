"""
Rackner FDI — shared schema (backend, Pydantic v2).
MIRRORS SCHEMA.md EXACTLY. If SCHEMA.md changes, change this to match.
Place at: app/schemas.py  (copied verbatim from the lock-shared-schema contract)
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

ObligationType = Literal[
    "report", "deliverable", "certification", "flow-down", "cyber", "legal", "financial"
]
TimeBucket = Literal["immediate", "30_days", "quarterly", "ongoing", "unclear"]
Verdict = Literal["pursue", "conditional", "no_bid"]


class Obligation(BaseModel):
    plain_english_text: str
    obligation_type: ObligationType
    trigger_or_deadline: Optional[str] = None
    responsible_party: Optional[str] = None
    time_bucket: TimeBucket = "unclear"
    verbatim_quote: str
    source_page: Optional[int] = None
    source_ref: Optional[str] = None
    verified: bool = False
    confidence: float = Field(ge=0.0, le=1.0)


class CompatibilityFactor(BaseModel):
    name: str
    weight: float = Field(ge=0.0, le=1.0)
    score: float = Field(ge=1.0, le=5.0)
    rationale: str


class Incumbent(BaseModel):
    name: str
    uei: str


class SpendByYear(BaseModel):
    year: str
    amount: float


class SpendSummary(BaseModel):
    total_obligated: float
    incumbent: Optional[Incumbent] = None
    by_year: list[SpendByYear] = Field(default_factory=list)
    trend: str = ""


class Contact(BaseModel):
    name: str
    title: str
    agency: str
    email: str
    confidence: float = Field(ge=0.0, le=1.0)
    procurement_integrity_flag: bool = False


class Opportunity(BaseModel):
    id: str
    title: str
    agency: str
    naics: Optional[str] = None
    set_aside: Optional[str] = None
    response_deadline: Optional[str] = None
    estimated_value: Optional[float] = None
    description: str = ""
    source_url: str = ""


class SizeTargets(BaseModel):
    min_value: float = 0
    max_value: float = 0


class LifecycleProfile(BaseModel):
    capabilities: list[str] = Field(default_factory=list)
    target_agencies: list[str] = Field(default_factory=list)
    naics_codes: list[str] = Field(default_factory=list)
    past_performance: list[str] = Field(default_factory=list)
    contract_vehicles: list[str] = Field(default_factory=list)
    set_aside_status: list[str] = Field(default_factory=list)
    size_targets: SizeTargets = Field(default_factory=SizeTargets)


class Analysis(BaseModel):
    opportunity_id: str
    compatibility_score: float = Field(ge=0.0, le=100.0)
    verdict: Verdict
    summary: str = ""
    factors: list[CompatibilityFactor] = Field(default_factory=list)
    obligations: list[Obligation] = Field(default_factory=list)
    spend: Optional[SpendSummary] = None
    contact: Optional[Contact] = None
    generated_at: Optional[str] = None


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


def compatibility_score(factors: list[CompatibilityFactor]) -> float:
    weighted = sum(f.weight * f.score for f in factors)
    return round((weighted - 1) / 4 * 100, 1)


def verdict_for(score: float) -> Verdict:
    return "pursue" if score >= 70 else "conditional" if score >= 50 else "no_bid"
