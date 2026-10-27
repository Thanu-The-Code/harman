"""Document digitisation (app/ocr) over HTTP.

  GET  /api/ocr/formats    enabled document formats, extensions and capabilities (the upload
                           dialog builds its file chooser from this); starts loading the OCR
                           models in the background so the first scan is not also the slowest
  GET  /api/ocr/health     engine settings and whether the models are loaded
  POST /api/ocr/template   file                  -> template elements (task_data) for the designer
  POST /api/ocr/digitize   file                  -> the document as-is (text, layout, page images)
  POST /api/ocr/read-form  file                  -> a filled document as a form plus its values
  POST /api/ocr/extract    file + form (JSON)    -> values for that form read from a filled copy
  POST /api/ocr/export     file + form + answers -> that workbook with the values written in

Turning a document into a template is template authoring (administrators / formats.manage);
reading a filled copy is open to anyone signed in. Each upload goes to the format handler
that accepts it; DOC_FORMATS switches formats on and off (see app/ocr/formats).
"""
from __future__ import annotations

import base64
import json
import threading
from typing import Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from loguru import logger
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..ocr import engine
from ..ocr.formats import (
    OCR_UNAVAILABLE,
    FormatRegistry,
    UnsupportedFile,
    UnsupportedFormat,
    UploadedFile,
    build_registry,
)
from ..ocr.title import suggest_title
from ..services.audit_service import log_audit_event
from ..services.auth_service import get_current_user_flexible
from .formats import require_formats_manage_permission

router = APIRouter()

MAX_UPLOAD = 25 * 1024 * 1024

_registry: FormatRegistry | None = None
_registry_lock = threading.Lock()
_warming = threading.Event()


def registry() -> FormatRegistry:
    """The enabled formats, built once (DOC_FORMATS is read at first use)."""
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = build_registry()
        return _registry


def _ocr_enabled() -> bool:
    return any(h.key in ("pdf", "image") for h in registry().handlers())


def _warm_up() -> None:
    """Load the OCR models once, in the background (a few seconds, ~1 GB of memory)."""
    if _warming.is_set() or not _ocr_enabled():
        return
    _warming.set()
    engine.warm_up()


async def _read(file: UploadFile) -> UploadedFile:
    data = await file.read()
    if not data:
        raise HTTPException(400, "The file is empty.")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "The file is larger than 25 MB.")
    return UploadedFile(data=data, filename=file.filename or "")


async def _run(capability: str, upload: UploadedFile, call: Callable):
    """Route the upload to its format handler. The work (OCR can take a minute a page) runs in
    a worker thread so other requests are served meanwhile; the engine serialises its own use."""
    try:
        handler = registry().resolve(upload, capability)
        return await run_in_threadpool(call, handler)
    except UnsupportedFormat as exc:
        raise HTTPException(415, str(exc)) from exc
    except UnsupportedFile as exc:
        raise HTTPException(400, str(exc)) from exc
    except engine.EngineError as exc:  # the engine failed twice on this document
        logger.error(f"OCR failed on {upload.filename!r}: {exc.__cause__!r}")
        raise HTTPException(503, str(exc)) from exc


def _task_data(form: str) -> list:
    try:
        task_data = json.loads(form)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "form must be the form's task_data as JSON") from exc
    if isinstance(task_data, dict):
        task_data = task_data.get("task_data", [])
    if not isinstance(task_data, list):
        raise HTTPException(400, "form must be a list of form elements")
    return task_data


@router.get("/formats")
def list_formats(current_user: User = Depends(get_current_user_flexible)):
    _warm_up()
    return {"formats": registry().describe(), "ocr_available": _ocr_enabled(), "ocr_unavailable_reason": OCR_UNAVAILABLE}


@router.get("/health")
def health(current_user: User = Depends(get_current_user_flexible)):
    return {"status": "ok", "formats": [h.key for h in registry().handlers()], **engine.settings()}


@router.post("/template")
async def template_from_document(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """A blank (or filled) form as template elements for the designer."""
    require_formats_manage_permission(current_user)
    upload = await _read(file)
    result = await _run("template", upload, lambda h: h.build_template(upload))
    # what Create Template opens with: the text that reads as the form's title
    result["title"] = suggest_title(result.get("task_data") or [])
    log_audit_event(
        db,
        current_user.id,
        "format.imported_from_document",
        "format",
        None,
        {"filename": upload.filename, "elements": len(result.get("task_data") or []), "stats": result.get("stats")},
        ip_address=request.client.host if request.client else None,
    )
    return result


@router.post("/digitize")
async def digitize(file: UploadFile = File(...), current_user: User = Depends(get_current_user_flexible)):
    require_formats_manage_permission(current_user)  # CPU-heavy: template authors only
    upload = await _read(file)
    return await _run("digitize", upload, lambda h: h.digitize(upload))


@router.post("/read-form")
async def read_form(file: UploadFile = File(...), current_user: User = Depends(get_current_user_flexible)):
    require_formats_manage_permission(current_user)
    upload = await _read(file)
    return await _run("read_form", upload, lambda h: h.read_form(upload))


@router.post("/extract")
async def extract_values(
    file: UploadFile = File(...),
    form: str = Form(...),
    current_user: User = Depends(get_current_user_flexible),
):
    require_formats_manage_permission(current_user)
    task_data = _task_data(form)
    upload = await _read(file)
    return await _run("extract", upload, lambda h: h.extract(upload, task_data))


@router.post("/export")
async def export(
    file: UploadFile = File(...),
    form: str = Form(...),
    answers: str = Form(...),
    current_user: User = Depends(get_current_user_flexible),
):
    """The uploaded workbook (e.g. the blank Excel form) with the form's answers written in."""
    require_formats_manage_permission(current_user)
    task_data = _task_data(form)
    try:
        values = json.loads(answers)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "answers must be JSON") from exc
    if isinstance(values, list):  # [{name, value}]
        values = {x.get("name"): x.get("value") for x in values if isinstance(x, dict) and x.get("name")}
    if not isinstance(values, dict):
        raise HTTPException(400, "answers must map field names to values")
    upload = await _read(file)
    result = await _run("export", upload, lambda h: h.export(upload, task_data, values))
    return {**result, "data": base64.b64encode(result["data"]).decode("ascii")}
