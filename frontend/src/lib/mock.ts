// In-browser mock backend — the frontend twin of extraction/adapter.py's
// mock fallback. When NEXT_PUBLIC_API_URL is unset, lib/api.ts routes here so
// the full UI works with zero backend running (Aggrey's API drops in later
// without touching any component).
//
// Every obligation below quotes data/samples/TeamAnvil-Demo-Solicitation.pdf
// word-for-word with the real page number, so quote verification and the
// Week-7 span highlight behave exactly like production. In mock mode any
// upload opens that seeded demo document.

import type {
  DocumentMeta,
  Obligation,
  ObligationGroups,
  PiiFinding,
  RoleInfo,
  ScanResult,
} from "./types";

export const DEMO_PDF_PATH = "/samples/TeamAnvil-Demo-Solicitation.pdf";
const DEMO_FILENAME = "TeamAnvil-Demo-Solicitation.pdf";
const PROCESSING_MS = 2500; // simulate the pipeline reading the document

const ROLES: RoleInfo[] = [
  { key: "contracts", label: "Contracts", question: "What are we on the hook for?" },
  { key: "proposal", label: "Proposal & Capture", question: "What do we write, and how will it be evaluated?" },
  { key: "program", label: "Program Management", question: "What do we deliver, and when?" },
  { key: "security", label: "Security & Compliance", question: "Which clauses apply, and what must we prove?" },
  { key: "leadership", label: "Leadership", question: "Where is the risk?" },
];

