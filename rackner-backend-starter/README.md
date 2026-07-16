# Team Anvil — Backend

The backend for **Team Anvil**, a Federal Document Intelligence Layer: upload a
government solicitation, pick your corporate role, and get a plain-English,
source-cited, deadline-aware register of everything your company is obligated to
do. (Rackner AI Innovation Fellowship · Team 1 — Aggrey, Kaliza, Remy.)

This backend is built **one week at a time**. Each week is tagged and is a
runnable superset of the week before it:

```bash
git checkout week1     # Foundation — DB connection (you are here)
git checkout week2     # Ingestion — PDF → text + word coordinates
git checkout week3     # Schema + end-to-end pipeline + upload API
# ... through week9 (Demo Day)
git checkout main      # latest
```

## What's here (through Week 3)

```
db/database.py            SQLAlchemy engine + SessionLocal + Base      [week1]
db/test_connection.py     proves Python can reach your database        [week1]
ingestion/extract_pdf.py  PDF → pages: text + word bounding boxes      [week2]
ingestion/segment.py      pages → FAR/DFARS clause chunks (page+chars) [week2]
db/models.py              Document · Clause · Obligation · User        [week3]
extraction/adapter.py     seam → Kaliza's extractor (mock fallback)    [week3]
pipeline/run.py           ingest → segment → extract → verify → save   [week3]
api/main.py               app assembly + CORS + retention loop         [week3]
api/routes/documents.py   scan · upload · get · pdf · delete           [week3]
core/pii.py               pre-upload PII scan (regex + Luhn)           [week4]
core/retention.py         3-day hard-delete (boot + hourly + on-access)[week4]
core/roles.py             5 roles + rule-based obligation→role tagger  [week5]
api/routes/obligations.py roles · role-filtered register · PATCH       [week5]
core/security.py          bcrypt password hashing + JWT sessions       [week6]
api/routes/auth.py        register · login (flag: AUTH_ENABLED)        [week6]
.env.example              copy to .env and set DATABASE_URL
```

## Week 2 — ingestion

`extract_pdf.py` turns a PDF into pages that keep **both** the page number and
the position of every word. Each page's `text` is rebuilt from its word list, so
a character span maps exactly back to pixel boxes via `boxes_for_span()` — that's
what makes span-level citation highlighting possible. `segment.py` then splits
each page into FAR/DFARS clause chunks carrying `clause_ref`, page, char offsets,
and the boxes for that span.

```bash
python ingestion/extract_pdf.py data/samples/your-file.pdf
```

Scanned, image-only PDFs have no word layer — they extract empty and are flagged
for the OCR fallback in Week 7.

## Week 3 — schema + pipeline

The whole chain now runs end to end and lands in the database:

```
POST /documents  →  extract_pages → segment_pages → extract_obligations
                 →  verify each verbatim_quote against the source
                 →  persist Document / Clause / Obligation
```

Every `verbatim_quote` is string-matched back to the document text; anything we
can't find is still stored but flagged `verified=False`. That's the
anti-hallucination guarantee — we never silently trust the model.

```bash
uvicorn api.main:app --reload      # http://localhost:8000/docs
```

## Week 4 — security features

**PII pre-upload gate.** `POST /documents/scan` extracts text, runs a regex +
Luhn scan (SSN, email, phone, card, DOB, passport) and returns masked findings —
**storing nothing**. The UI shows "sensitive information detected" and the user
confirms before the real `POST /documents` (which carries `pii_acknowledged`).

**3-day retention.** Every upload is stamped `expires_at = now + RETENTION_DAYS`.
`purge_expired()` hard-deletes the PDF from disk *and* its rows — on boot, hourly
in the background, and lazily whenever a document is accessed, so expiry holds
even if the server was asleep.

```bash
# prove retention works: everything expires immediately
RETENTION_DAYS=0 uvicorn api.main:app --reload
```

## Week 5 — role views

The pivot, in code: **one document, read once — every team gets its answers.**
`core/roles.py` holds the five roles (`contracts`, `proposal`, `program`,
`security`, `leadership`), each with the question that team asks. Adding a role
is one dict entry; nothing else changes.

