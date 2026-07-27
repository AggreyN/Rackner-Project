# Rackner FDI — Shared Schema (Source of Truth)
**Team Anvil · lock this before Week 2.** Commit at repo root as `SCHEMA.md`.

This file is the single contract between the three roles. If a field changes, it
changes **here first**, then in `schemas.py` (backend) and `types.ts` (frontend)
to match. Nobody invents field names locally.

- **Kaliza (AI)** produces `Analysis` (which contains `Obligation[]` and `CompatibilityFactor[]`).
- **Aggrey (Backend)** stores these in Postgres and returns them from the API using these exact names; also produces `Opportunity`, `SpendSummary`, `Contact`.
- **Remy (Frontend)** renders these; `types.ts` mirrors this file 1:1.

Naming rules: `snake_case` on the wire (JSON/DB/Python). `types.ts` uses the same
`snake_case` keys so no mapping layer is needed. All money is a number in USD.
All dates are ISO-8601 strings (`"2026-08-30"`).

---

## Analysis
The top-level object Kaliza's LLM produces for ONE opportunity the user opened.

| Field | Type | Notes |
|---|---|---|
| `opportunity_id` | string | FK to `Opportunity.id` |
| `compatibility_score` | number | 0–100, derived from the weighted factors |
| `verdict` | enum | `"pursue"` (≥70) · `"conditional"` (50–69) · `"no_bid"` (<50) |
| `summary` | string | 1–2 sentence plain-English take |
| `factors` | CompatibilityFactor[] | the scoring breakdown |
| `obligations` | Obligation[] | key requirements, each cited |
| `spend` | SpendSummary \| null | from USAspending (Aggrey fills) |
| `contact` | Contact \| null | from email discovery (Aggrey fills) |
| `generated_at` | string | ISO-8601 timestamp |

## CompatibilityFactor
One row of the score. Weights must sum to 1.0.

| Field | Type | Notes |
|---|---|---|
| `name` | string | e.g. `"Technical capability"` |
| `weight` | number | 0–1 (the 8 weights sum to 1.0) |
| `score` | number | 1–5 (integer or one decimal) |
| `rationale` | string | **required** — the cited "why" |

Canonical factor set + weights (v1, from Rackner's PWin model):
`technical_capability` 0.20 · `mission_alignment` 0.15 · `past_performance` 0.15 ·
`contract_vehicle_access` 0.10 · `set_aside_eligibility` 0.10 ·
`incumbent_advantage_inverse` 0.10 · `pricing_size_fit` 0.10 · `time_to_respond` 0.10.

## Obligation
A single requirement pulled from the solicitation. **Every obligation must carry a
verbatim quote that exists in the source** — this is the no-hallucination guarantee.

| Field | Type | Notes |
|---|---|---|
| `plain_english_text` | string | what the contractor must do |
| `obligation_type` | enum | `report` · `deliverable` · `certification` · `flow-down` · `cyber` · `legal` · `financial` |
| `trigger_or_deadline` | string \| null | e.g. `"within 72 hours"` |
| `responsible_party` | string \| null | usually `"Contractor"` |
| `time_bucket` | enum | `immediate` · `30_days` · `quarterly` · `ongoing` · `unclear` |
| `verbatim_quote` | string | exact source words |
| `source_page` | number \| null | page the quote is on |
| `source_ref` | string \| null | e.g. clause id `"252.204-7012"` or section `"§L.2"` |
| `verified` | boolean | true if `verbatim_quote` string-matches the source |
| `confidence` | number | 0.0–1.0 |

## Opportunity
A SAM.gov solicitation. Aggrey fetches from the SAM.gov API; everyone reads it.

| Field | Type | Notes |
|---|---|---|
| `id` | string | SAM.gov notice id |
| `title` | string | |
| `agency` | string | e.g. `"DoD · DISA"` |
| `naics` | string \| null | NAICS code |
| `set_aside` | string \| null | e.g. `"HUBZone"`, `"Full & Open"` |
| `response_deadline` | string \| null | ISO-8601 date |
| `estimated_value` | number \| null | USD |
| `description` | string | short summary |
| `source_url` | string | link back to SAM.gov |

## LifecycleProfile
Parsed once from the user's uploaded Opportunity Lifecycle plan (Kaliza). Drives
scoring + suggestions. Saved to the user's profile.

| Field | Type | Notes |
|---|---|---|
| `capabilities` | string[] | technical/domain strengths |
| `target_agencies` | string[] | |
| `naics_codes` | string[] | |
| `past_performance` | string[] | prior relevant work |
| `contract_vehicles` | string[] | vehicles the org can use |
| `set_aside_status` | string[] | e.g. `["HUBZone"]` |
| `size_targets` | object | `{ min_value: number, max_value: number }` |

## SpendSummary
From USAspending.gov (Aggrey).

| Field | Type | Notes |
|---|---|---|
| `total_obligated` | number | USD, prior contract |
| `incumbent` | object \| null | `{ name: string, uei: string }` |
| `by_year` | array | `{ year: string, amount: number }[]` |
| `trend` | string | e.g. `"↑ growing ~24%/yr"` |

## Contact
From the email-discovery service (Aggrey). **Human-in-the-loop.**

| Field | Type | Notes |
|---|---|---|
| `name` | string | |
| `title` | string | e.g. `"Contracting Officer"` |
| `agency` | string | |
| `email` | string | best candidate |
| `confidence` | number | 0–1 (verification result) |
| `procurement_integrity_flag` | boolean | true = active solicitation, outreach is constrained |

---

## The handoff contract (what plugs into what)
- Kaliza's `extract(chunk_text) -> Obligation[]` and `analyze(opportunity, lifecycle_profile) -> Analysis`.
- Aggrey's `GET /opportunities/{id}/analysis` returns an `Analysis`; DB tables mirror these fields.
- Remy's `types.ts` mirrors this file; components read `analysis.compatibility_score`, `analysis.obligations[]`, etc.
- **The no-hallucination rule lives in the pipeline:** after Kaliza returns obligations, the backend sets `verified = (verbatim_quote in source_text)`; the UI shows unverified quotes with a warning, never as fact.
