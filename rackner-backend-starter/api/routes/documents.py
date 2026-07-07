"""Document endpoints: PII pre-scan, upload, fetch, serve PDF, delete.

Flow the frontend follows:
  1. POST /documents/scan      → PII findings (nothing stored)
  2. (UI shows warning popup if findings; user confirms)
  3. POST /documents           → stores file + runs pipeline (pii_acknowledged)
  4. GET  /documents/{id}      → metadata + status
  5. GET  /documents/{id}/pdf  → the file itself, for the viewer pane
"""

import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from core.config import UPLOAD_DIR, MAX_UPLOAD_MB
from core.pii import scan_text
from core.retention import expiry_from_now, is_expired, purge_expired
from db.models import Document
from pipeline.run import process_document

router = APIRouter(prefix="/documents", tags=["documents"])


def _extract_text_quick(path: str) -> str:
    """Light text pull for the PII scan (PyMuPDF, no positions needed)."""
    import fitz
    with fitz.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def _save_upload(file: UploadFile) -> str:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")
    dest = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}.pdf")
    size = 0
    with open(dest, "wb") as out:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_MB * 1024 * 1024:
                out.close()
                os.remove(dest)
                raise HTTPException(413, f"File exceeds {MAX_UPLOAD_MB} MB limit.")
            out.write(chunk)
    return dest


@router.post("/scan")
async def scan_document(file: UploadFile = File(...)):
    """Step 1: PII check only. The temp file is deleted immediately after."""
    tmp_path = _save_upload(file)
    try:
        findings = scan_text(_extract_text_quick(tmp_path))
        return {
            "has_pii": bool(findings),
            "findings": [
                {"kind": f.kind, "count": f.count, "sample": f.sample_masked}
                for f in findings
            ],
        }
    finally:
        os.remove(tmp_path)  # scan stores NOTHING


@router.post("")
async def upload_document(
    file: UploadFile = File(...),
    pii_acknowledged: bool = Form(False),
    db: Session = Depends(get_db),
):
    """Step 3: real upload. Runs the full pipeline, stamps 3-day expiry."""
    path = _save_upload(file)
    doc = Document(
        filename=file.filename or "document.pdf",
        file_path=path,
        pii_acknowledged=pii_acknowledged,
        expires_at=expiry_from_now(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    process_document(db, doc)  # sync for MVP; queue is the scale-up path

    return {"id": doc.id, "status": doc.status, "expires_at": doc.expires_at.isoformat()}


@router.get("")
def list_documents(db: Session = Depends(get_db)):
    purge_expired(db)  # lazy enforcement of retention
    docs = db.scalars(select(Document).order_by(Document.uploaded_at.desc())).all()
    return [
        {
            "id": d.id, "filename": d.filename, "status": d.status,
            "num_pages": d.num_pages, "uploaded_at": d.uploaded_at.isoformat(),
            "expires_at": d.expires_at.isoformat() if d.expires_at else None,
            "pii_findings": d.pii_findings,
        }
        for d in docs
    ]


def _get_live_doc(doc_id: int, db: Session) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None or is_expired(doc):
        purge_expired(db)
        raise HTTPException(404, "Document not found (it may have passed its 3-day retention window).")
    return doc


@router.get("/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db)):
    d = _get_live_doc(doc_id, db)
    return {
        "id": d.id, "filename": d.filename, "status": d.status,
        "num_pages": d.num_pages, "expires_at": d.expires_at.isoformat() if d.expires_at else None,
    }


@router.get("/{doc_id}/pdf")
def get_document_pdf(doc_id: int, db: Session = Depends(get_db)):
    d = _get_live_doc(doc_id, db)
    if not d.file_path or not os.path.exists(d.file_path):
        raise HTTPException(410, "PDF no longer on disk.")
    return FileResponse(d.file_path, media_type="application/pdf", filename=d.filename)


@router.delete("/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    d = _get_live_doc(doc_id, db)
    if d.file_path and os.path.exists(d.file_path):
        os.remove(d.file_path)
    db.delete(d)
    db.commit()
    return {"deleted": doc_id}
