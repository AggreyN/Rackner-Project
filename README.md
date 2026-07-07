# Team Anvil — Federal Document Intelligence Layer

Rackner AI Innovation Fellowship · Kaliza (AI & Product) · Aggrey (Data & Backend) · Remy (Full Stack & Infra)

> One federal document, read once — every team gets the answers it needs.

Upload a federal contract or solicitation PDF, choose your role — Contracts,
Proposal & Capture, Program Management, Security & Compliance, or Leadership —
and get a plain-English, source-cited obligation register filtered for *your*
questions. See `APP_GUIDE.md` for the full product and security story.

## Repo layout

This is a shared monorepo. Each role owns a top-level area:

| Path            | Owner           | What lives here                                          |
| --------------- | --------------- | -------------------------------------------------------- |
| `frontend/`     | Remy (Role 3)   | Next.js split-pane workspace, SAM.gov intake, deploy/CI  |
| `backend/`      | Aggrey (Role 2) | Ingestion, pipeline, Postgres, FastAPI                   |
| `data/samples/` | shared          | Demo solicitation PDFs (incl. the seeded demo document)  |

Kaliza owns `backend/extraction/extractor.py` (called via the adapter — never
edited by others), the locked schema, and extraction/role-tagging quality.

## Frontend — quick start

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

No backend needed: with `NEXT_PUBLIC_API_URL` unset, `lib/api.ts` routes every
call to the built-in mock (`lib/mock.ts`), seeded from
`data/samples/TeamAnvil-Demo-Solicitation.pdf`. Point `NEXT_PUBLIC_API_URL` at
Aggrey's FastAPI to go live — no component changes needed.

Stack: Next.js 16 (App Router) · TypeScript · Tailwind CSS · Playwright · ESLint.

## Week-by-week checkpoints (Remy · Role 3)

Every Friday checkpoint is a git tag — `git checkout week-N` to see that week's app.

| Tag      | Due    | Deliverable                                                        |
| -------- | ------ | ------------------------------------------------------------------ |
| `week-2` | Jul 10 | Bundle merged; obligation register renders against the mock       |
| `week-3` | Jul 17 | Workspace polish: role switcher, group tabs, collapsible pane, responsive |
| `week-4` | Jul 24 | PII flow, upload errors/size limits/processing states, SAM.gov intake |
| `week-5` | Jul 31 | Status tracking + optimistic updates, CSV export, empty/loading/error states |
| `week-6` | Aug 7  | Infra hardening: security headers, auth flag, deployment docs      |
| `week-7` | Aug 14 | react-pdf span-level highlight — click an obligation, the sentence glows |
| `week-8` | Aug 21 | Deploy freeze: demo runbook, rollback plan, full Playwright suite  |
| `week-9` | Aug 28 | 🚀 Demo Day                                                        |

## Deployment

Auto-deploys to **AWS Amplify Hosting** on every push to `main` (see `amplify.yml`).
CI (`.github/workflows/ci.yml`) runs lint + build on every pull request.
Never demo against localhost — the deployed URL is the demo.
