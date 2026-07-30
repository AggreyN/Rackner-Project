// In-browser mock backend for Rackner FDI — the frontend twin of the
// FastAPI backend Aggrey is building. When NEXT_PUBLIC_API_URL is unset,
// lib/api.ts routes here so the full UI works with zero backend running.
//
// The seeded data mirrors the approved FDI mockup: four SAM.gov-style
// opportunities, a full analysis for the DISA SOC recompete, spend history
// shaped like USAspending.gov output, and a discovered contact with the
// Procurement Integrity flag. Every verbatim quote below is an exact
// substring of its source section, so quote verification and click-to-cite
// highlighting behave exactly like production.

import type {
  Analysis,
  ChatAnswer,
  ContactResult,
  LifecycleProfile,
  OpportunitySummary,
  Profile,
  SourceDocument,
  SpendSummary,
} from "./types";

const LATENCY_MS = 350; // simulate network + LLM
const delay = <T,>(v: T, ms = LATENCY_MS): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(v), ms));

// ---------- auth ----------

export async function login(email: string, password: string): Promise<{ access_token: string }> {
  const normalized = email.trim().toLowerCase();
  if (!normalized.endsWith("@rackner.com")) {
    throw new Error("Use your rackner.com work email for the demo.");
  }
  if (!password) throw new Error("Password required.");
  return delay({ access_token: `mock-jwt-${btoa(normalized)}` }, 500);
}

// ---------- profile / lifecycle plan ----------

let lifecycle: LifecycleProfile | null = {
  filename: "Rackner-Opportunity-Lifecycle-Plan.pdf",
  uploaded_at: "2026-07-20T14:05:00Z",
  capabilities: [
    "Cybersecurity & SOC operations",
    "DevSecOps & platform engineering",
    "Cloud migration (AWS GovCloud)",
    "Zero-trust architecture",
    "RMF / ATO support",
  ],
  naics_codes: ["541519", "541512", "541511"],
  target_agencies: ["DoD", "DISA", "Air Force", "DARPA"],
  set_asides: ["HUBZone", "Small Business"],
};

export async function getProfile(email: string): Promise<Profile> {
  const name = email.split("@")[0] || "user";
  return delay({
    user: {
      email,
      org: "rackner.com",
      initials: name.slice(0, 1).toUpperCase() || "R",
    },
    lifecycle,
  });
}

export async function uploadLifecyclePlan(file: File): Promise<LifecycleProfile> {
  // The real backend parses the PDF into a fit profile; the mock pretends.
  lifecycle = {
    filename: file.name,
    uploaded_at: new Date().toISOString(),
    capabilities: [
      "Cybersecurity & SOC operations",
      "DevSecOps & platform engineering",
      "Cloud migration (AWS GovCloud)",
      "Zero-trust architecture",
      "RMF / ATO support",
    ],
    naics_codes: ["541519", "541512", "541511"],
    target_agencies: ["DoD", "DISA", "Air Force", "DARPA"],
    set_asides: ["HUBZone", "Small Business"],
  };
  return delay(lifecycle, 900);
}

// ---------- opportunities ----------

