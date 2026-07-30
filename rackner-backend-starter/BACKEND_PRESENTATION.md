# Backend — Engineering Presentation Guide

> **Presenter:** Aggrey (Data & Backend)
> **Audience:** engineers
> **Goal:** explain what the backend does and the major things running through it, confidently, as the person who built it.
>
> This is a *speaking* guide. Bold "**Say:**" lines are what to say out loud; the rest is your backup for questions. Aim for ~8–10 minutes + Q&A.

---

## 0. The 30-second opener

**Say:** "The backend takes one federal solicitation PDF and turns it into a structured, cited list of everything the company is obligated to do — and it does it once, so every team reads the answers instead of the document. My side is the data pipeline: how a raw PDF becomes text with coordinates, gets segmented into clauses, runs through the extractor, and lands in Postgres — plus the security guarantees that wrap all of it: PII screening, 3-day retention, and an anti-hallucination check."

Three things you want them to remember (repeat them at the end):
1. **Every obligation is traceable** — page number, clause, verbatim quote, and pixel coordinates.
2. **Nothing is trusted blindly** — quotes are verified against the source; unverifiable ones are flagged, not hidden.
3. **The layers are swappable** — the extractor, the DB, and the roles are all behind seams, so pieces change without breaking the pipeline.

---

## 1. The mental model — draw this

Draw this left-to-right on the board. It *is* the presentation.

```
 PDF ──► extract_pdf ──► segment ──► adapter(extractor) ──► enrich ──► verify ──► Postgres ──► API
         (text +         (clause     (Claude, or a          (roles,    (quote in            (role-
          word boxes)     chunks)     mock fallback)         category,  source?)             filtered
                                                             time)                           views)
   └──────────── all orchestrated by pipeline/run.py: process_document() ────────────┘

 Wrapping everything:  PII scan  •  3-day retention  •  config/secrets  •  (optional) auth
```

**Say:** "One function — `process_document` in `pipeline/run.py` — is the spine. It calls each stage in order and never modifies any of them. That's the whole design in one line: a pipeline of swappable stages."

---

## 2. Walk the pipeline (the main event)

### Stage 1 — Ingestion: `ingestion/extract_pdf.py`  *(mine)*

**What it does:** opens the PDF with PyMuPDF and returns one `PageText` per page — carrying the text **and** a `Word` list where every word knows its character range *and* its bounding box on the page.

**Say:** "The non-obvious decision here: PyMuPDF gives you two views of a page — a plain text blob and a list of words with coordinates — and their character positions don't line up. So instead of trusting the blob, I **rebuild the page text from the word list**. That way a character offset always maps back to real pixels. That's the function `boxes_for_span` — give it a character range, it hands back the rectangles to highlight."

**Why it matters:** "Citations and span-level highlighting are a product requirement, not a nice-to-have. The coordinate trail — **page → char offset → pixel box** — starts at the very first step. That traceability is our moat."

**Own the edge case:** "Scanned, image-only pages have no word layer, so `words` is empty and I fall back to plain `get_text()`. Two of our five sample SAM.gov PDFs are image-only — those need OCR, which is Week 7."

### Stage 2 — Segmentation: `ingestion/segment.py`  *(mine)*

**What it does:** splits each page's text into **clause chunks** at FAR/DFARS clause-number boundaries (regex on patterns like `252.204-7012`). Text before the first clause on a page becomes a "narrative" chunk. Each `Chunk` carries `clause_ref`, `text`, `page`, `char_start/char_end`, and the **word boxes** for that span.

**Say:** "This gives the extractor bounded, meaningful units instead of a wall of text, and it stamps each chunk with the clause number, page, and character range. So an obligation is never 'trust me' — it's 'clause 252.204-7012, page 14,' with the exact words boxed."

**Why regex, not an LLM here:** "Clause numbers have a strict, known format. Regex is exact, instant, and free — I save the LLM budget for the part that needs judgment: turning clause text into plain-English obligations."

