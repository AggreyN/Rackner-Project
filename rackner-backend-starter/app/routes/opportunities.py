"""Opportunity search, suggestions and detail.

    GET /opportunities/search?q=&kinds=&expiring_from=&expiring_to=
    GET /opportunities/suggested?kinds=&expiring_from=&expiring_to=
    GET /opportunities/{id}

These are what make the rest of the app reachable: /analysis and /document both
need an Opportunity row, and this is what creates them. Results are upserted
into the cache so a later detail request doesn't depend on the upstream still
being available.

Two sources behind one shape. Live notices come from SAM.gov; `expiring_award`
rows come from USAspending's recompete radar. `kinds` decides which are
queried, so asking only for expiring awards costs no SAM call and vice versa.

Filtering is server-side by contract — the recompete radar spans the whole
award set and cannot be paged into the browser.
"""

from __future__ import annotations

import datetime
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.deps import current_user, get_db
from app.llm import gateway
from app.models import Analysis as AnalysisModel
from app.models import FitEstimate, SearchFetch
from app.models import LifecycleProfile as LifecycleProfileModel
from app.models import Opportunity, User
from app.routes.analysis import warm_analysis
from app.schemas import OpportunitySummary
from app.services import fit, samgov, usaspending
from app.services.http import UpstreamError

log = logging.getLogger(__name__)

router = APIRouter(tags=["opportunities"])

SAM_KINDS = {"solicitation", "presolicitation", "sources_sought", "baa"}


def _fail(exc: UpstreamError) -> HTTPException:
    """Upstream trouble becomes a 503 naming the service — never a silent
    empty list, which the UI would render as 'nothing exists'."""
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        f"{exc.service} is unavailable right now. {exc.detail}",
    )


def _parse_kinds(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]


def _lifecycle(db: Session, user: User) -> dict | None:
    row = db.scalar(
        select(LifecycleProfileModel)
        .where(LifecycleProfileModel.user_id == user.id)
        .order_by(LifecycleProfileModel.updated_at.desc())
    )
    if row is None:
        return None
    return {
        "capabilities": row.capabilities or [],
        "naics_codes": row.naics_codes or [],
        "target_agencies": row.target_agencies or [],
        "set_asides": row.set_aside_status or [],
    }


