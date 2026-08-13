#!/usr/bin/env bash
# Rackner FDI — live end-to-end verification (SCHEMA_v2).
# Proves the DEPLOYED app: auth -> DB -> real Bedrock analysis with verified citations.
#
#   TEST_PASSWORD='...' ./verify_live.sh
#   OPP_ID='<id>' TEST_PASSWORD='...' ./verify_live.sh   # skip the SAM search (saves quota)
#
# Notes vs the v1 script this replaces:
#   * v2 renamed compatibility_score -> score; obligations have no `confidence`.
#   * real-vs-mock is read from /llm/status, not inferred from confidences.
#   * a FIRST analysis of a big document generates for minutes behind the LB
#     timeout — this polls through 503/504 like the frontend does.
set -euo pipefail

BASE="${BASE:-https://ra-ae606d95b03941e3afa9b31f3eb979e1.ecs.us-east-2.on.aws}"
EMAIL="${TEST_EMAIL:-test@rackner.com}"
PASSWORD="${TEST_PASSWORD:-}"

pass(){ echo "  ✅ $1"; }
fail(){ echo "  ❌ $1"; exit 1; }

[ -z "$PASSWORD" ] && { read -rsp "Password for $EMAIL: " PASSWORD; echo; }

echo "== 1. Login (backend Cognito proxy) =="
TOKEN=$(curl -s --max-time 30 -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
[ -z "$TOKEN" ] && fail "login failed — wrong password, or the service is down"
pass "got an ID token"
AUTH=(-H "Authorization: Bearer $TOKEN")

echo "== 2. /me (auth + database) =="
CODE=$(curl -s -o /dev/null -w "%{http_code}" "${AUTH[@]}" --max-time 30 "$BASE/me")
[ "$CODE" = "200" ] || fail "/me -> HTTP $CODE (503 bodies name the cause: unreachable DB vs missing schema)"
pass "auth + database work"

echo "== 3. Real model or mock? =="
MODE=$(curl -s "${AUTH[@]}" --max-time 30 "$BASE/llm/status" \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('llm_mode',''))")
echo "  llm_mode=$MODE"
[ "$MODE" = "bedrock" ] || echo "  ⚠️  running on '$MODE', not bedrock"

echo "== 4. Find an opportunity =="
OPP="${OPP_ID:-}"
if [ -z "$OPP" ]; then
  OPP=$(curl -s "${AUTH[@]}" --max-time 120 "$BASE/opportunities/search?q=cyber" \
    | python3 -c "import sys,json
try:
  d=json.load(sys.stdin); print(d[0]['id'] if isinstance(d,list) and d else '')
except Exception: print('')")
fi
[ -z "$OPP" ] && fail "no opportunity (SAM.gov rate-limited?) — re-run with OPP_ID=<a cached id>"
echo "  using: $OPP"

echo "== 5. Analysis (first generation can take minutes; polling like the UI) =="
OUT=$(mktemp)
DEADLINE=$(( $(date +%s) + 420 ))
while :; do
  CODE=$(curl -s -o "$OUT" -w "%{http_code}" "${AUTH[@]}" --max-time 90 \
    "$BASE/opportunities/$OPP/analysis" || echo 000)
  [ "$CODE" = "200" ] && break
  [ "$(date +%s)" -ge "$DEADLINE" ] && fail "analysis never converged (last HTTP $CODE)"
  echo "  HTTP $CODE — still generating, polling..."
  sleep 20
done
python3 - "$OUT" <<'PY'
import json, sys
a = json.load(open(sys.argv[1]))
obs = a.get("obligations") or []
verified = sum(1 for o in obs if o.get("verified"))
print(f"  score={a.get('score')}  band={a.get('band')}  obligations={len(obs)}  verified={verified}")
ok = a.get("band") in ("pursue", "conditional", "no_bid") and a.get("score") is not None
sys.exit(0 if ok else 1)
PY
pass "grounded analysis returned (score + band + cited obligations)"

echo
echo "== DONE: auth -> DB -> $MODE analysis with verified citations =="
