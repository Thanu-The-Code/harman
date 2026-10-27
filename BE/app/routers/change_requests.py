"""
Document change request API - B9 of the client's record process flow.

The chart's second decision diamond routes every change to an existing format,
and every new format, through a change request the QMS Coordinator approves
before execution. `format_service` refuses to edit an active format at all, so
these endpoints are the only door.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..models_qms import ChangeRequest
from ..services import change_request_service as dcr
from ..services import format_service as fmts
from ..services.audit_service import log_audit_event
from ..services.auth_service import get_current_user_flexible

router = APIRouter()


# ---------------------------------------------------------------- payloads


class ChangeRequestPayload(BaseModel):
    kind: str = "change_existing"          # change_existing | new_format
    format_id: Optional[str] = None
    team_id: Optional[str] = None
    qms_coordinator_id: Optional[str] = None
    title: str = Field(max_length=200)
    reason: str
    current_state: Optional[str] = None
    proposed_change: str
    justification: Optional[str] = None


class DecisionPayload(BaseModel):
    action: str                            # approve | reject
    comment: str = ""


class FieldPayload(BaseModel):
    label: str
    field_type: str = "text"
    unit: Optional[str] = None
    spec_min: Optional[float] = None
    spec_max: Optional[float] = None
    spec_text: Optional[str] = None
    options: Optional[list[str]] = None
    required: bool = True
    help_text: Optional[str] = None


class ExecutePayload(BaseModel):
    """
    What the new revision, or the new format, should look like.

    Everything is optional for a revision: anything left out is carried forward
    from the format being superseded, which is what makes a small change a
    small amount of typing.
    """
    code: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    team_id: Optional[str] = None
    frequency: Optional[str] = None
    work_instruction_ref: Optional[str] = None
    work_instruction: Optional[str] = None
    storage_path: Optional[str] = None
    cft_target_days: Optional[int] = None
    process_owner_id: Optional[str] = None
    overall_process_owner_id: Optional[str] = None
    qms_coordinator_id: Optional[str] = None
    cft_member_ids: Optional[list[str]] = None
    fields: Optional[list[FieldPayload]] = None


# ----------------------------------------------------------- serialisation


def _person(user: Optional[User]) -> Optional[dict]:
    if not user:
        return None
    return {"id": user.id, "name": user.full_name or user.username,
            "email": user.email, "job_title": user.job_title}


KIND_LABELS = {
    dcr.CHANGE_EXISTING: "Change to an existing format",
    dcr.NEW_FORMAT: "New format",
}

STATUS_LABELS = {
    dcr.SUBMITTED: "Submitted",
    dcr.UNDER_REVIEW: "Under review",
    dcr.APPROVED: "Approved - awaiting execution",
    dcr.REJECTED: "Not approved",
    dcr.IMPLEMENTED: "Executed",  # the revision is drafted; it is released through the template review
}


def _json(request: ChangeRequest, viewer: Optional[User] = None) -> dict:
    fmt = request.format
    may_decide = dcr._may_decide(request, viewer) if viewer else False
    return {
        "id": request.id,
        "number": request.number,
        "kind": request.kind,
        "kind_label": KIND_LABELS.get(request.kind, request.kind),
        "format": {
            "id": fmt.id, "code": fmt.code, "title": fmt.title,
            "revision": fmt.revision, "status": fmt.status,
        } if fmt else None,
        "team": {"id": request.team.id, "code": request.team.code,
                 "name": request.team.name} if request.team else None,
        "title": request.title,
        "reason": request.reason,
        "current_state": request.current_state,
        "proposed_change": request.proposed_change,
        "justification": request.justification,
        "raised_by": _person(request.raiser),
        "raised_at": request.raised_at,
        "coordinator": _person(request.coordinator),
        "status": request.status,
        "status_label": STATUS_LABELS.get(request.status, request.status),
        "decided_at": request.decided_at,
        "decided_by": _person(request.decider),
        "decision_comment": request.decision_comment,
        "resulting_format": {
            "id": request.resulting_format.id,
            "code": request.resulting_format.code,
            "revision": request.resulting_format.revision,
            "status": request.resulting_format.status,
        } if request.resulting_format else None,
        # Resolved on the server so a button and the API cannot disagree.
        "can": {
            "decide": bool(may_decide and request.status in dcr.OPEN_STATUSES),
            "execute": bool(may_decide and request.status == dcr.APPROVED),
        },
    }


def _load(db: Session, request_id: str) -> ChangeRequest:
    request = dcr.get(db, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Change request not found")
    return request


# ------------------------------------------------------------------ routes



def _status(exc: Exception) -> int:
    """403 when it is the wrong person, 400 when it is the wrong moment or input."""
    return 403 if isinstance(exc, dcr.ChangeRequestPermissionError) else 400

@router.get("")
@router.get("/", include_in_schema=False)
def list_change_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
    status: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    format_id: Optional[str] = Query(None),
    mine: bool = Query(False, description="Only the ones I raised"),
    waiting: bool = Query(False, description="Only the ones waiting on me"),
):
    if waiting:
        found = dcr.waiting_for(db, current_user)
    else:
        found = dcr.list_requests(
            db, status=status, team_id=team_id, format_id=format_id,
            raised_by=current_user if mine else None,
        )
    return {
        "requests": [_json(r, current_user) for r in found],
        "stats": dcr.stats(db),
        "waiting_on_me": len(dcr.waiting_for(db, current_user)),
    }


@router.get("/{request_id}")
def get_change_request(request_id: str, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user_flexible)):
    return _json(_load(db, request_id), current_user)


@router.post("")
@router.post("/", include_in_schema=False)
def create_change_request(payload: ChangeRequestPayload,
                          db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user_flexible)):
    """B9 condition 1 - file the request and trigger the QMS Coordinator."""
    try:
        request = dcr.create(db, current_user, payload.model_dump())
    except dcr.ChangeRequestError as exc:
        raise HTTPException(status_code=_status(exc), detail=str(exc))

    log_audit_event(db, current_user.id, "change_request.created",
                    "change_request", request.id,
                    {"number": request.number, "kind": request.kind})
    return _json(request, current_user)


@router.post("/{request_id}/review")
def start_review(request_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user_flexible)):
    """The coordinator has picked it up, so the raiser can see it moving."""
    request = _load(db, request_id)
    try:
        request = dcr.start_review(db, request, current_user)
    except dcr.ChangeRequestError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return _json(request, current_user)


@router.post("/{request_id}/decide")
def decide(request_id: str, payload: DecisionPayload,
           db: Session = Depends(get_db),
           current_user: User = Depends(get_current_user_flexible)):
    """
    B9 condition 2 - the QMS Coordinator approves, and the Process Owner is told.

    Approving authorises the change; it does not make it. The revision is
    created by a separate call to /execute, which is what "approved before
    execution" means in practice.
    """
    request = _load(db, request_id)
    try:
        request = dcr.decide(db, request, current_user, payload.action, payload.comment)
    except dcr.ChangeRequestError as exc:
        raise HTTPException(status_code=_status(exc), detail=str(exc))

    log_audit_event(db, current_user.id, f"change_request.{payload.action}",
                    "change_request", request.id, {"number": request.number})
    return _json(request, current_user)


@router.post("/{request_id}/execute")
def execute(request_id: str, payload: ExecutePayload,
            db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user_flexible)):
    """
    Carry out an approved request: supersede the format with its next revision,
    or create the new one. Either way the result is a draft that has to be
    released deliberately before anybody fills it.
    """
    request = _load(db, request_id)
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if payload.fields is not None:
        data["fields"] = [f.model_dump() for f in payload.fields]

    try:
        created = dcr.execute(db, request, current_user, data)
    except (dcr.ChangeRequestError, fmts.FormatError) as exc:
        raise HTTPException(status_code=_status(exc), detail=str(exc))

    log_audit_event(db, current_user.id, "change_request.executed",
                    "change_request", request.id,
                    {"number": request.number,
                     "format": created.code, "revision": created.revision})
    return {
        "request": _json(request, current_user),
        "format": {
            "id": created.id, "code": created.code, "title": created.title,
            "revision": created.revision, "status": created.status,
            "readiness": fmts.readiness(created),
        },
    }
