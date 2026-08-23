# Rackner FDI — Feature Overview

**Federal Document Intelligence**: find federal opportunities, read the full
solicitation package, score it against your company, and interrogate it with a
grounded AI that cannot misquote its source.

Live app: https://main.d3rvrftm36ntnq.amplifyapp.com
Stack: Next.js (AWS Amplify) · FastAPI (ECS) · PostgreSQL (RDS) · Claude Sonnet 4.5 (Amazon Bedrock) · S3 · Textract · Cognito

---

## 1 · Opportunity discovery

- **Live SAM.gov search** — solicitations, presolicitations, sources sought,
  and BAAs, up to 100 notices per query, with agency/office, set-aside, NAICS,
  and response deadlines.
- **Recompete radar** — existing USAspending awards whose period of
  performance is ending (the 12–18-month capture window), with current award
  value and incumbent. These are opportunities *before* they become
  solicitations.
- **Suggested opportunities** — ranked against the company's uploaded
  lifecycle plan (NAICS hierarchy partial credit, agency targets, set-aside
  eligibility, capability keywords).
- **Rate-limit immunity** — every opportunity ever seen is cached. When
  SAM.gov's daily quota dies mid-session, search degrades to cached results
  with an honest notice; it never blanks and never lies about freshness.

## 2 · Full-document intelligence

- **Whole-package ingestion** — opening an opportunity pulls the notice
  description *and every attachment* (SOW, instructions, clause sets) through
  the PDF pipeline. Scanned pages are OCR'd via Amazon Textract; corrupt or
  unsupported files degrade to skipped, never to errors.
- **Pay-once caching** — each document is fetched and parsed exactly once,
  ever. Dead links are remembered and never re-attempted; a spent API quota
  retries on a fresh-quota day automatically.
- **Split-view reader** — the full text, sectioned by real clause references
  (`52.212-4`, `C.3.1`, …, uniquely suffixed when packages repeat clause
  numbers), served byte-identically to what the AI was shown. Virtualized
  rendering keeps 200-page packages smooth.

## 3 · AI analysis (PWin scoring)

- **Eight-factor weighted model** — technical capability, mission alignment,
  past performance, vehicle access, set-aside eligibility, incumbent
  advantage (inverse), pricing/size fit, time to respond. Each factor carries
  a 1–5 score with a written rationale citing actual evidence; weights sum to
  1.0; the 0–100 score and `pursue / conditional / no_bid` band are computed
  by the backend, never by the model.
- **Evidence-only scoring** — factors with no supporting evidence score
  conservatively and say so. Live example: the FDA NextGen Cyber package
  scored 73.8 *pursue* on genuine capability overlap, while a WOSB set-aside
  was correctly flagged as a disqualifier elsewhere.
- **Obligation extraction** — every "the Contractor shall…" across the whole
  package becomes a structured obligation: plain-English statement, type,
  time bucket, deadline label, and a **verbatim quote with citation**.
  Real-world scale: 478 obligations from one FDA package, 470 verified.
- **Built for big documents** — extraction fans out 8 sections at a time,
  a throttled section is retried then skipped rather than failing the run,
  duplicate generations are impossible (single-flight + database-enforced
  uniqueness), and results are cached per user. First analysis of a monster
  package takes a few minutes behind a live progress state; every later view
  is instant.

## 4 · Anvil AI — grounded chat

- **"Ask Anvil Anything"** about the solicitation in front of you. Answers
  come only from the document's own sections — never from general knowledge.
- **Verified citations** — every claim cites a section with a verbatim quote.
  The backend re-verifies each quote as an exact, character-for-character
  substring of the source (repairing whitespace drift, refusing anything
  else) — the model cannot mark its own homework. Clicking a verified
  citation jumps the reader to the section and highlights the exact sentence,
  guaranteed to land.
- **Honest when the document is silent** — "the document does not specify…"
  with zero fabricated citations (measured live, repeatedly).
