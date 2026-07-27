// Rackner FDI — shared schema (frontend).
// MIRRORS SCHEMA.md EXACTLY (snake_case keys match the API 1:1, no mapping layer).
// Place at: frontend/src/lib/types.ts
// If SCHEMA.md changes, change this to match.

export type ObligationType =
  | "report" | "deliverable" | "certification" | "flow-down" | "cyber" | "legal" | "financial";

export type TimeBucket = "immediate" | "30_days" | "quarterly" | "ongoing" | "unclear";

export type Verdict = "pursue" | "conditional" | "no_bid";

export interface Obligation {
  plain_english_text: string;
  obligation_type: ObligationType;
  trigger_or_deadline: string | null;
  responsible_party: string | null;
  time_bucket: TimeBucket;
  verbatim_quote: string;
  source_page: number | null;
  source_ref: string | null;
  verified: boolean;
  confidence: number; // 0.0–1.0
}

export interface CompatibilityFactor {
  name: string;
  weight: number; // 0–1, all weights sum to 1.0
  score: number;  // 1–5
  rationale: string;
}

export interface Incumbent {
  name: string;
  uei: string;
}

export interface SpendByYear {
  year: string;
  amount: number;
}

export interface SpendSummary {
  total_obligated: number;
  incumbent: Incumbent | null;
  by_year: SpendByYear[];
  trend: string;
}

export interface Contact {
  name: string;
  title: string;
  agency: string;
  email: string;
  confidence: number; // 0–1
  procurement_integrity_flag: boolean;
}

export interface Opportunity {
  id: string;
  title: string;
  agency: string;
  naics: string | null;
  set_aside: string | null;
  response_deadline: string | null; // ISO-8601 date
  estimated_value: number | null;   // USD
  description: string;
  source_url: string;
}

export interface SizeTargets {
  min_value: number;
  max_value: number;
}

export interface LifecycleProfile {
  capabilities: string[];
  target_agencies: string[];
  naics_codes: string[];
  past_performance: string[];
  contract_vehicles: string[];
  set_aside_status: string[];
  size_targets: SizeTargets;
}

// Top-level object Kaliza's LLM produces for one opportunity.
export interface Analysis {
  opportunity_id: string;
  compatibility_score: number; // 0–100
  verdict: Verdict;
  summary: string;
  factors: CompatibilityFactor[];
  obligations: Obligation[];
  spend: SpendSummary | null;
  contact: Contact | null;
  generated_at: string | null; // ISO-8601
}

// UI labels for the time buckets.
export const TIME_BUCKET_LABELS: Record<TimeBucket, string> = {
  immediate: "Immediate",
  "30_days": "Within 30 days",
  quarterly: "Quarterly / annual",
  ongoing: "Ongoing",
  unclear: "Timing unclear",
};

// Verdict → display + color intent (navy/green/amber/red per the design system).
export const VERDICT_META: Record<Verdict, { label: string; intent: "ok" | "warn" | "bad" }> = {
  pursue: { label: "Pursue", intent: "ok" },
  conditional: { label: "Conditional", intent: "warn" },
  no_bid: { label: "Likely no-bid", intent: "bad" },
};
