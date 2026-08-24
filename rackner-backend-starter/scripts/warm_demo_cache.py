#!/usr/bin/env python
"""Pre-demo cache warmer — run against prod with FRESH SAM.gov quota.

Why: SAM.gov's daily key quota is small and WILL die mid-presentation. The
backend caches everything it touches (opportunities rows, built documents,
per-user analyses), so warming the cache the day before means the demo serves
from RDS with zero live SAM calls on stage.

SAM budget math (the scarce resource): each search = 1 SAM call; each detail
view = ~2 (notice lookup + description fetch). Documents and analyses cost no
SAM calls (analyses cost Bedrock cents). The --sam-budget guard stops before
the quota is torched, and any 429 stops SAM-spending immediately.

Usage (from rackner-backend-starter/):
    ./venv/bin/python scripts/warm_demo_cache.py \
        --email <demo-account-email> --password '<demo-account-password>' \
        --terms cybersecurity devsecops "cloud migration" \
        --details 5 --demo-date 2026-08-28

Warm with the SAME account the demo will log in with — analyses are per-user.
"""

from __future__ import annotations

import argparse
import sys

import requests

DEFAULT_API = "https://ra-ae606d95b03941e3afa9b31f3eb979e1.ecs.us-east-2.on.aws"
RATE_LIMIT_MARKER = "rate limited"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--terms", nargs="+", default=["cybersecurity", "devsecops", "cloud migration"])
    ap.add_argument("--details", type=int, default=5, help="opportunities to fully warm")
    ap.add_argument("--demo-date", default="2026-08-28", help="prefer close dates after this")
    ap.add_argument("--sam-budget", type=int, default=16, help="max SAM.gov calls to spend")
    ap.add_argument(
        "--limit", type=int, default=100,
        help="rows per search (one SAM call regardless — max out to stock the cache)",
    )
    args = ap.parse_args()

    s = requests.Session()
    r = s.post(f"{args.api}/auth/login", json={"email": args.email, "password": args.password}, timeout=30)
    if r.status_code != 200:
        print(f"login failed ({r.status_code}): {r.text[:200]}")
        return 1
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"

    sam_spent = 0
    sam_dead = False
    candidates: dict[str, dict] = {}

    for term in args.terms:
        if sam_dead or sam_spent + 1 > args.sam_budget:
            print(f"skipping search '{term}' — SAM budget protection")
            continue
        sam_spent += 1
        r = s.get(
            f"{args.api}/opportunities/search",
            params={"q": term, "limit": args.limit},
            timeout=120,
        )
        if r.status_code != 200:
            detail = r.json().get("detail", "") if r.headers.get("content-type", "").startswith("application/json") else r.text
            print(f"search '{term}': {r.status_code} — {detail[:120]}")
            if RATE_LIMIT_MARKER in detail:
                sam_dead = True
            continue
        # The backend's default search now returns Solicitation, Combined
        # Synopsis/Solicitation, and Sources Sought (ptype o,k,r) — BAAs no
        # longer come back by default, and sources_sought (often dateless =
        # demo-safe) is exactly worth warming.
        rows = [x for x in r.json() if x.get("kind") in ("solicitation", "sources_sought")]
        print(f"search '{term}': {len(rows)} notices (cached)")
        for row in rows:
            candidates[row["id"]] = row

    # Prefer notices still open on demo day; no close date (BAAs) counts as open.
    def demo_safe(row: dict) -> bool:
        close = row.get("close_date")
        return close is None or close > args.demo_date

    ranked = sorted(
        candidates.values(),
        key=lambda x: (not demo_safe(x), x.get("kind") != "solicitation", x.get("close_date") or "9999"),
    )
    if not ranked:
        print("no candidates from search — nothing to warm (quota already dead?)")
        return 1

    print(f"\nwarming top {min(args.details, len(ranked))} of {len(ranked)} candidates:\n")
    warmed = []
    for row in ranked[: args.details]:
        oid = row["id"]
        # detail = notice lookup + description fetch; the document build then
        # downloads the notice's attachments server-side (~1 call each, capped
        # at 8). 4 is a conservative average for budgeting.
        if not sam_dead and sam_spent + 4 <= args.sam_budget:
            sam_spent += 4
        elif not sam_dead:
            print(f"  {oid[:12]}: skipped (SAM budget)")
            continue
        detail = s.get(f"{args.api}/opportunities/{oid}", timeout=120)
        if detail.status_code != 200:
            print(f"  {oid[:12]}: detail {detail.status_code}")
            continue
        doc = s.get(f"{args.api}/opportunities/{oid}/document", timeout=120)
        sections = len(doc.json().get("sections", [])) if doc.status_code == 200 else 0
        # The Bedrock call — persisted per-user, instant on demo day.
        an = s.get(f"{args.api}/opportunities/{oid}/analysis", timeout=180)
        if an.status_code != 200:
            print(f"  {oid[:12]}: analysis {an.status_code} — {an.text[:100]}")
            continue
        a = an.json()
        obligations = a.get("obligations", [])
        verified = sum(1 for o in obligations if o.get("verified"))
        d = detail.json()
        warmed.append(oid)
        print(
            f"  ✓ {d.get('title', '?')[:55]!r}\n"
            f"      {d.get('agency', '?')[:40]} | closes {d.get('close_date') or 'open'} | "
            f"score {a.get('score')} ({a.get('band')}) | sections {sections} | "
            f"obligations {len(obligations)} ({verified} verified)"
        )

    print(f"\nwarmed {len(warmed)} opportunities; SAM calls spent ≈ {sam_spent}")
    print("demo day: open these from search results or the pipeline — everything serves from cache.")
    return 0 if warmed else 1


if __name__ == "__main__":
    sys.exit(main())
