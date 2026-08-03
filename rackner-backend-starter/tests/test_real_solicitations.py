"""Ingest against the real federal solicitations in data/samples/.

The mock proves the plumbing; only a real 100-page solicitation proves the
parsing. These PDFs are committed as shared team fixtures precisely so this
runs in CI.

The assertions are deliberately about INVARIANTS, not about how many sections a
given PDF happens to produce — the parser will improve, and a test that pins
section counts would just be re-written every time instead of catching bugs.
"""

from __future__ import annotations

import pytest

from app.llm import gateway
from app.services import ingest


def _ids(paths):
    return [p.name for p in paths]


@pytest.fixture(scope="module")
def parsed(sample_pdfs):
    """(name, raw_text, sections) for every sample PDF that has a text layer."""
    out = []
    for path in sample_pdfs:
        raw = ingest.pdf_to_text(path.read_bytes())
        if raw.strip():
            out.append((path.name, raw, ingest.split_sections(raw)))
    return out


def test_samples_exist(sample_pdfs):
    assert sample_pdfs, "no PDFs in data/samples/ — the fixtures are missing"


def test_at_least_one_sample_has_a_text_layer(parsed):
    assert parsed, "every sample PDF came back empty; pypdf extraction is broken"


def test_extraction_produces_substantial_text(parsed):
    for name, raw, _ in parsed:
        assert len(raw) > 500, f"{name}: only {len(raw)} chars extracted"


def test_sections_are_exact_slices_of_the_pdf_text(parsed):
    """The grounding invariant, on real documents."""
    for name, raw, sections in parsed:
        for sec in sections:
            assert sec["text"] in raw, f"{name}: section {sec['ref']!r} is not a slice of the source"


def test_sections_reconstruct_the_source_exactly(parsed):
    """No character may be lost between parsing and serving."""
    for name, raw, sections in parsed:
        assert "".join(s["text"] for s in sections) == raw, f"{name}: sectioning lost characters"


def test_pages_are_sane(parsed):
    for name, raw, sections in parsed:
        page_count = raw.count("\f") + 1
        for sec in sections:
            assert 1 <= sec["page"] <= page_count, f"{name}: page {sec['page']} out of range"


def test_section_refs_are_clean(parsed):
    for name, _, sections in parsed:
        for sec in sections:
            assert not sec["ref"].startswith("§"), f"{name}: ref kept the § prefix"
            assert sec["ref"] == sec["ref"].strip(), f"{name}: ref has surrounding whitespace"


def test_no_section_is_empty(parsed):
    for name, _, sections in parsed:
        assert all(s["text"] for s in sections), f"{name}: produced an empty section"


def test_obligations_from_real_documents_are_grounded(parsed):
    """End to end on real text: anything marked verified must be highlightable."""
    checked = 0
    for name, _, sections in parsed:
        by_ref = {s["ref"]: s["text"] for s in sections}
        for ob in gateway.extract_obligations(sections):
            if not ob["verified"]:
                continue
            cited = by_ref.get(ob["citation"]["section"])
            assert cited is not None, f"{name}: citation names an unknown section"
            assert ob["verbatim_quote"] in cited, (
                f"{name}: verified quote not in its cited section — "
                f"UI indexOf would fail for {ob['verbatim_quote'][:80]!r}"
            )
            checked += 1
    assert checked > 0, "no verified obligations across any real sample — extraction may be broken"


def test_build_source_document_on_a_real_pdf(sample_pdfs):
    """The whole assembly path, including the label."""
    for path in sample_pdfs:
        data = path.read_bytes()
        if not ingest.pdf_to_text(data).strip():
            continue
        opp = {
            "id": "REAL-001",
            "title": "Real sample",
            "description": "",
            "solicitation_number": path.stem,
        }
        doc = ingest.build_source_document(opp, attachments=[data])
        assert doc["opportunity_id"] == "REAL-001"
        assert path.stem in doc["label"]
        assert doc["sections"], f"{path.name}: no sections built"
        return
    pytest.skip("no sample PDF had a text layer")


def test_scanned_pdf_degrades_instead_of_raising():
    """Image-only PDFs must return '' so callers can fall back, not crash."""
    assert ingest.pdf_to_text(b"%PDF-1.4\nnot really a pdf") == ""
    assert ingest.pdf_to_text(b"") == ""
