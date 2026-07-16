"""Document endpoints: upload, fetch, serve PDF, delete.

Flow the frontend follows:
  1. POST /documents           → stores file + runs the pipeline
  2. GET  /documents/{id}      → metadata + status
  3. GET  /documents/{id}/pdf  → the file itself, for the viewer pane

The PII pre-upload gate (POST /documents/scan) and 3-day retention land in
Week 4.
"""

import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from core.config import UPLOAD_DIR, MAX_UPLOAD_MB
from db.models import Document
from pipeline.run import process_document

router = APIRouter(prefix="/documents", tags=["documents"])


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


@router.post("")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Store the PDF and run the full pipeline over it."""
    path = _save_upload(file)
    doc = Document(
        filename=file.filename or "document.pdf",
        file_path=path,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    process_document(db, doc)  # sync for MVP; a queue is the scale-up path

    return {"id": doc.id, "status": doc.status}


@router.get("")
def list_documents(db: Session = Depends(get_db)):
    docs = db.scalars(select(Document).order_by(Document.uploaded_at.desc())).all()
    return [
        {
            "id": d.id, "filename": d.filename, "status": d.status,
            "num_pages": d.num_pages, "uploaded_at": d.uploaded_at.isoformat(),
        }
        for d in docs
    ]


def _get_doc(doc_id: int, db: Session) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found.")
    return doc


@router.get("/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db)):
    d = _get_doc(doc_id, db)
    return {
        "id": d.id, "filename": d.filename, "status": d.status,
        "num_pages": d.num_pages,
    }


@router.get("/{doc_id}/pdf")
def get_document_pdf(doc_id: int, db: Session = Depends(get_db)):
    d = _get_doc(doc_id, db)
    if not d.file_path or not os.path.exists(d.file_path):
        raise HTTPException(410, "PDF no longer on disk.")
    return FileResponse(d.file_path, media_type="application/pdf", filename=d.filename)


@router.delete("/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    d = _get_doc(doc_id, db)
    if d.file_path and os.path.exists(d.file_path):
        os.remove(d.file_path)
    db.delete(d)
    db.commit()
    return {"deleted": doc_id}
