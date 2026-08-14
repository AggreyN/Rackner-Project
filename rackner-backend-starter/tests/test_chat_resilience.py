"""Chat resilience — the blank-bubble incident (2026-08-13).

On a 478-obligation document, long answers truncated at the output-token cap,
the broken JSON parsed to {}, and users got HTTP 200 with answer: "" — blank
chat bubbles. Model-side failures surfaced as bare 500s. The rules now:
  * a chat answer is NEVER empty — truncated JSON is salvaged (the answer
    field is written first and usually survives), and total garbage becomes
    an explicit apology;
  * monster documents are budgeted: the most question-relevant sections go
    to the model, logged, never silently;
  * a model-side exception is a named, retriable 503.
"""

from __future__ import annotations

import json

import pytest

from app import config
from app.llm import gateway

SECTIONS = [
    {"ref": "C.1", "page": 1, "text": "The Contractor shall provide cybersecurity services."},
    {"ref": "C.2", "page": 2, "text": "Incident reporting is due within 72 hours."},
]


def _rig_invoke(monkeypatch, raw: str):
    from app.llm import bedrock_client

    monkeypatch.setattr(config, "LLM_MODE", "bedrock")
    monkeypatch.setattr(
        bedrock_client, "invoke", lambda system, prompt, max_tokens=None: raw
    )


# --- never-blank answers -------------------------------------------------------


def test_truncated_json_still_yields_the_answer_text(monkeypatch):
    truncated = (
        '{"answer": "Reporting is due within 72 hours of discovery.", '
        '"citations": [{"section": "C.2", "verbatim_quote": "Incident repo'
    )  # chopped mid-citation, exactly like the output-token cap does
    _rig_invoke(monkeypatch, truncated)
    out = gateway.answer_question("when is reporting due?", SECTIONS)
    assert out["answer"] == "Reporting is due within 72 hours of discovery."


def test_total_garbage_becomes_an_apology_not_a_blank(monkeypatch):
    _rig_invoke(monkeypatch, "%% not json at all %%")
    out = gateway.answer_question("anything?", SECTIONS)
    assert out["answer"].strip(), "a blank answer must be impossible"
    assert "ask again" in out["answer"]


def test_empty_model_output_becomes_an_apology(monkeypatch):
    _rig_invoke(monkeypatch, "")
    out = gateway.answer_question("anything?", SECTIONS)
    assert out["answer"].strip()


def test_escaped_quotes_survive_salvage(monkeypatch):
    truncated = '{"answer": "The clause says \\"report immediately\\" to the CO.", "citations": [{"sec'
    _rig_invoke(monkeypatch, truncated)
    out = gateway.answer_question("q", SECTIONS)
    assert out["answer"] == 'The clause says "report immediately" to the CO.'


def test_intact_responses_are_untouched(monkeypatch):
    intact = json.dumps(
        {
            "answer": "Within 72 hours.",
            "citations": [
                {"section": "C.2", "page": 2, "verbatim_quote": "Incident reporting is due within 72 hours."}
            ],
        }
    )
    _rig_invoke(monkeypatch, intact)
    out = gateway.answer_question("when?", SECTIONS)
    assert out["answer"] == "Within 72 hours."
    assert out["citations"][0]["verified"] is True


# --- the section budget --------------------------------------------------------


def _big_sections(n: int, chars: int) -> list[dict]:
    return [
        {"ref": f"S.{i}", "page": i, "text": f"filler section {i} " + "x" * chars}
        for i in range(n)
    ]


def test_small_documents_pass_through_untouched(monkeypatch):
    sections = _big_sections(5, 100)
    assert gateway._chat_sections("q", sections) == sections


def test_monster_documents_are_budgeted_and_keep_relevant_sections(monkeypatch):
    monkeypatch.setattr(config, "CHAT_MAX_SECTION_CHARS", 5000)
    sections = _big_sections(30, 1000)
    sections[17]["text"] = "the quantum cryptography transition plan " + "y" * 500
    kept = gateway._chat_sections("what about quantum cryptography?", sections)
    assert sum(len(s["text"]) for s in kept) <= 5000
    assert any("quantum cryptography" in s["text"] for s in kept), (
        "the question-relevant section must survive the cut"
    )
    assert kept[0]["ref"] == "S.0", "the opening section frames the document"
    refs = [s["ref"] for s in kept]
    assert refs == sorted(refs, key=lambda r: int(r.split(".")[1])), "document order kept"


def test_citations_from_budgeted_context_still_verify(monkeypatch):
    """The model only sees budgeted sections, but validation runs against the
    full set — a citation to a kept section must verify normally."""
    monkeypatch.setattr(config, "CHAT_MAX_SECTION_CHARS", 200)
    sections = [
        {"ref": "A", "page": 1, "text": "alpha " * 30},
        {"ref": "B", "page": 2, "text": "the payment terms are net thirty days"},
    ]
    intact = json.dumps(
        {
            "answer": "Net thirty.",
            "citations": [
                {"section": "B", "verbatim_quote": "payment terms are net thirty days"}
            ],
        }
    )
    _rig_invoke(monkeypatch, intact)
    out = gateway.answer_question("what are the payment terms?", sections)
    assert out["citations"][0]["verified"] is True


# --- the route fails soft ------------------------------------------------------


def test_model_side_failure_is_a_named_503(client, auth_headers, monkeypatch):
    from app.database import SessionLocal
    from app.models import Opportunity

    opp_id = "CHAT-RESIL-1"
    db = SessionLocal()
    try:
        row = db.get(Opportunity, opp_id) or Opportunity(
            id=opp_id, title="Chat resilience", agency="DoD"
        )
        db.add(row)
        row.description = "The Contractor shall answer questions."
        db.commit()
    finally:
        db.close()

    def boom(*a, **kw):
        raise RuntimeError("ThrottlingException from bedrock")

    monkeypatch.setattr(gateway, "answer_question", boom)
    r = client.post(
        f"/opportunities/{opp_id}/chat",
        headers=auth_headers,
        json={"question": "hello?"},
    )
    assert r.status_code == 503
    assert "ask again" in r.json()["detail"]
