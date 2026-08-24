# Rackner FDI — Feature Overview

**Federal Document Intelligence**: find federal opportunities, read the full
solicitation package, score it against your company, and interrogate it with an
AI that cannot misquote its source.

Live app: https://main.d3rvrftm36ntnq.amplifyapp.com
Stack: Next.js (AWS Amplify) · FastAPI (ECS) · PostgreSQL (RDS) · Claude Sonnet 4.5 (Amazon Bedrock) · S3 · Textract · Cognito

*Last updated 2026-08-24.*

---

## 1 · Opportunity discovery

- **Live SAM.gov search** — keyword search returns structured, comparable cards
  (agency, office, NAICS, set-aside, response deadline, days-to-close) instead
  of raw listings. Up to 100 notices per query.
- **Actionable notice types only** — the feed defaults to Solicitations,
  Combined Synopsis/Solicitations, and Sources Sought (SAM `ptype=o,k,r`), so
  award notices and administrative postings don't dilute results. Filtering
  happens server-side at SAM; users can still narrow to one type.
- **Runway floor** — notices closing too soon to prepare a real response are
  hidden (default: less than 90 days out). Sources Sought without a deadline are
  always kept. Tunable per deployment, or disabled with `SAM_MIN_RUNWAY_DAYS=0`.
- **Recompete radar** — existing USAspending awards whose period of performance
  ends 12–18 months out: early enough to shape the requirement and meet the
  contracting officer. Cards show the incumbent and current award value. These
  are opportunities *before* they become solicitations.
- **Suggested feed** — ranked against your uploaded lifecycle plan (NAICS
  hierarchy partial credit, agency targets, set-aside eligibility, capability
  keywords). With no plan on file it degrades to an unranked market view rather
  than an error.
- **Search results are a real page** — search state lives in the URL, so results
  are shareable and the browser Back button returns to them.

## 2 · Fit scoring that converges

- **One number, most-truthful source wins.** A card's fit score comes from the
  best evidence available: a completed analysis first, then a cached AI
  pre-screen, then a heuristic. Once the researched number exists, the card and
  the analysis screen agree — no more "69 on the list, 87 when I open it."
- **Estimates are labeled as estimates** so a first-pass triage number is never
  mistaken for a researched verdict.
- **AI pre-screen** — batched scoring of card metadata across a result page,
  cached per user, so ranking is stable across pages and days.

## 3 · Full-document intelligence

- **Whole-package ingestion** — opening an opportunity pulls the notice
  description *and every attachment* (SOW, instructions, clause sets) through
  the PDF pipeline. Analysis, chat, and citations read the real contract, not a
  summary blurb. Caps: 8 attachments per notice, 25 MB per file, 60 MB total.
- **OCR for scanned solicitations** (optional, `OCR_MODE=textract`) — image-only
  PDFs, which otherwise extract to nothing, become readable and citable. Only
  pages with no text layer are OCR'd, so digital pages keep byte-exact text.
- **Pay-once caching** — each package is fetched and parsed once, ever. Dead
  links are remembered and never re-attempted; a spent daily quota retries on a
  fresh-quota day instead of re-billing every page view.
- **Partial documents say they're partial** — "6 of 8 contract attachments
  loaded," with the reason and the fact that the rest arrive on a later visit. A
  truncated contract never silently poses as the whole thing.
- **Grow-only rebuilds** — grounding text never changes underneath a citation a
  user already saw. When more of the package arrives, affected analyses are
  regenerated rather than left pointing at text that moved.
- **Clause-aware sectioning** — citations name a real place in the contract
  (`Section C`, `C.3.1`, `252.204-7012`, `L.2`), uniquely suffixed when packages
  repeat clause numbers. Documents with no heading structure cite to a specific
  page rather than one unusable blob.

## 4 · AI analysis (PWin scoring)

