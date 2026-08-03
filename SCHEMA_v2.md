# Rackner FDI — Shared Schema v2 (Source of Truth)

**Supersedes `SCHEMA.md` (v1).** Derived mechanically from Remy's
`frontend/src/lib/types.ts`, which the team designated authoritative after the
7/22 product reframing (opportunity capture, not document upload).

Precedence rule, unchanged from v1 but with a new arbiter:

> If a field disagrees anywhere, **`types.ts` wins.** Change it there first,
> then mirror it here, then in `app/schemas.py`. Nobody invents field names
> locally.

Naming: `snake_case` on the wire (JSON/DB/Python). `types.ts` uses the same
`snake_case` keys, so there is no mapping layer. Dates are ISO-8601 strings.
Money is a number in USD **except** `OpportunitySummary.est_value`, which is a
pre-formatted display string (see note below).

---

## Auth & profile

### User
| Field | Type | Notes |
|---|---|---|
| `email` | string | |
| `org` | string | e.g. `"rackner.com"` — derived from the email domain |
| `initials` | string | for the avatar chip |

### LifecycleProfile
Parsed from the user's uploaded Opportunity Lifecycle plan. Powers compatibility
scoring and the suggested-opportunities ranking.

| Field | Type | Notes |
|---|---|---|
| `filename` | string | original upload name |
| `uploaded_at` | string | ISO-8601 |
| `capabilities` | string[] | |
| `naics_codes` | string[] | |
| `target_agencies` | string[] | |
| `set_asides` | string[] | e.g. `["HUBZone"]` |

### Profile
| Field | Type | Notes |
|---|---|---|
| `user` | User | |
| `lifecycle` | LifecycleProfile \| null | null until a plan is uploaded |

---

## Opportunities

### OpportunityKind
`"solicitation"` · `"baa"` · `"sources_sought"` · `"presolicitation"` · `"expiring_award"`

`expiring_award` is **not** a SAM.gov notice — it is an existing USAspending
award whose period of performance is ending, i.e. a recompete that has not been
solicited yet. That is the capture window.

### OpportunitySummary
| Field | Type | Notes |
|---|---|---|
| `id` | string | SAM.gov notice id, or USAspending award id for `expiring_award` |
| `title` | string | |
| `agency` | string | |
| `office` | string \| null | |
| `solicitation_number` | string \| null | |
| `naics` | string \| null | |
| `set_aside` | string \| null | |
| `kind` | OpportunityKind | |
| `description` | string | short text for cards |
| `close_date` | string \| null | ISO date — response deadline |
| `days_to_close` | number \| null | server-computed |
| `est_value` | string \| null | **display string**, e.g. `"$8–12M / 5yr"` |
| `incumbent` | string \| null | |
| `fit_score` | number \| null | 0–100 vs. the lifecycle plan; null with no plan on file |
| `expiry_date` | string \| null | `expiring_award` only — current award PoP end |
| `months_to_expiry` | number \| null | `expiring_award` only — server-computed |
| `current_award_value` | number \| null | `expiring_award` only — total obligated |

The three recompete fields are null on live solicitations; `close_date` /
`days_to_close` are null on `expiring_award` rows.

### Search filters (query params)
`GET /opportunities/search?q=&kinds=&expiring_from=&expiring_to=`

| Param | Type | Notes |
|---|---|---|
| `q` | string | free text |
| `kinds` | string | comma-separated OpportunityKind list; omit for all |
| `expiring_from` | number | months; only `expiring_award` rows in range |
| `expiring_to` | number | months |

Filtering is **server-side** — the recompete radar queries the whole award set
and cannot be paged into the browser. Canonical capture window: 12–18 months.

---

## Analysis

### Citation
| Field | Type | Notes |
|---|---|---|
| `section` | string | e.g. `"L.2"` — matches a `SourceSection.ref`, stored **without** `§` |
| `page` | number \| null | |

### FitBand
`"pursue"` (score ≥70) · `"conditional"` (50–69) · `"no_bid"` (<50)

