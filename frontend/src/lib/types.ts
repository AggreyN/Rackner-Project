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
  /** Display name ("Welcome, {username}") — mirrors Cognito's `name`
   *  attribute; null falls back to the email local-part. */
  username: string | null;
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

/** `expiring_award` is NOT a SAM.gov notice — it's an existing award from
 *  USAspending.gov whose period of performance is ending, i.e. a recompete
 *  that hasn't been solicited yet. That's the capture window; by the time a
 *  solicitation posts, the incumbent has usually already shaped it. */
export type OpportunityKind =
  | "solicitation"
  | "baa"
  | "sources_sought"
  | "presolicitation"
  | "expiring_award";

export interface OpportunitySummary {
  id: string; // SAM.gov notice id, or USAspending award id for expiring_award
  title: string;
  agency: string;
  office: string | null;
  solicitation_number: string | null;
  naics: string | null;
  set_aside: string | null;
  kind: OpportunityKind;
  description: string; // mini description for cards
  close_date: string | null; // ISO date — solicitation response deadline
  days_to_close: number | null;
  est_value: string | null; // e.g. "$8–12M / 5yr" (display string from backend)
  incumbent: string | null;
  /** 0–100 compatibility vs. the lifecycle plan; null until a plan is on file. */
  fit_score: number | null;
  /** Where fit_score came from: "analysis" = the user's cached full analysis
   *  (card and analysis screen agree); "estimate" = a metadata-only
   *  pre-screen (AI-batched or heuristic). Render estimates as approximate
   *  ("~72 est."), never as verdicts. Null when fit_score is null. */
  fit_source: "estimate" | "analysis" | null;

  // --- recompete radar (expiring_award only; null on live solicitations) ---
  /** Period-of-performance end date of the CURRENT award (ISO date).
   *  Backend maps this from USAspending's
   *  `period_of_performance_current_end_date`. */
  expiry_date: string | null;
  /** Months from today until `expiry_date`. Backend computes it so the
   *  window filter is evaluated server-side against the full dataset. */
  months_to_expiry: number | null;
  /** Total obligated on the expiring award — the size signal for a recompete. */
  current_award_value: number | null;
}

// ---------- search filters ----------

/** The capture sweet spot. Early enough to shape the requirement, meet the
 *  CO during sources-sought, and build a team before the RFP drops. */
export const RECOMPETE_WINDOW = { from: 12, to: 18 } as const;

export interface SearchFilters {
  /** Only return expiring awards whose `months_to_expiry` falls in
   *  [expiring_from, expiring_to]. Omit both for no expiry filtering. */
  expiring_from?: number;
  expiring_to?: number;
  /** Restrict to these kinds. Omit for all. */
  kinds?: OpportunityKind[];
}

export type TimingPreset = "all" | "recompete" | "expiring_soon" | "open";

export const TIMING_PRESETS: Array<{
  key: TimingPreset;
  label: string;
  hint: string;
  filters: SearchFilters;
}> = [
  { key: "all", label: "All", hint: "Everything we track.", filters: {} },
  {
    key: "recompete",
    label: "Recompete window · 12–18 mo",
    hint: "Contracts expiring in 12–18 months — early enough to shape the requirement and meet the CO before the RFP drops.",
    filters: {
      kinds: ["expiring_award"],
      expiring_from: RECOMPETE_WINDOW.from,
      expiring_to: RECOMPETE_WINDOW.to,
    },
  },
  {
    key: "expiring_soon",
    label: "Expiring ≤ 24 mo",
    hint: "Every tracked award ending within two years — includes the ones that are already too late to shape.",
    filters: { kinds: ["expiring_award"], expiring_from: 0, expiring_to: 24 },
  },
  {
    key: "open",
    label: "Open solicitations",
    hint: "Posted on SAM.gov and accepting responses now.",
    filters: { kinds: ["solicitation", "baa", "sources_sought", "presolicitation"] },
  },
];

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

// Optional third-party check of an INFERRED contact address (feature-flagged
// on the backend; null when off or when the contact came published from SAM).
export interface ContactVerification {
  provider: string; // "generect" | "hunter"
  status: string; // valid | accept_all | webmail | disposable | unknown | invalid | unverified
  checked_at: string | null;
}

export interface SourceDocument {
  opportunity_id: string;
  label: string; // e.g. "Source solicitation · HC1084-26-R-0042"
  sections: SourceSection[];
  // Attachment bookkeeping (optional — mock docs omit them). ingested =
  // attachments whose text is in sections; accounted = links resolved
  // (fetched or permanently dead); expected = links on the notice. When
  // expected > accounted, the rest loads once SAM.gov quota allows.
  attachments_ingested?: number;
  attachments_accounted?: number;
  attachments_expected?: number;
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
  verification?: ContactVerification | null;
}

// ---------- chatbot ----------

export interface ChatCitation {
  section: string;
  page: number | null;
  /** Exact source words — same highlight path as obligations. */
  verbatim_quote: string;
  /** Backend-verified exact substring of the cited section (never the model's
   *  own claim). Only verified quotes are safe to highlight. */
  verified: boolean;
}

export interface ChatAnswer {
  answer: string;
  citations: ChatCitation[];
}

export interface ChatMessage {
  /** UI-only: marks a synthetic error bubble; never sent to the backend. */
  error?: boolean;
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