const OPPORTUNITIES: OpportunitySummary[] = [
  {
    id: "disa-soc-0042",
    title: "Managed Cybersecurity & SOC Support Services",
    agency: "Dept. of Defense",
    office: "DISA",
    solicitation_number: "HC1084-26-R-0042",
    naics: "541519",
    set_aside: "HUBZone",
    kind: "solicitation",
    description:
      "Recompete for 24/7 SOC monitoring, incident response, and RMF support. HUBZone set-aside.",
    close_date: "2026-08-30",
    days_to_close: 21,
    est_value: "$8–12M / 5yr",
    incumbent: "SmallCyber LLC",
    fit_score: 82,
  },
  {
    id: "af-devsecops-0107",
    title: "Cloud Migration & DevSecOps Engineering",
    agency: "Dept. of the Air Force",
    office: "Platform One",
    solicitation_number: "FA8771-26-R-0107",
    naics: "541512",
    set_aside: null,
    kind: "solicitation",
    description: "DevSecOps pipeline modernization on a GovCloud environment. Full & open.",
    close_date: "2026-08-21",
    days_to_close: 12,
    est_value: "$4–6M",
    incumbent: null,
    fit_score: 64,
  },
  {
    id: "darpa-zt-baa-21",
    title: "Zero-Trust Architecture Advisory (BAA)",
    agency: "DARPA",
    office: "Broad Agency Announcement",
    solicitation_number: "HR001126S0021",
    naics: null,
    set_aside: null,
    kind: "baa",
    description: "Research BAA with three Areas of Interest — one closes in 9 days.",
    close_date: "2026-08-18",
    days_to_close: 9,
    est_value: "$2M / AOI",
    incumbent: null,
    fit_score: 75,
  },
  {
    id: "va-helpdesk-2201",
    title: "Enterprise IT Help Desk Consolidation",
    agency: "Dept. of Veterans Affairs",
    office: null,
    solicitation_number: "36C10B26R2201",
    naics: "541513",
    set_aside: null,
    kind: "solicitation",
    description:
      "Tier 1–3 help desk consolidation. Large-business full & open — outside our sweet spot.",
    close_date: "2026-09-18",
    days_to_close: 40,
    est_value: "$30M+",
    incumbent: "BigIntegrator Inc.",
    fit_score: 38,
  },
];

export async function searchOpportunities(query: string): Promise<OpportunitySummary[]> {
  const q = query.trim().toLowerCase();
  if (!q) return delay(OPPORTUNITIES);
  const terms = q.split(/\s+/).filter((t) => t.length > 2);
  const hits = OPPORTUNITIES.filter((o) => {
    const hay =
      `${o.title} ${o.agency} ${o.office ?? ""} ${o.naics ?? ""} ${o.set_aside ?? ""} ${o.description}`.toLowerCase();
    return terms.length === 0 || terms.some((t) => hay.includes(t));
  });
  return delay(hits.length ? hits : OPPORTUNITIES, 600);
}

export async function getSuggested(): Promise<OpportunitySummary[]> {
  // Ranked against the lifecycle plan; no plan on file → no scores.
  const ranked = [...OPPORTUNITIES].sort((a, b) => (b.fit_score ?? 0) - (a.fit_score ?? 0));
  return delay(lifecycle ? ranked : ranked.map((o) => ({ ...o, fit_score: null })));
}

export async function getOpportunity(id: string): Promise<OpportunitySummary> {
  const found = OPPORTUNITIES.find((o) => o.id === id);
  if (!found) throw new Error(`404: opportunity ${id} not found`);
  return delay(found, 200);
}

// ---------- analyses ----------

