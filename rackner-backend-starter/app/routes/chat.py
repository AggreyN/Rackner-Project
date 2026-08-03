"""The assistant.

    POST /opportunities/{id}/chat  {"question": "..."} -> ChatAnswer

Grounded in the same persisted SourceDocument sections that back /document and
/analysis, so an answer can only cite text the UI can actually show.

TWO CONTRACT GAPS — flagged, NOT decided unilaterally (SCHEMA_v2.md, open
questions 1 and 2):

  1. ChatCitation carries {section, page} only. The build spec asks for
     verbatim_quote and verified as well, so chat citations would use the same
     highlight path as obligations. That is a change to types.ts and needs
     Remy. The seam is ready: gateway.answer_question already resolves each
     citation against the section it names, so adding the quote is a small
     change here once the shape is agreed.

  2. No conversation history. The request sends a single question, so
     follow-ups ("what about the deadline for that?") have no context. Adding a
     `history` field is likewise a types.ts change. Until then this endpoint is
     honestly single-turn rather than pretending to remember.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import current_user, get_db
from app.llm import gateway
from app.models import Opportunity, User
from app.routes.documents import get_or_build_document
from app.schemas import ChatAnswer, ChatRequest

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

    return ChatAnswer(**gateway.answer_question(question, doc.sections))
