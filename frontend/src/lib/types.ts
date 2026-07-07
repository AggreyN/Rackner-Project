// The locked team schema — the single source of truth for the frontend.
// If the schema changes at Tuesday's sync, change it HERE and TypeScript
// will point at every component that needs updating.

export interface Obligation {
  id: number;
  plain_english_text: string;
  obligation_type: string | null;
  trigger_or_deadline: string | null;
  responsible_party: string | null;
  roles: string[];
  category: string | null;
  time_bucket: "immediate" | "30_days" | "quarterly" | "ongoing" | "unclear" | null;
  verbatim_quote: string | null;
  page: number | null;
  confidence: number | null;
  verified: boolean;
  status: "open" | "in-review" | "done";
  relevant_to_role: boolean;
}

export interface ObligationGroups {
  role: string | null;
  group_by: string;
  total: number;
  groups: Record<string, Obligation[]>;
}

export interface RoleInfo {
  key: string;
  label: string;
  question: string;
}

export interface PiiFinding {
  kind: string;
  count: number;
  sample: string;
}

export interface ScanResult {
  has_pii: boolean;
  findings: PiiFinding[];
}

export interface DocumentMeta {
  id: number;
  filename: string;
  status: "processing" | "ready" | "failed";
  num_pages: number | null;
  expires_at: string | null;
}

// A citation click: which page to jump to and which sentence should glow.
// nonce lets re-clicking the same obligation re-trigger the scroll/glow.
export interface CiteTarget {
  page: number;
  quote: string | null;
  nonce: number;
}

export const TIME_BUCKET_LABELS: Record<string, string> = {
  immediate: "Immediate (hours)",
  "30_days": "Within 30 days",
  quarterly: "Quarterly / annual",
  ongoing: "Ongoing",
  unclear: "Timing unclear",
};