const ANALYSES: Record<string, Analysis> = {
  "disa-soc-0042": {
    opportunity_id: "disa-soc-0042",
    score: 82,
    band: "pursue",
    verdict: "Strong fit — recommend pursue",
    factors: [
      {
        key: "mission",
        label: "Strategic / mission alignment",
        weight: 0.15,
        score: 4.4,
        rationale: "DISA cyber operations is a named target market in the lifecycle plan.",
        citation: { section: "§C.1", page: 4 },
      },
      {
        key: "technical",
        label: "Technical & domain capability",
        weight: 0.2,
        score: 4.8,
        rationale: "24/7 SOC, incident response, and RMF support map to core capabilities.",
        citation: { section: "§C.3.1", page: 6 },
      },
      {
        key: "past_perf",
        label: "Past-performance relevance",
        weight: 0.15,
        score: 4.0,
        rationale: "Two comparable DoD SOC engagements within the last three years.",
        citation: { section: "§M.2", page: 18 },
      },
      {
        key: "vehicle",
        label: "Contract-vehicle access",
        weight: 0.1,
        score: 4.0,
        rationale: "Open solicitation via SAM.gov — no restricted vehicle required.",
        citation: { section: "§L.2", page: 14 },
      },
      {
        key: "set_aside",
        label: "Set-aside eligibility",
        weight: 0.1,
        score: 5.0,
        rationale: "HUBZone set-aside; Rackner is HUBZone-certified per the lifecycle plan.",
        citation: { section: "§K.1", page: 12 },
      },
      {
        key: "incumbent",
        label: "Incumbent advantage (inverse)",
        weight: 0.1,
        score: 2.8,
        rationale: "SmallCyber LLC holds the expiring contract with growing spend.",
        citation: null,
      },
      {
        key: "pricing",
        label: "Pricing / size fit",
        weight: 0.1,
        score: 4.2,
        rationale: "$8–12M over 5 years sits inside the plan's target award band.",
        citation: null,
      },
      {
        key: "time",
        label: "Time to respond / shape",
        weight: 0.1,
        score: 3.0,
        rationale: "21 days to closing is workable but leaves no slack for teaming.",
        citation: { section: "§L.2", page: 14 },
      },
    ],
    obligations: [
      {
        id: 1,
        text: "Submit proposal via SAM.gov portal",
        obligation_type: "submission",
        time_bucket: "immediate",
        deadline_label: "Immediate · 21 days",
        verbatim_quote:
          "Offers are due no later than 2:00 PM ET on 30 August 2026 through the SAM.gov submission portal.",
        citation: { section: "§L.2", page: 14 },
        verified: true,
      },
      {
        id: 2,
        text: "Maintain 24/7 SOC coverage w/ 15-min incident response",
        obligation_type: "performance",
        time_bucket: "ongoing",
        deadline_label: "Ongoing",
        verbatim_quote:
          "The Contractor shall provide continuous 24x7x365 monitoring and respond to Severity-1 incidents within 15 minutes.",
        citation: { section: "§C.3.1", page: 6 },
        verified: true,
      },
      {
        id: 3,
        text: "Hold DoD IL5 authorization & CMMC Level 2",
        obligation_type: "certification",
        time_bucket: "at_award",
        deadline_label: "At award",
        verbatim_quote:
          "Offeror must possess or obtain CMMC Level 2 certification prior to contract award.",
        citation: { section: "§M.4", page: 19 },
        verified: true,
      },
      {
        id: 4,
        text: "Submit monthly performance & compliance report",
        obligation_type: "reporting",
        time_bucket: "quarterly",
        deadline_label: "Monthly · CDRL A001",
        verbatim_quote:
          "A monthly status report shall be delivered by the 5th business day of each month (CDRL A001).",
        citation: { section: "§F.2", page: 11 },
        verified: true,
      },
    ],
  },
  "af-devsecops-0107": {
    opportunity_id: "af-devsecops-0107",
    score: 64,
    band: "conditional",
    verdict: "Conditional — full & open with a tight window",
    factors: [
      {
        key: "mission",
        label: "Strategic / mission alignment",
        weight: 0.15,
        score: 4.0,
        rationale: "Platform One is a named target; DevSecOps is a plan priority.",
        citation: { section: "§C.2", page: 3 },
      },
      {
        key: "technical",
        label: "Technical & domain capability",
        weight: 0.2,
        score: 4.2,
        rationale: "GovCloud pipeline modernization matches the cloud-migration capability.",
        citation: { section: "§C.4", page: 5 },
      },
      {
        key: "past_perf",
        label: "Past-performance relevance",
        weight: 0.15,
        score: 3.2,
        rationale: "One comparable pipeline effort; no Platform One past performance.",
        citation: null,
      },
      {
        key: "vehicle",
        label: "Contract-vehicle access",
        weight: 0.1,
        score: 4.0,
        rationale: "Open solicitation; no vehicle barrier.",
        citation: null,
      },
      {
        key: "set_aside",
        label: "Set-aside eligibility",
        weight: 0.1,
        score: 3.0,
        rationale: "Full & open — no set-aside leverage for Rackner.",
        citation: { section: "§K.2", page: 9 },
      },
      {
        key: "incumbent",
        label: "Incumbent advantage (inverse)",
        weight: 0.1,
        score: 4.5,
        rationale: "New requirement, no incumbent — level playing field.",
        citation: null,
      },
      {
        key: "pricing",
        label: "Pricing / size fit",
        weight: 0.1,
        score: 3.8,
        rationale: "$4–6M is inside the target band, at the smaller end.",
        citation: null,
      },
      {
        key: "time",
        label: "Time to respond / shape",
        weight: 0.1,
        score: 2.0,
        rationale: "12 days to closing is aggressive for a full technical volume.",
        citation: { section: "§L.1", page: 8 },
      },
    ],
    obligations: [
      {
        id: 1,
        text: "Submit technical volume within 12 days",
        obligation_type: "submission",
        time_bucket: "immediate",
        deadline_label: "Immediate · 12 days",
        verbatim_quote:
          "Proposals shall be submitted electronically no later than 5:00 PM CT on 21 August 2026.",
        citation: { section: "§L.1", page: 8 },
        verified: true,
      },
      {
        id: 2,
        text: "Deliver CI/CD pipeline IOC within 90 days of award",
        obligation_type: "performance",
        time_bucket: "30_days",
        deadline_label: "90 days after award",
        verbatim_quote:
          "The Contractor shall achieve initial operating capability of the modernized pipeline within 90 days of award.",
        citation: { section: "§C.4", page: 5 },
        verified: true,
      },
      {
        id: 3,
        text: "Staff must hold IAT Level II certifications",
        obligation_type: "certification",
        time_bucket: "at_award",
        deadline_label: "At award",
        verbatim_quote:
          "All personnel with privileged access shall possess IAT Level II certification at time of performance.",
        citation: { section: "§H.3", page: 7 },
        verified: false,
      },
    ],
  },
  "darpa-zt-baa-21": {
    opportunity_id: "darpa-zt-baa-21",
    score: 75,
    band: "pursue",
    verdict: "Pursue AOI-2 — short window, strong research fit",
    factors: [
      {
        key: "mission",
        label: "Strategic / mission alignment",
        weight: 0.15,
        score: 4.2,
        rationale: "Zero-trust research aligns with the plan's architecture capability.",
        citation: { section: "AOI-2", page: 3 },
      },
      {
        key: "technical",
        label: "Technical & domain capability",
        weight: 0.2,
        score: 4.4,
        rationale: "Zero-trust advisory is a named lifecycle capability.",
        citation: { section: "AOI-2", page: 3 },
      },
      {
        key: "past_perf",
        label: "Past-performance relevance",
        weight: 0.15,
        score: 3.5,
        rationale: "Research-style past performance is lighter than delivery work.",
        citation: null,
      },
      {
        key: "vehicle",
        label: "Contract-vehicle access",
        weight: 0.1,
        score: 4.0,
        rationale: "BAA is open to all responsible sources.",
        citation: { section: "§1.1", page: 1 },
      },
      {
        key: "set_aside",
        label: "Set-aside eligibility",
        weight: 0.1,
        score: 3.0,
        rationale: "No set-aside — evaluated on technical merit.",
        citation: null,
      },
      {
        key: "incumbent",
        label: "Incumbent advantage (inverse)",
        weight: 0.1,
        score: 4.5,
        rationale: "No incumbent for new research areas.",
        citation: null,
      },
      {
        key: "pricing",
        label: "Pricing / size fit",
        weight: 0.1,
        score: 3.5,
        rationale: "$2M per AOI is below the plan's target band but strategic.",
        citation: null,
      },
      {
        key: "time",
        label: "Time to respond / shape",
        weight: 0.1,
        score: 2.2,
        rationale: "AOI-2 abstract due in 9 days — very tight.",
        citation: { section: "AOI-2", page: 3 },
      },
    ],
    obligations: [
      {
        id: 1,
        text: "Submit AOI-2 abstract within 9 days",
        obligation_type: "submission",
        time_bucket: "immediate",
        deadline_label: "Immediate · 9 days",
        verbatim_quote: "Abstracts for Area of Interest 2 are due no later than 18 August 2026.",
        citation: { section: "AOI-2", page: 3 },
        verified: true,
      },
      {
        id: 2,
        text: "Full proposals by invitation only after abstract review",
        obligation_type: "submission",
        time_bucket: "30_days",
        deadline_label: "After abstract review",
        verbatim_quote:
          "Full proposals will be accepted by invitation following abstract evaluation.",
        citation: { section: "§4.2", page: 6 },
        verified: true,
      },
    ],
  },
  "va-helpdesk-2201": {
    opportunity_id: "va-helpdesk-2201",
    score: 38,
    band: "no_bid",
    verdict: "Likely no-bid — outside the plan's sweet spot",
    factors: [
      {
        key: "mission",
        label: "Strategic / mission alignment",
        weight: 0.15,
        score: 2.0,
        rationale: "VA help desk work is not a lifecycle target market.",
        citation: null,
      },
      {
        key: "technical",
        label: "Technical & domain capability",
        weight: 0.2,
        score: 2.5,
        rationale: "Tier 1–3 help desk is adjacent to, not core to, plan capabilities.",
        citation: { section: "§C.2", page: 4 },
      },
      {
        key: "past_perf",
        label: "Past-performance relevance",
        weight: 0.15,
        score: 1.8,
        rationale: "No comparable help-desk consolidation past performance.",
        citation: null,
      },
      {
        key: "vehicle",
        label: "Contract-vehicle access",
        weight: 0.1,
        score: 4.0,
        rationale: "Open solicitation; no vehicle barrier.",
        citation: null,
      },
      {
        key: "set_aside",
        label: "Set-aside eligibility",
        weight: 0.1,
        score: 2.0,
        rationale: "Full & open, sized for large integrators.",
        citation: { section: "§K.1", page: 10 },
      },
      {
        key: "incumbent",
        label: "Incumbent advantage (inverse)",
        weight: 0.1,
        score: 1.5,
        rationale: "BigIntegrator Inc. is deeply entrenched with a growing footprint.",
        citation: null,
      },
      {
        key: "pricing",
        label: "Pricing / size fit",
        weight: 0.1,
        score: 1.5,
        rationale: "$30M+ exceeds the plan's target award band.",
        citation: null,
      },
      {
        key: "time",
        label: "Time to respond / shape",
        weight: 0.1,
        score: 4.0,
        rationale: "40 days is comfortable — but the fit isn't there.",
        citation: { section: "§L.3", page: 22 },
      },
    ],
    obligations: [
      {
        id: 1,
        text: "Submit proposal within 40 days",
        obligation_type: "submission",
        time_bucket: "30_days",
        deadline_label: "40 days",
        verbatim_quote: "Proposals are due no later than 4:00 PM ET on 18 September 2026.",
        citation: { section: "§L.3", page: 22 },
        verified: true,
      },
      {
        id: 2,
        text: "Operate consolidated service desk across all VISNs",
        obligation_type: "performance",
        time_bucket: "ongoing",
        deadline_label: "Ongoing",
        verbatim_quote:
          "The Contractor shall operate a consolidated Tier 1 through Tier 3 service desk supporting all Veterans Integrated Service Networks.",
        citation: { section: "§C.1", page: 3 },
        verified: true,
      },
    ],
  },
};

