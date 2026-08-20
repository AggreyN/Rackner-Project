# Rackner FDI — Operating Cost Model

_Last updated 2026-08-17 · basis: Claude Sonnet 4.5 on Amazon Bedrock at
$3 / million input tokens, $15 / million output tokens · always-on infra in
us-east-2._

The core cost property of the architecture: **spend tracks *novel work*, not
clicks.** Documents are ingested once ever; analyses and fit estimates are
cached per user; only chat is pay-per-question. A team living in
already-analyzed pipelines costs cents a day.

---

## 1 · Fixed infrastructure (always-on)

| Item | Monthly |
|---|---|
| ECS Fargate task (0.5 vCPU / 1 GB) | ~$18 |
| Application Load Balancer | ~$20 |
| RDS PostgreSQL (db.t4g.micro class) | ~$15–25 |
| S3 + ECR + CloudWatch + data transfer | ~$2–5 |
| **Total fixed** | **~$55–65 / month** |

(Amplify frontend hosting is ~$0–1 at this traffic. Cognito is free at this
scale. Tear the stack down when idle → fixed cost ≈ $0.)

## 2 · Variable: AI operations (Bedrock)

| Operation | Trigger & caching | Typical tokens (in / out) | Cost |
|---|---|---|---|
| **Search pre-screen** | Once per *new* (user × opportunity); cached in `fit_estimates`, invalidated only by a new plan upload | ~8K / ~1.2K per 60-row page | **~4–5¢ per fresh page; repeat searches ≈ $0** |
| **Full analysis — typical notice** (1–10 sections) | Once per (user × opportunity); cached until the document grows | ~10–40K / ~3–8K | **~3–15¢** |
| **Full analysis — monster package** (60-section cap, hundreds of pages) | Same caching | ~150K / ~45K across ~60 calls | **~$1.00–1.20** |
| **Chat question — typical doc** | Every question (answers not cached) | ~3–10K / ~0.5–1K | **~1–3¢** |
| **Chat question — monster doc** | Context budgeted to ~120K chars | ~30–35K / ~1K | **~10–12¢** |

## 3 · Variable: everything else

| Item | Cost |
|---|---|
| SAM.gov API | $0 (quota-limited, not billed) |
| USAspending API | $0 |
| Textract OCR | $1.50 / 1,000 pages — only *scanned* pages, only once per document; ≈ $0–2/mo in practice |
| S3 storage (uploaded plans) | pennies |

## 4 · Per-user profiles

| Profile | Assumed daily activity | Model cost |
|---|---|---|
| **Heavy** (capture lead, daily driver) | 5 searches (2 fresh), 3 new analyses (1 big + 2 small), 15 chat questions | **~$2.15/day ≈ $45–50/month** |
| **Regular** | a few searches, ~1 new analysis, ~5 chat questions/day | **~$10–15/month** |
| **Occasional** (reviews the shared pipeline, asks questions) | mostly cache hits + chat | **~$2–5/month** |

First-month costs run *below* these numbers: document ingestion is shared
team-wide, and each user's analyzed pipeline compounds into cache hits.

## 5 · Scenarios vs the $2,000/month budget

| Team | Model spend | + Fixed | Total | % of budget |
|---|---|---|---|---|
| **6 users, all heavy** | ~$285 | ~$60 | **~$345** | 17% |
| **6 users, realistic mix** (2 heavy / 4 occasional) | ~$135 | ~$60 | **~$195** | 10% |
| **6 users, light/demo** | ~$25 | ~$60 | **~$85** | 4% |
| Capacity at full budget | ~$1,940 | ~$60 | $2,000 | **≈ 40 heavy users** (100+ mixed) |

## 6 · Cost levers (if headroom is ever needed)

1. **Haiku for pre-screen and chat** — ~12× cheaper per token; pre-screen
   drops to ~0.4¢/page, typical chat to fractions of a cent. One env-var-able
   change (`BEDROCK_MODEL_ID` per operation).
2. **Extraction cap** (`LLM_MAX_EXTRACT_SECTIONS`, default 60) — bounds the
   worst-case analysis cost; lower it to trade obligation depth for cost.
3. **Chat context budget** (`CHAT_MAX_SECTION_CHARS`) — already bounds
   monster-doc chat; lowering it cuts per-question cost linearly.
4. **Teardown when idle** — fixed infra → ~$0 between engagement periods.

## 7 · Pricing implication

Marginal cost per *engaged* user is dominated by **fresh analyses**
(~$1/big package). Per-seat pricing with generous-but-bounded analysis
counts — or metering big-package analyses as usage — maps cleanly onto how
costs actually accrue. At $50/seat/month, seat revenue covers the heaviest
observed usage profile with margin.
