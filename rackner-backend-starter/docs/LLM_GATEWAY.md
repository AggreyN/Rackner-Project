# LLM Gateway — implementation & usage guide

The **LLM Gateway** is the single seam between the Rackner FDI backend and the
model that reads solicitations. It produces two things, matching
[`/SCHEMA.md`](../../SCHEMA.md) exactly:

- **Obligations** — `extract(chunk_text) -> Obligation[]`
- **Analysis** — `analyze(opportunity, lifecycle_profile) -> Analysis` (score, verdict, factors, obligations)

It ships in **two modes**, chosen by one env var:

| `LLM_MODE` | What runs | Needs AWS? | Cost |
|---|---|---|---|
| `mock` (default) | Deterministic, schema-valid stand-in | No | $0 |
| `bedrock` | Real **Claude Sonnet 4.5** on Amazon Bedrock | Yes | Bedrock token pricing |

**Right now it runs in `mock`** — the whole flow (upload → analyze → render →
verify) works today with no credentials. Turning on real Claude is a config
change, not a code change: the Bedrock code is already written and in the repo.

---

## 1. Where it lives

```
app/llm/
  gateway.py        ← public API: extract_obligations(), analyze(). Routes mock↔bedrock,
                       normalizes to the schema, runs the no-hallucination verify,
                       derives score+verdict on the backend. Callers only touch this.
  mock.py           ← the no-AWS stand-in (LLM_MODE=mock)
  bedrock_client.py ← boto3 invoke_model → Claude on Bedrock (LLM_MODE=bedrock)
  prompts.py        ← the system prompts + JSON contract  ◀── Kaliza edits this
  verify.py         ← verified = (verbatim_quote appears in source_text)   [backend guarantee]
app/routes/analyses.py   ← the HTTP endpoints (below)
```

**The one rule:** the backend — not the model — sets `verified`, and the backend
— not the model — computes `compatibility_score` and `verdict`. Those are
deterministic guarantees that don't depend on trusting the model.

---

## 2. Run it as-is (mock, no AWS)

```bash
cd rackner-backend-starter && source venv/bin/activate
# .env already has LLM_MODE=mock (or leave it unset — mock is the default)
alembic upgrade head          # if you haven't already
uvicorn app.main:app --reload # http://localhost:8000/docs
```

Smoke-test the gateway (register/login first to get $TOKEN — see the root README):

```bash
# Generate an analysis for a fake opportunity
curl -s -X POST localhost:8000/opportunities/NOTICE-123/analysis \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{
    "title":"Cyber Support Services","agency":"DoD · DISA","naics":"541512","set_aside":"HUBZone",
    "source_text":"The Contractor shall report any cyber incident within 72 hours. Monthly status reports must be delivered.",
    "lifecycle_profile":{"naics_codes":["541512"],"set_aside_status":["HUBZone"],"capabilities":["cybersecurity"]}
  }' | python -m json.tool

curl -s localhost:8000/llm/status -H "Authorization: Bearer $TOKEN"   # {"mode":"mock","model_id":null}
```

You'll get a full `Analysis`: 8 weighted factors (summing to 1.0), a
compatibility score, a verdict, and cited obligations with `verified: true`
(the mock copies its quotes out of the source, so the verify path passes).

---

## 3. Turn on real Claude (Bedrock) — the AWS side

Steps 1–2 are the gatekeepers; nothing works until Bedrock grants model access.

1. **AWS account with Amazon Bedrock** available in your region (default `us-east-1`).
2. **Request model access** to **Claude Sonnet 4.5** in the Bedrock console →
   *Model access*. It's gated per-account and can take a few minutes to approve.
3. **Credentials** on the machine running the backend, with an IAM policy allowing
   `bedrock:InvokeModel` on the model ARN. Provide them the usual AWS way:
   - env vars `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (+ `AWS_SESSION_TOKEN` if temporary), **or**
   - an AWS profile, **or**
   - an IAM role (on ECS/EC2 in production — the preferred option).
4. **Set env vars** in `.env`:
   ```bash
   LLM_MODE=bedrock
   AWS_REGION=us-east-1
   BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0
   ```
   The `us.` prefix is a **US cross-region inference profile** — it keeps
   inference inside US regions, which is what we want for federal data. Confirm
   the exact id in the Bedrock console (the date suffix can differ by account).
5. **Restart** the backend. Verify:
   ```bash
   curl -s localhost:8000/llm/status -H "Authorization: Bearer $TOKEN"
   # {"mode":"bedrock","model_id":"us.anthropic.claude-sonnet-4-5-..."}
   ```
   Then POST an analysis as above — the `[MOCK]` markers disappear and you get
   real Claude output.

**Minimal IAM policy:**
```json
{ "Version": "2012-10-17", "Statement": [{
  "Effect": "Allow", "Action": "bedrock:InvokeModel",
  "Resource": "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-5-*"
}]}
```

**Troubleshooting:**
- `AccessDeniedException` → model access not granted (step 2) or IAM missing `bedrock:InvokeModel`.
- `ValidationException: model id` → wrong `BEDROCK_MODEL_ID` for your region; copy it from the console.
- `Could not connect / NoCredentialsError` → no AWS credentials resolved (step 3).
- Bedrock is intentionally **not** mocked-over on error — a misconfigured Bedrock raises a real 500 rather than silently returning fake data.

> Note: `bedrock_client.py` uses `boto3.invoke_model` with the Anthropic Messages
> API body. An alternative is the Anthropic Bedrock SDK (`AnthropicBedrock`),
> which some teams prefer — either works; we chose boto3 to keep dependencies to
> what's already in `requirements.txt`.

---

## 4. The API (the contract other roles code against)

All routes require `Authorization: Bearer <token>`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/opportunities/{id}/analysis` | Run the gateway, persist, return an `Analysis` |
| `GET` | `/opportunities/{id}/analysis` | Latest stored `Analysis` for this user + opportunity |
| `POST` | `/llm/extract` | `{chunk_text, source_text?}` → `Obligation[]` (no DB write; for testing) |
| `GET` | `/llm/status` | `{mode, model_id}` — tells mock apart from real Claude |