export async function getAnalysis(id: string): Promise<Analysis> {
  const a = ANALYSES[id];
  if (!a) throw new Error(`404: no analysis for ${id}`);
  return delay(a, 1100); // the LLM "reads" the document
}

// ---------- source documents ----------

const DOCUMENTS: Record<string, SourceDocument> = {
  "disa-soc-0042": {
    opportunity_id: "disa-soc-0042",
    label: "Source solicitation · HC1084-26-R-0042",
    sections: [
      {
        ref: "C.3.1",
        heading: "SECTION C — DESCRIPTION / SPECIFICATIONS",
        page: 6,
        text: "C.3.1 Security Operations. The Contractor shall provide continuous 24x7x365 monitoring and respond to Severity-1 incidents within 15 minutes. The Contractor shall staff a Security Operations Center meeting DoD IL5 standards and maintain RMF documentation for all monitored enclaves.",
      },
      {
        ref: "F.2",
        heading: "SECTION F — DELIVERIES",
        page: 11,
        text: "F.2 Reporting. A monthly status report shall be delivered by the 5th business day of each month (CDRL A001). Reports shall include incident metrics, SLA compliance, and staffing status for the reporting period.",
      },
      {
        ref: "K.1",
        heading: "SECTION K — REPRESENTATIONS",
        page: 12,
        text: "K.1 Set-Aside. This procurement is a HUBZone set-aside. Offerors must be certified HUBZone small business concerns at the time of offer.",
      },
      {
        ref: "L.2",
        heading: "SECTION L — INSTRUCTIONS",
        page: 14,
        text: "L.2 Submission. Offers are due no later than 2:00 PM ET on 30 August 2026 through the SAM.gov submission portal. Late offers will not be considered.",
      },
      {
        ref: "M.4",
        heading: "SECTION M — EVALUATION",
        page: 19,
        text: "M.4 Certifications. Offeror must possess or obtain CMMC Level 2 certification prior to contract award. Failure to certify renders the offer ineligible for award.",
      },
    ],
  },
  "af-devsecops-0107": {
    opportunity_id: "af-devsecops-0107",
    label: "Source solicitation · FA8771-26-R-0107",
    sections: [
      {
        ref: "C.4",
        heading: "SECTION C — STATEMENT OF WORK",
        page: 5,
        text: "C.4 Pipeline Modernization. The Contractor shall achieve initial operating capability of the modernized pipeline within 90 days of award. All pipeline stages shall execute within the designated GovCloud environment.",
      },
      {
        ref: "H.3",
        heading: "SECTION H — SPECIAL REQUIREMENTS",
        page: 7,
        text: "H.3 Personnel. Contractor personnel supporting privileged functions shall meet DoD 8570 baseline requirements for their assigned roles.",
      },
      {
        ref: "L.1",
        heading: "SECTION L — INSTRUCTIONS",
        page: 8,
        text: "L.1 Submission. Proposals shall be submitted electronically no later than 5:00 PM CT on 21 August 2026. Volumes exceeding the page limits will not be evaluated.",
      },
    ],
  },
  "darpa-zt-baa-21": {
    opportunity_id: "darpa-zt-baa-21",
    label: "Source BAA · HR001126S0021",
    sections: [
      {
        ref: "1.1",
        heading: "PART 1 — OVERVIEW",
        page: 1,
        text: "1.1 Scope. This Broad Agency Announcement seeks revolutionary research in zero-trust architectures. Awards may take the form of procurement contracts, grants, or other transactions.",
      },
      {
        ref: "AOI-2",
        heading: "AREA OF INTEREST 2 — ZERO-TRUST ADVISORY",
        page: 3,
        text: "AOI-2. Abstracts for Area of Interest 2 are due no later than 18 August 2026. Proposers should describe novel approaches to continuous verification in contested environments.",
      },
      {
        ref: "4.2",
        heading: "PART 4 — APPLICATION PROCESS",
        page: 6,
        text: "4.2 Full Proposals. Full proposals will be accepted by invitation following abstract evaluation. Invited proposers will have 30 calendar days to submit.",
      },
    ],
  },
  "va-helpdesk-2201": {
    opportunity_id: "va-helpdesk-2201",
    label: "Source solicitation · 36C10B26R2201",
    sections: [
      {
        ref: "C.1",
        heading: "SECTION C — PERFORMANCE WORK STATEMENT",
        page: 3,
        text: "C.1 Scope. The Contractor shall operate a consolidated Tier 1 through Tier 3 service desk supporting all Veterans Integrated Service Networks. Service levels are defined in Attachment 2.",
      },
      {
        ref: "L.3",
        heading: "SECTION L — INSTRUCTIONS",
        page: 22,
        text: "L.3 Submission. Proposals are due no later than 4:00 PM ET on 18 September 2026. Submit via the VA acquisition portal only.",
      },
    ],
  },
};

