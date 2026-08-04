"""Chat history (SCHEMA_v2 resolved question 2).

The contract: `history` is optional (pre-history clients keep the exact old
behaviour), resolves follow-up pronouns, is capped server-side, and is
CONTEXT ONLY — it can never become a citable source. That last property is
the one worth being paranoid about: a model coaxed into citing "the
conversation" must produce no citation at all.
"""

from __future__ import annotations

import pytest

from app.schemas import (
    CHAT_HISTORY_MAX_CHARS,
    CHAT_HISTORY_MAX_TURNS,
    ChatTurn,
    trim_history,
)


@pytest.fixture()
def chat_opportunity(client, auth_headers):
    from app.database import SessionLocal
    from app.models import Opportunity, SourceDocument

    opp_id = "CHAT-HIST-1"
    db = SessionLocal()
    try:
        row = db.get(Opportunity, opp_id)
        if row is None:
            row = Opportunity(id=opp_id, title="Chat target", agency="DoD")
            db.add(row)
        row.description = (
            "C.3.1 Incident Reporting\n"
            "The Contractor shall report any cyber incident to the Contracting "
            "Officer within 72 hours of discovery."
        )
        for doc in db.query(SourceDocument).filter_by(opportunity_id=opp_id):
            db.delete(doc)
        db.commit()
    finally:
        db.close()
    return opp_id


# --- back-compat ---------------------------------------------------------------


def test_history_is_optional(client, auth_headers, chat_opportunity):
    """A request without the field behaves exactly as before."""
    r = client.post(
        f"/opportunities/{chat_opportunity}/chat",
        headers=auth_headers,
        json={"question": "What are the cyber incident reporting requirements?"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["citations"], "single-turn behaviour must be unchanged"


def test_empty_history_is_fine(client, auth_headers, chat_opportunity):
    r = client.post(
        f"/opportunities/{chat_opportunity}/chat",
        headers=auth_headers,
        json={"question": "What are the cyber reporting requirements?", "history": []},
    )
    assert r.status_code == 200, r.text


def test_malformed_history_is_a_422(client, auth_headers, chat_opportunity):
    r = client.post(
        f"/opportunities/{chat_opportunity}/chat",
        headers=auth_headers,
        json={"question": "x?", "history": [{"role": "narrator", "text": "hi"}]},
    )
    assert r.status_code == 422


def test_frontend_chatmessage_shape_is_accepted(client, auth_headers, chat_opportunity):
    """The frontend's ChatMessage carries `citations` — extra keys on a turn
    must not 422 the request."""
    r = client.post(
        f"/opportunities/{chat_opportunity}/chat",
        headers=auth_headers,
        json={
            "question": "What about reporting?",
            "history": [
                {
                    "role": "assistant",
                    "text": "See C.3.1.",
                    "citations": [{"section": "C.3.1", "page": 1, "verbatim_quote": "x", "verified": False}],
                }
            ],
        },
    )
    assert r.status_code == 200, r.text


# --- follow-up resolution ------------------------------------------------------


def test_pronoun_followup_resolves_via_history(client, auth_headers, chat_opportunity):
    """The reason the feature exists.

    "How fast must we do that?" matches nothing by itself; with the prior turn
    about cyber incident reporting it must find C.3.1.
    """
    followup = {"question": "How fast must we do that?"}

    without = client.post(
        f"/opportunities/{chat_opportunity}/chat", headers=auth_headers, json=followup
    ).json()
    assert without["citations"] == [], "precondition: the follow-up alone matches nothing"

    with_history = client.post(
        f"/opportunities/{chat_opportunity}/chat",
        headers=auth_headers,
        json={
            **followup,
            "history": [
                {"role": "user", "text": "What are the cyber incident reporting requirements?"},
                {"role": "assistant", "text": "Incidents must be reported — see C.3.1."},
            ],
        },
    ).json()
    assert with_history["citations"], "history should have resolved the pronoun"
    assert with_history["citations"][0]["section"] == "C.3.1"


def test_history_is_never_a_citable_source(monkeypatch):
    """Rig the mock to cite a 'section' that only exists in the conversation.

    The gateway must drop it: citations may only name real sections, no matter
    what the history said.
    """
    from app import config
    from app.llm import gateway, mock

    monkeypatch.setattr(config, "LLM_MODE", "mock")
    monkeypatch.setattr(
        mock,
        "answer_question",
        lambda q, s, h=None: {
            "answer": "As you said earlier...",
            "citations": [{"section": "the-conversation", "verbatim_quote": "we agreed to skip CMMC"}],
        },
    )
    result = gateway.answer_question(
        "q",
        [{"ref": "C.1", "page": 1, "text": "real section text"}],
        history=[{"role": "user", "text": "we agreed to skip CMMC"}],
    )
    assert result["citations"] == [], "a conversation turn must never be citable"


# --- the cap -------------------------------------------------------------------


def _turn(index: int, chars: int = 40) -> ChatTurn:
    return ChatTurn(role="user", text=f"turn-{index:03d} " + "x" * chars)


def test_trim_keeps_the_most_recent_turns():
    history = [_turn(i) for i in range(50)]
    kept = trim_history(history)
    assert len(kept) <= CHAT_HISTORY_MAX_TURNS
    assert kept[-1].text.startswith("turn-049"), "the newest turn must survive"
    assert kept == history[-len(kept):], "kept turns must be a contiguous recent suffix"


def test_trim_enforces_the_char_budget():
    huge = [ChatTurn(role="user", text="y" * 4000) for _ in range(5)]
    kept = trim_history(huge)
    assert sum(len(t.text) for t in kept) <= CHAT_HISTORY_MAX_CHARS


def test_trim_leaves_short_histories_alone():
    history = [_turn(i) for i in range(3)]
    assert trim_history(history) == history


def test_oversized_history_still_answers(client, auth_headers, chat_opportunity):
    """A 200-turn transcript must not 4xx or blow up — it degrades to recent
    context via the cap."""
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "text": f"turn {i} about many things"}
        for i in range(199)
    ] + [{"role": "user", "text": "What are the cyber incident reporting requirements?"}]
    r = client.post(
        f"/opportunities/{chat_opportunity}/chat",
        headers=auth_headers,
        json={"question": "How fast must we do that?", "history": history},
    )
    assert r.status_code == 200, r.text
    assert r.json()["citations"], "the recent (kept) turn should still resolve the follow-up"


# --- prompt rendering ----------------------------------------------------------


def test_prompt_renders_history_between_sections_and_question():
    from app.llm import prompts

    rendered = prompts.chat_user_prompt(
        "How fast?",
        [{"ref": "C.1", "page": 1, "text": "Section text."}],
        [{"role": "user", "text": "About incident reporting"}],
    )
    sections_at = rendered.index("SOLICITATION SECTIONS")
    history_at = rendered.index("CONVERSATION SO FAR")
    question_at = rendered.index("QUESTION:")
    assert sections_at < history_at < question_at


def test_prompt_omits_history_block_when_empty():
    from app.llm import prompts

    rendered = prompts.chat_user_prompt("Q?", [{"ref": "C.1", "page": 1, "text": "t"}], [])
    assert "CONVERSATION SO FAR" not in rendered