def _cache(db: Session, summaries: list[dict]) -> None:
    """Upsert by id so detail/analysis work after the search that found them."""
    for s in summaries:
        if not s.get("id"):
            continue
        row = db.get(Opportunity, s["id"])
        if row is None:
            row = Opportunity(id=s["id"])
            db.add(row)
        row.title = s.get("title") or ""
        row.agency = s.get("agency") or ""
        row.office = s.get("office")
        row.solicitation_number = s.get("solicitation_number")
        row.naics = s.get("naics")
        row.set_aside = s.get("set_aside")
        row.kind = s.get("kind") or "solicitation"
        # Only set when present: cache-replayed summaries don't carry the
        # internal key, and blanking a stored URL on every replay loses data.
        if s.get("_source_url"):
            row.source_url = s["_source_url"]
        row.est_value = s.get("est_value")
        row.incumbent = s.get("incumbent")
        row.current_award_value = s.get("current_award_value")
        for field, key in (("close_date", "close_date"), ("expiry_date", "expiry_date")):
            raw = s.get(key)
            setattr(row, field, datetime.date.fromisoformat(raw) if raw else None)
        # Only overwrite a stored description with a non-empty one: the search
        # payload has none, and blanking it would destroy the grounding text a
        # previous detail fetch already stored.
        if s.get("description"):
            row.description = s["description"]
        # Same guard for attachment links: cached-row fallbacks don't carry the
        # key, and blanking links would orphan an already-built full document.
        if s.get("_resource_links"):
            row.resource_links = s["_resource_links"]
        # A live fetch that returns this row makes it fresh NOW — without this
        # the dashboard replay's freshness-window filter dropped rows a live
        # refresh had just paid for (audit 2026-08-19).
        row.fetched_at = datetime.datetime.now(datetime.timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        # Two identical searches raced the same INSERTs. Retry once: the
        # second pass sees the winner's rows via db.get and updates them.
        db.rollback()
        for s in summaries:
            if not s.get("id"):
                continue
            if db.get(Opportunity, s["id"]) is None:
                db.add(Opportunity(id=s["id"], title=s.get("title") or "",
                                   agency=s.get("agency") or ""))
        db.commit()


def _to_summary(row: Opportunity, today: datetime.date | None = None) -> dict:
    """Cached row -> OpportunitySummary. The two derived fields are computed at
    serialization, never stored, so they can't go stale in the database."""
    today = today or datetime.date.today()
    months = (
        round((row.expiry_date - today).days / 30.44) if row.expiry_date else None
    )
    return {
        "id": row.id,
        "title": row.title,
        "agency": row.agency,
        "office": row.office,
        "solicitation_number": row.solicitation_number,
        "naics": row.naics,
        "set_aside": row.set_aside,
        "kind": row.kind,
        "description": row.description or "",
        "close_date": row.close_date.isoformat() if row.close_date else None,
        "days_to_close": (row.close_date - today).days if row.close_date else None,
        "est_value": row.est_value,
        "incumbent": row.incumbent,
        "fit_score": None,
        "expiry_date": row.expiry_date.isoformat() if row.expiry_date else None,
        "months_to_expiry": months,
        "current_award_value": (
            float(row.current_award_value) if row.current_award_value is not None else None
        ),
    }


def _clean(summaries: list[dict]) -> list[OpportunitySummary]:
    """Drop the internal underscore keys before they reach the wire."""
    return [
        OpportunitySummary(**{k: v for k, v in s.items() if not k.startswith("_")})
        for s in summaries
    ]


def _row_recently_fetched(row: Opportunity) -> bool:
    """A notice with a GENUINELY empty description used to refetch SAM (2
    calls) on every detail view forever. If we fetched it live recently,
    serve it as-is; retry only once the freshness window lapses."""
    fetched = row.fetched_at
    if fetched is None:
        return False
    if fetched.tzinfo is None:  # SQLite round-trips naive datetimes
        fetched = fetched.replace(tzinfo=datetime.timezone.utc)
    age = datetime.datetime.now(datetime.timezone.utc) - fetched
    return age.total_seconds() < config.SAM_SEARCH_TTL_HOURS * 3600


def _sam_query_key(query: str, sam_kinds: list[str] | None) -> str:
    """Bounded ledger key: sha256 of the normalized (query, kinds).

    Hashed because the raw query is user-controlled and unbounded — a long
    query overflowing the column would 500 AFTER the live call burned quota,
    and repeat forever since the ledger never stamps.
    """
    import hashlib

    kinds_part = ",".join(sorted(set(sam_kinds))) if sam_kinds else "all"
    raw = f"{(query or '').strip().lower()}|{kinds_part}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _sam_fetch_is_fresh(db: Session, query: str, sam_kinds: list[str] | None) -> bool:
    row = db.scalar(
        select(SearchFetch).where(
            SearchFetch.query_key == _sam_query_key(query, sam_kinds)
        )
    )
    if row is None or row.fetched_at is None:
        return False
    fetched = row.fetched_at
    if fetched.tzinfo is None:  # SQLite round-trips naive datetimes
        fetched = fetched.replace(tzinfo=datetime.timezone.utc)
    age = datetime.datetime.now(datetime.timezone.utc) - fetched
    return age.total_seconds() < config.SAM_SEARCH_TTL_HOURS * 3600


def _record_sam_fetch(db: Session, query: str, sam_kinds: list[str] | None) -> None:
    key = _sam_query_key(query, sam_kinds)
    now = datetime.datetime.now(datetime.timezone.utc)
    row = db.scalar(select(SearchFetch).where(SearchFetch.query_key == key))
    if row is None:
        row = SearchFetch(query_key=key, fetched_at=now)
        db.add(row)
    else:
        row.fetched_at = now
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # concurrent request recorded the same key — equally fresh


def _cached_sam_rows(db: Session, *, query: str, kinds: list[str], limit: int) -> list[dict]:
    """Serve SAM rows from the cache: the freshness-window replay AND the
    SAM-down fallback.

    Matching is per-WORD (any token hits title/description/solicitation
    number, wildcards escaped) — SAM's own full-text search is looser than a
    literal phrase match, and an over-narrow replay would fabricate empty
    result pages. Notices already past their close date are excluded: serving
    a dead deadline from cache is worse than serving nothing. Empty-query
    replays (the dashboard) are limited to rows fetched inside the freshness
    window, so one user's old niche searches don't become everyone's feed.
    """
    wanted = [k for k in kinds if k in SAM_KINDS] or list(SAM_KINDS)
    today = datetime.date.today()
    stmt = select(Opportunity).where(
        Opportunity.kind.in_(wanted),
        (Opportunity.close_date.is_(None)) | (Opportunity.close_date >= today),
    )
    if query:
        words = [w for w in query.split() if len(w) >= 3] or [query.strip()]
        clauses = []
        for word in words:
            needle = "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            clauses.append(
                Opportunity.title.ilike(needle, escape="\\")
                | Opportunity.description.ilike(needle, escape="\\")
                | Opportunity.solicitation_number.ilike(needle, escape="\\")
            )
        combined = clauses[0]
        for clause in clauses[1:]:
            combined = combined | clause
        stmt = stmt.where(combined)
    else:
        window_start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            hours=config.SAM_SEARCH_TTL_HOURS
        )
        stmt = stmt.where(Opportunity.fetched_at >= window_start)
    rows = db.scalars(
        stmt.order_by(Opportunity.fetched_at.desc()).limit(limit)
    ).all()
    return [_to_summary(row) for row in rows]


