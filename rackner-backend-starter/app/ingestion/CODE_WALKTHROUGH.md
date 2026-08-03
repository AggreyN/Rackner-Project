# `ingestion/` — PDF → structured text → clause chunks

> This is the front of the pipeline (Aggrey's area). It takes a raw PDF and turns it into something the extractor can reason about: text that still knows **what page and character offset it came from**. That traceability is what lets the frontend highlight the exact source of every obligation.

Files: `extract_pdf.py`, `segment.py`.

---

## `extract_pdf.py` — read the PDF, keep the page numbers **and word coordinates**

Uses **PyMuPDF** (imported as `fitz`) to pull text out page by page, with the pixel box of every word (Week 2).

- `Word` (dataclass) — one word plus where it sits: its character range (`char_start`, `char_end`) inside the page string, and its bounding box (`x0, y0, x1, y1`) on the page image.
- `PageText` (dataclass) — `page_number` (1-based) + `text` + `words`. The page `text` is **rebuilt from the word list**, so a slice `text[a:b]` corresponds exactly to the words whose char ranges fall in `[a, b)`. That's what makes char-offset → pixel-box mapping reliable.
- `extract_pages(pdf_path)` — opens the PDF, iterates pages, returns a `list[PageText]` with word boxes. The function the whole pipeline is built on (`pipeline/run.py` imports it).
- `boxes_for_span(page, char_start, char_end)` — the payoff: give it a character span (a clause's or an obligation's range) and it returns the pixel rectangles to highlight.
- `find_span(haystack, needle)` — locates a `verbatim_quote` in a page's text, tolerating whitespace/line-break differences. Used by the pipeline to both verify a quote and pin down where to highlight it (Week 7).
- `_ocr_words(page)` — OCR fallback for scanned pages (Week 7). Optional: with `pytesseract` + the `tesseract` binary installed, an image-only page is rendered and OCR'd into words *with* boxes, scaled back to PDF points so they share one coordinate system with the text layer. Without the toolchain it returns nothing and ingestion carries on — OCR never becomes a hard dependency.
- `main()` + the `__main__` block — standalone smoke test: `python ingestion/extract_pdf.py data/samples/x.pdf` prints a per-page word count and a sample word's char range + box.

**Why it matters / talking point:** "We keep the page number *and the coordinates* attached to every word from the very first step. Citations and span-level highlighting are a product requirement, not an afterthought — so the coordinate trail (page → char offset → pixel box) starts here, at ingestion."

**Likely question — "What about scanned PDFs with no text layer?"** → `get_text("words")` returns nothing for image-only pages, so we try the OCR fallback (`_ocr_words`), which puts OCR'd words into the *same* coordinate system; `PageText.ocr` marks pages that came from OCR. Of the 5 sample SAM.gov PDFs, `W50S8J26QA017.pdf` and `W912HN26RA012.pdf` are image-only — they're exactly the ones OCR is for. The dependencies stay optional (commented in `requirements.txt`) so a machine without `tesseract` still runs everything else.

**Likely question — "Why rebuild the text from words instead of using `get_text()`?"** → The plain-text blob and the word list have *different* character positions, so offsets from one don't index into the other. Rebuilding `text` from the words keeps a single, consistent coordinate system end to end.

**Likely question — "Why PyMuPDF over pdfplumber?"** → PyMuPDF is fast and reliable and gives word boxes directly. `pdfplumber` (also in requirements) is there for tables and finer character-level coordinates if we need them.

---

## `segment.py` — split page text into FAR/DFARS clauses

Sits between `extract_pdf.py` (Aggrey, unchanged) and the extractor (Kaliza, unchanged). It slices each page into **clause chunks** so the extractor works on coherent units, and so every obligation can point back to a clause reference.

- `CLAUSE_REF` (regex) — matches clause numbers like `52.204-21` and `252.204-7012`, with an optional `FAR`/`DFARS` prefix. (52.x = FAR, 252.x = DFARS.)
- `Chunk` (dataclass) — `clause_ref` (or `None` for narrative text between clauses), `text`, `page`, `char_start`, `char_end`, and `boxes` (the word rectangles covering the chunk's span, resolved via `extract_pdf.boxes_for_span`). The offsets and boxes are what survive all the way to a frontend highlight. `boxes` is empty for pages with no word layer (scanned images). Persisting boxes onto the `clauses` table is Week 7; Week 2 makes them available at the chunk level.
- `segment_pages(pages)` — for each page:
  1. Find all clause references on the page.
  2. If there are none, the whole page is one **narrative** chunk (`clause_ref=None`).
  3. Otherwise, any text *before* the first reference becomes a narrative chunk, then each clause reference starts a new chunk that runs until the next reference (or end of page).

**Why it matters / talking point:** "Segmentation gives the extractor bounded, meaningful units instead of a wall of text, and it stamps each chunk with the clause number, page, and character range — so an obligation isn't just 'trust me,' it's 'clause 252.204-7012, page 14.'"

**Known limitation we own (say it before they ask):** "v1 segments *within* a page. A clause that spans a page break isn't stitched yet — that's a tracked v2 item. It doesn't affect correctness of citations, just occasionally splits one clause into two chunks."

**Likely question — "Why regex and not an LLM to find clauses?"** → Clause numbers have a strict, well-known format — regex is exact, instant, and free. We save the LLM budget for the part that actually needs judgment: turning clause text into plain-English obligations.