### FitFactor
One row of the PWin model. Weights sum to 1.0.

| Field | Type | Notes |
|---|---|---|
| `key` | string | e.g. `"technical_capability"` |
| `label` | string | e.g. `"Technical capability"` |
| `weight` | number | 0–1 |
| `score` | number | 1–5 |
| `rationale` | string | required — the cited "why" |
| `citation` | Citation \| null | |

Canonical weights (v1, retained): `technical_capability` 0.20 ·
`mission_alignment` 0.15 · `past_performance` 0.15 · `contract_vehicle_access`
0.10 · `set_aside_eligibility` 0.10 · `incumbent_advantage_inverse` 0.10 ·
`pricing_size_fit` 0.10 · `time_to_respond` 0.10.

### TimeBucket
`immediate` · `30_days` · `at_award` · `quarterly` · `ongoing` · `unclear`

(v2 adds `at_award`, which v1 lacked.)

### Obligation
Every obligation carries a verbatim quote that exists in the source — the
no-hallucination guarantee.

| Field | Type | Notes |
|---|---|---|
| `id` | number | stable within one analysis |
| `text` | string | plain-English statement of the requirement |
| `obligation_type` | string | free string, e.g. `submission`, `performance`, `certification`, `reporting` |
| `time_bucket` | TimeBucket | |
| `deadline_label` | string | display, e.g. `"Immediate · 21 days"` |
| `verbatim_quote` | string | exact source words |
| `citation` | Citation | required |
| `verified` | boolean | set by the **backend**, never the model |

### Analysis
| Field | Type | Notes |
|---|---|---|
| `opportunity_id` | string | |
| `score` | number | 0–100 |
| `band` | FitBand | derived from `score` |
| `verdict` | string | **free-text one-liner**, e.g. `"Strong fit — recommend pursue"` |
| `factors` | FitFactor[] | |
| `obligations` | Obligation[] | |

`band` and `verdict` are **both** present and are different things — `band` is
the enum, `verdict` is prose for humans.

---

## Source document (the grounding contract)

### SourceSection
| Field | Type | Notes |
|---|---|---|
| `ref` | string | `"C.3.1"` — no `§` prefix |
| `heading` | string | |
| `text` | string | **canonical string** |
| `page` | number | |

### SourceDocument
| Field | Type | Notes |
|---|---|---|
| `opportunity_id` | string | |
| `label` | string | e.g. `"Source solicitation · HC1084-26-R-0042"` |
| `sections` | SourceSection[] | |

**The grounding rule.** `SourceSection.text` is the one canonical string. The
backend sets `obligation.verified = (verbatim_quote is an exact substring of
that same text)`, and `GET /document` serves that identical string. The UI
highlights via `text.indexOf(quote)`, so for every `verified=true` obligation
that lookup must succeed. Never normalize for matching and then serve the
original. Unverified quotes are returned with `verified=false`, never dropped.

---

## Spend (USAspending.gov)

### SpendYear
| Field | Type |
|---|---|
| `fiscal_year` | string — `"FY25"` |
| `amount` | number |

### SpendSummary
| Field | Type | Notes |
|---|---|---|
| `opportunity_id` | string | |
| `years` | SpendYear[] | |
| `total_obligated` | number | |
| `incumbent` | `{name, uei}` \| null | |
| `trend_pct` | number \| null | `24` → "↑ growing ~24%/yr"; negative → declining |

---

## Contact discovery

### ContactResult
| Field | Type | Notes |
|---|---|---|
| `opportunity_id` | string | |
| `name` | string | |
| `title` | string | |
| `office` | string | |
| `email` | string | most probable candidate |
| `confidence` | number | 0–1 from the verifier |
| `active_solicitation` | boolean | Procurement Integrity Act guard — true means the UI must show outreach restrictions and require a human in the loop |

---

## Assistant

### ChatCitation
| Field | Type |
|---|---|
| `section` | string |
| `page` | number \| null |