def _collect(
    db: Session,
    *,
    query: str,
    kinds: list[str],
    expiring_from: int | None,
    expiring_to: int | None,
    limit: int,
) -> list[dict]:
    """Query whichever sources the requested kinds imply — independently.

    One source being down must not blank the other (measured failure mode: a
    rate-limited SAM key 503'd the whole search while USAspending was
    healthy). Each source degrades on its own — SAM falls back to cached rows
    — and only when EVERY requested source produced nothing and at least one
    errored does the caller see a 503.
    """
    wants_expiring = (not kinds) or ("expiring_award" in kinds)
    wants_live = (not kinds) or bool(set(kinds) & SAM_KINDS)

    results: list[dict] = []
    failures: list[UpstreamError] = []

    if wants_live:
        sam_kinds = [k for k in kinds if k in SAM_KINDS] or None
        replayed = False
        if _sam_fetch_is_fresh(db, query, sam_kinds):
            # This query was asked live within the freshness window — the
            # cached rows ARE the answer. Zero SAM quota spent. If the replay
            # matcher finds nothing for a non-empty query (its ilike semantics
            # are narrower than SAM's), fall through to a live fetch rather
            # than serving a confident empty page.
            cached = _cached_sam_rows(db, query=query, kinds=kinds, limit=limit)
            if cached or not query:
                results.extend(cached)
                replayed = True
        if not replayed:
            try:
                results.extend(samgov.search(query, kinds=sam_kinds, limit=limit))
                _record_sam_fetch(db, query, sam_kinds)
            except UpstreamError as exc:
                failures.append(exc)
                cached = _cached_sam_rows(db, query=query, kinds=kinds, limit=limit)
                if cached:
                    log.warning(
                        "%s unavailable (%s); serving %d cached solicitations",
                        exc.service,
                        exc.detail,
                        len(cached),
                    )
                    results.extend(cached)

    if wants_expiring:
        try:
            expiring = usaspending.expiring_awards(
                from_months=expiring_from if expiring_from is not None else 12,
                to_months=expiring_to if expiring_to is not None else 18,
                limit=limit,
            )
        except UpstreamError as exc:
            failures.append(exc)
            expiring = []
        # USAspending has no free-text search, so apply `q` here — otherwise a
        # text search would return recompete rows about anything, which reads
        # as wrong results rather than a missing filter.
        if query:
            needle = query.lower()
            expiring = [
                row
                for row in expiring
                if needle
                in " ".join(
                    str(row.get(field) or "")
                    for field in ("title", "description", "incumbent", "agency", "solicitation_number")
                ).lower()
            ]
        results.extend(expiring)

    if not results and failures:
        # Nothing from anywhere and at least one upstream is down — a clean
        # error beats an empty list the UI would render as "nothing exists".
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "; ".join(f"{f.service} is unavailable right now. {f.detail}" for f in failures),
        )
    return results


