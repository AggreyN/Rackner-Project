# Backend Code Walkthrough — the whole picture

> Read this first, then the per-folder walkthroughs. This is the narrative you can give in a meeting: what the backend does, how a request flows through it, and why we built it the way we did.

## The one-sentence pitch

**One federal document, read once — every corporate team gets the obligations that matter to *them*, each one citing the exact clause and page it came from, with the document auto-deleted after 3 days.**

## What problem it solves

A federal solicitation/contract (from SAM.gov) is 50–200 pages of dense FAR/DFARS legalese. Today five different teams each read the whole thing looking for their slice. We read it **once**, extract every obligation ("the contractor *shall*…"), and serve each team a filtered, ranked view of what they're on the hook for — with a verbatim quote + page number behind every item so nothing is taken on trust.

## End-to-end data flow (memorize this — it's the backbone of the demo)

```
Upload a PDF
   │
   ▼
[api/routes/documents.py]  POST /documents/scan   → PII pre-check (stores nothing)
   │  (UI popup if sensitive info found; user confirms)
   ▼
[api/routes/documents.py]  POST /documents        → save file to disk, stamp 3-day expiry
   │
   ▼
[pipeline/run.py] process_document()  ← orchestrates everything below, modifies nothing it calls
   │
   ├─ [ingestion/extract_pdf.py]  extract_pages()   PDF → text per page (keeps page numbers)
   ├─ [ingestion/segment.py]      segment_pages()   page text → FAR/DFARS clause chunks
   ├─ [extraction/adapter.py]     extract_obligations()  chunk → obligations (Claude, or a mock)
   │        └─ enrich(): tags each obligation with roles + category + time_bucket
   ├─ [core/pii.py]  scan_text()   records what PII kinds were present (masked, counts only)
   └─ verify: string-match every quote back to the source → verified True/False
   │
   ▼
Postgres  (documents · clauses · obligations)   [db/models.py]
   │
   ▼
[api/routes/obligations.py]  GET /obligations/document/{id}?role=…&group_by=…
   → role-filtered, grouped, citation-carrying obligations for the frontend
```

## Folder map (what lives where, one line each)

| Folder | Responsibility | Owner |
|---|---|---|
| `api/` | The HTTP layer — FastAPI app, routes, DB session dependency | Remy / shared |
| `core/` | Policy & config — settings, PII scanner, retention, roles, auth crypto | shared |
| `ingestion/` | Turn a PDF into structured text + clause chunks | Aggrey |
| `extraction/` | The seam to Kaliza's obligation extractor (+ enrichment) | Kaliza / adapter shared |
| `pipeline/` | Composes ingestion → extraction → DB, with the verification check | Aggrey |
| `db/` | SQLAlchemy engine + the three tables (+ users) | Aggrey |
| `docs/` | Onboarding docs (getting started, learning path) | — |
| `data/samples/`, `tests/` | Sample PDFs and a (currently empty) test folder | — |

## The 5 security measures (a likely meeting topic — know all five)

1. **PII pre-upload scan** — we scan the file *before* storing it; if we find SSNs/emails/etc. the UI makes the user explicitly confirm. The scan itself stores nothing. (`core/pii.py`, `/documents/scan`)
2. **3-day retention** — every document gets `expires_at = now + 3 days` and is hard-deleted (file **and** DB rows) on startup, hourly, and on access. (`core/retention.py`)
3. **Credentials** — passwords are never stored, only bcrypt hashes; sessions are short-lived JWTs. Auth ships **feature-flagged off** so the demo has no login friction. (`core/security.py`, `api/routes/auth.py`)
4. **Secrets** — live in `.env` (git-ignored) locally, env vars in AWS. Never in code. (`core/config.py`)
5. **Anti-hallucination** — every verbatim quote the extractor returns is string-matched back to the source text; unmatched quotes are stored but flagged `verified=False` so the UI can mark them "⚠ not verified." (`pipeline/run.py`)

## Design decisions we made on purpose (so we can defend them)

- **Adapter pattern around the extractor** — the pipeline never imports Kaliza's file directly; it goes through `extraction/adapter.py`. Her file can change, or be missing entirely, and the app still runs (falls back to a marked low-confidence mock). This is what lets frontend/backend build in parallel with the AI work.
- **Role logic in one place** (`core/roles.py`) — adding a new corporate team is a single dict entry, no other code changes.
- **Rule-based v1 for roles/categories** — transparent and auditable now; the function signatures are designed so an LLM classifier can drop in later without touching callers.
- **Synchronous pipeline for the MVP** — `process_document` runs inline on upload. Simple and demo-friendly; the obvious scale-up is a background queue (Celery/RQ), which is a one-function change at the call site.
- **Citations are first-class** — page numbers and character offsets are carried from ingestion all the way to the API. That traceability is the product's moat.

## Glossary (so no term trips you up)

- **FAR / DFARS** — Federal Acquisition Regulation / its DoD supplement. The clause libraries contracts reference (e.g. `252.204-7012`).
- **Solicitation** — the government's request for proposals (what we download from SAM.gov).
- **Obligation** — something the contractor must do ("shall submit…", "shall report within 72 hours…").
- **Clause** — a referenced section of the contract; our unit of segmentation.
- **CUI** — Controlled Unclassified Information; a security-relevant data category.
- **Verbatim quote** — the exact source sentence backing an obligation, used for the anti-hallucination check.

## Likely questions → crisp answers

- **"What if the AI hallucinates an obligation?"** → Every quote is matched back to the source; unmatched ones are flagged `verified=False`. We surface confidence, and reviewers can edit/close items (human-in-the-loop `PATCH`).
- **"Where does the Anthropic key go? Is it safe?"** → `.env` locally (git-ignored), AWS env vars in prod. Never committed. Without it, the adapter mock keeps the whole app working.
- **"How do you guarantee the 3-day delete actually happens even if the server was asleep?"** → Three independent triggers: on boot, hourly loop, and lazily on any access. Expiry is checked, not just scheduled.
- **"Why Postgres and not just files?"** → We need relational joins (a document has many clauses, a clause has many obligations) and cascade deletes for retention. `cascade="all, delete-orphan"` means deleting a document wipes its children automatically.
- **"Can two teams see different things?"** → Yes — `?role=` filters and ranks, but never *hides* other items (they're dimmed, not removed). Transparency over a false "that's everything."

## Running it locally

```bash
cd rackner-backend-starter
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set DATABASE_URL, ANTHROPIC_API_KEY
uvicorn api.main:app --reload # → http://localhost:8000/docs
```
