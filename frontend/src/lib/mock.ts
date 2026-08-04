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
  ChatMessage,
  ContactResult,
  LifecycleProfile,
  OpportunitySummary,
  Profile,
  SearchFilters,
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

/** Months from today until an ISO date. The real backend computes this
 *  server-side from USAspending's period_of_performance_current_end_date so
 *  the window filter can run against the whole dataset, not a page of it. */
function monthsUntil(iso: string): number {
  const then = new Date(`${iso}T00:00:00`).getTime();
  const now = Date.now();
  return Math.round((then - now) / (1000 * 60 * 60 * 24 * 30.44));
}

/** Solicitations carry no expiry — those three fields are recompete-only. */
const NO_EXPIRY = {
  expiry_date: null,
  months_to_expiry: null,
  current_award_value: null,
} as const;

const OPPORTUNITIES: OpportunitySummary[] = [
  {
    ...NO_EXPIRY,
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
    ...NO_EXPIRY,
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
    ...NO_EXPIRY,
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
    ...NO_EXPIRY,
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

  // --- recompete radar: existing awards from USAspending, not yet solicited ---
  // These have no solicitation number because no RFP exists yet. That's the
  // point: catch them 12–18 months out, while the requirement can still be
  // shaped, instead of reacting to a posting the incumbent already influenced.
  {
    id: "army-soc-w15p7t",
    title: "Army Enterprise SOC Operations (expiring)",
    agency: "Dept. of the Army",
    office: "PEO EIS",
    solicitation_number: null,
    naics: "541519",
    set_aside: null,
    kind: "expiring_award",
    description:
      "Current SOC operations award ends in FY27. Direct match to our SOC capability — recompete likely.",
    close_date: null,
    days_to_close: null,
    est_value: "$14M (current award)",
    incumbent: "Vantage Defense Systems",
    fit_score: 79,
    expiry_date: "2027-09-30",
    months_to_expiry: monthsUntil("2027-09-30"),
    current_award_value: 14_200_000,
  },
  {
    id: "navy-cloud-n6600",
    title: "Navy Cloud Hosting & Migration Support (expiring)",
    agency: "Dept. of the Navy",
    office: "NAVWAR",
    solicitation_number: null,
    naics: "541512",
    set_aside: "Small Business",
    kind: "expiring_award",
    description:
      "GovCloud hosting and migration support ending FY27. Small-business set-aside on the current award.",
    close_date: null,
    days_to_close: null,
    est_value: "$9M (current award)",
    incumbent: "Tidewater Cloud Partners",
    fit_score: 71,
    expiry_date: "2027-11-30",
    months_to_expiry: monthsUntil("2027-11-30"),
    current_award_value: 8_900_000,
  },
  {
    id: "disa-netops-hc1084",
    title: "DISA Network Operations Support (expiring)",
    agency: "Dept. of Defense",
    office: "DISA",
    solicitation_number: null,
    naics: "541519",
    set_aside: null,
    kind: "expiring_award",
    description:
      "Network operations and monitoring award ending FY27. Same customer as our SOC pursuit — warm relationship.",
    close_date: null,
    days_to_close: null,
    est_value: "$6M (current award)",
    incumbent: "Northgate Technical",
    fit_score: 68,
    expiry_date: "2027-08-31",
    months_to_expiry: monthsUntil("2027-08-31"),
    current_award_value: 6_400_000,
  },
  {
    id: "gsa-helpdesk-47qtca",
    title: "GSA Enterprise Service Desk (expiring)",
    agency: "General Services Administration",
    office: "FAS",
    solicitation_number: null,
    naics: "541513",
    set_aside: null,
    kind: "expiring_award",
    description:
      "Service desk award ending FY27. Large-business scope, low capability overlap — tracked, not targeted.",
    close_date: null,
    days_to_close: null,
    est_value: "$22M (current award)",
    incumbent: "BigIntegrator Inc.",
    fit_score: 34,
    expiry_date: "2027-10-31",
    months_to_expiry: monthsUntil("2027-10-31"),
    current_award_value: 21_800_000,
  },
  {
    id: "dhs-zerotrust-70rsat",
    title: "DHS Zero-Trust Implementation (expiring)",
    agency: "Dept. of Homeland Security",
    office: "CISA",
    solicitation_number: null,
    naics: "541512",
    set_aside: null,
    kind: "expiring_award",
    description:
      "Zero-trust rollout ending FY28. Strong capability match but still too early to shape.",
    close_date: null,
    days_to_close: null,
    est_value: "$11M (current award)",
    incumbent: "Beacon Federal",
    fit_score: 77,
    expiry_date: "2028-05-31",
    months_to_expiry: monthsUntil("2028-05-31"),
    current_award_value: 11_300_000,
  },
  {
    id: "af-cyberrange-fa8773",
    title: "Air Force Cyber Range Sustainment (expiring)",
    agency: "Dept. of the Air Force",
    office: "AFLCMC",
    solicitation_number: null,
    naics: "541519",
    set_aside: null,
    kind: "expiring_award",
    description:
      "Cyber range sustainment ending FY27. Good fit, but the shaping window has effectively closed.",
    close_date: null,
    days_to_close: null,
    est_value: "$5M (current award)",
    incumbent: "Redhorse Cyber",
    fit_score: 72,
    expiry_date: "2027-03-31",
    months_to_expiry: monthsUntil("2027-03-31"),
    current_award_value: 4_700_000,
  },
];

/** Mirrors what the backend does in SQL. Kept in one place so the mock and
 *  the real API can't drift on filter semantics. */
function applyFilters(
  list: OpportunitySummary[],
  filters: SearchFilters = {}
): OpportunitySummary[] {
  let out = list;

  if (filters.kinds?.length) {
    out = out.filter((o) => filters.kinds!.includes(o.kind));
  }

  if (filters.expiring_from !== undefined || filters.expiring_to !== undefined) {
    const lo = filters.expiring_from ?? Number.NEGATIVE_INFINITY;
    const hi = filters.expiring_to ?? Number.POSITIVE_INFINITY;
    // Anything without an expiry date is not a recompete — exclude it rather
    // than silently treating a missing date as "in range".
    out = out.filter(
      (o) => o.months_to_expiry !== null && o.months_to_expiry >= lo && o.months_to_expiry <= hi
    );
  }

  return out;
}

function matchesQuery(o: OpportunitySummary, terms: string[]): boolean {
  if (terms.length === 0) return true;
  const hay =
    `${o.title} ${o.agency} ${o.office ?? ""} ${o.naics ?? ""} ${o.set_aside ?? ""} ${o.incumbent ?? ""} ${o.description}`.toLowerCase();
  return terms.some((t) => hay.includes(t));
}

/** Expiring awards sort by soonest-expiring; everything else by fit. */
function sortForDisplay(list: OpportunitySummary[]): OpportunitySummary[] {
  return [...list].sort((a, b) => {
    if (a.months_to_expiry !== null && b.months_to_expiry !== null) {
      return a.months_to_expiry - b.months_to_expiry;
    }
    return (b.fit_score ?? 0) - (a.fit_score ?? 0);
  });
}

export async function searchOpportunities(
  query: string,
  filters: SearchFilters = {}
): Promise<OpportunitySummary[]> {
  const terms = query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter((t) => t.length > 2);

  const scoped = applyFilters(OPPORTUNITIES, filters);
  const hits = scoped.filter((o) => matchesQuery(o, terms));

  // A filter that legitimately matches nothing must return nothing — falling
  // back to "everything" here would quietly lie about the window.
  return delay(sortForDisplay(terms.length === 0 ? scoped : hits), 600);
}

export async function getSuggested(filters: SearchFilters = {}): Promise<OpportunitySummary[]> {
  const ranked = sortForDisplay(applyFilters(OPPORTUNITIES, filters));
  // No plan on file → nothing to score against.
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

/** An expiring award has no RFP yet, so there is nothing to cite and no
 *  obligations to extract. Fit is still scorable from the award's scope and
 *  the USAspending record — that's the whole point of looking this early.
 *  Factors carry null citations, which the UI renders without a link. */
function recompeteAnalysis(opp: OpportunitySummary): Analysis {
  const band = opp.fit_score! >= 70 ? "pursue" : opp.fit_score! >= 50 ? "conditional" : "no_bid";
  const months = opp.months_to_expiry ?? 0;
  const inWindow = months >= 12 && months <= 18;

  const f = (key: string, label: string, weight: number, score: number, rationale: string) => ({
    key,
    label,
    weight,
    score,
    rationale,
    citation: null,
  });

  return {
    opportunity_id: opp.id,
    score: opp.fit_score!,
    band,
    verdict: inWindow
      ? `In the capture window — ${months} months to expiry`
      : months < 12
        ? `Expires in ${months} months — likely too late to shape`
        : `Expires in ${months} months — track, revisit at 18 months`,
    factors: [
      f("mission", "Strategic / mission alignment", 0.15, opp.fit_score! >= 70 ? 4.3 : 2.4,
        `${opp.agency} is ${opp.fit_score! >= 70 ? "a named target market" : "outside the plan's target markets"}.`),
      f("technical", "Technical & domain capability", 0.2, opp.fit_score! >= 70 ? 4.5 : 2.6,
        "Scored from the current award's scope description on USAspending."),
      f("past_perf", "Past-performance relevance", 0.15, 3.6,
        "Comparable work in the lifecycle plan's past-performance section."),
      f("vehicle", "Contract-vehicle access", 0.1, 3.5,
        "Vehicle for the recompete is not yet announced."),
      f("set_aside", "Set-aside eligibility", 0.1, opp.set_aside ? 4.5 : 3.0,
        opp.set_aside
          ? `Current award is a ${opp.set_aside} set-aside — likely to carry forward.`
          : "Current award is unrestricted; set-aside status may change at recompete."),
      f("incumbent", "Incumbent advantage (inverse)", 0.1, 2.5,
        `${opp.incumbent ?? "The incumbent"} holds the expiring award — expect them to defend it.`),
      f("pricing", "Pricing / size fit", 0.1, 3.8,
        `Current award value ${opp.est_value ?? "unknown"} against the plan's target band.`),
      f("time", "Time to shape", 0.1, inWindow ? 4.6 : months < 12 ? 1.8 : 3.2,
        inWindow
          ? "Inside the 12–18 month window — time to meet the CO and shape requirements."
          : months < 12
            ? "Under 12 months; the requirement is probably already shaped."
            : "Over 18 months out; revisit once it enters the window."),
    ],
    obligations: [], // no solicitation posted yet — nothing to extract or cite
  };
}

export async function getAnalysis(id: string): Promise<Analysis> {
  const a = ANALYSES[id];
  if (a) return delay(a, 1100); // the LLM "reads" the document
  const opp = OPPORTUNITIES.find((o) => o.id === id);
  if (opp?.kind === "expiring_award") return delay(recompeteAnalysis(opp), 900);
  throw new Error(`404: no analysis for ${id}`);
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

/** For an expiring award the USAspending record IS the primary evidence —
 *  it's a real contract with real obligations to date. Derived from the
 *  current award value so the mock stays internally consistent. */
function recompeteSpend(opp: OpportunitySummary): SpendSummary {
  const total = opp.current_award_value ?? 0;
  const shares = [0.19, 0.23, 0.28, 0.3]; // ramping profile
  const years = ["FY22", "FY23", "FY24", "FY25"].map((fy, i) => ({
    fiscal_year: fy,
    amount: Math.round(total * shares[i]),
  }));
  return {
    opportunity_id: opp.id,
    years,
    total_obligated: total,
    incumbent: opp.incumbent ? { name: opp.incumbent, uei: "UEI on file" } : null,
    trend_pct: 16,
  };
}

export async function getSpend(id: string): Promise<SpendSummary> {
  const s = SPEND[id];
  if (s) return delay(s, 500);
  const opp = OPPORTUNITIES.find((o) => o.id === id);
  if (opp?.kind === "expiring_award") return delay(recompeteSpend(opp), 500);
  throw new Error(`404: no spend data for ${id}`);
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
  if (c) return delay(c, 700);
  const opp = OPPORTUNITIES.find((o) => o.id === id);
  if (opp?.kind === "expiring_award") {
    // No active solicitation → outreach IS appropriate here. This is exactly
    // the window the Procurement Integrity flag is telling you to use.
    return delay(
      {
        opportunity_id: opp.id,
        name: "Contracting officer on the current award",
        title: "Contracting Officer",
        office: `${opp.agency}${opp.office ? ` · ${opp.office}` : ""}`,
        email: "resolved from the award record on request",
        confidence: 0.6,
        active_solicitation: false,
      },
      700
    );
  }
  throw new Error(`404: no contact for ${id}`);
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
        {
          section: "§M.4",
          page: 19,
          // Exact substrings of DOCUMENTS["disa-soc-0042"] section text — the
          // same invariant the backend guarantees, so the highlight works in
          // mock mode too.
          verbatim_quote:
            "Offeror must possess or obtain CMMC Level 2 certification prior to contract award.",
          verified: true,
        },
        {
          section: "§K.1",
          page: 12,
          verbatim_quote: "This procurement is a HUBZone set-aside.",
          verified: true,
        },
      ],
    },
  },
  {
    match: /deadline|due|close|when/i,
    opp: "disa-soc-0042",
    answer: {
      answer:
        "Offers are due 2:00 PM ET on 30 August 2026 through the SAM.gov submission portal — 21 days out. Late offers will not be considered.",
      citations: [
        {
          section: "§L.2",
          page: 14,
          verbatim_quote:
            "Offers are due no later than 2:00 PM ET on 30 August 2026 through the SAM.gov submission portal.",
          verified: true,
        },
      ],
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

export async function askChat(
  id: string,
  question: string,
  history: ChatMessage[] = []
): Promise<ChatAnswer> {
  const rule = CHAT_RULES.find((r) => (!r.opp || r.opp === id) && r.match.test(question));
  if (rule) return delay(rule.answer, 900);

  // Follow-up resolution, mirroring the backend: a question that matches no
  // rule by itself ("what about the deadline for that?") retries against the
  // most recent user turns, so pronouns resolve in mock mode too.
  for (let i = history.length - 1; i >= 0; i--) {
    const turn = history[i];
    if (turn.role !== "user") continue;
    const followupRule = CHAT_RULES.find(
      (r) => (!r.opp || r.opp === id) && r.match.test(`${turn.text} ${question}`)
    );
    if (followupRule) return delay(followupRule.answer, 900);
  }

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
