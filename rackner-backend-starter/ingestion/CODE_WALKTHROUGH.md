# `ingestion/` — PDF → structured text → clause chunks

> This is the front of the pipeline (Aggrey's area). It takes a raw PDF and turns it into something the extractor can reason about: text that still knows **what page and character offset it came from**. That traceability is what lets the frontend highlight the exact source of every obligation.

Files: `extract_pdf.py`, `segment.py`.

---

## `extract_pdf.py` — read the PDF, keep the page numbers

Uses **PyMuPDF** (imported as `fitz`) to pull text out page by page.

- `PageText` (dataclass) — `page_number` (1-based, human-friendly) + `text`. The whole point: text never loses its page.
- `extract_pages(pdf_path)` — opens the PDF, iterates pages, returns a `list[PageText]`. This is the function the whole pipeline is built on (`pipeline/run.py` imports it).
- `main()` + the `__main__` block — lets you run it standalone as a smoke test: `python ingestion/extract_pdf.py data/samples/x.pdf` prints a 400-char preview per page.

**Why it matters / talking point:** "We deliberately keep the page number attached to every chunk of text from the very first step. Citations are a product requirement, not an afterthought — so page-tracking starts here, at ingestion."

**Likely question — "What about scanned PDFs with no text layer?"** → `get_text()` returns empty for image-only pages; the standalone preview even prints a hint about that. OCR (pytesseract/pdf2image) is the planned Week-10 fallback — the dependencies are already listed but commented out in `requirements.txt`.

**Likely question — "Why PyMuPDF over pdfplumber?"** → PyMuPDF is fast and reliable for the text layer. `pdfplumber` (also in requirements) is there for tables and character-level coordinates when we add span-level highlighting.

---

## `segment.py` — split page text into FAR/DFARS clauses

Sits between `extract_pdf.py` (Aggrey, unchanged) and the extractor (Kaliza, unchanged). It slices each page into **clause chunks** so the extractor works on coherent units, and so every obligation can point back to a clause reference.

- `CLAUSE_REF` (regex) — matches clause numbers like `52.204-21` and `252.204-7012`, with an optional `FAR`/`DFARS` prefix. (52.x = FAR, 252.x = DFARS.)
- `Chunk` (dataclass) — `clause_ref` (or `None` for narrative text between clauses), `text`, `page`, `char_start`, `char_end`. The offsets are what survive all the way to a frontend highlight.
- `segment_pages(pages)` — for each page:
  1. Find all clause references on the page.
  2. If there are none, the whole page is one **narrative** chunk (`clause_ref=None`).
  3. Otherwise, any text *before* the first reference becomes a narrative chunk, then each clause reference starts a new chunk that runs until the next reference (or end of page).

**Why it matters / talking point:** "Segmentation gives the extractor bounded, meaningful units instead of a wall of text, and it stamps each chunk with the clause number, page, and character range — so an obligation isn't just 'trust me,' it's 'clause 252.204-7012, page 14.'"

**Known limitation we own (say it before they ask):** "v1 segments *within* a page. A clause that spans a page break isn't stitched yet — that's a tracked v2 item. It doesn't affect correctness of citations, just occasionally splits one clause into two chunks."

**Likely question — "Why regex and not an LLM to find clauses?"** → Clause numbers have a strict, well-known format — regex is exact, instant, and free. We save the LLM budget for the part that actually needs judgment: turning clause text into plain-English obligations.
