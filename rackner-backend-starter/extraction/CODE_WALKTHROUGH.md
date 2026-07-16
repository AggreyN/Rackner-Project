# `extraction/` — the seam to the AI extractor

> This folder is a **boundary**, not a big pile of logic. Its whole job is to isolate the rest of the backend from Kaliza's AI extractor so the two can evolve independently — and so the app never breaks when the extractor is absent, mid-change, or has no API key.

Files: `adapter.py` (ours). `extractor.py` is Kaliza's real Claude-based extractor — see the wiring note at the bottom.

---

## `adapter.py` — adapter + enrichment

Two responsibilities:

### 1. Route to the real extractor, or fall back to a mock
`extract_obligations(chunk_text)`:
- Tries to import Kaliza's `extract` from `extraction.extractor`.
- If it's present **and** an `ANTHROPIC_API_KEY` is set → use the real extractor.
- Otherwise → a deterministic **mock** (`_mock_extract`) that finds "shall"/"must" sentences and emits one obviously low-confidence (`0.55`) obligation, clearly marked.

`_mock_extract` keeps the entire app runnable end-to-end for frontend/UI work with **no API key and no AI code** in place.

### 2. Enrich every obligation with the intelligence-layer fields
`enrich(raw)` takes one extracted obligation and adds:
- `roles` — via `core/roles.classify_roles` (which teams care about it).
- `category` — via `_CATEGORY_BY_TYPE`, a rule-based map from obligation type → legal/security/reporting/deliverable/financial.
- `time_bucket` — via `_time_bucket`, which reads the trigger/deadline text for cues ("72 hours" → immediate, "30 days" → 30_days, "quarterly/annual" → quarterly, else ongoing/unclear).

Everything Kaliza returns is preserved (`**raw`) and we only *add* fields — we never mutate her output.

**Why it matters / talking point:** "This is the adapter pattern. The pipeline depends on *our* stable function `extract_obligations`, never on Kaliza's file directly. Her extractor can change signature, be rewritten, or not exist — the app still runs. This is what let backend, frontend, and the AI work happen in parallel without blocking each other."

**Likely question — "What's the mock for? Isn't that fake data?"** → It's clearly labeled low-confidence and only runs when there's no real extractor/key. Its purpose is a working demo and unblocked frontend development, not to fake results in production.

**Likely question — "Why derive category/time_bucket with rules instead of asking the model?"** → They're cheap, deterministic, and explainable, and they keep Kaliza's schema focused on the hard part (finding the obligation + the quote). Both are single-function swaps if we later want the model to do it.

---

## Wiring note (know this — it's a real open item)

`adapter.py` imports Kaliza's extractor as `from extraction.extractor import extract`, i.e. it expects the file at **`rackner-backend-starter/extraction/extractor.py`**. In the latest pull, Kaliza's `extractor.py` landed at the **repo root** instead. Until it's moved (or the import path is reconciled), the import fails and the adapter uses the mock.

The failing import is intentionally guarded (`try/except ImportError`) and carries a `# type: ignore[import-not-found]` so the type-checker doesn't flag the optional dependency. **Nothing crashes** — the app just runs on the mock until the extractor is wired in. This is a one-line fix once we decide the canonical location.
