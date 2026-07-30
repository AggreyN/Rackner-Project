# Frontend Infrastructure — Code Review Guide

Team Anvil — Federal Document Intelligence (Next.js frontend)

This document explains how the frontend is built and why, aimed at an engineer
reviewing the code. It focuses on architecture, key patterns, and the test
suite rather than a feature-by-feature tour.

---

## 1. Tech stack at a glance

| Concern | Choice |
|---|---|
| Framework | **Next.js (App Router)**, React 19, Turbopack |
| Language | TypeScript (strict), `tsc --noEmit` in CI |
| Styling | Tailwind-style utility classes, flat navy/white design system |
| PDF rendering | Native browser viewer via `<iframe>` + `#page=N` jumps (react-pdf span-highlight is a documented later upgrade) |
| E2E testing | **Playwright** across desktop / tablet / mobile |
| Hosting | AWS Amplify (monorepo, `appRoot: frontend`) |
| Backend seam | Env-gated: in-browser mock ↔ real extraction API |

Run locally: `cd frontend && npm run dev` → http://localhost:3000
Type check: `npm run typecheck` · Lint: `npm run lint` · E2E: `npm run test:e2e`

---

## 2. Directory layout

```
frontend/src/
  app/                         # Next.js App Router (routes = folders)
    page.tsx                   # "/"  — intake: upload + SAM.gov + role picker
    workspace/[docId]/page.tsx # "/workspace/:id" — the obligation register + doc pane
    api/sam/search/route.ts    # server route — SAM.gov search proxy
    api/sam/fetch/route.ts     # server route — SAM.gov attachment proxy
    globals.css, layout.tsx
  components/                  # presentational + interactive building blocks
    UploadZone, SamIntake, RolePicker, PiiModal,
    ObligationList, ObligationCard, DocumentPane
  hooks/
    useDocumentIntake.ts       # the intake pipeline (validate→scan→PII→upload→poll)
  lib/
    api.ts                     # THE single backend boundary
    mock.ts                    # in-browser mock backend (the "seam")
    types.ts                   # shared schema / contract
    csv.ts                     # register → CSV export
    theme.ts
  tests/                       # Playwright specs (see §8)
```

**Mental model:** two routed screens (`/` and `/workspace/:id`); everything else
is a component composed into those two. All backend access funnels through
`lib/api.ts`.

---

## 3. The mock seam — the most important design decision

**`lib/api.ts` is the only file that talks to a backend.** No component calls
`fetch` directly. The client decides at module load whether to hit a real API or
an in-browser mock:

```ts
const BASE = process.env.NEXT_PUBLIC_API_URL;
const USE_MOCK = !BASE;                       // unset URL → mock mode
export async function getObligations(...) {
  if (USE_MOCK) return mock.getObligations(...);
  return json(await fetch(`${BASE}/obligations?...`));
}
```

- **Unset `NEXT_PUBLIC_API_URL` → mock** (`lib/mock.ts`): the entire UI runs with
  seeded data, no backend, no network. This is how the app demos and how the
  Playwright suite runs deterministically.
- **Set `NEXT_PUBLIC_API_URL` → real backend**: every call switches over with
  **zero component changes**.

**Why it matters for review:**
- The UI was built against a **frozen schema** (`lib/types.ts`) shared by mock
  and real backend, so the real API drops in without touching components.
- `lib/mock.ts` is a faithful twin of the backend's own mock-fallback path —
  it simulates the async lifecycle (processing delay, polling, status
  transitions) so behavior matches production, not just shapes.
- **Trade-off to name:** in mock mode the "analysis" is *seeded*, not live. The
  obligations are hand-authored but each quotes the demo PDF verbatim with the
  correct page number, so citation/verification logic exercises the real code
  path. Extraction accuracy is a backend concern, out of scope for this repo.

---

## 4. The schema contract (`lib/types.ts`)

A single source of truth for the shapes crossing the boundary — `Obligation`,
`DocumentMeta`, `RoleInfo`, grouping/label maps. Both the mock and the eventual
real backend must satisfy these types. Reviewer takeaways:

- Obligations carry `verbatim_quote`, `page`, `confidence`, and a `verified`
  flag — the data model is built for **traceability**, not just display.
- `verified: false` is a first-class state (a deliberately unverified seed
  exists to exercise the "model hallucinated a clause" path).

---

## 5. Async document lifecycle (`hooks/useDocumentIntake.ts`)

Document intake is a multi-step pipeline, encapsulated in one hook so both the
drag-and-drop path (`UploadZone`) and the SAM.gov path (`SamIntake`) reuse
identical logic:

```
validate (size/type) → scan for PII → [PiiModal ack] → upload → poll status → ready
```

- **Polling, not assumed-sync:** after upload the client polls document status
  until `ready`, handling `processing` / `failed` explicitly (spinners, retry).
- **Single `onFile` entry point:** a file dropped in the browser and a PDF pulled
  from SAM.gov flow through the exact same handler — no duplicated logic.

---

## 6. Server-side proxy pattern (SAM.gov)

The SAM.gov integration is split across two **server routes** so the shared API
key never reaches the browser:

- `app/api/sam/search/route.ts` — proxies the opportunity search. Reads
  `process.env.SAM_API_KEY` **server-side**, caches results per day+query (the
  public key allows ~10 req/day), and returns clearly-marked sample results when
  no key is set so the UI works everywhere.