`POST /opportunities/{id}/analysis` body: `source_text` (the solicitation text to
extract + verify against), optional `lifecycle_profile` (else the user's saved
one), and optional opportunity metadata (`title`, `agency`, `naics`, `set_aside`,
`description`, `source_url`) cached if we don't have that id yet.

---

## 5. How Kaliza uses it

Kaliza owns **extraction quality** — the prompts, the few-shot examples, and the
scoring rubric. She does **not** touch plumbing, persistence, or the verify/score
math. Two ways to plug in, easiest first.

### Option A (recommended): tune the prompts

Everything Kaliza needs is in **`app/llm/prompts.py`**:

- `EXTRACT_SYSTEM` — how to pull obligations (types, `time_bucket` buckets, the
  "quote exactly, don't paraphrase" rule). Add few-shot examples here.
- `ANALYZE_SYSTEM` — the 8-factor rubric and weights.
- `extract_user_prompt` / `analyze_user_prompt` — how the chunk / opportunity is framed.

Edit those, set `LLM_MODE=bedrock`, and iterate against real solicitations. No
other file changes. Prompt edits are reviewable in git.

### Option B: drop in your own extractor module

If Kaliza has standalone Python (her own model calls, post-processing, eval set),
add a module that exposes two functions and point the gateway at it:

```python
# app/llm/kaliza.py  (new file — Kaliza owns it)
def extract(chunk_text: str) -> list[dict]:
    """Return a list of obligation dicts (see the shape below).
    Do NOT set `verified` — the backend computes it."""
    ...

def analyze_factors(opportunity: dict, lifecycle_profile: dict) -> dict:
    """Return {"summary": str, "factors": [factor dict, ...]}.
    Do NOT compute compatibility_score or verdict — the backend derives them."""
    ...
```

Then in `app/llm/gateway.py`, swap the two `from app.llm import bedrock_client`
branches to call `kaliza.extract(...)` / `kaliza.analyze_factors(...)`. That's the
only wiring change; the adapter shape is identical to `mock.py`, so use
[`mock.py`](../app/llm/mock.py) as the reference implementation.

### The exact shapes Kaliza returns

**Obligation** (list one per requirement). Copy `verbatim_quote` **character-for-character** from the source:
```python
{
  "plain_english_text": str,                    # what the contractor must do
  "obligation_type": "report" | "deliverable" | "certification"
                    | "flow-down" | "cyber" | "legal" | "financial",
  "trigger_or_deadline": str | None,            # e.g. "within 72 hours"
  "responsible_party": str | None,              # usually "Contractor"
  "time_bucket": "immediate" | "30_days" | "quarterly" | "ongoing" | "unclear",
  "verbatim_quote": str,                        # EXACT source words (verify depends on this)
  "source_page": int | None,
  "source_ref": str | None,                     # clause id e.g. "252.204-7012"
  "confidence": float,                          # 0.0–1.0
  # NO "verified" — the backend sets it
}
```

**CompatibilityFactor** (return all 8; weights must sum to 1.0):
```python
{"name": "technical_capability", "weight": 0.20, "score": 4.0, "rationale": "cited why"}
# names+weights: technical_capability .20, mission_alignment .15, past_performance .15,
# contract_vehicle_access .10, set_aside_eligibility .10, incumbent_advantage_inverse .10,
# pricing_size_fit .10, time_to_respond .10
```

### What the backend does for her (so she doesn't have to)

- **Verifies** every quote against the source and sets `verified` (`app/llm/verify.py`).
- **Derives** `compatibility_score` (0–100) and `verdict` (pursue ≥70 / conditional 50–69 / no_bid <50) from her factors (`app/schemas.py`).
- **Persists** and serves the `Analysis`.

### Testing her output in isolation

```bash
# Does her extractor return schema-valid, verifiable obligations?
curl -s -X POST localhost:8000/llm/extract -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"chunk_text":"The Contractor shall submit a monthly report."}' | python -m json.tool
```
Each obligation should come back with `verified: true` when the quote is copied
exactly from the input. If it's `false`, the quote was paraphrased — fix the
prompt/extractor, not the backend.

### Rules of the road (why they exist)

- **Quote exactly.** The verify check is a literal (whitespace-normalized) match. Paraphrase → `verified: false` → the UI shows it with a ⚠, never as fact.
- **Don't set `verified`, don't compute `score`/`verdict`.** The backend owns those so the guarantees can't be undermined by the model.
- **Use `LLM_MODE=mock` for frontend/dev work** — no key, no cost, instant, schema-valid.
