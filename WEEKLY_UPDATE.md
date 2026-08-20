# Rackner FDI — Weekly Update (Aug 14 – Aug 20, 2026)

_Everything shipped this week, in the order it landed. All of it is deployed
and live-verified on the public stack. Backend tests grew 333 → **378** (both
SQLite and Postgres); browser tests 105 → **109**._

---

## Anvil AI: chat that never goes blank *(Aug 14)*

The chat blanked out on long answers over the giant FDA package. Root cause:
answers truncated at the model's output cap, the broken response parsed to
nothing, and users got empty bubbles.

- Truncated responses are **salvaged** (the answer text survives the cut);
  total garbage becomes an explicit "ask again" — a blank answer is now
  impossible, guaranteed at both the backend and the UI.
- Doubled the answer headroom; monster documents send the sections
  **relevant to the question** instead of the whole 200KB+ package each turn.
- Model overload says so plainly instead of surfacing a raw 500.
- The assistant is now branded **Anvil AI** — "Ask Anvil Anything about this
  contract…".
- Alongside: Remy's demo hardening (session-expiry redirects, big-package
  rendering performance, first-generation messaging) merged and verified.

## Fit scores that converge instead of mislead *(Aug 17)*

The card said 69 while the full analysis said 87 — two instruments sharing
one unlabeled gauge.

- **Once you've analyzed an opportunity, its card shows the analysis score**
  (`fit_source: "analysis"`, solid badge) — card and analysis screen can
  never disagree again.
- Everything else is a labeled **estimate**: a dashed "~72 est." badge,
  scored by a **batched AI pre-screen** (one model call per search page,
  metadata only, zero SAM quota, cached per user, invalidated when the plan
  changes). Heuristic fallback everywhere the model shouldn't run.
- Live proof: the FDA card now reads 95.0/87.5 from real analyses.

## Quota-immune search *(Aug 17–19)*

- **Search freshness ledger**: a query anyone ran in the last 12 hours serves
  entirely from cache — **zero SAM.gov calls** on repeat searches and
  dashboard loads. Only genuinely new or expired queries spend quota.
- **The recompete radar joined the ledger** (Aug 19): dashboard loads went
  from ~8.7s of live USAspending pagination to **0.2s** from cache, and an
  outage serves stale rows instead of a blank panel.

## Search results are a real page *(Aug 18)*

The YouTube model: searches now live at URLs (`/?q=cyber`), so **Back from a
solicitation returns to your results** (query intact) instead of resetting to
the home page. Results URLs are shareable and refreshable; the re-fetch on
Back is free via the ledger.

## The bug audit *(Aug 19)* — 10 confirmed bugs + security, all fixed

A four-lens adversarial audit (zero SAM calls, local-only) found and we fixed:

- **Frozen partial documents** — one transient download hiccup permanently
  marked attachments "resolved"; documents stayed incomplete forever,
  silently. Transient failures now retry; only truly-dead links resolve.
- **The vanishing dashboard** — cached rows dropped out of the feed for 12h
  windows because live refreshes never re-stamped them as fresh.
- **Three outage classes**: out-of-range scores permanently 500ing an
  analysis; DB connections held hostage through multi-minute generations
  (~15 concurrent = sitewide outage); a cache-upsert race.
- **Trust bugs**: re-uploading a lifecycle plan now resets your analyses too
  (old-profile verdicts no longer masquerade as current); text-less
  attachments no longer trigger rebuilds that wiped everyone's analyses.
- **Security**: the real SAM key had been committed to GitHub in
  `.env.example` since Aug 3 (scrubbed — **rotation still pending**), and
  leaked into user-visible error messages (now redacted at the source).
- Plus a minors batch: no more wedged search button, chat error bubbles kept
  out of model history, "Closed" instead of "Closes in −12 days", friendlier
  analysis-wait messaging, and a test suite that physically cannot touch
  live government APIs.

## Accounts & profile management *(Aug 19–20)*

- **Usernames** — display names live in Cognito (`name` attribute) and flow
  into the app automatically; set one with
  `scripts/set_cognito_username.sh <email> "Name"`. The top bar now greets
  **"Welcome, Team Anvil"**; avatar initials follow the name.
- **Remove plan** — a delete button next to *Replace plan* (with
  confirmation), backed by a new `DELETE /profile/lifecycle` endpoint that
  removes the plan, its S3 file, and everything scored against it. Used it
  to clean the demo plan off `test@rackner.com`.

## Reference docs added this week

- **`FEATURES.md`** — full product feature overview (demo crib sheet).
- **`COSTS.md`** — operating cost model: ~$85–345/month at 6 users
  (4–17% of the $2k budget); capacity ≈ 40 heavy users.
- **`SCHEMA_v2.md`** kept current: `fit_source`, `username`,
  `DELETE /profile/lifecycle`.

---

## Open items

| Item | Owner |
|---|---|
| **Rotate the SAM.gov API key** (public in git history since Aug 3) | Aggrey/admin |
| Pre-demo cache warm, morning of **Aug 27** (`scripts/warm_demo_cache.py`) | Aggrey + Claude |
| Bug-audit round 2 (in progress; report pending) | Claude |
| Higher-tier SAM key from Rackner (10/day is tight) | Team → Rackner |
| Post-demo: billing alert + infra teardown | Aggrey/admin |