@router.get("/opportunities/search", response_model=list[OpportunitySummary])
def search_opportunities(
    q: str = Query("", description="free-text title search"),
    kinds: str | None = Query(None, description="comma-separated OpportunityKind list"),
    expiring_from: int | None = Query(None, description="months, expiring_award only"),
    expiring_to: int | None = Query(None, description="months, expiring_award only"),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[OpportunitySummary]:
    results = _collect(
        db,
        query=q,
        kinds=_parse_kinds(kinds),
        expiring_from=expiring_from,
        expiring_to=expiring_to,
        limit=limit,
    )
    _cache(db, results)
    _apply_fit(db, user, results, _lifecycle(db, user))
    return _clean(results)


@router.get("/opportunities/suggested", response_model=list[OpportunitySummary])
def suggested_opportunities(
    kinds: str | None = Query(None),
    expiring_from: int | None = Query(None),
    expiring_to: int | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[OpportunitySummary]:
    """Ranked against the user's lifecycle plan.

    With no plan on file this degrades to an unranked feed (every fit_score
    null) rather than erroring — a new user should still see the market.
    """
    lifecycle = _lifecycle(db, user)
    results = _collect(
        db,
        query="",
        kinds=_parse_kinds(kinds),
        expiring_from=expiring_from,
        expiring_to=expiring_to,
        limit=limit,
    )
    _cache(db, results)
    _apply_fit(db, user, results, lifecycle)
    return _clean(results)


def _apply_fit(db: Session, user: User, rows: list[dict], lifecycle: dict | None) -> list[dict]:
    """Attach fit_score + fit_source to every row; sort best-first with a plan.

    Precedence, most-truthful first:
      1. the user's cached ANALYSIS score — once the researched number exists,
         the card must agree with the analysis screen (fit_source="analysis");
      2. a cached AI pre-screen estimate (stable across pages and days);
      3. a fresh batched AI pre-screen — ONE model call for the whole page,
         persisted so it is never paid twice (bedrock mode only);
      4. the deterministic heuristic (mock mode, model failure, or ids the
         model skipped) — still an "estimate".
    With no plan on file everything stays null, unranked.
    """
    ids = [r["id"] for r in rows if r.get("id")]
    if not ids:
        return rows

    analysis_by = {
        a.opportunity_id: a.score
        for a in db.scalars(
            select(AnalysisModel).where(
                AnalysisModel.user_id == user.id,
                AnalysisModel.opportunity_id.in_(ids),
            )
        )
    }

    estimate_by: dict[str, float] = {}
    if lifecycle:
        estimate_by = {
            e.opportunity_id: e.score
            for e in db.scalars(
                select(FitEstimate).where(
                    FitEstimate.user_id == user.id,
                    FitEstimate.opportunity_id.in_(ids),
                )
            )
        }
        need = [
            r
            for r in rows
            if r.get("id")
            and r["id"] not in analysis_by
            and r["id"] not in estimate_by
        ]
        # Below the floor (a detail view's single row), skip the model: the
        # heuristic is instant and the analysis pre-warm supersedes any
        # estimate within a minute of the click anyway.
        if len(need) >= config.FIT_PRESCREEN_MIN_ROWS:
            try:
                fresh = gateway.prescreen_scores(lifecycle, need)
            except Exception:
                # The search page must never break because scoring hiccuped.
                log.warning("AI pre-screen failed; using heuristic", exc_info=True)
                fresh = {}
            if fresh:
                try:
                    for oid, score in fresh.items():
                        db.add(
                            FitEstimate(user_id=user.id, opportunity_id=oid, score=score)
                        )
                    db.commit()
                except IntegrityError:
                    # A concurrent request raced us on some row. Salvage the
                    # rest one-by-one instead of dropping the whole batch.
                    db.rollback()
                    for oid, score in fresh.items():
                        try:
                            db.add(
                                FitEstimate(
                                    user_id=user.id, opportunity_id=oid, score=score
                                )
                            )
                            db.commit()
                        except IntegrityError:
                            db.rollback()
                estimate_by.update(fresh)

    for r in rows:
        oid = r.get("id")
        if oid in analysis_by:
            r["fit_score"], r["fit_source"] = analysis_by[oid], "analysis"
        elif lifecycle and oid in estimate_by:
            r["fit_score"], r["fit_source"] = estimate_by[oid], "estimate"
        elif lifecycle:
            r["fit_score"], r["fit_source"] = fit.score(r, lifecycle), "estimate"
        else:
            r["fit_score"], r["fit_source"] = None, None

    if lifecycle:
        rows.sort(key=lambda o: (o.get("fit_score") or 0.0), reverse=True)
    return rows


def _maybe_prewarm(
    background: BackgroundTasks, *, opportunity_id: str, description: str | None, user: User
) -> None:
    """Queue a background analysis warm when there is text to ground in.

    Fired from the detail view — the moment we know the user is looking at
    this opportunity — so the analysis tab is a cache hit instead of a 30s+
    synchronous Bedrock call (SCHEMA_v2 question 3, option (a)). The task runs
    after the response is sent; warm_analysis dedupes and fails soft.
    """
    if config.ANALYSIS_PREWARM and (description or "").strip():
        background.add_task(warm_analysis, opportunity_id, user.id)


@router.get("/opportunities/{opportunity_id}", response_model=OpportunitySummary)
def get_opportunity(
    opportunity_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> OpportunitySummary:
    """Cached if we have it, otherwise fetched from SAM.gov and cached.

    The description is fetched here and not during search: it is a second
    round-trip per notice, and it is what /document grounds obligations in.
    """
    row = db.get(Opportunity, opportunity_id)
    if row is not None and (
        row.description
        or row.kind == "expiring_award"
        or _row_recently_fetched(row)
    ):
        summary = _to_summary(row)
        _apply_fit(db, user, [summary], _lifecycle(db, user))
        _maybe_prewarm(
            background, opportunity_id=row.id, description=row.description, user=user
        )
        return OpportunitySummary(**summary)

    try:
        fetched = samgov.get_opportunity(opportunity_id)
    except UpstreamError as exc:
        if row is not None:
            summary = _to_summary(row)  # serve stale rather than nothing
            _apply_fit(db, user, [summary], _lifecycle(db, user))
            _maybe_prewarm(
                background, opportunity_id=row.id, description=row.description, user=user
            )
            return OpportunitySummary(**summary)
        raise _fail(exc) from exc

    if fetched is None:
        if row is not None:
            summary = _to_summary(row)
            _apply_fit(db, user, [summary], _lifecycle(db, user))
            _maybe_prewarm(
                background, opportunity_id=row.id, description=row.description, user=user
            )
            return OpportunitySummary(**summary)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown opportunity.")

    fetched["description"] = samgov.fetch_description(fetched.get("_description_url", ""))
    _cache(db, [fetched])
    _apply_fit(db, user, [fetched], _lifecycle(db, user))
    _maybe_prewarm(
        background,
        opportunity_id=fetched["id"],
        description=fetched.get("description"),
        user=user,
    )
    return _clean([fetched])[0]
