// Thin API client — every backend call lives here, nowhere else.
// This file IS the frontend↔backend contract for Rackner FDI. The FastAPI
// backend (Aggrey) implements these routes; the analysis payloads (Kaliza's
// scoring + obligations JSON) match lib/types.ts exactly.
//
// Expected backend routes (all JSON unless noted):
//   POST /auth/login                          {email, password} → {access_token}
//   GET  /profile                             → Profile (user + lifecycle plan)
//   POST /profile/lifecycle   (multipart PDF) → LifecycleProfile
//   GET  /opportunities/search?q=&kinds=&expiring_from=&expiring_to=
//                                             → OpportunitySummary[]   (SAM.gov, server-side key)
//   GET  /opportunities/suggested?kinds=&expiring_from=&expiring_to=
//                                             → OpportunitySummary[]   (ranked vs lifecycle plan)
//
//   Recompete radar: `kinds=expiring_award` + expiring_from/to (months) returns
//   EXISTING awards from USAspending whose period of performance ends inside
//   that window — not SAM.gov notices. 12–18 months is the capture sweet spot.
//   GET  /opportunities/{id}                  → OpportunitySummary
//   GET  /opportunities/{id}/analysis         → Analysis               (gov-safe LLM, cited)
//   GET  /opportunities/{id}/document         → SourceDocument         (parsed text w/ sections)
//   GET  /opportunities/{id}/spend            → SpendSummary           (USAspending.gov)
//   GET  /opportunities/{id}/contact          → ContactResult          (email discovery + verifier)
//   POST /opportunities/{id}/chat             {question} → ChatAnswer
//
// When NEXT_PUBLIC_API_URL is unset, every call routes to the in-browser
// mock (lib/mock.ts) so the UI runs with no backend — same seam pattern the
// team has used since week 2.

import { getToken } from "./auth";
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
import * as mock from "./mock";

const BASE = process.env.NEXT_PUBLIC_API_URL;
const USE_MOCK = !BASE;

function headers(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

// ---------- auth ----------

export async function login(email: string, password: string): Promise<{ access_token: string }> {
  if (USE_MOCK) return mock.login(email, password);
  return json(
    await fetch(`${BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    })
  );
}

// ---------- profile / lifecycle plan ----------

export async function getProfile(email: string): Promise<Profile> {
  if (USE_MOCK) return mock.getProfile(email);
  return json(await fetch(`${BASE}/profile`, { headers: headers() }));
}

export async function uploadLifecyclePlan(file: File): Promise<LifecycleProfile> {
  if (USE_MOCK) return mock.uploadLifecyclePlan(file);
  const form = new FormData();
  form.append("file", file);
  return json(
    await fetch(`${BASE}/profile/lifecycle`, { method: "POST", headers: headers(), body: form })
  );
}

// ---------- opportunities ----------

/** Serializes SearchFilters into the query params the backend expects.
 *  Filtering MUST happen server-side — the recompete radar queries the whole
 *  USAspending award set, which can't be paged into the browser. */
function filterParams(filters: SearchFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.expiring_from !== undefined) {
    params.set("expiring_from", String(filters.expiring_from));
  }
  if (filters.expiring_to !== undefined) {
    params.set("expiring_to", String(filters.expiring_to));
  }
  if (filters.kinds?.length) params.set("kinds", filters.kinds.join(","));
  return params;
}

export async function searchOpportunities(
  query: string,
  filters: SearchFilters = {}
): Promise<OpportunitySummary[]> {
  if (USE_MOCK) return mock.searchOpportunities(query, filters);
  const params = filterParams(filters);
  params.set("q", query);
  return json(await fetch(`${BASE}/opportunities/search?${params}`, { headers: headers() }));
}

export async function getSuggested(filters: SearchFilters = {}): Promise<OpportunitySummary[]> {
  if (USE_MOCK) return mock.getSuggested(filters);
  const params = filterParams(filters);
  const qs = params.toString();
  return json(
    await fetch(`${BASE}/opportunities/suggested${qs ? `?${qs}` : ""}`, { headers: headers() })
  );
}

export async function getOpportunity(id: string): Promise<OpportunitySummary> {
  if (USE_MOCK) return mock.getOpportunity(id);
  return json(
    await fetch(`${BASE}/opportunities/${encodeURIComponent(id)}`, { headers: headers() })
  );
}

// ---------- analysis / document / spend / contact ----------

export async function getAnalysis(id: string): Promise<Analysis> {
  if (USE_MOCK) return mock.getAnalysis(id);
  // First-time generation on a big document runs server-side for a while;
  // the backend answers 503 + Retry-After until the cached row exists.
  // Poll through those so the caller's loading state simply persists —
  // the user sees the skeleton, not an error, and lands on the analysis.
  const url = `${BASE}/opportunities/${encodeURIComponent(id)}/analysis`;
  const deadline = Date.now() + 5 * 60 * 1000;
  for (;;) {
    const res = await fetch(url, { headers: headers() });
    if (res.status !== 503 || Date.now() >= deadline) return json(res);
    const retryAfter = Number(res.headers.get("retry-after")) || 15;
    await new Promise((r) => setTimeout(r, retryAfter * 1000));
  }
}

export async function getSourceDocument(id: string): Promise<SourceDocument> {
  if (USE_MOCK) return mock.getSourceDocument(id);
  return json(
    await fetch(`${BASE}/opportunities/${encodeURIComponent(id)}/document`, { headers: headers() })
  );
}

export async function getSpend(id: string): Promise<SpendSummary> {
  if (USE_MOCK) return mock.getSpend(id);
  return json(
    await fetch(`${BASE}/opportunities/${encodeURIComponent(id)}/spend`, { headers: headers() })
  );
}

export async function getContact(id: string): Promise<ContactResult> {
  if (USE_MOCK) return mock.getContact(id);
  return json(
    await fetch(`${BASE}/opportunities/${encodeURIComponent(id)}/contact`, { headers: headers() })
  );
}

// ---------- chatbot ----------

export async function askChat(
  id: string,
  question: string,
  history: ChatMessage[] = []
): Promise<ChatAnswer> {
  if (USE_MOCK) return mock.askChat(id, question, history);
  return json(
    await fetch(`${BASE}/opportunities/${encodeURIComponent(id)}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers() },
      // Prior turns let the backend resolve follow-ups ("the deadline for
      // THAT"). Citations are display state — send role/text only. The
      // backend caps length server-side, so the whole transcript is fine.
      body: JSON.stringify({
        question,
        history: history.map(({ role, text }) => ({ role, text })),
      }),
    })
  );
}