### ChatAnswer
| Field | Type |
|---|---|
| `answer` | string |
| `citations` | ChatCitation[] |

---

## Routes (the 11 the frontend calls)

| Method | Path | Returns |
|---|---|---|
| POST | `/auth/login` | `{access_token}` — exact key |
| GET | `/profile` | Profile |
| POST | `/profile/lifecycle` | LifecycleProfile — **multipart** file upload |
| GET | `/opportunities/search?q=&kinds=&expiring_from=&expiring_to=` | OpportunitySummary[] |
| GET | `/opportunities/suggested?kinds=&expiring_from=&expiring_to=` | OpportunitySummary[] |
| GET | `/opportunities/{id}` | OpportunitySummary |
| GET | `/opportunities/{id}/analysis` | Analysis — **GET-only, generate-on-miss** |
| GET | `/opportunities/{id}/document` | SourceDocument |
| GET | `/opportunities/{id}/spend` | SpendSummary |
| GET | `/opportunities/{id}/contact` | ContactResult |
| POST | `/opportunities/{id}/chat` | `{question}` → ChatAnswer |

Plus `/`, `/health`, and `POST /auth/register` (kept for seeding; the UI never
calls it). Everything except `/auth/login`, `/`, `/health` requires a bearer
token.

---

## v1 → v2 changes

Renames and reshapes, for anyone porting v1 code:

| v1 | v2 |
|---|---|
| `Analysis.compatibility_score` | `Analysis.score` |
| `Analysis.verdict` (enum) | `Analysis.band` (enum) — and `verdict` becomes free text |
| `Analysis.summary`, `.generated_at`, `.spend`, `.contact` | removed from the wire type |
| `CompatibilityFactor{name,…}` | `FitFactor{key,label,…,citation}` |
| `Obligation.plain_english_text` | `Obligation.text` |
| `Obligation.source_page` + `.source_ref` | `Obligation.citation{section,page}` |
| `Obligation.trigger_or_deadline` | `Obligation.deadline_label` |
| `Obligation.responsible_party`, `.confidence` | removed |
| — | `Obligation.id` added |
| `Opportunity` | `OpportunitySummary` (+ `kind` and the recompete fields) |
| `Opportunity.response_deadline` | `close_date` (+ `days_to_close`) |
| `Opportunity.estimated_value: number` | `est_value: string` (display) |
| `Contact` | `ContactResult` |
| `Contact.agency` | `ContactResult.office` |
| `Contact.procurement_integrity_flag` | `ContactResult.active_solicitation` |
| `SpendSummary.by_year[{year,…}]` | `.years[{fiscal_year,…}]` |
| `SpendSummary.trend: string` | `.trend_pct: number` |
| `LifecycleProfile.past_performance`, `.contract_vehicles`, `.size_targets` | removed from the wire type |
| `LifecycleProfile.set_aside_status` | `.set_asides` |
| — | `filename`, `uploaded_at` added |
| — | `SourceDocument`, `SourceSection`, `Profile`, `User`, `ChatAnswer` added |

### DB ↔ wire differences (intentional)
The `lifecycle_profiles` table keeps `past_performance`, `contract_vehicles`,
`size_min`, `size_max` even though v2 does not expose them. They still feed
`pricing_size_fit` and `past_performance` scoring server-side; they are simply
not serialized. Dropping the columns would lose scoring signal for no gain.

### Open contract questions (not decided unilaterally)
1. **`ChatCitation` grounding.** The build spec asks for `verbatim_quote` and
   `verified` on chat citations so they use the same highlight path. `types.ts`
   has only `{section, page}`. Adding them is a contract change — needs Remy.
2. **Chat history.** `POST /chat` sends no prior turns, so follow-ups have no
   context. Adding `history` is a contract change — needs Remy.
3. **Analysis latency.** A real model over a 100-page solicitation can exceed
   30s and the client sets no timeout. Current approach: keep `GET` synchronous
   and cache/pre-warm. The alternative — `202` + poll — is a contract change.
