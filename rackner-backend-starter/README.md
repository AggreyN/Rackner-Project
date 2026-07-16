# Team Anvil — Backend (Week 1: Foundation)

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

## Week 1 — what's here

Just the foundation: a shared database connection and a smoke test.

```
db/database.py         SQLAlchemy engine + SessionLocal + Base
db/test_connection.py  proves Python can reach your database
.env.example           copy to .env and set DATABASE_URL
requirements.txt        Week-1 dependency subset
```

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
