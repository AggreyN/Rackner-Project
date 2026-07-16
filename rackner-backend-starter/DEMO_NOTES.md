# Demo Day — backend numbers & talking points

> Aggrey (Data & Backend). Everything here is **measured on the 5 sample SAM.gov
> PDFs** in `data/samples/`, reproducible with `python scripts/smoke_test.py`.
> Numbers are from a local M-series Mac, SQLite, mock extractor — re-measure
> before you quote them on stage.

## The numbers

| | Measured |
|---|---|
| Documents processed clean | **5 / 5** |
| Total corpus | **695 pages · 205,523 words** |
| Ingest + segment throughput | **~173 pages/sec** (peak 188 on the 638-page doc) |
| Full pipeline (upload → stored) | 51p in ~0.6s · 638p in ~4s |
| Clauses extracted | 825 across the corpus |
| Obligations extracted | 313 (36 + 277) |
| **Quotes verified against source** | **313 / 313 (100%)** |
| **Obligations carrying citation coordinates** | **313 / 313 (100%)** |
| Retention | 3 days, hard-delete; verified with `RETENTION_DAYS=0` |

Per-document:

| Document | Pages | Words | Clauses | Obligations | Verified |
|---|---|---|---|---|---|
| `77670.pdf` | 51 | 21,519 | 271 | 36 | 36/36 |
| `W912HN26RA006.pdf` | 638 | 182,796 | 551 | 277 | 277/277 |
| `1305M226Q0038.pdf` | 3 | 1,208 | 3 | 0 | — |
| `W50S8J26QA017.pdf` | 1 | 0 | — | — | scanned |
| `W912HN26RA012.pdf` | 2 | 0 | — | — | scanned |

## Say this if asked

**"How do you know it isn't hallucinating?"**
Every obligation carries a `verbatim_quote`, and we *locate that quote in the
source PDF* — `find_span` on the page text. Finding it **is** the verification,
and the same lookup returns the pixel boxes we highlight. 313/313 verified on our
corpus. A quote we can't find is still stored but flagged `verified=false` — we
flag, never silently drop, because recall beats a false sense of completeness.

**"What about scanned documents?"**
2 of our 5 samples are image-only with no text layer. We *detect and report*
them rather than returning a confident empty answer. Week 7 added an optional
OCR fallback (pytesseract) that puts OCR'd words into the same page→char→box
coordinate system. It's optional on purpose — a missing `tesseract` never breaks
ingestion of normal PDFs.

**"Why did that 3-page document return zero obligations?"**
Because it's a Past Performance Questionnaire — a form. Zero occurrences of
"shall" or "must". Zero is the right answer; the system says so rather than
inventing something.

**"What's the security story?"**
Three things: (1) PII is screened *before* storage — `/documents/scan` returns
masked findings and stores nothing; the user confirms knowingly. (2) Every
document is hard-deleted after 3 days — file *and* rows, cascading — enforced on
boot, hourly, and on access, so it holds even if the server slept. (3) Passwords
are bcrypt-only, sessions are short-lived JWTs, secrets live in env vars.

**"What would you do next?"**
Three honest gaps, below.

## Known gaps — own these before they're asked

1. **Eval precision/recall is not measured.** The extraction quality numbers need
   Kaliza's labelled eval set; we have *verification* rate (quote really exists),
   not *extraction accuracy* (did we find every obligation, and are they right?).
   Don't conflate the two on stage — 100% verified ≠ 100% correct.
2. **These numbers use the mock extractor.** `extraction/adapter.py` falls back to
   a keyword mock when `extraction/extractor.py` / `ANTHROPIC_API_KEY` are absent.
   Mock output is deliberately marked `confidence: 0.55`. Re-measure with the
   real extractor wired in.
3. **Cross-page clauses aren't stitched.** `segment.py` works within a page, so a
   clause spanning a page break becomes two chunks. It doesn't corrupt citations
   (each half cites correctly) — it just splits one clause in two.

Smaller: retention sweep is in-process (a restart-resilient job is the scale-up
path); `process_document` runs synchronously on upload (single call site, ready
to move behind a queue).

## Live demo commands

```bash
python scripts/smoke_test.py                  # the whole story, 5/5 clean
uvicorn api.main:app --reload                 # http://localhost:8000/docs
RETENTION_DAYS=0 uvicorn api.main:app         # prove the retention story
python ingestion/extract_pdf.py data/samples/77670.pdf   # coordinates, page 1
```
