"""Textract OCR fallback for scanned PDFs — offline, Textract stubbed.

The contract: OCR is off by default (zero AWS), touches ONLY pages without a
text layer when on, and every failure path returns what pypdf already gave.
The live half (real Textract on the two committed scanned samples) is opt-in
in test_textract_live.py.
"""

from __future__ import annotations

import pytest

from app.services import ingest

# A tiny real PDF with a text layer, built once with PyMuPDF.
_fitz = pytest.importorskip("fitz")


def _digital_pdf(*page_texts: str) -> bytes:
    doc = _fitz.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    return doc.tobytes()


def _imageonly_pdf(pages: int = 2) -> bytes:
    """Pages containing only a drawn rectangle — no text layer anywhere."""
    doc = _fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.draw_rect(_fitz.Rect(72, 72, 300, 300), fill=(0.8, 0.8, 0.8))
    return doc.tobytes()


# --- default: OCR off ----------------------------------------------------------


def test_off_by_default_scanned_pdf_degrades_to_empty(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "OCR_MODE", "off")
    assert ingest.pdf_to_text(_imageonly_pdf()).strip() == ""


def test_off_by_default_never_touches_aws(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "OCR_MODE", "off")
    monkeypatch.setattr(
        ingest, "_textract_lines", lambda png: pytest.fail("Textract called with OCR off")
    )
    ingest.pdf_to_text(_imageonly_pdf())


# --- OCR on, Textract stubbed ---------------------------------------------------


@pytest.fixture
def textract_on(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "OCR_MODE", "textract")


def test_scanned_pages_are_ocred(textract_on, monkeypatch):
    calls = []

    def fake_ocr(png: bytes):
        calls.append(png)
        return f"C.{len(calls)} OCR RECOVERED\nThe Contractor shall comply."

    monkeypatch.setattr(ingest, "_textract_lines", fake_ocr)
    text = ingest.pdf_to_text(_imageonly_pdf(pages=2))

    assert len(calls) == 2, "both text-less pages should be OCR'd"
    assert "OCR RECOVERED" in text
    assert text.count("\f") == 1, "page structure (form feeds) must survive OCR"


def test_digital_pages_are_never_ocred(textract_on, monkeypatch):
    """Hybrid rule: pypdf text is byte-exact; OCR must not replace it."""
    monkeypatch.setattr(
        ingest, "_textract_lines", lambda png: pytest.fail("OCR ran on a digital page")
    )
    text = ingest.pdf_to_text(
        _digital_pdf("C.1 Statement of Work. The Contractor shall provide monitoring services.")
    )
    assert "The Contractor shall provide monitoring services." in text


def test_mixed_document_ocrs_only_the_scanned_pages(textract_on, monkeypatch):
    digital = _fitz.open()
    page = digital.new_page()
    page.insert_text(
        (72, 72), "C.1 Digital page. The Contractor shall deliver monthly reports promptly."
    )
    digital.new_page().draw_rect(_fitz.Rect(72, 72, 200, 200), fill=(0.5, 0.5, 0.5))
    data = digital.tobytes()

    calls = []

    def fake_ocr(png):
        calls.append(png)
        return "SCANNED EXHIBIT TEXT"

    monkeypatch.setattr(ingest, "_textract_lines", fake_ocr)
    text = ingest.pdf_to_text(data)

    assert len(calls) == 1, "exactly the one scanned page gets OCR'd"
    pages = text.split("\f")
    assert "deliver monthly reports" in pages[0]
    assert "SCANNED EXHIBIT TEXT" in pages[1]


def test_ocr_output_is_canonicalized(textract_on, monkeypatch):
    """OCR text enters through the same boundary as everything else."""
    monkeypatch.setattr(
        ingest, "_textract_lines", lambda png: "Client Reference’s “Signature”\r\nLine two"
    )
    text = ingest.pdf_to_text(_imageonly_pdf(pages=1))
    assert "Reference's" in text and '"Signature"' in text
    assert "\r" not in text


def test_textract_failure_degrades_to_pypdf_result(textract_on, monkeypatch):
    monkeypatch.setattr(ingest, "_textract_lines", lambda png: None)
    assert ingest.pdf_to_text(_imageonly_pdf()).strip() == ""


def test_render_failure_degrades_cleanly(textract_on, monkeypatch):
    monkeypatch.setattr(ingest, "_render_page_png", lambda data, index: None)
    monkeypatch.setattr(
        ingest, "_textract_lines", lambda png: pytest.fail("OCR called with no image")
    )
    assert ingest.pdf_to_text(_imageonly_pdf()).strip() == ""


def test_garbage_bytes_still_return_empty(textract_on, monkeypatch):
    monkeypatch.setattr(ingest, "_textract_lines", lambda png: "SHOULD NOT APPEAR")
    assert ingest.pdf_to_text(b"%PDF-1.4\nnot really a pdf") == ""


def test_ocred_document_flows_into_sections(textract_on, monkeypatch):
    """End of the chain: OCR'd text must feed the same sectioning invariants."""
    monkeypatch.setattr(
        ingest,
        "_textract_lines",
        lambda png: "252.204-7012 Safeguarding\nThe Contractor shall report incidents.",
    )
    text = ingest.pdf_to_text(_imageonly_pdf(pages=1))
    sections = ingest.split_sections(text)
    assert sections
    assert all(s["text"] in text for s in sections)
    assert "".join(s["text"] for s in sections) == text
