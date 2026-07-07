# Team Anvil — Federal Document Intelligence Layer

> One federal document, read once — every team gets the answers it needs.
> Rackner AI Innovation Fellowship · Kaliza (AI & Product) · Aggrey (Data & Backend) · Remy (Full Stack & Infra)

**Commit this file to the `main` branch as `APP_GUIDE.md`.**

## What the app does

Upload a federal contract or solicitation PDF. Choose your role — Contracts, Proposal & Capture, Program Management, Security & Compliance, or Leadership. The app reads the document once and shows you a plain-English register of everything the company is on the hook for, filtered and ranked for *your* role, with every item citing the exact clause and page it came from. Obligations can be grouped by time (immediate / 30 days / quarterly / ongoing), by category (legal, reporting, security, deliverable, financial), or by type — and tracked open → in-review → done.

## Using the app

1. **Upload** — drag a PDF onto the landing page. The file is first scanned for sensitive information (SSNs, emails, phone numbers, DOBs, card numbers). If anything is found you'll get a popup — *"Sensitive information detected — are you sure you want to upload?"* — and nothing is stored unless you confirm.
2. **Pick your role** — each card shows the question that team asks of a document. You can switch roles anytime in the workspace header.
3. **Work the register** — obligations on the left; the source document on the right (collapsible). Click **"View in document → p.N"** on any obligation to jump the PDF to the cited page. Items not relevant to your role are dimmed, never hidden.
4. **Track** — click an obligation's status chip to cycle open → in-review → done.

## Running it locally

**Backend** (from the backend folder, venv active):
```bash
pip install -r requirements.txt          # includes the additions
cp .env.example .env                     # set DATABASE_URL, ANTHROPIC_API_KEY
uvicorn api.main:app --reload            # http://localhost:8000/docs
```

**Frontend** (from `frontend/`):
```bash
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev   # http://localhost:3000
```

No Anthropic API key? The extractor adapter falls back to a clearly-marked low-confidence mock so the full UI still works — useful for frontend development.

## Security measures (implemented)

| Measure | How it works | Where |
|---|---|---|
| PII pre-upload detection | File is scanned server-side *before* storage; user must explicitly confirm via popup; acknowledgment is recorded | `core/pii.py`, `PiiModal.tsx` |
| 3-day retention | Every document gets `expires_at = upload + 3 days`; hard-deleted (file + DB rows) on startup, hourly, and on access | `core/retention.py` |
| Credential storage | Passwords never stored — bcrypt hashes only; JWT sessions expire in 12h; feature-flagged via `AUTH_ENABLED` | `core/security.py`, `api/routes/auth.py` |
| Secrets | Live in `.env` (git-ignored) locally, environment variables in AWS — never in code | `core/config.py` |
| Transport | HTTPS in production (Amplify terminates TLS); CORS restricted to known origins | `api/main.py` |
| Anti-hallucination | Every verbatim quote is string-matched back to the source; unmatched quotes are flagged "⚠ not verified" in the UI | `pipeline/run.py` |

## Architecture (modular by design)

Each box below is swappable without touching the others — the seams are config (`core/config.py`), the extractor adapter, and the API client.

```
frontend/ (Next.js · Amplify)                 backend/ (FastAPI)
  app/page.tsx        upload + role picker      api/main.py        assembly + retention loop
  app/workspace/…     split-pane workspace      api/routes/        documents · obligations · auth
  components/         PiiModal, RolePicker,     core/              config · pii · retention ·
                      ObligationList/Card,                         security · roles
                      DocumentPane (collapsible) pipeline/run.py   ingest → segment → extract →
  lib/api.ts          ALL backend calls                             verify → persist
  lib/types.ts        the locked schema         ingestion/         extract_pdf (Aggrey) · segment
                                                extraction/        adapter → Kaliza's extractor.py
                                                db/                models · database (Postgres)
```

**Ownership:** Kaliza — `extraction/`, role classification quality, eval set. Aggrey — `ingestion/`, `db/`, `pipeline/`, retention. Remy — `frontend/`, deploy, SAM.gov intake.

## Roadmap hooks (already stubbed)

- **Company capability matching** (*"can we actually meet this obligation?"*) — add a `company_profiles` table and compare against obligation requirements; the role-view layer is where it plugs in.
- **Institutional memory** — documents + obligations already persist per-document; a cross-document search endpoint is the next step (needs a retention exemption decision first).
- **Span-level highlight** — `DocumentPane.tsx` is the only file to touch (iframe → react-pdf).