export async function getSourceDocument(id: string): Promise<SourceDocument> {
  const d = DOCUMENTS[id];
  if (!d) throw new Error(`404: no source document for ${id}`);
  return delay(d, 400);
}

// ---------- spend history (USAspending.gov) ----------

const SPEND: Record<string, SpendSummary> = {
  "disa-soc-0042": {
    opportunity_id: "disa-soc-0042",
    years: [
      { fiscal_year: "FY22", amount: 1_600_000 },
      { fiscal_year: "FY23", amount: 2_100_000 },
      { fiscal_year: "FY24", amount: 2_700_000 },
      { fiscal_year: "FY25", amount: 3_300_000 },
    ],
    total_obligated: 9_700_000,
    incumbent: { name: "SmallCyber LLC", uei: "ABC123XYZ" },
    trend_pct: 24,
  },
  "af-devsecops-0107": {
    opportunity_id: "af-devsecops-0107",
    years: [],
    total_obligated: 0,
    incumbent: null,
    trend_pct: null,
  },
  "darpa-zt-baa-21": {
    opportunity_id: "darpa-zt-baa-21",
    years: [
      { fiscal_year: "FY24", amount: 1_200_000 },
      { fiscal_year: "FY25", amount: 1_900_000 },
    ],
    total_obligated: 3_100_000,
    incumbent: null,
    trend_pct: 58,
  },
  "va-helpdesk-2201": {
    opportunity_id: "va-helpdesk-2201",
    years: [
      { fiscal_year: "FY22", amount: 24_000_000 },
      { fiscal_year: "FY23", amount: 26_500_000 },
      { fiscal_year: "FY24", amount: 27_800_000 },
      { fiscal_year: "FY25", amount: 29_200_000 },
    ],
    total_obligated: 107_500_000,
    incumbent: { name: "BigIntegrator Inc.", uei: "QRS789TUV" },
    trend_pct: 7,
  },
};

