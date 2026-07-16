# `api/` — the HTTP layer (FastAPI)

> This is the front door. It defines the FastAPI app, wires in the routes, and hands each request a database session. The routes are thin — they validate input, call `core/` and `pipeline/`, and shape the JSON the frontend expects. Business logic lives in `core/`/`pipeline/`, not here.

Files: `main.py`, `deps.py`, `routes/documents.py`, `routes/obligations.py`, `routes/auth.py`.

---

## `main.py` — app assembly + the retention loop

- Builds the `FastAPI` app with a title/description (the description even tells users about the 3-day auto-delete).
- **CORS** — `CORSMiddleware` restricted to `ALLOWED_ORIGINS` from config (localhost + the Amplify URL). Not `*` — only known origins.
- **Routers** — mounts `documents` and `obligations` always; mounts `auth` **only if `AUTH_ENABLED`** (feature flag). Removing or adding a router never affects the others.
- **`lifespan`** — on startup: create tables (dev convenience; Alembic owns prod), run `purge_expired` once (sweep on boot), and launch `_retention_loop`, a background task that purges expired docs **every hour**. On shutdown it cancels the task.
- `GET /` — a health check.

**Why it matters / talking point:** "The app is assembled from independent modules — each router is self-contained, and the retention sweep runs both on boot and hourly in the background. Auth is one flag away from on." This is where retention triggers (a) and (b) live (the third, on-access, is in the documents route).

---

## `deps.py` — the DB session dependency

`get_db()` — a FastAPI dependency that opens a `SessionLocal`, `yield`s it to the route, and **always closes it** in `finally`. Every route gets its session via `Depends(get_db)`, so connections are never leaked and never shared across requests.

**Talking point:** "One tiny function guarantees every request gets a fresh session that's always cleaned up — the standard FastAPI + SQLAlchemy pattern."

---

## `routes/documents.py` — upload, scan, fetch, serve, delete

Implements the frontend's exact flow (documented at the top of the file).

- **`POST /documents/scan`** — step 1: save to a temp path, extract text, run the PII scan, return findings, and **delete the temp file in `finally`**. The scan stores *nothing*.
- **`POST /documents`** — step 3: the real upload. `_save_upload` streams the file to disk in 1 MB chunks, rejects non-PDFs (400) and anything over `MAX_UPLOAD_MB` (413). Creates the `Document` with `pii_acknowledged` and a 3-day `expires_at`, then calls `process_document` (the pipeline) **synchronously** ("sync for MVP; queue is the scale-up path"). Returns id/status/expiry.
- **`GET /documents`** — lists documents; calls `purge_expired` first (**lazy retention enforcement**).
- **`GET /documents/{id}`** and **`/{id}/pdf`** — both go through `_get_live_doc`, which 404s (and purges) if the doc is missing or expired. The `/pdf` route streams the file back via `FileResponse` for the viewer pane (410 if the file's gone from disk).
- **`DELETE /documents/{id}`** — removes the file and the row.

**Why it matters / talking point:** "Notice retention is enforced *on access*, not just on a timer — `_get_live_doc` treats an expired document as already gone. And the size/type checks + streamed write mean we never load a whole untrusted file into memory or accept a non-PDF." Security measures #1 and #2 both surface here.

**Likely question — "Why scan and upload as two separate calls?"** → So the UI can show the 'sensitive info detected — proceed?' popup and get explicit consent *before* anything is stored. The scan is stateless and leaves no trace.

---

## `routes/obligations.py` — the read model for the workspace

- **`GET /obligations/roles`** — returns the role picker options straight from `core/roles.ROLES` (single source of truth).
- **`GET /obligations/document/{id}?role=&group_by=`** — the main workspace query:
  - Pulls all obligations for the document, serializes them (including `relevant_to_role`).
  - **Filtering that doesn't hide** — when a `role` is given, items are *sorted* so the role's items come first, then by time urgency (`_TIME_ORDER`: immediate → 30_days → quarterly → ongoing → unclear). Non-relevant items are still returned (the UI dims them). Deliberate: transparency over a false "that's everything."
  - **Grouping** — by `time` (default), `category`, or `type`, into a `{group: [items]}` dict.
- **`PATCH /obligations/{id}`** — human-in-the-loop: set `status` (validated to `open|in-review|done`) or edit the plain-English text.

**Why it matters / talking point:** "This endpoint is the whole 'intelligence layer' made visible — same underlying obligations, re-ranked and grouped per team, with review actions. And it never hides an obligation from a user just because it's not 'theirs.'"

**Likely question — "Why sort instead of filter out other roles?"** → A contracts person glancing at a security item is fine; a contracts person *never seeing* a security obligation that turns out to be theirs is a liability. Dim, don't hide.

---

## `routes/auth.py` — register/login (only when `AUTH_ENABLED`)

- Pydantic `Credentials` model with `EmailStr` validation.
- **`POST /register`** — enforces a 10-char minimum, rejects duplicate emails (409), stores a bcrypt hash, returns a JWT.
- **`POST /login`** — verifies the hash; returns the **same error whether the email is unknown or the password is wrong** (401) so we don't leak which emails have accounts. Returns a JWT on success.

**Why it matters / talking point:** "Credential handling is isolated in one file. Passwords are bcrypt-hashed via `core/security`, never stored or logged in plaintext, and login errors are deliberately ambiguous to avoid account enumeration." Security measure #3.

**Likely question — "Where's the token checked on protected routes?"** → `core/security.decode_token` is the verifier; since auth ships feature-flagged off for the demo, route-level enforcement is the next step when we turn the flag on.
