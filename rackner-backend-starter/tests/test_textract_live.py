"""Live Textract on the two committed image-only solicitations — opt-in.

    RUN_TEXTRACT_TESTS=1 pytest tests/test_textract_live.py

W50S8J26QA017.pdf (0 chars via pypdf) and W912HN26RA012.pdf (1 char) are the
documents that justified wiring OCR at all. This proves the real service
recovers usable text from them and that the recovered text satisfies the same
sectioning invariants as digital documents. Costs money per page; needs AWS
credentials with textract:DetectDocumentText.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_TEXTRACT_TESTS") != "1",
    reason="live Textract test; set RUN_TEXTRACT_TESTS=1 (costs money, needs AWS creds)",
)

SAMPLES = Path(__file__).resolve().parent.parent.parent / "data" / "samples"
SCANNED = ["W50S8J26QA017.pdf", "W912HN26RA012.pdf"]


@pytest.fixture(autouse=True)
def textract_on(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "OCR_MODE", "textract")


@pytest.mark.parametrize("name", SCANNED)
def test_scanned_sample_recovers_text(name):
    from app.services import ingest

    data = (SAMPLES / name).read_bytes()

    # Precondition: still unreadable without OCR (if pypdf ever starts reading
    # these, the sample no longer tests what it claims to).
    assert len(ingest._pypdf_page_texts(data) and "".join(ingest._pypdf_page_texts(data)).strip()) <= 1

    text = ingest.pdf_to_text(data)
    assert len(text.strip()) > 200, f"{name}: Textract recovered almost nothing"


@pytest.mark.parametrize("name", SCANNED)
def test_ocred_sample_satisfies_sectioning_invariants(name):
    from app.services import ingest

    text = ingest.pdf_to_text((SAMPLES / name).read_bytes())
    if not text.strip():
        pytest.fail(f"{name}: no text recovered")
    sections = ingest.split_sections(text)
    assert sections
    assert all(s["text"] in text for s in sections), "sections must be exact slices"
    assert "".join(s["text"] for s in sections) == text, "sectioning must be lossless"
