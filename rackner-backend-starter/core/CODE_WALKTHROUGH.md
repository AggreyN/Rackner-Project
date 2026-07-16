# `core/` — policy & configuration

> This folder holds the **decisions**, not the plumbing. Anything you'd want to change without hunting through the codebase — settings, what counts as PII, how long we keep files, what the roles are, how passwords are hashed — lives here. Every other module reads *from* `core/`, never the other way around.

Files: `config.py`, `pii.py`, `retention.py`, `roles.py`, `security.py`.

---

## `config.py` — one place to change behavior

Loads settings from the `.env` file (via `python-dotenv`), with sane defaults so the app still boots if a value is missing.

Key values:
- `DATABASE_URL` — Postgres connection string.
- `ANTHROPIC_API_KEY` + `EXTRACTION_MODEL` — for Kaliza's extractor (`claude-sonnet-4-5`).
- `RETENTION_DAYS` (default **3**) — the retention window.
- `UPLOAD_DIR`, `MAX_UPLOAD_MB` (default 50) — where files go and the size cap.
- `AUTH_ENABLED` (default **false**), `JWT_SECRET`, `JWT_EXPIRY_HOURS` (12) — auth feature flag + token config.
- `ALLOWED_ORIGINS` — CORS allowlist (localhost + the deployed Amplify URL), parsed from a comma-separated env var.

**Why it matters / talking point:** "Configuration is centralized. Changing the retention window from 3 days to 7, or flipping auth on, is a one-line env change — no code edits, no redeploy of logic." Defaults mean a teammate can clone and run without a fully populated `.env`.

---

## `pii.py` — the pre-upload PII scanner

Scans document text for likely sensitive info and reports **kinds + counts + a masked sample** — never the raw values.

- `PiiFinding` (dataclass) — `kind` ("SSN"), `count`, `sample_masked` ("*******89").
- `_PATTERNS` — a dict of transparent, auditable regexes: SSN, email, phone, credit card, date of birth, passport. Chosen over an ML model precisely *because* they're explainable in a compliance conversation.
- `_luhn_ok()` — runs the **Luhn checksum** on credit-card matches to cut false positives (a random 16-digit string won't pass Luhn).
- `_mask()` — keeps only the last 2 characters so the user can recognize their own data without us echoing it.
- `scan_text(text)` — returns the list of findings.

**Why it matters / talking point:** "We detect PII *before* anything is stored, and we store only masked kinds and counts — never the sensitive value itself. The credit-card check is Luhn-validated to avoid crying wolf on every long number." This is security measure #1.

**Likely question — "Regexes miss things, right?"** → Yes, v1 is intentionally high-precision and transparent for the compliance story. The `_PATTERNS` dict is the single extension point; adding a detector (or swapping in an ML model behind `scan_text`) doesn't touch callers.

---

## `retention.py` — 3-day hard delete

Enforces "contracts don't linger in our system."

- `expiry_from_now()` — `now (UTC) + RETENTION_DAYS`.
- `is_expired(doc)` — compares `expires_at` to now; **tolerates naive timestamps** from older rows by assuming UTC (avoids a tz-aware/naive comparison crash).
- `_delete_document()` — removes the **file from disk first**, then the DB row; children (clauses, obligations) go via cascade. Swallows `OSError` if the file's already gone so DB cleanup still proceeds.
- `purge_expired(session)` — loops all documents, deletes the expired ones, commits, returns the count.

**Why three enforcement points?** It's called (a) on app startup, (b) hourly in a background loop (both in `api/main.py`), and (c) lazily whenever a document is fetched (`api/routes/documents.py`). "Expiry survives a server that was asleep — we don't rely on a single cron that might not have fired." Security measure #2.

**Likely question — "Why delete the file before the row?"** → If we deleted the row first and then crashed, we'd have an orphaned file on disk with no record pointing to it. File-first means the DB is always the source of truth for what still exists.

---

## `roles.py` — the "intelligence layer," and the pivot's heart

This is what turns a generic extractor into a *per-team* product.

- `Role` (frozen dataclass) — `key`, `label`, the `question` that team asks of a document, the `obligation_types` most relevant to them, and `keywords` that boost relevance.
- `ROLES` — the five teams: **contracts, proposal, program, security, leadership**. Each carries its guiding question (e.g. Contracts = "What are we legally on the hook for?").
- `classify_roles(obligation_type, text)` — tags an obligation with **every** role it matters to. An obligation matches a role if its type is in that role's list **or** its text contains one of the role's keywords. Falls back to `["contracts"]` because every obligation is legally relevant at minimum.

**Why it matters / talking point:** "Adding a new corporate team is *one dict entry here* — nothing else in the codebase changes. The role picker in the UI, the API filter, and the enrichment step all read from this one source." That's the modularity story.

**Likely question — "This is just keyword matching?"** → Deliberately, for v1: transparent and auditable. The signature `classify_roles(type, text) -> list[str]` is designed so an LLM classifier can replace the body later without touching a single caller.

---

## `security.py` — auth & credential crypto (feature-flagged)

Only exercised when `AUTH_ENABLED=true`; kept in one reviewable place.

- `hash_password` / `verify_password` — bcrypt via passlib. Bcrypt is **slow-by-design and salted per user**, so a leaked hash is expensive to brute-force.
- `create_token(user_id, email)` — a short-lived **JWT** (HS256) with a `sub`, `email`, and `exp`. No session table needed — the token expires on its own.
- `decode_token` — verifies/parses; returns `None` on any JWT error instead of throwing.

**Why it matters / talking point:** "Passwords are never stored — only bcrypt hashes. Sessions are stateless JWTs that self-expire in 12 hours. And it's all behind a feature flag so the demo stays frictionless while the security design is already in place." Security measure #3.

**Likely question — "Why ship auth if it's off?"** → So the architecture and the credential-handling story are real and reviewable now; flipping the flag is the only step to turn it on. We didn't want to bolt security on later.
