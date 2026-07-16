"""Obligation endpoints — role-filtered, grouped, citation-carrying."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from core.roles import ROLES
from db.models import Obligation

router = APIRouter(prefix="/obligations", tags=["obligations"])

_TIME_ORDER = {"immediate": 0, "30_days": 1, "quarterly": 2, "ongoing": 3, "unclear": 4}


@router.get("/roles")
def list_roles():
    """Feeds the frontend role picker — roles come from one config source."""
    return [
        {"key": r.key, "label": r.label, "question": r.question}
        for r in ROLES.values()
    ]


@router.get("/document/{doc_id}")
def obligations_for_document(
    doc_id: int,
    role: str | None = None,
    group_by: str = "time",  # time | category | type
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(Obligation).where(Obligation.document_id == doc_id)
    ).all()

    def to_dict(o: Obligation) -> dict:
        return {
            "id": o.id,
            "plain_english_text": o.plain_english_text,
            "obligation_type": o.obligation_type,
            "trigger_or_deadline": o.trigger_or_deadline,
            "responsible_party": o.responsible_party,
            "roles": o.roles or [],
            "category": o.category,
            "time_bucket": o.time_bucket,
            "verbatim_quote": o.verbatim_quote,
            "page": o.page,
            "confidence": o.confidence,
            "verified": o.verified,
            "status": o.status,
            "relevant_to_role": (role in (o.roles or [])) if role else True,
        }

    items = [to_dict(o) for o in rows]

    # Role filter puts the user's items first but never hides the rest —
    # transparency beats a false sense of "that's everything."
    if role:
        items.sort(key=lambda x: (not x["relevant_to_role"], _TIME_ORDER.get(x["time_bucket"] or "unclear", 4)))
    else:
        items.sort(key=lambda x: _TIME_ORDER.get(x["time_bucket"] or "unclear", 4))

    key_fn = {
        "time": lambda x: x["time_bucket"] or "unclear",
        "category": lambda x: x["category"] or "other",
        "type": lambda x: x["obligation_type"] or "other",
    }.get(group_by, lambda x: "all")

    groups: dict[str, list] = {}
    for it in items:
        groups.setdefault(key_fn(it), []).append(it)

    return {"role": role, "group_by": group_by, "total": len(items), "groups": groups}


@router.patch("/{obligation_id}")
def update_obligation(
    obligation_id: int,
    status: str | None = None,
    plain_english_text: str | None = None,
    db: Session = Depends(get_db),
):
    """Human-in-the-loop review: accept/edit/close an obligation."""
    o = db.get(Obligation, obligation_id)
    if o is None:
        raise HTTPException(404, "Obligation not found.")
    if status is not None:
        if status not in ("open", "in-review", "done"):
            raise HTTPException(400, "status must be open | in-review | done")
        o.status = status
    if plain_english_text is not None:
        o.plain_english_text = plain_english_text
    db.commit()
    return {"id": o.id, "status": o.status}
