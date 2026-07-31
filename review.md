# Week 2 Frontend — Code Review Prep (Remy)

Your cheat sheet for the Rackner engineering review. Everything here is about the
**frontend at the `week-2` checkpoint** — what each piece is, how it works, why it
was built this way, and the questions a reviewer is likely to ask.

---

## 1. What the app is (30-second pitch)

**Team Anvil — a federal document intelligence layer.** A user uploads one federal
contract/solicitation PDF, picks their **role** (Contracts, Proposal & Capture,
Program, Security, Leadership), and gets back a plain-English, source-cited
**obligation register** filtered for their role. One document is read once; every
team gets the answers relevant to them.

**Where week-2 sits:** this is the "gate check" milestone — the bundle is merged and
the register renders end-to-end against data. It's the **skeleton**: the two screens,
the locked data schema, and the backend seam all exist. Polish (responsive layout,
status tracking, CSV, auth, PDF highlighting) comes in later weeks.

---

## 2. Tech stack — what was used and why

| Tool | Version | Why it's here |
|---|---|---|
| **Next.js** | 16.2.9 (App Router, Turbopack) | React framework; App Router gives file-based routing + server/client component split. Deploys cleanly to AWS Amplify. |
| **React** | 19.2.4 | UI library. Uses the new `use()` hook for unwrapping async route params. |
| **TypeScript** | 5.x | Type safety end-to-end; the data schema (`lib/types.ts`) is enforced by the compiler. |
| **Tailwind CSS** | v4 (via `@tailwindcss/postcss`) | Utility-first styling. v4 is config-less — no `tailwind.config.js`. Colors are passed as arbitrary values like `bg-[#16324f]`. |
| **Geist / Geist Mono** | via `next/font/google` | Fonts, self-hosted at build time by Next. |
| **@anthropic-ai/sdk** | 0.110.0 | Present in deps (Claude is the backend's engine); not called from the frontend. |
| **Playwright** | 1.61.1 | E2E test runner. At week-2 it's the scaffold default; the real UI test suite lands week-3. |
| **ESLint** | 9 + `eslint-config-next` | Linting; runs in CI on every PR. |

**Deliberately NOT used:** no Redux/Zustand/state library (plain React hooks are
enough), no component library like MUI/shadcn (hand-rolled flat components — the
design is intentionally minimal government-tool aesthetic), no data-fetching library
like React Query (the API surface is small enough for plain `fetch`).

---

## 3. Folder structure (frontend only)

```
frontend/
├── src/
│   ├── app/                          # Next.js App Router — routes are folders
│   │   ├── layout.tsx                # root layout: <html>, fonts, metadata (SERVER component)
│   │   ├── globals.css               # Tailwind import + base styles
│   │   ├── page.tsx                  # "/"  → landing (upload + role picker)
│   │   └── workspace/[docId]/
│   │       └── page.tsx              # "/workspace/123?role=security" → the split-pane workspace
│   ├── components/                   # all presentational/UI pieces (client components)
│   │   ├── UploadZone.tsx            # drag-drop upload + orchestrates the scan→PII→upload flow
│   │   ├── PiiModal.tsx              # "sensitive info detected" confirmation dialog
│   │   ├── RolePicker.tsx            # the 5 role cards
│   │   ├── ObligationList.tsx        # left pane: grouped register + group-by tabs
│   │   ├── ObligationCard.tsx        # one obligation (plain English + evidence + status)
│   │   └── DocumentPane.tsx          # right pane: the source PDF (collapsible iframe)
│   └── lib/                          # non-UI logic
│       ├── types.ts                  # THE LOCKED SCHEMA — shared shape of every object
│       ├── api.ts                    # the ONLY file that talks to the backend
│       ├── mock.ts                   # in-browser fake backend (used when no API URL is set)
│       └── theme.ts                  # design tokens (navy/white color constants)
└── public/samples/
    └── TeamAnvil-Demo-Solicitation.pdf   # seeded demo doc the mock serves
```

**The one rule to remember:** the codebase has clean layers. Components render;
`lib/api.ts` is the single doorway to the backend; `lib/types.ts` is the single
source of truth for data shapes. Change a route or a field in one place and the whole
app follows.

---

## 4. The two screens & how they flow

### Screen A — Landing (`app/page.tsx`)
A client component. On mount it fetches the role list (`getRoles()`). It holds three
pieces of state: `roles`, the selected `role`, and the uploaded `docId`. When **both**
a doc and a role exist, a `useEffect` routes the user to
`/workspace/{docId}?role={role}`.

**Upload flow (the security choreography), lives in `UploadZone.tsx`:**
1. User drops/selects a PDF.
2. `scanDocument(file)` → backend scans for PII **before storing anything**.
3. If PII is found → show `PiiModal`. The file is **not uploaded** until the user
   clicks "I understand — upload anyway" (explicit consent is the security point).
4. On confirm (or if no PII) → `uploadDocument(file, acknowledged)` → returns a
   `docId` → landing routes into the workspace.

`busy`/`error` strings drive the small status text under the drop zone.

### Screen B — Workspace (`app/workspace/[docId]/page.tsx`)
The split-pane view (modeled on Claude's dual view): **register on the left, source
PDF on the right.**

- Reads `docId` from the URL path and `role` from the `?role=` query.
- Fetches the document metadata, the role list, and the obligations
  (`getObligations(docId, role, groupBy)`).
- **Role switcher** (the `<select>`) changes which role filters the register.
- **`groupBy`** state (`time` / `category` / `type`) controls how obligations are
  grouped — passed down to `ObligationList`.
- **`citePage`** state is the link between the two panes: clicking "View in document
  → p.N" on a card sets `citePage`, which tells `DocumentPane` to jump the PDF to
  that page.
- **`collapsed`** state hides/shows the document pane.

**`ObligationList`** groups the obligations and renders a section per group with an
`ObligationCard` for each. **`ObligationCard`** shows the plain-English obligation,
its evidence row (deadline, party, type, confidence, verified/⚠ badge), the verbatim
quote, and the "View in document" citation link. It also owns a local status chip
(open → in-review → done) with an optimistic update.

**`DocumentPane`** (week-2 version) renders the PDF in a plain `<iframe>`. Citation
clicks append `#page=N` to the URL; a `key={src}` forces the iframe to honor re-jumps.

---

## 5. The three ideas a reviewer should walk away understanding

### (a) The single backend seam — `lib/api.ts`
Every network call the frontend makes lives in this one file: `scanDocument`,
`uploadDocument`, `getDocument`, `documentPdfUrl`, `getRoles`, `getObligations`,
`updateObligationStatus`. Components never call `fetch` directly. **Benefit:** the
backend can change a route or the base URL and only this file changes.

### (b) The mock fallback — parallel work without a backend
`api.ts` reads `process.env.NEXT_PUBLIC_API_URL`. If it's **unset**, every function
routes to `lib/mock.ts` — an in-browser fake backend with 19 hand-authored
obligations, the 5 roles, a filename-based PII "scan," and a simulated processing
delay. If it's **set**, the same functions hit the real FastAPI backend.

**Why it matters:** it let the frontend be built and demoed with zero backend running
— the exact same trick the backend team uses (their extractor falls back to a mock
when there's no Anthropic API key). It's how three people worked in parallel without
blocking each other. To go live: set one environment variable, no component changes.

### (c) The locked schema — `lib/types.ts`
One TypeScript file defines every shape the app passes around: `Obligation`,
`ObligationGroups`, `RoleInfo`, `PiiFinding`, `ScanResult`, `DocumentMeta`. This is
the **contract** between frontend and backend — the backend's JSON must match these
types. Because it's TypeScript, if the schema changes, the compiler points at every
component that needs updating.

---

## 6. Design system

Flat, navy-and-white, "serious government tool, not an AI demo." Tokens in
`lib/theme.ts` (also applied inline as Tailwind arbitrary values):

- Navy `#16324f` (primary), navy-dark `#0f2438` (hover), muted `#51606f` (secondary text)
- Hairline borders `#d7dee6`, page wash `#f5f7f9`, white surfaces
- Verified green `#1e7a46`, unverified amber `#9a6a1e` (used sparingly)
- **No gradients, no shadows-as-decoration, no glassmorphism.** Hairline borders only.

---

## 7. Next.js 16 specifics worth being able to explain

These are the "why is this line weird" spots a reviewer might flag:

- **`"use client"`** at the top of interactive components — Next 16 components are
  server components by default; anything using hooks/state/events must opt into the
  client. `layout.tsx` has no directive → it's a server component.
- **Async route params:** in Next 16, `params` is a **Promise**. The workspace
  unwraps it with React's `use(params)` hook — that's why the signature is
  `params: Promise<{ docId: string }>`.
- **Suspense boundary:** `useSearchParams()` requires a `<Suspense>` wrapper to build
  as a static page — that's why the workspace splits into `Workspace` (wrapper) and
  `WorkspaceInner` (the real component).
- **`next/link`** instead of `<a>` for internal navigation (client-side routing +
  a lint rule enforces it).

---

## 8. Known limitations at week-2 (be honest about these)

These are **intentional** — they're on the roadmap for later weeks, not oversights:

| Limitation | Fixed in |
|---|---|
| **PDF opens a "save/download" dialog on some browsers** — the iframe hands the PDF to the browser's native viewer, which downloads it if the browser is set to. | Week 7 (react-pdf renders on a canvas — no download) |
| Not responsive — fixed 46% left pane, no mobile layout | Week 3 |
| Status tracking is per-card local state, not persisted; no live counts | Week 5 |
| No CSV export | Week 5 |
| No auth | Week 6 |
| No real Playwright suite yet (scaffold config only) | Week 3 |
| Upload has no size/type guardrails beyond `accept="application/pdf"` | Week 4 |
| Citation jump is page-level (`#page=N`), not the exact sentence | Week 7 (span highlight) |

---

## 9. Questions reviewers may ask — and your answers

**"Why no state management library?"**
The app has two screens and a handful of state values. Plain React hooks (`useState`,
`useEffect`, `useCallback`) are sufficient; adding Redux/Zustand would be
over-engineering for this surface.

**"Why plain `fetch` and not React Query / SWR?"**
Small, well-defined API surface (7 calls, all in one file). A caching layer isn't
justified yet. If we needed background refetching or cache invalidation later, `api.ts`
is the single place to add it.

**"How does the frontend work without a backend running?"**
`lib/api.ts` falls back to `lib/mock.ts` when `NEXT_PUBLIC_API_URL` is unset. Same
function signatures, canned data. Setting the env var flips every call to the real
backend with no component changes.

**"How do you keep the frontend and backend schemas in sync?"**
`lib/types.ts` is the single source of truth. The backend returns JSON matching these
types; TypeScript enforces our side. It's a documented contract both teams code to.

**"Isn't the mock hiding integration bugs?"**
Yes, that's the real risk — the mock is a stand-in, so schema drift between it and the
real API won't show until we point at the backend. That's exactly what the
`main-prototype` integration test is for.

**"Why is the whole PDF in an iframe?"**
It's the v1 viewer — zero dependencies, gets us a working split-pane immediately. The
tradeoff is the browser-download behavior and page-level (not sentence-level)
citations. Week 7 swaps in react-pdf for canvas rendering + span highlighting, and
that swap touches **only `DocumentPane.tsx`** because of the clean seam.

**"Where does styling live — is there a config?"**
Tailwind v4 is config-less. Colors are arbitrary values inline; the shared tokens are
documented in `lib/theme.ts`. No `tailwind.config.js` to maintain.

**"What's the security story on the frontend?"**
The upload flow scans for PII *before* storing and requires explicit user consent via
the modal. The frontend orchestrates that flow, but the actual PII detection,
storage, and 3-day retention are the backend's job.

---

## 10. How to run it

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000 — runs against the built-in mock

# to run against the real backend instead:
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

No backend and no API keys required for the mock path — a reviewer can clone, install,
and click through the whole flow immediately.

---

*Scope note: this covers the frontend only. The backend (ingestion, Claude extraction,
verification, Postgres, retention, auth) is Aggrey's and Kaliza's — the frontend
consumes it through the `lib/api.ts` contract described above.*