**Own the limitation:** "v1 segments within a page; a clause spanning a page break isn't stitched yet. It doesn't hurt citation correctness — it just occasionally splits one clause into two chunks. Tracked for v2."

### Stage 3 — Extraction seam: `extraction/adapter.py`  *(shared)*

**What it does:** the boundary between the pipeline and Kaliza's Claude extractor. It tries to import her module; if it's missing or there's no API key, it runs a deterministic **mock** that returns clearly low-confidence (0.55) obligations.

**Say:** "The pipeline never imports Kaliza's file directly — it goes through this adapter. Her code can change, or not exist yet, and the whole app still runs end-to-end on the mock. That's what let the frontend and I build in parallel with the AI work instead of waiting on it."

### Stage 4 — Enrichment: `enrich()` in the adapter  *(shared)*

**What it does:** takes the extractor's raw obligation and derives three fields **we never ask the LLM for** — `roles` (which teams care), `category` (legal/security/reporting/…), and `time_bucket` (immediate / 30 days / quarterly / ongoing). All rule-based from `core/roles.py`.

**Say:** "Deriving these ourselves keeps them transparent and auditable, and keeps the LLM output schema small. Adding a new team is one dict entry in `core/roles.py` — nothing else changes."

### Stage 5 — Verification: in `pipeline/run.py`  *(mine)*

**What it does:** every obligation's `verbatim_quote` is normalized and string-matched back into the full document text. Match → `verified=True`; no match → stored but `verified=False`.

**Say:** "This is our anti-hallucination guarantee. If the model quotes something that isn't actually in the document, we don't drop it silently and we don't trust it — we store it flagged, and the UI marks it '⚠ not verified.' Reviewers stay in control."

### Stage 6 — Persistence: `db/models.py` + `pipeline/run.py`  *(mine)*

**What it does:** writes three related tables — `documents` → `clauses` → `obligations` — with `cascade="all, delete-orphan"` so deleting a document wipes its children automatically.

**Say:** "The relational shape matters for two reasons: one document has many clauses, a clause has many obligations — that's a natural join; and cascade delete is what makes retention a one-line delete instead of manual cleanup."

---

## 3. What's running *through* everything (cross-cutting)

These aren't a pipeline stage — they wrap the whole system. Engineers will ask about these.

### PII screening — `core/pii.py`
**Say:** "Before we store anything, the file is scanned for SSNs, emails, phones, cards, DOBs, passports — transparent regexes, not a black-box model, because this is a compliance story. Credit-card matches are Luhn-checked to kill false positives. The scan endpoint stores **nothing**; if it finds something, the UI makes the user explicitly confirm. After a real upload we keep only masked **kinds and counts**, never raw values."

### 3-day retention — `core/retention.py`
**Say:** "Every document is stamped `expires_at = upload + 3 days` and hard-deleted — file on disk *and* DB rows. And I enforce it three independent ways: on startup, hourly in a background loop, and lazily whenever a document is accessed. So expiry holds even if the server was asleep and a cron never fired. I delete the file before the row, so the DB is never pointing at a file that's already gone."

### Config & secrets — `core/config.py`
**Say:** "One config module. Secrets live in `.env` locally (git-ignored) and in AWS env vars in prod — never in code. Changing the retention window or flipping auth on is a one-line env change, no code edit."

### Auth — `core/security.py` + `api/routes/auth.py` (feature-flagged OFF)
**Say:** "Auth is built but flagged off so the demo has zero login friction. When it's on: passwords are never stored — only bcrypt hashes — and sessions are short-lived JWTs that self-expire. We designed security in, rather than bolting it on later."

