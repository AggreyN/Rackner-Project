# Rackner Contract Obligation Extractor

Turns dense government contracts/solicitations into a **plain-English, source-cited, deadline-aware checklist of obligations** — demoable entirely on public SAM.gov documents.

> Rackner AI Innovation Fellowship · Team 1 (Aggrey, Kaliza, Remy)

## Quick start (backend)

New here? Read **[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)** — a step-by-step Week 1 setup for macOS.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
createdb rackner
python db/test_connection.py      # should print "✅ Connected to PostgreSQL!"
```

## Project structure

```
ingestion/   PDF parsing + clause segmentation   (Role 2 · Weeks 2-3)
db/          connection, models, migrations       (Role 2 · Weeks 4-6)
api/         FastAPI endpoints for the frontend    (Role 2 · Week 8)
data/        sample SAM.gov PDFs for testing
docs/        learning path + getting-started guide
tests/       tests
```

## Roles

- **Role 1 — AI & Product Lead:** LLM extraction pipeline, prompts, JSON schema, eval set, product priorities.
- **Role 2 — Data & Backend Lead (Aggrey):** ingestion, segmentation, Postgres schema, obligation tracking layer. *(This repo's backend.)*
- **Role 3 — Full Stack & Infra Lead:** React/Next.js split-pane UI, SAM.gov API, deployment, the click-to-highlight demo.

## Learning path

See **[docs/LEARNING_PATH.md](docs/LEARNING_PATH.md)** for a week-by-week study plan mapped to the deadlines.
