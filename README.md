# Rackner Project — Contract Obligation Extractor

Rackner AI Innovation Fellowship · Team 1 (Aggrey, Kaliza, Remy)

Turn a dense government contract or solicitation PDF into a plain-English,
source-cited, deadline-aware **obligation register** a busy person can act on.

## Repo layout

This is a shared monorepo. Each role owns a top-level area:

| Path         | Owner            | What lives here                                            |
| ------------ | ---------------- | ---------------------------------------------------------- |
| `frontend/`  | Remy (Role 3)    | Next.js + TypeScript split-pane UI, SAM.gov integration    |
| `backend/`   | Aggrey (Role 2)  | Ingestion, segmentation, Postgres, FastAPI (`ingestion/`, `db/`, `api/`) |
| `data/samples/` | shared        | Real SAM.gov solicitation PDFs used for testing            |

> The frontend builds against a shared **`mock-obligations.json`** (locked in
> Week 3 with Role 1 + Aggrey) until Aggrey's real API lands in Week 8.

## Frontend — quick start

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

Stack: Next.js 16 (App Router) · TypeScript · Tailwind CSS · ESLint.

## Deployment

Auto-deploys to **Render** on every push to `main` (see `render.yaml`).
CI (`.github/workflows/ci.yml`) runs lint + build on every pull request.
