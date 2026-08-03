# Rackner FDI — Backend

FastAPI + PostgreSQL backend for **Rackner FDI** (Federal Document Intelligence):
search SAM.gov opportunities, score them against a company's lifecycle plan, and
surface cited obligations with a no-hallucination guarantee.

This is the **Week 1 deliverable**: the shared data schema + auth. Domain
features (SAM.gov, USAspending, the LLM analysis gateway, contact discovery) are
stubbed as TODOs for later weeks.

## Layout

```
app/
  main.py        FastAPI app + CORS + health + a protected /me
  config.py      env-driven settings (DATABASE_URL, AUTH_MODE, COGNITO_*, JWT_SECRET, AWS_REGION)
  database.py    SQLAlchemy engine + SessionLocal + Base + get_db
  models.py      the 5 tables (users, lifecycle_profiles, opportunities, analyses, contacts)
  schemas.py     Pydantic models — mirrors /SCHEMA.md exactly (the shared contract)
  auth.py        Cognito JWT verify (JWKS) + local bcrypt register/login + current_user
  routes/
    auth.py      /auth/register, /auth/login  (local mode)
    health.py    /  and  protected /me
alembic/         migrations (0001 creates all 5 tables)
```

The source of truth for every field name is [`/SCHEMA.md`](../SCHEMA.md) at the
repo root; `app/schemas.py` mirrors it 1:1.

## Auth modes

`AUTH_MODE` (in `.env`) selects how identity works:

- **`local`** (default) — no AWS needed. `/auth/register` + `/auth/login` hash
  passwords with **bcrypt** and return a short-lived JWT we sign with `JWT_SECRET`.
- **`cognito`** — the frontend authenticates against an Amazon Cognito User Pool
  and sends the Cognito JWT; the backend validates it against the pool's JWKS
  (issuer + audience checked) and upserts a `users` row keyed by `cognito_sub`.
  No passwords are stored in this mode.

`current_user` works transparently in either mode; `/me` is protected by it.

## Run it locally (local mode, Postgres)

```bash
cd rackner-backend-starter
python3 -m venv venv && source venv/bin/activate      # if you don't have one
pip install -r requirements.txt

cp .env.example .env                                   # then set JWT_SECRET, DATABASE_URL
createdb rackner_fdi                                   # or point DATABASE_URL at your DB

alembic upgrade head                                   # creates all 5 tables
uvicorn app.main:app --reload                          # http://localhost:8000/docs
```

## Verify the auth flow

```bash
# register → returns { "access_token": "..." }
curl -s -X POST localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@rackner.com","password":"supersecret1"}'

# login → returns a token
TOKEN=$(curl -s -X POST localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@rackner.com","password":"supersecret1"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# protected route: with the token → 200 + your user; without it → 401
curl -s localhost:8000/me -H "Authorization: Bearer $TOKEN"
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/me
```

## Notes

- Secrets come from the environment (`.env` locally, real env vars in AWS) — never
  hard-coded. `JWT_SECRET` must be a long random string in anything but a throwaway demo.
- Removed in the pivot (do not re-add here): role picker / corporate-role
  classification, PII pre-upload scanning, 3-day document retention.
