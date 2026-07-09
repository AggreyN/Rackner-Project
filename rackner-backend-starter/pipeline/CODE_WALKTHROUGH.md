# `pipeline/` — the orchestrator

> This is where the whole backend comes together (Aggrey's area). One function, `process_document`, runs a PDF through every stage — ingestion, segmentation, extraction, PII, verification — and writes the results to Postgres. Crucially, it **composes the other modules without modifying any of them**.

File: `run.py`.

---

## `run.py` — `process_document(session, doc)`

The single entry point the upload endpoint calls. Step by step:

1. **Extract** — `extract_pages(doc.file_path)` turns the PDF into per-page text; we record `doc.num_pages`.
2. **Build the verification corpus** — join all page text into `full_text` and compute a normalized version (`_normalize`: collapse whitespace, lowercase). This is what quotes get matched against.
3. **PII record** — `scan_text(full_text)` → store just `{kind: count}` on the document (masked, counts only; no raw values). Feeds the UI's "this doc contained N emails" note.
4. **Segment → extract → persist** — for each clause `Chunk` from `segment_pages`:
   - Create and `flush()` a `Clause` row (flush so we get `clause.id` before inserting its obligations).
   - For each obligation from `extract_obligations(chunk.text)`, create an `Obligation` row carrying the plain-English text, type, trigger, party, the enrichment fields (roles/category/time_bucket), the verbatim quote, page, and confidence.
5. **Anti-hallucination check** — `verified = bool(quote) and _normalize(quote) in norm_full`. If the model's quote can't be found in the actual document, we still store the obligation but mark it **unverified** so the UI can flag it.
6. **Status + commit** — set `doc.status = "ready"` on success; on any exception set `"failed"` and re-raise; **always commit** in `finally` so partial progress and the status flag persist.

**Why it matters / talking point:** "The pipeline is the composition root. It knows the *order* of operations but delegates every hard task to a focused module — ingestion, segmentation, extraction, PII. That's why any one stage can be swapped or scaled without rewriting the flow."

---

## The design points worth saying out loud

- **`flush()` vs `commit()`** — we `flush()` the clause to get its database ID (so obligations can reference `source_clause_id`) without committing the transaction mid-loop. One commit at the end keeps the whole document atomic-ish.
- **`try/except/finally` around everything** — a bad PDF or a model error marks the document `failed` rather than leaving it stuck in `processing`, and the `finally` commit guarantees that status is saved. Failures are visible, not silent.
- **Verification is cheap and honest** — a normalized substring match. It won't catch a cleverly paraphrased hallucination, but it *does* catch fabricated quotes, and it never blocks an item — it flags it. Reviewers make the final call (human-in-the-loop `PATCH` in the obligations route).
- **Synchronous by choice (MVP)** — `process_document` runs inline on upload (see the comment in `documents.py`: "sync for MVP; queue is the scale-up path"). For big docs or high volume, wrap this call in a background worker — the function itself doesn't change.

**Likely question — "What happens on a huge or corrupt PDF?"** → It's caught, the document is marked `failed`, and the exception propagates for logging. The user sees a failed status instead of a hang.

**Likely question — "Isn't running this inline on the request slow?"** → For the MVP demo, yes, and that's an accepted trade-off for simplicity. The single call site is designed to move to a queue (Celery/RQ) with no change to the pipeline logic.

**Likely question — "Why store unverified obligations at all?"** → Recall over silent loss. A flagged-but-present item lets a human decide; dropping it would hide a possible real obligation.
