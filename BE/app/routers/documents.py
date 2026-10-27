"""
Looking at the sheet a record was filled from.

What is left of a document repository. The product this grew out of kept a
filing cabinet: folders, tags, correspondents, bulk edits, a semantic search, a
staging tray watched for dropped files. The record process needs none of it,
because a record's evidence is not filed by anybody - it arrives attached to
one record, is read once, and is looked at afterwards only to check what the
paper actually said.

So this serves exactly that: the bytes, a picture of the first page, the text
the OCR recovered, and enough about the file for the viewer to know how to
show it. Everything else went with the filing cabinet.

The route prefix stays `/api/documents` because a record points at its evidence
by document id, and those ids are already written into filed records.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Document, User
from ..services import thumbnails
from ..services.auth_service import require_permission_flexible
from ..services.file_utils import safe_headers, served_type

router = APIRouter()

# What a browser can show in place, as opposed to what it can only download.
VIEWABLE_TYPES = ("image/", "text/")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp")
TEXT_SUFFIXES = (".txt", ".md", ".markdown", ".csv", ".log")


def _load(db: Session, document_id: str) -> Document:
    """Fetch evidence metadata shared by the document viewer endpoints."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="That evidence is not on file.")
    return document


def _bytes_of(document: Document) -> Path:
    """The file on disk, or a 404 that says the bytes are the missing part."""
    path = Path(document.file_path) if document.file_path else None
    if not path or not path.exists():
        raise HTTPException(
            status_code=404,
            detail="The record points at this sheet, but the file is no longer on disk.")
    return path


def _page_count(path: Path) -> Optional[int]:
    """How many pages, when that is cheap to answer. None rather than a guess."""
    if path.suffix.lower() != ".pdf":
        return None
    try:
        from PyPDF2 import PdfReader

        with open(path, "rb") as handle:
            return len(PdfReader(handle).pages)
    except Exception:
        return None


@router.get("/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(require_permission_flexible("documents.read"))):
    """Return the metadata needed to identify and describe one evidence file."""
    document = _load(db, document_id)
    return {
        "id": document.id,
        "title": document.title or document.original_filename or document.filename,
        "filename": document.original_filename or document.filename,
        "mime_type": document.mime_type,
        "file_size": document.file_size,
        "ocr_status": document.ocr_status,
        "ocr_engine": document.ocr_engine,
        "ocr_confidence": document.ocr_confidence,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    }


@router.get("/{document_id}/preview-info")
def get_preview_info(document_id: str, db: Session = Depends(get_db),
                     current_user: User = Depends(require_permission_flexible("documents.read"))):
    """
    Tell the viewer how to show this sheet before it tries.

    The front end should not have to guess a renderer from a filename. This
    reports what the file actually is, whether the bytes are still there, and
    what to fall back to when the browser cannot display it.
    """
    document = _load(db, document_id)

    path = Path(document.file_path) if document.file_path else None
    on_disk = bool(path and path.exists())

    mime = (document.mime_type or "").lower()
    if not mime and path:
        mime = (mimetypes.guess_type(str(path))[0] or "").lower()
    suffix = path.suffix.lower() if path else ""

    if mime == "application/pdf" or suffix == ".pdf":
        mode = "pdf"
    elif mime.startswith("image/") or suffix in IMAGE_SUFFIXES:
        mode = "image"
    elif mime.startswith("text/") or suffix in TEXT_SUFFIXES:
        mode = "text"
    else:
        mode = "unsupported"

    if not on_disk:
        mode = "missing"

    return {
        "document_id": document.id,
        "title": document.title or document.original_filename or document.filename,
        "filename": document.original_filename or document.filename,
        "mime_type": mime or "application/octet-stream",
        "file_size": document.file_size,
        "mode": mode,
        "file_url": f"/api/documents/{document.id}/file",
        "download_url": f"/api/documents/{document.id}/download",
        "has_text": bool((document.full_text or "").strip()),
        "text_length": len(document.full_text or ""),
        "page_hint": _page_count(path) if on_disk else None,
    }


@router.get("/{document_id}/text")
def get_document_text(document_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(require_permission_flexible("documents.read"))):
    """Return OCR text and structured extraction for the evidence viewer."""
    document = _load(db, document_id)
    return {
        "document_id": document.id,
        "title": document.title or document.original_filename,
        "text": document.full_text or "",
        "ocr_status": document.ocr_status,
        "ocr_engine": document.ocr_engine,
        "ocr_confidence": document.ocr_confidence,
        "structured_html": document.structured_html or "",
    }


@router.get("/{document_id}/file")
def get_document_file(document_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(require_permission_flexible("documents.read"))):
    """
    The sheet itself, for the viewer.

    Anything a browser can render is served inline, plain text and markdown
    included - served as an attachment they download instead of displaying,
    which is why a preview would never match the real page.
    """
    document = _load(db, document_id)
    path = _bytes_of(document)

    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    if media_type.startswith("text/"):
        # Text served as-is would be sniffed; pin the charset so accents survive.
        media_type = f"{media_type}; charset=utf-8"

    if media_type.startswith(VIEWABLE_TYPES) or media_type == "application/pdf":
        return FileResponse(
            path=str(path),
            media_type=media_type,
            headers={
                **safe_headers(media_type),
                "Content-Disposition": "inline",
                # Evidence is reopened often while a record is reviewed, but a
                # sheet can also be replaced - revalidate rather than cache hard.
                "Cache-Control": "private, no-cache, must-revalidate",
            },
        )

    return FileResponse(path=str(path), media_type=media_type,
                        filename=document.original_filename, headers=safe_headers(media_type))


@router.get("/{document_id}/download")
def download_document(document_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(require_permission_flexible("documents.read"))):
    """Download the original evidence file as an attachment."""
    document = _load(db, document_id)
    path = _bytes_of(document)
    return FileResponse(
        path=str(path),
        media_type=served_type(path.name)[0],
        filename=document.original_filename or document.filename,
        headers=safe_headers(served_type(path.name)[0]),
    )


@router.get("/{document_id}/thumbnail")
def get_document_thumbnail(document_id: str, db: Session = Depends(get_db),
                           current_user: User = Depends(require_permission_flexible("documents.read"))):
    """
    A PNG of the sheet's first page.

    404 when the format cannot be pictured. The caller is expected to draw a
    typed placeholder rather than a broken image, so this is a normal outcome
    and not an error worth logging.
    """
    document = _load(db, document_id)
    path = _bytes_of(document)

    png = thumbnails.thumbnail(document_id, path, document.mime_type)
    if png is None:
        raise HTTPException(status_code=404, detail="No preview for this file type")

    return Response(
        content=png,
        media_type="image/png",
        # Cached under a modification-time key, so a long browser cache is safe.
        headers={"Cache-Control": "private, max-age=86400"},
    )
    