- **Eight-factor weighted model** — technical capability, mission alignment,
  past performance, vehicle access, set-aside eligibility, incumbent advantage
  (inverse), pricing/size fit, time to respond. Each factor carries a 1–5 score
  with a written rationale citing actual evidence; weights sum to 1.0; the
  0–100 score and `pursue / conditional / no_bid` band are computed by the
  backend, never by the model.
- **Evidence-only scoring** — factors with no supporting evidence score
  conservatively and say so. Live example: the FDA NextGen Cyber package scores
  **95.0 pursue** against a matching capability profile, and **41.2 no-bid**
  against a business-development-services profile — the same document, correctly
  scored differently per company.
- **Obligation extraction** — every "the Contractor shall…" across the whole
  package becomes a structured obligation: plain-English statement, type, time
  bucket, deadline label, and a **verbatim quote with citation**. Real scale:
  **483 obligations from one FDA package, 474 verified**.
- **Built for big documents** — extraction fans out 8 sections at a time; a
  throttled section is retried then skipped rather than failing the run;
  duplicate generations are impossible (single-flight plus a database
  uniqueness constraint); results cache per user. First analysis of a monster
  package takes a few minutes behind a live progress state, every later view is
  instant, and a background pre-warm usually finishes before the user clicks.

## 5 · Anvil AI — grounded chat

- **"Ask Anvil Anything"** about the solicitation in front of you, in an inline
  panel or a draggable floating window that keeps the analysis and the document
  visible while you interrogate it.
- **Verified citations** — every claim cites a section with a verbatim quote.
  The backend re-verifies each quote as an exact, character-for-character
  substring of the text it serves; the model cannot mark its own homework.
  Clicking a citation scrolls the reader to that passage and highlights the
  exact sentence — guaranteed to land, because the highlight is a plain string
  match on the identical text.
- **Honest when the document is silent** — "the document does not specify…"
  with zero fabricated citations.
- **Conversational** — follow-ups resolve through chat history ("how fast must
  we do *that*?"), but history is context only and can never become a citable
  source. Long transcripts are capped server-side.
- **Never blank, never raw errors** — truncated model responses are salvaged,
  total failures become an explicit "ask again," and overload becomes a clean
  retriable message. On huge packages the question-relevant sections are
  selected to fit budget.

## 6 · Bring your own contracts

- **PDF import** — upload a contract that isn't on SAM.gov (an agency-emailed
  RFP, a teaming partner's package) and get the full product on it: fit score,
  obligations, Anvil chat, click-to-cite, identical to a SAM notice.
- **Private by default** — imported opportunities belong to the uploader alone.
  They never appear in shared lists and return "not found" to anyone else.
- **No confusing duplicates** — re-uploading the same file opens the existing
  record. Title, agency, NAICS, set-aside, and close date are read from the
  document's opening pages, with filename-derived fallbacks so an import never
  fails because metadata extraction did.

## 7 · Company fit — the lifecycle plan

- **Upload your capture plan (PDF)** — parsed into capabilities, NAICS codes,
  target agencies, and set-asides; stored encrypted; drives fit scores on every
  card and the suggested ranking.
- **Replace or remove it at any time.** Deletion is real: the stored file and
  every score and analysis derived from it are purged together, so numbers from
  an old profile can never resurface.
- Analyses are **per account** — each user's scores reflect their own plan.

## 8 · Saved work

- **Star any opportunity** — solicitations and recompetes alike — and reach it
  from a saved drawer on every screen. Saved items open directly, independent of
  whatever filters the feed is applying.

## 9 · Spend intelligence

- Per-opportunity **USAspending history**: fiscal-year obligation series, total
  obligated, incumbent (name and UEI), and trend percentage — the "is this
  program growing?" answer at a glance.
- Keyed on the incumbent, which is the number that matters for a recompete.
  Where there is no incumbent to key on, the panel stays empty rather than
  showing an invented or misleading total.

## 10 · Contact discovery

- Contracting-officer contacts from SAM.gov's own point-of-contact data (real
  published emails, high confidence), with pattern inference strictly
  confidence-capped below it. **Nothing is ever guessed silently** — no contact
  means "no contact found."
