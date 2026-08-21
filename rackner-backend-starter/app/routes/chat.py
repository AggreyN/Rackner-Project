"""The assistant.

    POST /opportunities/{id}/chat  {"question": "..."} -> ChatAnswer

Grounded in the same persisted SourceDocument sections that back /document and
/analysis, so an answer can only cite text the UI can actually show.

Both former contract gaps are now closed (SCHEMA_v2.md, resolved questions 1
and 2): citations carry verbatim_quote/verified through the same grounding
pipeline as obligations, and the request accepts optional `history` — prior
turns the model may use to resolve what a follow-up refers to, never as a
citable source. History is capped server-side (schemas.trim_history), so a
long conversation degrades to recent context rather than blowing the model's
window; clients that omit it keep the old single-turn behaviour.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import current_user, get_db, ensure_visible
from app.llm import gateway
from app.models import Opportunity, User
from app.routes.documents import get_or_build_document
from app.schemas import ChatAnswer, ChatRequest, trim_history

log = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

MAX_QUESTION_CHARS = 2000


@router.post("/opportunities/{opportunity_id}/chat", response_model=ChatAnswer)
def ask(
    opportunity_id: str,
    body: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ChatAnswer:
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A question is required.")
    if len(question) > MAX_QUESTION_CHARS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Question exceeds {MAX_QUESTION_CHARS} characters.",
        )

    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown opportunity.")
    ensure_visible(opp, user)

    doc = get_or_build_document(db, opp)
    if not doc.sections:
        # Nothing to ground an answer in. Say so rather than answering from the
        # model's general knowledge of federal contracting.
        return ChatAnswer(
            answer=(
                "No source text has been ingested for this opportunity yet, so "
                "there is nothing to answer from."
            ),
            citations=[],
        )

    history = [t.model_dump() for t in trim_history(body.history)]
    # Materialize sections and release the pooled connection before the model
    # call — chat turns run seconds-to-minutes and must not hold the pool.
    sections = [
        {"ref": sec.ref, "page": sec.page, "text": sec.text} for sec in doc.sections
    ]
    db.commit()
    try:
        return ChatAnswer(**gateway.answer_question(question, sections, history))
    except HTTPException:
        raise
    except Exception:
        # A model-side failure (Bedrock throttle, network) was reaching users
        # as a bare 500. A chat turn fails soft: named 503, retriable.
        log.warning("chat turn failed against the model", exc_info=True)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The assistant couldn't reach the model — ask again in a moment.",
        )
