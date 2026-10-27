"""API for requests to amend information on an existing QMS record."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..models_qms import RecordChangeRequest
from ..services import format_service as fmts
from ..services import record_change_request_service as rcrs
from ..services.audit_service import log_audit_event
from ..services.auth_service import get_current_user_flexible

router = APIRouter()


class CreatePayload(BaseModel):
    record_id: str
    title: Optional[str] = Field(None, max_length=200)
    reason: str
    assigned_to_id: Optional[str] = None


class EditPayload(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    reason: Optional[str] = None


class AssignPayload(BaseModel):
    assigned_to_id: Optional[str] = None


class DecisionPayload(BaseModel):
    action: str
    comment: str = ""


class ImplementPayload(BaseModel):
    note: str = ""


def _person(user: Optional[User]) -> Optional[dict]:
    if not user:
        return None
    return {
        "id": user.id,
        "name": user.full_name or user.username,
        "email": user.email,
        "job_title": user.job_title,
        "department": user.department,
    }


STATUS_LABELS = {
    rcrs.OPEN: "Open",
    rcrs.APPROVED: "Approved",
    rcrs.IMPLEMENTED: "Implemented",
    rcrs.NOT_APPROVED: "Not approved",
}


def _json(request: RecordChangeRequest, viewer: User) -> dict:
    record = request.record
    fmt = record.format
    values = [
        {
            "id": value.id,
            "label": value.label,
            "value": value.value,
            "unit": value.unit,
            "in_spec": value.in_spec,
        }
        for value in (record.values or [])
    ]
    total_items = len(values)
    completed_items = sum(
        1 for value in values
        if value["value"] is not None and str(value["value"]).strip()
    )
    may_decide = rcrs.can_decide(request, viewer)
    may_assign = request.status == rcrs.OPEN and rcrs.can_assign(viewer)
    return {
        "id": request.id,
        "number": request.number,
        "title": request.title,
        "reason": request.reason,
        "status": request.status,
        "status_label": STATUS_LABELS[request.status],
        "raised_by": _person(request.raiser),
        "raised_at": request.raised_at,
        "assigned_to": _person(request.assignee),
        "assigned_at": request.assigned_at,
        "decided_by": _person(request.decider),
        "decided_at": request.decided_at,
        "decision_comment": request.decision_comment,
        "implemented_by": _person(request.implementer),
        "implemented_at": request.implemented_at,
        "implementation_note": request.implementation_note,
        "record": {
            "id": record.id,
            "number": record.number,
            "document_name": fmt.title if fmt else record.number,
            "document_type": (
                f"{fmts.FREQUENCY_LABELS.get(fmt.frequency, fmt.frequency)} inspection"
                if fmt else None
            ),
            "format": {
                "id": fmt.id,
                "code": fmt.code,
                "title": fmt.title,
                "revision": record.format_revision,
            } if fmt else None,
            "department": record.team.name if record.team else None,
            "department_code": record.team.code if record.team else None,
            "filled_by": _person(record.filler),
            "filled_at": record.filled_at,
            "submitted_at": record.submitted_at,
            "total_items": total_items,
            "completed_items": completed_items,
            "completion_percent": (
                round(completed_items * 100 / total_items) if total_items else 0
            ),
            "fields": values,
            "document": {
                "id": record.document.id,
                "title": (
                    record.document.title or record.document.original_filename
                    or record.document.filename
                ),
                "mime_type": record.document.mime_type,
                "file_url": f"/api/documents/{record.document.id}/file",
            } if record.document else None,
        },
        "can": {
            "edit": request.status == rcrs.OPEN and (
                viewer.is_admin or request.raised_by == viewer.id
            ),
            "assign": may_assign,
            "decide": may_decide,
            "implement": rcrs.can_implement(request, viewer),
        },
    }


def _load(db: Session, request_id: str) -> RecordChangeRequest:
    request = rcrs.get(db, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Record change request not found")
    return request


def _raise_http(exc: rcrs.RecordChangeRequestError) -> None:
    if isinstance(exc, rcrs.RecordChangeRequestNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, rcrs.RecordChangeRequestPermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
@router.get("/", include_in_schema=False)
def list_record_change_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
    status: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=200),
    mine: bool = Query(False),
    waiting: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    waiting_assignee_id = current_user.id if not current_user.is_admin else None
    assigned_to_id = waiting_assignee_id if waiting else None
    try:
        found, total = rcrs.list_requests(
            db,
            status=status,
            department=department,
            search=search,
            assigned_to_id=assigned_to_id,
            raised_by_id=current_user.id if mine else None,
            waiting=waiting,
            page=page,
            page_size=page_size,
        )
        waiting_count = rcrs.list_requests(
            db,
            assigned_to_id=waiting_assignee_id,
            waiting=True,
            page=1,
            page_size=100,
        )[1]
    except rcrs.RecordChangeRequestError as exc:
        _raise_http(exc)
    return {
        "requests": [_json(request, current_user) for request in found],
        "stats": rcrs.stats(db),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "waiting_on_me": waiting_count,
    }


@router.get("/{request_id}")
def get_record_change_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    return _json(_load(db, request_id), current_user)


@router.post("")
@router.post("/", include_in_schema=False)
def create_record_change_request(
    payload: CreatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    try:
        request = rcrs.create(db, current_user, payload.model_dump())
    except rcrs.RecordChangeRequestError as exc:
        _raise_http(exc)
    log_audit_event(
        db, current_user.id, "record_change_request.created",
        "record_change_request", request.id, {"number": request.number},
    )
    return _json(request, current_user)


@router.patch("/{request_id}")
def edit_record_change_request(
    request_id: str,
    payload: EditPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    request = _load(db, request_id)
    try:
        request = rcrs.update(
            db, request, current_user,
            {key: value for key, value in payload.model_dump().items()
             if key in payload.model_fields_set},
        )
    except rcrs.RecordChangeRequestError as exc:
        _raise_http(exc)
    log_audit_event(
        db, current_user.id, "record_change_request.edited",
        "record_change_request", request.id, {"number": request.number},
    )
    return _json(request, current_user)


@router.post("/{request_id}/assign")
def assign_record_change_request(
    request_id: str,
    payload: AssignPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    request = _load(db, request_id)
    try:
        request = rcrs.assign(
            db, request, current_user, payload.assigned_to_id
        )
    except rcrs.RecordChangeRequestError as exc:
        _raise_http(exc)
    log_audit_event(
        db, current_user.id, "record_change_request.assigned",
        "record_change_request", request.id,
        {"number": request.number, "assigned_to": request.assigned_to_id},
    )
    return _json(request, current_user)


@router.post("/{request_id}/decide")
def decide_record_change_request(
    request_id: str,
    payload: DecisionPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    request = _load(db, request_id)
    try:
        request = rcrs.decide(
            db, request, current_user, payload.action, payload.comment
        )
    except rcrs.RecordChangeRequestError as exc:
        _raise_http(exc)
    log_audit_event(
        db, current_user.id, f"record_change_request.{request.status}",
        "record_change_request", request.id,
        {"number": request.number, "comment": request.decision_comment},
    )
    return _json(request, current_user)


@router.post("/{request_id}/implement")
def implement_record_change_request(
    request_id: str,
    payload: ImplementPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    request = _load(db, request_id)
    try:
        request = rcrs.implement(db, request, current_user, payload.note)
    except rcrs.RecordChangeRequestError as exc:
        _raise_http(exc)
    log_audit_event(
        db, current_user.id, "record_change_request.implemented",
        "record_change_request", request.id,
        {"number": request.number, "note": request.implementation_note},
    )
    return _json(request, current_user)
