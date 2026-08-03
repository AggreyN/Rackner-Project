# Rackner FDI — Frontend

Federal Document Intelligence & opportunity capture (post-pivot, 7/22 reframing).
Search live SAM.gov opportunities, score fit against Rackner's Opportunity
Lifecycle plan with cited evidence, follow the money on USAspending, and find
the contracting contact.

Next.js 16 · React 19 · TypeScript · Tailwind 4 · Playwright.

## Run it

```bash
npm install
npm run dev            # http://localhost:3000 — runs against the built-in mock
```

No backend or API keys needed: with `NEXT_PUBLIC_API_URL` unset, `lib/api.ts`
routes every call to the in-browser mock (`lib/mock.ts`). Point it at the
FastAPI backend to go live — no component changes:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Mock sign-in accepts any `@rackner.com` email + any password.

## The flow (Phase 1)

1. **Sign in** (`/login`) — JWT from `POST /auth/login`; bcrypt hashes server-side.
2. **Lifecycle plan on file** — chip in the top bar; the parsed "fit profile" powers scoring.
3. **Search / discover** (`/`) — SAM.gov search + suggested contracts ranked by fit.
4. **Analyze** (`/opportunity/[id]`) — compatibility donut (8 weighted CAP factors),
   obligations grouped by time/type with **verified citations**, click-to-cite highlight
   in the collapsible source pane.
5. **Follow the money** — USAspending spend history + incumbent.
6. **Find the contact** — discovered email w/ confidence + the Procurement Integrity flag.
7. **Ask the assistant** — per-opportunity chat, answers cited to the source.

## Architecture notes

- `src/lib/types.ts` — the **locked schema** (the team contract).
- `src/lib/api.ts` — every backend call + the expected FastAPI route list; the only
  file that talks to the network.
- `src/lib/mock.ts` — seeded demo data; quotes are exact substrings of the source
  sections so verification/highlighting behave like production.
- Cut in the pivot: role picker, PII pre-upload scan, 3-day retention, upload-first flow.

## Tests

```bash
npx playwright test        # desktop + tablet + mobile, against the mock on :3100
```

Covers: auth redirect/sign-in/out, suggested ranking + fit badges, search,
lifecycle profile modal, donut + 8 factors, obligations regrouping, click-to-cite
glow, pane collapse/toggle, spend panel, contact + integrity flag, chat citations.
