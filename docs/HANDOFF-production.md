# Production handoff — making the new frontend features real

**Context:** the frontend now ships six features (floating Anvil chat, PDF
import, per-user bookmarks + saved drawer, neutral scoring mode, click-to-cite
in the parsed source view, big-package rendering). This document lists exactly
what has to change *outside the frontend* for each one to work in production,
and who owns it.

Verified against `rackner-backend-starter/` as of this commit — the "already
works" claims below were checked in the code, not assumed.

---

## TL;DR

| Feature | Backend work needed | Owner |
|---|---|---|
| Floating Anvil chat window | **None** — uses existing `/chat` | — |
| Click-to-cite source view | **None** — uses existing `/document` | — |
| Neutral mode (no lifecycle plan) | **None** — already correct server-side | — |
| Recompete window filters | **None** — already wired | — |
| Bookmarks / saved drawer | New table + 3 routes | Aggrey |
| Remove lifecycle plan | 1 route | Aggrey |
| Import PDF | 1 route + 4 design decisions | Aggrey + Kaliza |

Two of the six are already production-correct. The only substantial item is
PDF import.

---

## Already production-ready — do not rebuild

### Neutral mode

`app/services/fit.py` already does the right thing:

```python
def score(opportunity, lifecycle) -> float | None:
    """0-100 structural overlap, or None with no plan on file."""
    if not lifecycle:
        return None
```

and `rank()` preserves the original order rather than sorting by a score that
does not exist. Both `/opportunities/search` and `/opportunities/suggested`
call through this path.

The frontend change was purely presentational: dash badges instead of numbers,
plus an explicit "nothing is scored" note so the absence reads as deliberate
rather than broken. **No backend change required.**

### Recompete window filters

`/opportunities/search` and `/opportunities/suggested` already accept
`kinds`, `expiring_from`, and `expiring_to`. The frontend sends them as query
params. Already end-to-end.

### Floating chat + click-to-cite

Both are pure frontend. The floating window renders the same conversation as
the inline panel (shared `useChat` state) and posts to the existing
`POST /opportunities/{id}/chat`. Click-to-cite reads the existing
`GET /opportunities/{id}/document` and highlights by exact substring match.

---

## Aggrey — backend items

### 1. Bookmarks (smallest — suggest doing first)

Nothing exists today: no table, no routes.

**Schema**

```
bookmarks
  user_id         FK -> users.id
  opportunity_id  FK -> opportunities.id
  created_at      timestamptz
  UNIQUE (user_id, opportunity_id)
```

**Routes**

```
GET    /profile/bookmarks        -> ["disa-soc-0042", "navy-pcte-0118"]
PUT    /profile/bookmarks/{id}   -> 204   (idempotent save)
DELETE /profile/bookmarks/{id}   -> 204   (idempotent unsave)
```

Return bare opportunity IDs, not full objects — the frontend already resolves
each ID through `GET /opportunities/{id}`, which is cached.

**Frontend swap point:** `frontend/src/lib/bookmarks.ts` is the only file that
changes. It currently persists to `localStorage` keyed by the signed-in email.
Keep that as the offline/mock path.

Estimated: 1–2 hours.

### 2. `DELETE /profile/lifecycle`

Today `app/routes/profile.py` has `GET /profile` and
`POST /profile/lifecycle` only. Removing the plan needs a delete.

Deleting the `lifecycle_profiles` row is sufficient — scoring already
degrades to neutral automatically (see above), so nothing else has to change.

**Decision:** hard-delete the row, or soft-delete and purge the S3 object
referenced by `source_s3_key`? The plan PDF is user-uploaded business
material, so purging is probably right.

Estimated: 30 minutes.

### 3. `POST /opportunities/import` (the real work)

Accept a contract PDF that is not on SAM.gov, run the normal pipeline, and
return an `OpportunitySummary` the frontend can navigate to.

**Most of this already exists.** `POST /profile/lifecycle` already does the
upload half — reuse it directly:

- `await file.read()` + empty check -> 400
- `MAX_UPLOAD_BYTES` check -> 413
- `ingest.load_text(data, filename)`
- the "no text could be read — scanned PDF?" -> 422 path
- `storage.put(data, filename=filename, prefix=...)`

The only new part is what happens after: instead of `lifecycle_parse.parse()`,
continue into `split_sections()` -> analysis -> quote verification, exactly as
a SAM-sourced document does, and persist an `Opportunity` row plus its
`SourceDocument` / `SourceSection` rows.

**Four decisions that are not code:**

1. **ID scheme.** `imported-1` is mock-only. Production needs stable,
   non-colliding IDs — suggest `imp_<uuid4>` so an imported ID can never be
   mistaken for a SAM notice ID.
2. **Ownership / visibility.** Is an imported document private to the
   uploader, or visible to everyone at the org? This affects the
   `opportunities` table (needs an owner column if private) and every list
   query. Recommend private-to-uploader for v1 — it is the safer default and
   can be widened later.
3. **Deduplication.** Same PDF uploaded twice: create a second record, or
   content-hash and return the existing one? Hashing avoids a confusing
   duplicate list.
4. **Missing metadata.** An imported PDF has no NAICS, agency, or set-aside.
   See Kaliza's item below — the answer changes what this route returns.

**Response:** the same `OpportunitySummary` shape as any other opportunity.
The frontend routes straight to `/opportunity/{id}` on success.

Estimated: roughly a day, most of it in decisions 1–4 rather than code.

---

## Kaliza — one real product decision

`fit.score()` weights **NAICS + agency + set-aside + capability**. An imported
PDF supplies *none of the first three* — only capability text. So an imported
document either:

**(a)** scores on capability alone, producing a number that sits in the same
list as SAM-sourced scores but is not comparable to them; or

**(b)** returns `fit_score: null` and renders a dash, while obligations are
still extracted and cited normally.

**Recommendation: (b).** A 61 next to an 82 implies a comparison the inputs
cannot support, and the whole credibility story of this product is that we do
not show numbers we cannot defend. Obligations, citations, and chat all still
work — only the fit number is withheld.

If (b) is chosen, the frontend should say why, e.g. *"Imported documents are
not fit-scored — no NAICS, agency, or set-aside to compare against your
lifecycle plan."* Say the word and I will add that copy.

**Secondary question:** should the LLM infer NAICS / agency / set-aside from
the document text to fill those gaps? That is a prompt change plus an accuracy
question — and an inferred NAICS driving a fit score is a quiet way to
manufacture a number. Worth deciding explicitly rather than by default.

---

## Remy — frontend follow-ups once the above lands

1. **Delete the mock import fabrication** in `frontend/src/lib/mock.ts`. The
   real path (`importOpportunityPdf` -> `POST /opportunities/import`) is
   already written in `lib/api.ts` and needs no change.
2. **Swap `lib/bookmarks.ts`** to the real routes, keeping `localStorage` as
   the offline fallback.
3. **Add the imported-document copy** once Kaliza decides (a) or (b).

---

## Known-risk callout for the demo

**PDF import currently fabricates its analysis from the filename — it never
reads the uploaded file.** In mock mode every imported document yields the
same three obligations and the same score; only the title changes. This is
fine as a demonstration of the UI contract and dangerous if anyone reads the
obligations aloud as if they came from the document on screen.

Until `POST /opportunities/import` exists, either point the frontend at a
backend that implements it, or do not demo import. A visible "mock analysis —
not derived from this file" banner can be added in minutes if the feature
needs to stay in the demo path.
