// The locked FDI schema — the single source of truth for the frontend.
// This is the contract the FastAPI backend (Aggrey) and the analysis LLM
// (Kaliza) serve. If a field changes at a team sync, change it HERE and
// TypeScript will point at every component that needs updating.
//
// Pivot note (7/22 reframing): the product is opportunity capture, not
// document upload. Users search SAM.gov, score an opportunity against the
// company's lifecycle plan, follow the money, and find the contact.

// ---------- auth & profile ----------

export interface User {
  email: string;
  org: string; // e.g. "rackner.com"
  initials: string;
}

/** Parsed "fit profile" from the uploaded Opportunity Lifecycle plan.
 *  Powers compatibility scoring + the suggested-opportunities ranking. */
export interface LifecycleProfile {
  filename: string;
  uploaded_at: string; // ISO 8601
  capabilities: string[];
  naics_codes: string[];
  target_agencies: string[];
  set_asides: string[]; // e.g. ["HUBZone"]
}

export interface Profile {
  user: User;
  lifecycle: LifecycleProfile | null;
}

// ---------- opportunities (SAM.gov) ----------

export type OpportunityKind = "solicitation" | "baa" | "sources_sought" | "presolicitation";

export interface OpportunitySummary {
  id: string; // SAM.gov notice id
  title: string;
  agency: string;
  office: string | null;
  solicitation_number: string | null;
  naics: string | null;
  set_aside: string | null;
  kind: OpportunityKind;
  description: string; // mini description for cards
  close_date: string | null; // ISO date
  days_to_close: number | null;
  est_value: string | null; // e.g. "$8–12M / 5yr" (display string from backend)
  incumbent: string | null;
  /** 0–100 compatibility vs. the lifecycle plan; null until a plan is on file. */
  fit_score: number | null;
}

// ---------- analysis (the demo's heart) ----------

export type FitBand = "pursue" | "conditional" | "no_bid";

/** One factor of the CAP-derived Pre-Qualification/PWin model (§2 of the
 *  build plan). Backend scores 1–5 with a cited rationale; weights sum to 1. */
export interface FitFactor {
  key: string;
  label: string;
  weight: number; // 0–1
  score: number; // 1–5
  rationale: string;
  citation: Citation | null;
}

export interface Citation {
  section: string; // e.g. "§L.2"
  page: number | null;
}

export type TimeBucket = "immediate" | "30_days" | "at_award" | "quarterly" | "ongoing" | "unclear";

export interface Obligation {
  id: number;
  text: string; // plain-English obligation
  obligation_type: string; // submission | performance | certification | reporting | ...
  time_bucket: TimeBucket;
  deadline_label: string; // e.g. "Immediate · 21 days"
  verbatim_quote: string;
  citation: Citation;
  /** Quote string-matched back to the source text — the anti-hallucination gate. */
  verified: boolean;
}

export interface Analysis {
  opportunity_id: string;
  score: number; // 0–100
  band: FitBand; // ≥70 pursue · 50–69 conditional · <50 no_bid
  verdict: string; // one-line human verdict, e.g. "Strong fit — recommend pursue"
  factors: FitFactor[];
  obligations: Obligation[];
}

// ---------- source document ----------

export interface SourceSection {
  ref: string; // "C.3.1"
  heading: string; // "SECTION C — DESCRIPTION / SPECIFICATIONS"
  text: string; // parsed text; verbatim quotes are exact substrings of this
  page: number;
}

export interface SourceDocument {
  opportunity_id: string;
  label: string; // e.g. "Source solicitation · HC1084-26-R-0042"
  sections: SourceSection[];
}

// ---------- spend history (USAspending.gov) ----------

export interface SpendYear {
  fiscal_year: string; // "FY25"
  amount: number; // dollars
}

export interface SpendSummary {
  opportunity_id: string;
  years: SpendYear[];
  total_obligated: number;
  incumbent: { name: string; uei: string } | null;
  trend_pct: number | null; // e.g. 24 → "↑ growing ~24%/yr"; negative → declining
}

// ---------- contact discovery ----------

export interface ContactResult {
  opportunity_id: string;
  name: string;
  title: string;
  office: string;
  email: string; // most probable candidate
  confidence: number; // 0–1 from the verifier
  /** Procurement Integrity Act guard: when true the UI must show the
   *  outreach-restrictions flag and require a human in the loop. */
  active_solicitation: boolean;
}

// ---------- chatbot ----------

export interface ChatCitation {
  section: string;
  page: number | null;
}

export interface ChatAnswer {
  answer: string;
  citations: ChatCitation[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  citations?: ChatCitation[];
}

// ---------- display constants ----------

export const TIME_BUCKET_LABELS: Record<TimeBucket, string> = {
  immediate: "Immediate",
  "30_days": "Within 30 days",
  at_award: "At award",
  quarterly: "Quarterly / monthly",
  ongoing: "Ongoing",
  unclear: "Timing unclear",
};

export const TIME_BUCKET_ORDER: TimeBucket[] = [
  "immediate",
  "30_days",
  "at_award",
  "quarterly",
  "ongoing",
  "unclear",
];

export const BAND_LABELS: Record<FitBand, string> = {
  pursue: "Pursue",
  conditional: "Conditional",
  no_bid: "Likely no-bid",
};