```bash
GET /obligations/roles                                  # feeds the role picker
GET /obligations/document/{id}?role=security&group_by=time
PATCH /obligations/{id}   # open → in-review → done
```

The role filter **ranks** rather than hides: your role's obligations sort first,
but everything stays visible. Transparency beats a false sense of "that's
everything."

## Week 6 — hardening

Accounts are **off by default** (`AUTH_ENABLED=false`) so the demo needs no
login. When enabled, `api/routes/auth.py` mounts `register` / `login`:

- Passwords are never stored — only a salted **bcrypt** hash (`core/security.py`).
- Sessions are short-lived **JWTs** (12h, HS256); no session table to leak.
- Login returns the same error whether or not the email exists.
- Secrets live in `.env` (git-ignored) locally, env vars in AWS.

Also enforced: PDF-only uploads, a `MAX_UPLOAD_MB` cap streamed during write
(so an oversized file never lands whole on disk), and CORS restricted to
`ALLOWED_ORIGINS`.

```bash
AUTH_ENABLED=true uvicorn api.main:app --reload
```

> Dependency note: `bcrypt` is pinned `<4.1`. passlib 1.7.4's backend probe
> breaks on bcrypt 4.1+, which makes every password hash raise.

## Week 7 — citation grounding + OCR

The coordinate trail that started in Week 2 now reaches the database and the API.
Each obligation's `verbatim_quote` is **located** on its page (`find_span`,
tolerant of line-break/whitespace differences), and that span becomes pixel
rectangles:

```jsonc
// GET /obligations/document/{id}
{ "verbatim_quote": "...", "page": 14,
  "quote_char_start": 986, "quote_char_end": 1104,
  "quote_boxes": [[161.0, 290.4, 179.0, 302.9], ...] }   // ready to draw
```

Finding the quote **is** the verification — a quote we can't locate is stored
`verified=false` rather than silently trusted. (A quote straddling a page break
still verifies via the whole-document check; it just carries no boxes.)

**OCR fallback (optional).** Scanned, image-only pages have no word layer. If
`pytesseract` + `tesseract` are installed, those pages are OCR'd into the *same*
page→char→box coordinate system, and `PageText.ocr` marks them. Without the
toolchain ingestion still works — scanned pages just come back empty.

```bash
pip install pytesseract pdf2image && brew install tesseract poppler
```

## Week 8 — integration freeze

One command runs the whole backend against every sample PDF — no Postgres
required (it uses a throwaway SQLite DB and upload dir):

```bash
python scripts/smoke_test.py                       # all of data/samples/
python scripts/smoke_test.py path/to/one.pdf       # just one
```

It asserts what we promise on stage: uploads reach `ready`, clauses and
obligations land, **every** quote verifies against the source, obligations carry
citation coordinates, the PII scan stores nothing, and scanned PDFs are reported
rather than silently empty.

### Repo layout note

The backend lives in **`rackner-backend-starter/`** (not `backend/`). Folder-level
walkthroughs live next to the code they describe:

```
ingestion/CODE_WALKTHROUGH.md   extraction/CODE_WALKTHROUGH.md
db/CODE_WALKTHROUGH.md          pipeline/CODE_WALKTHROUGH.md
core/CODE_WALKTHROUGH.md        api/CODE_WALKTHROUGH.md
```

## Week 9 — Demo Day

Measured numbers, talking points, and the gaps worth owning out loud:
**[DEMO_NOTES.md](DEMO_NOTES.md)**. Bug fixes only from here.

## Quick start

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Option A — Postgres:
createdb rackner
python db/test_connection.py      # -> "✅ Connected to PostgreSQL!"

# Option B — no Postgres yet: set DATABASE_URL=sqlite:///./dev.db in .env
```

## Roles

- **Role 1 — AI & Product Lead (Kaliza):** LLM extraction, prompts, JSON schema, eval set.
- **Role 2 — Data & Backend Lead (Aggrey):** ingestion, segmentation, Postgres, pipeline, API. *(This repo's backend.)*
- **Role 3 — Full Stack & Infra Lead (Remy):** Next.js frontend, SAM.gov intake, AWS deploy, CI.