export async function getSpend(id: string): Promise<SpendSummary> {
  const s = SPEND[id];
  if (!s) throw new Error(`404: no spend data for ${id}`);
  return delay(s, 500);
}

// ---------- contact discovery ----------

const CONTACTS: Record<string, ContactResult> = {
  "disa-soc-0042": {
    opportunity_id: "disa-soc-0042",
    name: "Janet Morales",
    title: "Contracting Officer",
    office: "DISA Acquisition Directorate",
    email: "janet.morales@disa.mil",
    confidence: 0.92,
    active_solicitation: true,
  },
  "af-devsecops-0107": {
    opportunity_id: "af-devsecops-0107",
    name: "David Chen",
    title: "Contracting Specialist",
    office: "AFLCMC / Platform One",
    email: "david.chen.3@us.af.mil",
    confidence: 0.74,
    active_solicitation: true,
  },
  "darpa-zt-baa-21": {
    opportunity_id: "darpa-zt-baa-21",
    name: "Dr. Priya Nair",
    title: "Program Manager",
    office: "DARPA Information Innovation Office",
    email: "priya.nair@darpa.mil",
    confidence: 0.88,
    active_solicitation: false,
  },
  "va-helpdesk-2201": {
    opportunity_id: "va-helpdesk-2201",
    name: "Robert Ellison",
    title: "Contracting Officer",
    office: "VA Technology Acquisition Center",
    email: "robert.ellison@va.gov",
    confidence: 0.81,
    active_solicitation: true,
  },
};