// Seed data — quotes are exact substrings of the demo PDF.
type Seed = Omit<Obligation, "id" | "status" | "relevant_to_role">;
const SEEDS: Seed[] = [
  {
    plain_english_text: "Report any cyber incident to DoD at dibnet.dod.mil within 72 hours of discovering it.",
    obligation_type: "reporting",
    trigger_or_deadline: "72 hours from discovery",
    responsible_party: "Contractor",
    roles: ["security", "contracts", "leadership"],
    category: "security",
    time_bucket: "immediate",
    verbatim_quote:
      "The Contractor shall rapidly report cyber incidents within 72 hours of discovery to the Department of Defense at https://dibnet.dod.mil.",
    page: 4,
    confidence: 0.98,
    verified: true,
  },
  {
    plain_english_text: "Hold the program kickoff meeting within 10 business days of contract award.",
    obligation_type: "meeting",
    trigger_or_deadline: "10 business days after award",
    responsible_party: "Contractor",
    roles: ["program", "contracts"],
    category: "deliverable",
    time_bucket: "30_days",
    verbatim_quote:
      "The Contractor shall hold a program kickoff meeting within 10 business days after contract award.",
    page: 2,
    confidence: 0.96,
    verified: true,
  },
  {
    plain_english_text: "Submit the Quality Control Plan within 15 days of contract award.",
    obligation_type: "deliverable",
    trigger_or_deadline: "15 days after award",
    responsible_party: "Contractor",
    roles: ["program", "contracts"],
    category: "deliverable",
    time_bucket: "30_days",
    verbatim_quote:
      "The Contractor shall submit a Quality Control Plan within 15 days after contract award.",
    page: 2,
    confidence: 0.97,
    verified: true,
  },
  {
    plain_english_text: "Deliver the System Design Document within 30 days of contract award, including data and security architecture.",
    obligation_type: "deliverable",
    trigger_or_deadline: "30 days after award",
    responsible_party: "Contractor",
    roles: ["program", "security"],
    category: "deliverable",
    time_bucket: "30_days",
    verbatim_quote:
      "The Contractor shall deliver the System Design Document within 30 days after contract award.",
    page: 2,
    confidence: 0.99,
    verified: true,
  },
  {
    plain_english_text: "Every person needing access to Government systems must finish cyber awareness training first.",
    obligation_type: "compliance",
    trigger_or_deadline: "Before system access is granted",
    responsible_party: "Contractor personnel",
    roles: ["security", "program"],
    category: "security",
    time_bucket: "immediate",
    verbatim_quote:
      "All Contractor personnel requiring access to Government systems shall complete cyber awareness training before access is granted.",
    page: 2,
    confidence: 0.95,
    verified: true,
  },
  {
    plain_english_text: "Get written Contracting Officer approval at least 15 days before swapping any key personnel.",
    obligation_type: "approval",
    trigger_or_deadline: "15 days before substitution",
    responsible_party: "Contractor",
    roles: ["program", "contracts"],
    category: "legal",
    time_bucket: "ongoing",
    verbatim_quote:
      "Key personnel substitutions require written approval from the Contracting Officer no fewer than 15 days in advance.",
    page: 2,
    confidence: 0.9,
    verified: true,
  },
  {
    plain_english_text: "Submit a Contract Status Report by the 15th of every month.",
    obligation_type: "reporting",
    trigger_or_deadline: "15th of each month",
    responsible_party: "Contractor",
    roles: ["program", "contracts", "leadership"],
    category: "reporting",
    time_bucket: "ongoing",
    verbatim_quote:
      "The Contractor shall submit a Contract Status Report no later than the 15th day of each month.",
    page: 3,
    confidence: 0.98,
    verified: true,
  },
  {
    plain_english_text: "Run quarterly program management reviews on-site at the Government facility.",
    obligation_type: "meeting",
    trigger_or_deadline: "Quarterly; slides due 5 business days prior",
    responsible_party: "Contractor",
    roles: ["program", "leadership"],
    category: "reporting",
    time_bucket: "quarterly",
    verbatim_quote:
      "The Contractor shall conduct quarterly program management reviews at the Government facility.",
    page: 3,
    confidence: 0.94,
    verified: true,
  },
  {
    plain_english_text: "Invoice monthly through Wide Area Workflow, referencing the CLIN on every charge.",
    obligation_type: "financial",
    trigger_or_deadline: "Monthly",
    responsible_party: "Contractor",
    roles: ["contracts"],
    category: "financial",
    time_bucket: "ongoing",
    verbatim_quote:
      "The Contractor shall submit invoices electronically through Wide Area Workflow on a monthly basis.",
    page: 3,
    confidence: 0.97,
    verified: true,
  },
  {
    plain_english_text: "Provide a transition-out plan at least 90 days before the contract ends.",
    obligation_type: "deliverable",
    trigger_or_deadline: "90 days before contract completion",
    responsible_party: "Contractor",
    roles: ["program", "contracts"],
    category: "deliverable",
    time_bucket: "ongoing",
    verbatim_quote:
      "The Contractor shall provide a transition-out plan no later than 90 days before contract completion",
    page: 3,
    confidence: 0.88,
    verified: true,
  },
  {
    plain_english_text: "Keep every covered information system compliant with NIST SP 800-171.",
    obligation_type: "compliance",
    trigger_or_deadline: null,
    responsible_party: "Contractor",
    roles: ["security"],
    category: "security",
    time_bucket: "ongoing",
    verbatim_quote:
      "The Contractor shall provide adequate security on all covered contractor information systems in accordance with NIST SP 800-171.",
    page: 4,
    confidence: 0.97,
    verified: true,
  },
  {
    plain_english_text: "Keep FedRAMP Moderate authorization on every cloud service used for this contract; data stays in the U.S.",
    obligation_type: "compliance",
    trigger_or_deadline: null,
    responsible_party: "Contractor",
    roles: ["security", "leadership"],
    category: "security",
    time_bucket: "ongoing",
    verbatim_quote:
      "The Contractor shall maintain FedRAMP Moderate authorization for all cloud services used in performance of this contract.",
    page: 4,
    confidence: 0.96,
    verified: true,
  },
  {
    plain_english_text: "Keep subcontracting under 50% of what the Government pays (small business set-aside limit).",
    obligation_type: "compliance",
    trigger_or_deadline: null,
    responsible_party: "Contractor",
    roles: ["contracts", "leadership"],
    category: "legal",
    time_bucket: "ongoing",
    verbatim_quote:
      "The Contractor shall not pay more than 50 percent of the amount paid by the Government for contract performance to subcontractors that are not similarly situated entities.",
    page: 4,
    confidence: 0.93,
    verified: true,
  },
  {
    plain_english_text: "Disclose any organizational conflict of interest within 5 days of discovering it.",
    obligation_type: "reporting",
    trigger_or_deadline: "5 days from discovery",
    responsible_party: "Contractor",
    roles: ["contracts", "leadership"],
    category: "legal",
    time_bucket: "immediate",
    verbatim_quote:
      "The Contractor shall disclose any actual or potential organizational conflict of interest within 5 days of discovery.",
    page: 4,
    confidence: 0.92,
    verified: true,
  },
  {
    plain_english_text: "Submit the proposal by 2:00 PM Eastern on August 15, 2026 — late proposals are rejected.",
    obligation_type: "deadline",
    trigger_or_deadline: "Aug 15, 2026, 2:00 PM ET",
    responsible_party: "Offeror",
    roles: ["proposal", "leadership"],
    category: "deliverable",
    time_bucket: "immediate",
    verbatim_quote:
      "Proposals are due no later than 2:00 PM Eastern Time on August 15, 2026.",
    page: 5,
    confidence: 0.99,
    verified: true,
  },
  {
    plain_english_text: "Keep the technical proposal to 25 pages (cover, TOC, and resumes excluded).",
    obligation_type: "compliance",
    trigger_or_deadline: "At proposal submission",
    responsible_party: "Offeror",
    roles: ["proposal"],
    category: "deliverable",
    time_bucket: "immediate",
    verbatim_quote:
      "Technical proposals shall not exceed 25 pages, excluding the cover page, table of contents, and resumes.",
    page: 5,
    confidence: 0.97,
    verified: true,
  },
  {
    plain_english_text: "Send written questions by July 25, 2026; answers arrive as a SAM.gov amendment.",
    obligation_type: "deadline",
    trigger_or_deadline: "Jul 25, 2026",
    responsible_party: "Offeror",
    roles: ["proposal"],
    category: "deliverable",
    time_bucket: "immediate",
    verbatim_quote:
      "Offerors shall submit questions in writing no later than July 25, 2026.",
    page: 5,
    confidence: 0.95,
    verified: true,
  },
  {
    plain_english_text: "Award is a best-value tradeoff where technical merit counts significantly more than price.",
    obligation_type: "evaluation",
    trigger_or_deadline: null,
    responsible_party: "Government",
    roles: ["proposal", "leadership"],
    category: "legal",
    time_bucket: "unclear",
    verbatim_quote:
      "The Government will evaluate proposals using a best value tradeoff between technical merit and price.",
    page: 5,
    confidence: 0.9,
    verified: true,
  },
  {
    // Deliberately unverified: the model "remembered" standard flow-down text
    // that is NOT in this document — the verifier caught it.
    plain_english_text: "Flow the DFARS 252.204-7012 safeguarding requirements down to subcontractors handling covered defense information.",
    obligation_type: "compliance",
    trigger_or_deadline: null,
    responsible_party: "Contractor",
    roles: ["contracts", "security"],
    category: "security",
    time_bucket: "ongoing",
    verbatim_quote:
      "The Contractor shall include the substance of this clause in all subcontracts involving covered defense information.",
    page: 4,
    confidence: 0.62,
    verified: false,
  },
];

