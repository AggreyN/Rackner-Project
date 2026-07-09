# `db/` — database connection + schema

> The data layer (Aggrey's area). One file sets up the connection to Postgres; one defines the tables as Python classes (SQLAlchemy ORM); one is a smoke test. Everything else in the backend imports the engine/session and the models from here.

Files: `database.py`, `models.py`, `test_connection.py`.

---

## `database.py` — the shared connection

- `engine = create_engine(DATABASE_URL, echo=False)` — the core Postgres connection. `echo=True` would print every SQL statement (useful while learning); we keep it off.
- `SessionLocal = sessionmaker(...)` — factory for short-lived sessions (a "workspace" for reads/writes). `autoflush=False, autocommit=False` means **we** control when data is flushed and committed — important for the pipeline, which flushes to get IDs but commits once.
- `Base = declarative_base()` — every table class inherits from this; it's how SQLAlchemy knows about our tables.

**Talking point:** "This is the one place that knows how to reach Postgres. The API depends on `SessionLocal` (via `api/deps.get_db`), the pipeline and retention take a `Session` — nobody constructs their own connection."

---

## `models.py` — the schema (four tables)

Uses the modern typed SQLAlchemy 2.0 style (`Mapped[...]`, `mapped_column(...)`). `_utcnow()` gives timezone-aware UTC defaults.

### `Document` — one uploaded PDF
Key columns: `filename`, `file_path` (where the PDF sits on disk), `source` (e.g. SAM.gov notice ID), `num_pages`, `status` (`processing|ready|failed`), `pii_findings` (JSON — kinds+counts only), `pii_acknowledged`, `uploaded_at`, `expires_at` (the 3-day retention stamp).
Relationships: `clauses` and `obligations`, both with **`cascade="all, delete-orphan"`** — deleting a document automatically deletes its children (this is what makes retention a clean single delete).

### `Clause` — a segmented section
`document_id` (FK, `ondelete="CASCADE"`), `clause_ref` ("252.204-7012"), `text`, `page`, `char_start`, `char_end`. The offsets are the citation trail from `segment.py`.

### `Obligation` — the product's core unit
- From the extractor: `plain_english_text`, `obligation_type`, `trigger_or_deadline`, `responsible_party`, `verbatim_quote`, `confidence`.
- Intelligence-layer fields (added by `adapter.enrich`): `roles` (JSON array), `category`, `time_bucket`.
- Traceability & workflow: `source_clause_id` (FK), `page`, `verified` (the anti-hallucination flag), `status` (`open|in-review|done`).

### `User` — only used when auth is on
`email` (unique), `password_hash` (**bcrypt hash only — never plaintext**), `created_at`.

**Why it matters / talking point:** "The schema mirrors the domain: a document *has many* clauses, a clause *has many* obligations. That relational shape is why we chose Postgres — we get joins and cascading deletes for free, which the retention feature leans on directly."

**Design note — the columns tell the whole product story:** `verified` = anti-hallucination, `roles`/`category`/`time_bucket` = the intelligence layer, `status` = human-in-the-loop review, `expires_at` = retention, `pii_findings` = the security scan. If someone asks "where does feature X live," it's a column here.

**Likely question — "Why store `roles` as JSON instead of a join table?"** → An obligation's roles are a small, read-mostly list we always fetch with the obligation — JSON keeps v1 simple and fast. A join table is the normalization path if we ever need to query "all obligations for role X across documents."

**Migrations:** this schema is additive over the starter, so run
`alembic revision --autogenerate -m "intelligence layer" && alembic upgrade head`
after changes. In dev, `api/main.py` also calls `Base.metadata.create_all` on startup as a convenience — but **Alembic owns production schema**.

---

## `test_connection.py` — the Week-1 smoke test

Runs `SELECT version();` and prints ✅/❌ with a troubleshooting checklist (is Postgres running, did you `createdb rackner`, is the venv active, did you copy `.env`). Pure diagnostics — not part of the app runtime. Run it with `python db/test_connection.py`.

**Talking point:** "First thing a new teammate runs to prove their environment can reach the database before touching any app code."