export async function getContact(id: string): Promise<ContactResult> {
  const c = CONTACTS[id];
  if (!c) throw new Error(`404: no contact for ${id}`);
  return delay(c, 700);
}

// ---------- chatbot ----------

const CHAT_RULES: Array<{ match: RegExp; opp?: string; answer: ChatAnswer }> = [
  {
    match: /disqualif|eligib|qualify|bar us|gate/i,
    opp: "disa-soc-0042",
    answer: {
      answer:
        "Two gates: (1) CMMC Level 2 is required at award — confirm your certification timeline; (2) it's a HUBZone set-aside, which Rackner qualifies for. No OCI flags detected.",
      citations: [
        { section: "§M.4", page: 19 },
        { section: "§K.1", page: 12 },
      ],
    },
  },
  {
    match: /deadline|due|close|when/i,
    opp: "disa-soc-0042",
    answer: {
      answer:
        "Offers are due 2:00 PM ET on 30 August 2026 through the SAM.gov submission portal — 21 days out. Late offers will not be considered.",
      citations: [{ section: "§L.2", page: 14 }],
    },
  },
  {
    match: /incumbent|competitor|smallcyber/i,
    opp: "disa-soc-0042",
    answer: {
      answer:
        "The incumbent is SmallCyber LLC (UEI ABC123XYZ), with $9.7M obligated on the expiring contract and spend growing ~24%/yr. Expect them to recompete; your HUBZone eligibility and SOC depth are the differentiators.",
      citations: [],
    },
  },
];

export async function askChat(id: string, question: string): Promise<ChatAnswer> {
  const rule = CHAT_RULES.find((r) => (!r.opp || r.opp === id) && r.match.test(question));
  if (rule) return delay(rule.answer, 900);
  const a = ANALYSES[id];
  return delay(
    {
      answer: a
        ? `Based on the analysis, this scores ${a.score}/100 (${a.verdict.toLowerCase()}). Ask about deadlines, eligibility gates, or the incumbent for cited specifics.`
        : "I can answer questions about deadlines, eligibility, obligations, and the incumbent for this opportunity.",
      citations: [],
    },
    900
  );
}