- `app/api/sam/fetch/route.ts` — downloads an attachment server-side and streams
  it back. Appends the key to the outbound `sam.gov` URL only; the key is never
  returned to the client.

**Security properties a reviewer should verify:**
- Key is `SAM_API_KEY`, **not** `NEXT_PUBLIC_*` → server-only, never bundled.
- The fetch proxy enforces an **allowlist** (`https://*.sam.gov` only) so it
  can't be used as an open proxy.
- Error responses don't echo the key.

---

## 7. State management & data integrity

- **One source of truth per concern.** Citation target (`cite`) and document
  state live in the workspace page and flow one-directionally into child
  components — no prop-drilling of mutable state, no duplicated stores.
- **Optimistic updates with rollback.** Obligation status changes apply
  instantly in the UI and roll back if the server call fails
  (`ObligationList` + status overrides). The register stays responsive without
  blocking on the network.
- **Pure, testable core logic.** Non-trivial algorithms (e.g. CSV serialization
  in `lib/csv.ts`) are pure functions with no React/DOM deps, so they're unit-
  testable in isolation.
- **Explicit UI states.** Skeleton / empty / error-with-retry are first-class,
  not afterthoughts — the register renders sensibly at every stage of loading.

---

## 8. Playwright test suite (the part reviewers ask about)

### What it is
End-to-end tests that launch a **real browser**, load the actual app, and drive
full user flows (upload → pick role → open workspace → work the register →
export). Config: `frontend/playwright.config.ts`.

### How it's configured
```ts
projects: [
  { name: "desktop", use: { ...devices["Desktop Chrome"] } },
  { name: "tablet",  use: { ...devices["iPad Mini"] } },
  { name: "mobile",  use: { ...devices["iPhone 13"] } },
],
webServer: { command: "npm run dev -- --port 3100", url: "http://localhost:3100",
             reuseExistingServer: !process.env.CI },
use: { baseURL: "http://localhost:3100", trace: "on-first-retry" },
```

Key decisions and *why they matter*:

- **Same specs, three device profiles.** Every test runs on desktop, tablet, and
  mobile viewports. The layout genuinely changes per screen (the split-pane
  register/document view collapses to a toggle on mobile, headers stick
  differently), so a desktop-only test would pass while mobile is broken. One
  test file → three runs; this is why the suite reports ~40+ passing tests from
  ~17 scenarios.
- **Runs against the mock-backed app.** No `NEXT_PUBLIC_API_URL` → seeded data,
  no live backend, no network flake. Deterministic, so it's safe to gate CI on.
- **Isolated port (3100).** Its own dev server so it never collides with a
  running dev instance on 3000; auto-starts and reuses locally.
- **CI hardening.** On CI: `retries: 2`, `forbidOnly` (a stray `test.only`
  fails the build), `workers: 1` for stability, and a **trace on first retry**
  (a replayable timeline for debugging intermittent failures).

### Test files
| File | Covers |
|---|---|
| `tests/app.spec.ts` | Core app — landing, workspace nav, register/document panes |
| `tests/intake.spec.ts` | Upload → scan → PII → process flow |
| `tests/register.spec.ts` | Obligation register — grouping, status, counts |

Run: `npm run test:e2e` (produces an HTML report).

### Honest scope caveat
The suite proves the **UI behaves correctly on every device against known data**
— it does **not** assert on real extraction accuracy (that's a backend concern,
and the backend isn't wired in mock mode). Framing this upfront in the review
reads as rigor.

---

## 9. Build & deploy (Amplify)

- Monorepo config: `amplify.yml` with `appRoot: frontend`; build runs
  `npm ci` → `npm run build`, artifacts from `.next`, with `node_modules` and
  `.next/cache` cached for faster rebuilds.
- **Secrets:** `SAM_API_KEY` (and later `NEXT_PUBLIC_API_URL`) are set in the
  **Amplify Console → Environment variables**, never committed. `.env` is
  gitignored. Because Amplify's console env vars are build-time by default, the
  build injects the key into a runtime `.env.production` so the server routes can
  read it at request time.
- CI runs typecheck; security headers and a deployment runbook accompany the
  hosting config.

---

## 10. Things a reviewer should probe (self-flagged)

- **Mock-first velocity vs. real integration.** Building against a rich mock let
  the full UI ship before the backend existed; the cost is that live analysis is
  pending the real API (`NEXT_PUBLIC_API_URL`). The seam makes that swap a
  one-line env change.
- **In-memory mock state** resets on reload — intentional for demo/dev; real
  persistence is the backend's job.
- **Client-side matching / rendering** (citations, CSV) keeps features working
  today and stays correct once real data arrives, since quotes are exact
  substrings of the source.
- **Single API boundary** is a strength to point at: change the backend URL or a
  route once and the whole app follows.

---

### Quick reviewer checklist
- [ ] Backend calls only in `lib/api.ts`? (grep for stray `fetch(` in components)
- [ ] `SAM_API_KEY` never `NEXT_PUBLIC_`? never in client bundle? (`grep -r SAM_API_KEY .next/static`)
- [ ] `.env` gitignored and untracked?
- [ ] Playwright green across all three device projects?
- [ ] Types in `lib/types.ts` are the single contract for mock + real backend?