- **Conversational** — follow-ups resolve through chat history ("how fast
  must we do *that*?"), but history is context only: it can never become a
  citable source. Long transcripts are capped server-side.
- **Never blank, never raw errors** — truncated model responses are salvaged,
  total failures become an explicit "ask again," and model-side overload is a
  clean retriable message. On huge packages, the question-relevant sections
  are selected to fit budget.

## 5 · Company fit — the lifecycle plan

- **Upload your capture plan (PDF)** — parsed into capabilities, NAICS codes,
  target agencies, set-asides; stored encrypted in S3; drives fit scores on
  every opportunity card and the suggested ranking.
- Analyses are **per-account**: each user's scores reflect their own plan.

## 6 · Spend intelligence

- Per-opportunity **USAspending history**: fiscal-year obligation series,
  total obligated, incumbent (name + UEI), and spend trend percentage —
  the "is this program growing?" answer at a glance.

## 7 · Contact discovery

- Contracting-officer contacts from SAM.gov's own point-of-contact data
  (real emails, high confidence), with pattern-inference strictly
  confidence-capped below it. **Nothing is ever guessed silently** — no
  contact means "no contact found," and active solicitations carry a
  **Procurement Integrity Act guard** requiring a human in the loop before
  outreach.
- **Optional, disclosed email verification** (off by default): when
  `EMAIL_VERIFY_PROVIDER` is set (Generect or Hunter), *inferred* addresses
  — never SAM-published ones — are checked against the provider before
  serving. Provably-nonexistent candidates are dropped; a confirmed one may
  rise to confidence 0.75, still visibly below the published tier. Every
  verification failure degrades to today's unverified behavior (a hard
  daily call cap and per-contact TTL bound the spend), and the response
  carries a `verification {provider, status, checked_at}` field so the UI
  can say exactly what was checked and when. There are **no third-party
  lookups of any kind while the flag is off.**

## 8 · Security & platform

- **Amazon Cognito authentication** — RS256-signed ID tokens validated
  against the pool's public keys (with rotation handling); the login form
  works through a backend proxy; passwords never touch the application
  database. Sessions that expire mid-use redirect cleanly instead of erroring.
- **Gov-safe AI path** — Claude runs through Amazon Bedrock (US cross-region
  inference profile), authorized by an IAM task role: no API keys in code,
  token counts logged but never prompt text.
- **Fail-soft everywhere** — every external dependency (SAM.gov,
  USAspending, Bedrock, Textract, the database itself) degrades to a named,
  actionable error or a cached fallback. A blank panel or bare 500 is treated
  as a bug.
- **Operational hygiene** — migrations run on container boot (with real
  errors surfaced, not swallowed), JSON logs with request IDs, secrets from
  env/Secrets Manager, least-privilege IAM, non-root container, encrypted
  storage (SSE + TLS to RDS).
- **Zero-AWS demo mode** — `LLM_MODE=mock` + local auth runs the entire app
  on a laptop with deterministic, schema-identical fake data.

## 9 · Quality engineering

- **345 backend tests** run on both SQLite and PostgreSQL, including a
  contract test that parses the frontend's `types.ts` directly and diffs it
  against the backend's schemas — the two sides cannot drift silently.
- **105 Playwright browser tests** on the production build, desktop and
  mobile.
- Grounding properties are tested against **real federal solicitation PDFs**
  and against the **live model** (opt-in suites for Bedrock, Cognito,
  Textract, SAM.gov, USAspending).
- Every major feature shipped through adversarial review; the review findings
  (race conditions, quota burns, truncation blanking) each carry a regression
  test.

---

*Contract reference: `SCHEMA_v2.md` (source of truth, mirrored by
`frontend/src/lib/types.ts`). Ops runbooks: `scripts/warm_demo_cache.py`
(pre-demo cache warm), `scripts/verify_live.sh` (one-command live E2E check).*