// ---------------------------------------------------------------------------
// In-memory state (module-level; resets on reload, like a fresh backend)

interface MockDoc {
  meta: DocumentMeta;
  uploadedAt: number;
}

const docs = new Map<number, MockDoc>();
let nextDocId = 1;

const obligations: Obligation[] = SEEDS.map((s, i) => ({
  ...s,
  id: i + 1,
  status: "open",
  relevant_to_role: true,
}));

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

function docMeta(id: number): DocumentMeta {
  const d = docs.get(id);
  if (!d) {
    // Unknown id (e.g. hard refresh) — behave like the seeded demo document.
    return { id, filename: DEMO_FILENAME, status: "ready", num_pages: 5, expires_at: expiry(Date.now()) };
  }
  const ready = Date.now() - d.uploadedAt > PROCESSING_MS;
  return { ...d.meta, status: ready ? "ready" : "processing" };
}

function expiry(uploadedAt: number): string {
  return new Date(uploadedAt + 3 * 24 * 60 * 60 * 1000).toISOString();
}

// ---------------------------------------------------------------------------
// The mock API surface — mirrors lib/api.ts one-to-one.

export async function scanDocument(file: File): Promise<ScanResult> {
  await delay(600);
  // Deterministic: the seeded demo doc (and anything named *pii*) trips the
  // detector — its page 1 carries a POC email and phone number.
  const name = file.name.toLowerCase();
  const findings: PiiFinding[] =
    name.includes("demo") || name.includes("pii")
      ? [
          { kind: "Email address", count: 1, sample: "j***.merritt.civ@army.mil" },
          { kind: "Phone number", count: 1, sample: "(256) ***-0142" },
        ]
      : [];
  return { has_pii: findings.length > 0, findings };
}

