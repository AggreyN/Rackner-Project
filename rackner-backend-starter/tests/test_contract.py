"""The anti-drift test: Pydantic models vs. Remy's types.ts, field by field.

This exists because drift already cost this project real time — the backend and
frontend each declared themselves "the single source of truth" and disagreed on
nine types at once. A doc can't prevent that; a failing test can.

It parses frontend/src/lib/types.ts directly rather than a copy, so there is
nothing to keep in sync. If Remy renames a field, this goes red on the next run
and names the exact field.

If a mismatch here is intentional, don't loosen the assert — add the field to
KNOWN_SERVER_ONLY (with a reason) so the exemption is visible in review.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import schemas

TYPES_TS = (
    Path(__file__).resolve().parent.parent.parent
    / "frontend"
    / "src"
    / "lib"
    / "types.ts"
)

# Backend-only fields, deliberately not on the wire. Keep each one justified.
KNOWN_SERVER_ONLY: dict[str, set[str]] = {
    # SCHEMA_v2.md "DB <-> wire": these still feed scoring but v2 doesn't ship them.
    "LifecycleProfile": set(),
}

# types.ts interface -> backend model. Only types the API actually serves.
PAIRS = [
    ("User", schemas.User),
    ("LifecycleProfile", schemas.LifecycleProfile),
    ("Profile", schemas.Profile),
    ("OpportunitySummary", schemas.OpportunitySummary),
    ("Citation", schemas.Citation),
    ("FitFactor", schemas.FitFactor),
    ("Obligation", schemas.Obligation),
    ("Analysis", schemas.Analysis),
    ("SourceSection", schemas.SourceSection),
    ("SourceDocument", schemas.SourceDocument),
    ("SpendYear", schemas.SpendYear),
    ("SpendSummary", schemas.SpendSummary),
    ("ContactResult", schemas.ContactResult),
    ("ChatCitation", schemas.ChatCitation),
    ("ChatAnswer", schemas.ChatAnswer),
]

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")
# A top-level field line:  `  name?: type;`  /  `  "name": type;`
_FIELD = re.compile(r"^\s{2}\"?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\"?\??\s*:", re.MULTILINE)


def _read_types_ts() -> str:
    if not TYPES_TS.exists():
        pytest.skip(f"types.ts not found at {TYPES_TS}")
    return TYPES_TS.read_text(encoding="utf-8")


def _interface_body(source: str, name: str) -> str:
    """The brace-balanced body of `export interface <name> { ... }`."""
    m = re.search(rf"export\s+interface\s+{re.escape(name)}\s*\{{", source)
    if not m:
        pytest.fail(f"interface {name} not found in types.ts")
    depth, start = 0, m.end() - 1
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1 : i]
    pytest.fail(f"unbalanced braces for interface {name}")


def ts_fields(name: str) -> set[str]:
    source = _read_types_ts()
    body = _interface_body(source, name)
    # Strip comments so `// note: foo` isn't mistaken for a field.
    body = _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", body))
    # Drop nested object literals; we only compare top-level keys.
    body = re.sub(r"\{[^{}]*\}", " ", body)
    return set(_FIELD.findall(body))


@pytest.mark.parametrize("ts_name,model", PAIRS, ids=[p[0] for p in PAIRS])
def test_model_matches_types_ts(ts_name, model):
    expected = ts_fields(ts_name)
    actual = set(model.model_fields)
    allowed_extra = KNOWN_SERVER_ONLY.get(ts_name, set())

    missing = expected - actual
    extra = actual - expected - allowed_extra

    assert not missing, (
        f"{ts_name}: backend is MISSING {sorted(missing)} that types.ts declares. "
        f"The frontend will read undefined."
    )
    assert not extra, (
        f"{ts_name}: backend has EXTRA {sorted(extra)} not in types.ts. "
        f"Either add them to types.ts or to KNOWN_SERVER_ONLY with a reason."
    )


def test_analysis_keeps_band_and_verdict_separate():
    """The single most-reverted mistake in this codebase.

    v2 has BOTH: `band` is the enum, `verdict` is prose. Anyone "fixing" this
    by renaming verdict->band breaks the frontend's ScoreBadge.
    """
    fields = schemas.Analysis.model_fields
    assert "band" in fields and "verdict" in fields
    assert "compatibility_score" not in fields, "v1 name; v2 uses `score`"
    assert "score" in fields


def test_time_bucket_matches_frontend():
    """types.ts drives the union, including v2's added `at_award`."""
    source = _read_types_ts()
    m = re.search(r"export\s+type\s+TimeBucket\s*=([^;]+);", source)
    assert m, "TimeBucket union not found in types.ts"
    expected = set(re.findall(r'"([^"]+)"', m.group(1)))
    actual = set(schemas.TimeBucket.__args__)
    assert actual == expected, f"TimeBucket drift: backend={sorted(actual)} ts={sorted(expected)}"


def test_fit_band_matches_frontend():
    source = _read_types_ts()
    m = re.search(r"export\s+type\s+FitBand\s*=([^;]+);", source)
    assert m, "FitBand union not found in types.ts"
    expected = set(re.findall(r'"([^"]+)"', m.group(1)))
    assert set(schemas.FitBand.__args__) == expected


def test_opportunity_kind_matches_frontend():
    source = _read_types_ts()
    m = re.search(r"export\s+type\s+OpportunityKind\s*=([^;]+);", source)
    assert m, "OpportunityKind union not found in types.ts"
    expected = set(re.findall(r'"([^"]+)"', m.group(1)))
    assert set(schemas.OpportunityKind.__args__) == expected


def test_factor_weights_sum_to_one():
    assert abs(sum(schemas.FACTOR_WEIGHTS.values()) - 1.0) < 1e-9


def test_every_factor_has_a_label():
    assert set(schemas.FACTOR_WEIGHTS) == set(schemas.FACTOR_LABELS)


def test_band_thresholds():
    """SCHEMA_v2: >=70 pursue, 50-69 conditional, <50 no_bid."""
    assert schemas.band_for(70) == "pursue"
    assert schemas.band_for(69.9) == "conditional"
    assert schemas.band_for(50) == "conditional"
    assert schemas.band_for(49.9) == "no_bid"


def test_routes_match_the_contract(client):
    """Every path the frontend calls must exist, spelled identically."""
    api_ts = TYPES_TS.parent / "api.ts"
    if not api_ts.exists():
        pytest.skip("api.ts not found")

    called = set()
    for raw in re.findall(r"\$\{BASE\}([^`\"']*)", api_ts.read_text(encoding="utf-8")):
        path = raw.split("?")[0]
        path = re.sub(r"\$\{[^}]*\}", "{id}", path).rstrip("/")
        if path.startswith("/"):
            called.add(path)

    served = {
        re.sub(r"\{[^}]*\}", "{id}", p).rstrip("/")
        for p in client.get("/openapi.json").json()["paths"]
    }

    # Week 3 routes are not built yet; assert only on what this week shipped.
    week2 = {"/auth/login", "/profile", "/profile/lifecycle",
             "/opportunities/{id}/analysis", "/opportunities/{id}/document"}
    missing = (called & week2) - served
    assert not missing, f"frontend calls these but the backend doesn't serve them: {sorted(missing)}"