### The API surface — `api/`
- `POST /documents/scan` → PII pre-check (stores nothing)
- `POST /documents` → save + run pipeline + stamp expiry
- `GET /documents/{id}` and `/{id}/pdf` → metadata and the file for the viewer
- `GET /obligations/document/{id}?role=…&group_by=…` → role-filtered, grouped obligations
- `PATCH /obligations/{id}` → human-in-the-loop: change status / edit text

**Say:** "Role filtering ranks the user's items to the top but never hides the others — they're dimmed, not removed. Transparency beats a false 'that's everything.'"

---

## 4. Design decisions I'll defend

| Decision | Why |
|---|---|
| Rebuild page text from word boxes | The plain blob and word list have different offsets; one coordinate system end-to-end is the only way highlighting stays correct. |
| Adapter around the extractor | Parallel development; the app runs without the API key; swapping models never touches the pipeline. |
| Regex for clauses, LLM for meaning | Use the cheap exact tool where the format is strict; spend the LLM where judgment is needed. |
| Synchronous pipeline for MVP | Simple and demo-friendly. The scale-up is a background queue — a one-line change at the call site in `documents.py`. |
| Rule-based roles/enrichment v1 | Transparent and auditable now; the function signatures let an LLM classifier drop in later with no caller changes. |
| Verify quotes against source | Cheap, deterministic hallucination guard that keeps a human in the loop. |

---

## 5. Known limitations (say them before they ask — it reads as strength)

- **Cross-page clauses** aren't stitched yet (within-page segmentation only). *v2.*
- **OCR** for image-only PDFs isn't wired — 2 of 5 samples need it. *Week 7; deps already listed, commented, in requirements.txt.*
- **Bbox persistence**: boxes are computed at the chunk level but not yet written to the `clauses` table. *Week 7.*
- **Pipeline is synchronous** — fine for demo scale; a queue is the path to concurrency.
- **Extractor wiring**: Kaliza's `extractor.py` currently sits at the repo root, not `extraction/extractor.py` where the adapter looks — so it's running on the **mock** until that's reconciled. *(Flag this honestly if the topic of "is it using real Claude yet" comes up.)*

---

## 6. Anticipated Q&A

- **"What if the model hallucinates?"** → Quote is string-matched to the source; unmatched = `verified=False`, surfaced in the UI, editable by a reviewer.
- **"Where does the Anthropic key live? Is it safe?"** → `.env` locally, AWS env vars in prod, never committed. No key → mock keeps the app working.
- **"How do you know the 3-day delete actually runs?"** → Three triggers: boot, hourly, on-access. It's checked, not merely scheduled.
- **"Why Postgres over flat files?"** → Relational joins (doc→clause→obligation) and cascade delete for retention.
- **"How do you highlight the exact source in the PDF?"** → `boxes_for_span` maps a character range to word bounding boxes; the coordinate trail starts at ingestion.
- **"Is it using real Claude right now?"** → The seam is ready; it runs on the mock until the extractor module is wired to `extraction/extractor.py`. Flipping to real is import + API key, no pipeline change.
- **"Can two teams see different obligations?"** → Same data, different *view* — `?role=` ranks and dims; nothing is hidden.

---

## 7. Optional live demo script

```bash
cd rackner-backend-starter && source venv/bin/activate
uvicorn api.main:app --reload          # open http://localhost:8000/docs
# 1. POST /documents/scan  with a sample PDF → show PII findings, nothing stored
# 2. POST /documents       → returns id, status "ready", expires_at (3 days out)
# 3. GET  /obligations/document/{id}?role=security&group_by=time
#      → point out: roles, verified flag, page + verbatim quote on each item
```
Standalone ingestion proof (no server):
```bash
python ingestion/extract_pdf.py data/samples/1305M226Q0038.pdf
# shows pages, word counts, and a sample word's char range + pixel box
```

---

## 8. Close — the three takeaways

**Say:** "So, three things: every obligation is **traceable** to page, clause, quote, and coordinates; nothing is **trusted blindly** — we verify against the source; and every layer is **swappable** behind a seam. That's the backend."