export async function uploadDocument(
  file: File,
  _piiAcknowledged: boolean
): Promise<{ id: number; status: string; expires_at: string }> {
  await delay(400);
  const id = nextDocId++;
  const uploadedAt = Date.now();
  docs.set(id, {
    uploadedAt,
    meta: {
      id,
      filename: file.name || DEMO_FILENAME,
      status: "processing",
      num_pages: 5,
      expires_at: expiry(uploadedAt),
    },
  });
  return { id, status: "processing", expires_at: expiry(uploadedAt) };
}

export async function getDocument(id: number): Promise<DocumentMeta> {
  await delay(200);
  return docMeta(id);
}

export function documentPdfUrl(_id: number): string {
  // Mock mode always shows the seeded demo document so citations line up.
  return DEMO_PDF_PATH;
}

export async function getRoles(): Promise<RoleInfo[]> {
  await delay(150);
  return ROLES;
}

const TIME_ORDER = ["immediate", "30_days", "quarterly", "ongoing", "unclear"];

export async function getObligations(
  _docId: number,
  role: string | null,
  groupBy: string
): Promise<ObligationGroups> {
  await delay(300);

  const tagged = obligations.map((o) => ({
    ...o,
    relevant_to_role: role ? o.roles.includes(role) : true,
  }));
  // Relevant items first inside every group — dimmed, never hidden.
  tagged.sort((a, b) => Number(b.relevant_to_role) - Number(a.relevant_to_role));

  const keyOf = (o: Obligation): string => {
    if (groupBy === "category") return o.category ?? "uncategorized";
    if (groupBy === "type") return o.obligation_type ?? "other";
    return o.time_bucket ?? "unclear";
  };

  const groups: Record<string, Obligation[]> = {};
  for (const o of tagged) (groups[keyOf(o)] ??= []).push(o);

  const ordered: Record<string, Obligation[]> = {};
  const names = Object.keys(groups).sort((a, b) => {
    if (groupBy === "time") return TIME_ORDER.indexOf(a) - TIME_ORDER.indexOf(b);
    return a.localeCompare(b);
  });
  for (const n of names) ordered[n] = groups[n];

  return { role, group_by: groupBy, total: tagged.length, groups: ordered };
}

export async function updateObligationStatus(id: number, status: string): Promise<void> {
  await delay(150);
  const o = obligations.find((x) => x.id === id);
  if (o) o.status = status as Obligation["status"];
}
