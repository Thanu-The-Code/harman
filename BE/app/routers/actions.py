"""
Corrective and preventive actions, and the reporting screen that counts them.

Two things that belong to the same half of the quality system: what was done
about a finding, and whether the plant is keeping up with it. The rules live in
`capa_service` and `inspection_report`; this layer validates input, shapes
output and decides who may call what.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..models_qms import ACTION_OPEN, Record
from ..services import capa_service as capa
from ..services import inspection_report as report
from ..services.audit_service import log_audit_event
from ..services.auth_service import get_current_user_flexible

router = APIRouter()


# ---------------------------------------------------------------- payloads


class ActionPayload(BaseModel):
    record_id: str
    kind: str = "corrective"
    finding: Optional[str] = None
    action: str = Field(max_length=4000)
    root_cause: Optional[str] = None
    owner_id: Optional[str] = None
    due_date: Optional[str] = None


class ActionEdit(BaseModel):
    kind: Optional[str] = None
    finding: Optional[str] = None
    action: Optional[str] = None
    root_cause: Optional[str] = None
    owner_id: Optional[str] = None
    due_date: Optional[str] = None


class ClosurePayload(BaseModel):
    note: str = ""


# ------------------------------------------------------------------ reading


@router.get("")
@router.get("/", include_in_schema=False)
def list_actions(db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user_flexible),
                 status: Optional[str] = Query(None),
                 kind: Optional[str] = Query(None),
                 team_id: Optional[str] = Query(None),
                 record_id: Optional[str] = Query(None),
                 mine: bool = Query(False, description="Only actions I own"),
                 overdue: bool = Query(False)):
    """
    Every action, narrowed the ways the screens ask for.

    The overdue sweep runs here rather than in a background job: this is one of
    the two screens that would report an overdue action anyway, so it is the
    honest place to notice one has slipped. It writes at most once per action.
    """
    capa.sweep_overdue(db)

    rows = capa.listing(
        db, status=status, kind=kind, team_id=team_id, record_id=record_id,
        owner=current_user if mine else None, overdue_only=overdue,
    )
    return {
        "actions": [capa.to_dict(a) for a in rows],
        "summary": capa.summary(db, team_id=team_id),
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user_flexible),
              days: int = Query(90, ge=1, le=1825),
              team_id: Optional[str] = Query(None),
              inspection_date: Optional[date] = Query(None),
              # today / month / year; when absent the last `days` days (the dashboard's range picker)
              period: Optional[str] = Query(None)):
    """
    The reporting screen, in one request.

    Declared before /{action_id}: routes match in order, and otherwise
    "dashboard" would be read as an action id.
    """
    capa.sweep_overdue(db)
    report.sweep_pending(db)
    return report.dashboard(db, days=days, team_id=team_id,
                            inspection_date=inspection_date, period=period)


@router.get("/{action_id}")
def get_action(action_id: str, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user_flexible)):
    action = capa.get(db, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="That action does not exist.")
    return capa.to_dict(action)


# ------------------------------------------------------------------ writing


@router.post("")
@router.post("/", include_in_schema=False)
def raise_action(payload: ActionPayload, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user_flexible)):
    """Record what is being done about a finding."""
    record = db.query(Record).filter(Record.id == payload.record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="That record does not exist.")

    try:
        action = capa.raise_action(db, record, current_user, payload.model_dump())
    except capa.ActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    log_audit_event(db, current_user.id, "action.raised", "corrective_action",
                    action.id, {"record": record.number, "kind": action.kind})
    return capa.to_dict(action)


@router.put("/{action_id}")
def edit_action(action_id: str, payload: ActionEdit,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user_flexible)):
    action = capa.get(db, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="That action does not exist.")

    # Only the keys actually sent, so a form that carries three fields cannot
    # silently blank the two it does not show.
    sent = payload.model_dump(exclude_unset=True)
    try:
        action = capa.update_action(db, action, current_user, sent)
    except capa.ActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    log_audit_event(db, current_user.id, "action.updated", "corrective_action",
                    action.id, sent)
    return capa.to_dict(action)


@router.post("/{action_id}/close")
def close_action(action_id: str, payload: ClosurePayload,
                 db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user_flexible)):
    """
    Mark it done.

    Closing an action does not clear the record's N-ok flag. That decision is
    the Overall Process Owner's at B5, and an action list must not be able to
    route around it.
    """
    action = capa.get(db, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="That action does not exist.")

    try:
        action = capa.close_action(db, action, current_user, payload.note)
    except capa.ActionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    log_audit_event(db, current_user.id, "action.closed", "corrective_action",
                    action.id, {"note": payload.note[:200]})
    return capa.to_dict(action)


@router.post("/{action_id}/reopen")
def reopen_action(action_id: str, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user_flexible)):
    action = capa.get(db, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="That action does not exist.")
    if action.status == ACTION_OPEN:
        return capa.to_dict(action)

    action = capa.reopen(db, action, current_user)
    log_audit_event(db, current_user.id, "action.reopened", "corrective_action",
                    action.id, {})
    return capa.to_dict(action)
