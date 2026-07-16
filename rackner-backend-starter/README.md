# Team Anvil — Backend (Week 2: Ingestion)

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

## What's here (through Week 2)

```
db/database.py            SQLAlchemy engine + SessionLocal + Base      [week1]
db/test_connection.py     proves Python can reach your database        [week1]
ingestion/extract_pdf.py  PDF → pages: text + word bounding boxes      [week2]
ingestion/segment.py      pages → FAR/DFARS clause chunks (page+chars) [week2]
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