- **Procurement Integrity Act guard** — while a solicitation's response window
  is open, the panel surfaces the outreach restrictions and keeps a human in the
  loop. The flag is computed from today's date, so it switches off when the
  window actually closes.
- **Optional, disclosed email verification** (off by default): when
  `EMAIL_VERIFY_PROVIDER` is set (Generect or Hunter), *inferred* addresses —
  never SAM-published ones — are checked before serving. Provably nonexistent
  candidates are dropped; a confirmed one may rise to 0.75 confidence, still
  visibly below the published tier. A daily call cap and per-contact TTL bound
  the spend, every failure degrades to unverified, and the response says what
  was checked and when. **No third-party lookups of any kind while the flag is
  off.**

## 11 · Security & platform

- **Amazon Cognito authentication** — RS256-signed ID tokens validated against
  the pool's public keys, with rotation handling and throttled key refetches;
  passwords never touch the application database. Sessions that expire mid-use
  redirect cleanly with an explanatory banner instead of filling the app with
  errors.
- **Gov-safe AI path** — Claude runs through Amazon Bedrock on a US
  cross-region inference profile, authorized by an IAM task role: no API keys in
  code, token counts logged but never prompt text.
- **Fail-soft everywhere** — every external dependency (SAM.gov, USAspending,
  Bedrock, Textract, the database itself) degrades to a named, actionable error
  or a cached fallback. An outage never renders as "no results," and a blank
  panel or bare 500 is treated as a bug.
- **Cost and quota guardrails** — every expensive path is capped and every
  skipped item is logged rather than silently truncated. Repeat searches inside
  a 12-hour freshness window cost **zero** SAM.gov quota, which is what lets a
  10-call/day key survive a working day.
- **Privacy by construction** — imported documents and lifecycle plans are
  scoped to their owner on every route; logs carry request IDs and route
  templates, never tokens, document text, or the specific notices a user viewed.
- **Operational hygiene** — migrations run on container boot with real errors
  surfaced, JSON logs, secrets from env/Secrets Manager, least-privilege IAM,
  non-root container, encryption at rest and in transit.
- **Zero-AWS demo mode** — mock LLM plus local auth runs the entire app on a
  laptop with deterministic, schema-identical data: no AWS account, no keys, no
  cost. `GET /llm/status` always reports whether a session is on real Claude.

## 12 · Quality engineering

- **438 backend tests** run on **both SQLite and PostgreSQL** against the real
  migration chain, plus 25 opt-in live suites (Bedrock, Cognito, Textract,
  SAM.gov, USAspending) behind explicit flags so they never cost money by
  accident. A guard blocks live government API calls from the offline suite.
- **50 Playwright journeys across 3 device sizes** (150 executions) on the
  production build — sign-in, search, citation highlighting, chat, bookmarks,
  import, recompete radar, session expiry, and large-document performance
  budgets.
- **Contract test** — parses the frontend's `types.ts` directly and diffs it
  against the backend's schemas in both directions, then asserts every route the
  client calls is actually served. The two sides cannot drift silently.
- **Grounding is tested against real federal solicitation PDFs** and against the
  live model, not just fixtures.
- Every major feature ships through **adversarial review**: independent agents
  try to break the change, findings are verified by refutation before they're
  accepted, and each confirmed finding lands with a regression test. Recent
  catches include cache races, quota burns, stale-score persistence, and
  truncation blanking — all found before users saw them.

---

*Contract reference: `SCHEMA_v2.md` (source of truth, mirrored by
`frontend/src/lib/types.ts`). Cost model: `COSTS.md`. Ops runbooks:
`scripts/warm_demo_cache.py` (pre-demo cache warm), `scripts/verify_live.sh`
(one-command live end-to-end check).*
