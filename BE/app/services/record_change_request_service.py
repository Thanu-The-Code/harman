"""Record-level change requests, separate from B9 format revision control."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..models import User
from ..models_qms import (
    Format, QualityTeam, Record, RecordChangeRequest, RecordEvent,
)
from . import notification_service as notify, transitions

OPEN, APPROVED, IMPLEMENTED, NOT_APPROVED = (
    "open", "approved", "implemented", "not_approved"
)
STATUSES = (OPEN, APPROVED, IMPLEMENTED, NOT_APPROVED)


class RecordChangeRequestError(ValueError):
    """The requested transition is not allowed."""


class RecordChangeRequestPermissionError(RecordChangeRequestError):
    """The actor is not allowed to perform the requested action."""


class RecordChangeRequestNotFoundError(RecordChangeRequestError):
    """The requested record or request does not exist."""


def create(db: Session, actor: User, data: dict) -> RecordChangeRequest:
    record = get_record(db, data["record_id"])
    if record.stage == "cancelled":
        raise RecordChangeRequestError("A cancelled record cannot be changed.")
    if record.filled_at is None:
        raise RecordChangeRequestError(
            "A record must be filled before a change request can be raised."
        )
    if not _may_raise(record, actor):
        raise RecordChangeRequestPermissionError(
            "Only the record's Process Owner, its filler, or an authorised "
            "records user may raise a change request."
        )

    duplicate = (
        db.query(RecordChangeRequest)
        .filter(
            RecordChangeRequest.record_id == record.id,
            RecordChangeRequest.status == OPEN,
        )
        .first()
    )
    if duplicate:
        raise RecordChangeRequestError(
            f"{duplicate.number} is already open for this record."
        )

    reason = (data.get("reason") or "").strip()
    if not reason:
        raise RecordChangeRequestError("Describe why the record needs to change.")

    assigned_to_id = data.get("assigned_to_id")
    if assigned_to_id and not _may_assign(actor):
        raise RecordChangeRequestPermissionError(
            "Who decides a record change request is chosen by an administrator or QMS approver.")
    if assigned_to_id is None and record.format:
        assigned_to_id = record.format.qms_coordinator_id
    assignee = _validate_assignee(db, assigned_to_id, raiser=actor) if assigned_to_id else None
    title = (data.get("title") or "").strip()
    if not title and record.format:
        title = record.format.title
    if not title:
        title = record.number

    request = RecordChangeRequest(
        number=_next_number(db),
        record_id=record.id,
        title=title[:200],
        reason=reason,
        status=OPEN,
        raised_by=actor.id,
        raised_at=datetime.now(timezone.utc),
        assigned_to_id=assignee.id if assignee else None,
        assigned_at=datetime.now(timezone.utc) if assignee else None,
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    _record_event(
        db, request, actor, "change_request_opened",
        f"{_name(actor)} raised {request.number}.", request.reason,
    )
    if assignee:
        notify.notify(
            db, notify.RECORD_CHANGE_REQUEST_SUBMITTED,
            to=assignee,
            subject=f"[{request.number}] record change request needs review",
            body=(
                f"{_name(actor)} raised {request.number} for record "
                f"{record.number}.\n\nReason:\n{request.reason}"
            ),
            related_type="record_change_request",
            related_id=request.id,
        )
    logger.info(f"Record change request {request.number} raised")
    return request


def get(db: Session, request_id: str) -> Optional[RecordChangeRequest]:
    return (
        db.query(RecordChangeRequest)
        .filter(RecordChangeRequest.id == request_id)
        .first()
    )


def get_record(db: Session, record_id: str) -> Record:
    record = db.query(Record).filter(Record.id == record_id).first()
    if not record:
        raise RecordChangeRequestNotFoundError("Record not found.")
    return record


def update(
    db: Session,
    request: RecordChangeRequest,
    actor: User,
    data: dict,
) -> RecordChangeRequest:
    if request.status != OPEN:
        raise RecordChangeRequestError("Only an open request can be edited.")
    if not (actor.is_admin or request.raised_by == actor.id):
        raise RecordChangeRequestPermissionError(
            "Only the person who raised it may edit it."
        )

    if "title" in data and data["title"] is not None:
        title = data["title"].strip()
        if not title:
            raise RecordChangeRequestError("The request title cannot be empty.")
        request.title = title[:200]
    if "reason" in data and data["reason"] is not None:
        reason = data["reason"].strip()
        if not reason:
            raise RecordChangeRequestError("Describe why the record needs to change.")
        request.reason = reason
    db.commit()
    db.refresh(request)
    return request


def assign(
    db: Session,
    request: RecordChangeRequest,
    actor: User,
    assigned_to_id: Optional[str],
) -> RecordChangeRequest:
    if request.status != OPEN:
        raise RecordChangeRequestError("Only an open request can be assigned.")
    if not _may_assign(actor):
        raise RecordChangeRequestPermissionError(
            "Only an administrator or QMS/records approver may assign requests."
        )
    assignee = _validate_assignee(db, assigned_to_id, raiser=request.raiser) if assigned_to_id else None
    request.assigned_to_id = assignee.id if assignee else None
    request.assigned_at = datetime.now(timezone.utc) if assignee else None
    db.commit()
    db.refresh(request)

    _record_event(
        db, request, actor, "change_request_assigned",
        f"{_name(actor)} assigned {request.number}.",
        f"Assigned to {_name(assignee)}." if assignee else "Assignment cleared.",
    )
    if assignee:
        notify.notify(
            db, notify.RECORD_CHANGE_REQUEST_SUBMITTED,
            to=assignee,
            subject=f"[{request.number}] record change request assigned to you",
            body=(
                f"You have been assigned to review {request.number} for record "
                f"{request.record.number}.\n\nReason:\n{request.reason}"
            ),
            related_type="record_change_request",
            related_id=request.id,
        )
    return request


def decide(
    db: Session,
    request: RecordChangeRequest,
    actor: User,
    action: str,
    comment: str = "",
) -> RecordChangeRequest:
    action = (action or "").strip().lower()
    if action == "reject":
        action = NOT_APPROVED
    if action not in ("approve", NOT_APPROVED):
        raise RecordChangeRequestError(
            "Decision must be 'approve' or 'not_approved'."
        )
    if request.status != OPEN:
        raise RecordChangeRequestError(
            f"{request.number} is already {request.status} and cannot be decided again."
        )
    if not _may_decide(request, actor):
        raise RecordChangeRequestPermissionError(
            "Only the assigned approver may decide this request."
        )
    if action == NOT_APPROVED and not comment.strip():
        raise RecordChangeRequestError(
            "A request marked not approved must include a reason."
        )

    decided = transitions.claim(
        db, RecordChangeRequest, request.id, [OPEN],
        status=APPROVED if action == "approve" else NOT_APPROVED, decided_by=actor.id,
        decided_at=datetime.now(timezone.utc), decision_comment=comment.strip() or None)
    db.refresh(request)
    if not decided:  # decided a moment ago, by another click or person
        raise RecordChangeRequestError(f"{request.number} has just been decided ({request.status.replace('_', ' ')}).")
    _record_event(
        db, request, actor, "change_request_decided",
        f"{_name(actor)} marked {request.number} {request.status.replace('_', ' ')}.",
        request.decision_comment,
    )

    notify.notify(
        db, notify.RECORD_CHANGE_REQUEST_DECIDED,
        to=[request.raiser, request.record.filler],
        subject=f"[{request.number}] record change request {request.status.replace('_', ' ')}",
        body=(
            f"{_name(actor)} marked {request.number} "
            f"{request.status.replace('_', ' ')}."
            + (f"\n\nComment:\n{request.decision_comment}"
               if request.decision_comment else "")
        ),
        related_type="record_change_request",
        related_id=request.id,
    )
    return request


def implement(
    db: Session,
    request: RecordChangeRequest,
    actor: User,
    note: str = "",
) -> RecordChangeRequest:
    if request.status != APPROVED:
        raise RecordChangeRequestError(
            "Only an approved request can be marked implemented."
        )
    if not can_implement(request, actor):
        raise RecordChangeRequestPermissionError(
            "Only the requester, assigned approver, Process Owner, or an "
            "administrator may mark the request implemented."
        )
    implemented = transitions.claim(
        db, RecordChangeRequest, request.id, [APPROVED],
        status=IMPLEMENTED, implemented_by=actor.id, implemented_at=datetime.now(timezone.utc),
        implementation_note=note.strip() or None)
    db.refresh(request)
    if not implemented:
        raise RecordChangeRequestError(f"{request.number} has just been marked implemented.")
    _record_event(
        db, request, actor, "change_request_implemented",
        f"{_name(actor)} marked {request.number} implemented.",
        request.implementation_note,
    )
    notify.notify(
        db, notify.RECORD_CHANGE_REQUEST_IMPLEMENTED,
        to=[request.raiser, request.assignee],
        subject=f"[{request.number}] record change request implemented",
        body=(
            f"{request.number} for record {request.record.number} has been "
            "marked implemented."
            + (f"\n\nNote:\n{request.implementation_note}"
               if request.implementation_note else "")
        ),
        related_type="record_change_request",
        related_id=request.id,
    )
    return request


def list_requests(
    db: Session,
    *,
    status: Optional[str] = None,
    department: Optional[str] = None,
    search: Optional[str] = None,
    assigned_to_id: Optional[str] = None,
    raised_by_id: Optional[str] = None,
    waiting: bool = False,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[RecordChangeRequest], int]:
    query = (
        db.query(RecordChangeRequest)
        .join(Record, Record.id == RecordChangeRequest.record_id)
        .outerjoin(Format, Format.id == Record.format_id)
        .outerjoin(QualityTeam, QualityTeam.id == Record.team_id)
    )
    if status:
        if status not in STATUSES:
            raise RecordChangeRequestError(f"Unknown status '{status}'.")
        query = query.filter(RecordChangeRequest.status == status)
    if department:
        query = query.filter(
            or_(
                QualityTeam.name.ilike(f"%{department}%"),
                QualityTeam.code.ilike(f"%{department}%"),
            )
        )
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(or_(
            RecordChangeRequest.number.ilike(pattern),
            RecordChangeRequest.title.ilike(pattern),
            RecordChangeRequest.reason.ilike(pattern),
            Record.number.ilike(pattern),
            Format.title.ilike(pattern),
            Format.code.ilike(pattern),
        ))
    if assigned_to_id and not waiting:
        query = query.filter(
            RecordChangeRequest.assigned_to_id == assigned_to_id
        )
    if raised_by_id:
        query = query.filter(RecordChangeRequest.raised_by == raised_by_id)
    if waiting:
        query = query.filter(RecordChangeRequest.status == OPEN)
        if assigned_to_id:
            query = query.filter(or_(
                RecordChangeRequest.assigned_to_id == assigned_to_id,
                RecordChangeRequest.assigned_to_id.is_(None),
            ))

    total = query.count()
    requests = (
        query.order_by(RecordChangeRequest.raised_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return requests, total


def stats(db: Session) -> dict[str, int]:
    return {
        status: db.query(RecordChangeRequest)
        .filter(RecordChangeRequest.status == status)
        .count()
        for status in STATUSES
    }


def can_decide(request: RecordChangeRequest, actor: User) -> bool:
    return request.status == OPEN and _may_decide(request, actor)


def can_assign(actor: User) -> bool:
    return _may_assign(actor)


def can_implement(request: RecordChangeRequest, actor: User) -> bool:
    record = request.record
    return request.status == APPROVED and bool(
        actor.is_admin
        or request.raised_by == actor.id
        or request.assigned_to_id == actor.id
        or _is_process_owner(record, actor)
    )


def _is_process_owner(record: Record, actor: User) -> bool:
    """The record's Process Owner: chosen at submission, else the format's (B15)."""
    from . import record_service

    return actor.id in record_service.process_owner_ids(record)


def can_raise(record: Record, actor: User) -> bool:
    """Whether `actor` may raise a change request on `record` now (what `create` checks)."""
    return bool(record.stage != "cancelled" and record.filled_at is not None
                and _may_raise(record, actor))


def _may_raise(record: Record, actor: User) -> bool:
    return bool(
        actor.is_admin
        or record.filled_by == actor.id
        or _is_process_owner(record, actor)
        or actor.has_permission("records.create")
        or actor.has_permission("change_requests.create")
    )


def _may_assign(actor: User) -> bool:
    return bool(
        actor.is_admin
        or actor.has_permission("change_requests.approve")
        or actor.has_permission("records.approve")
    )


def _may_decide(request: RecordChangeRequest, actor: User) -> bool:
    if actor.is_admin:
        return True
    if request.raised_by == actor.id:
        return False  # four eyes: the person asking for a change does not grant it
    if not (actor.can_approve or actor.has_permission("records.approve")
            or actor.has_permission("change_requests.approve")):
        return False
    if request.assigned_to_id:
        return request.assigned_to_id == actor.id
    return True


def _validate_assignee(db: Session, user_id: str, raiser: Optional[User] = None) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise RecordChangeRequestError("The assigned user is missing or inactive.")
    if raiser is not None and user.id == raiser.id and not raiser.is_admin:
        raise RecordChangeRequestError("A request is decided by somebody other than the person who raised it.")
    if not (
        user.is_admin
        or user.can_approve
        or user.has_permission("records.approve")
        or user.has_permission("change_requests.approve")
    ):
        raise RecordChangeRequestError(
            "The assigned user is not allowed to approve requests."
        )
    return user


def _next_number(db: Session) -> str:
    prefix = f"RCR-{datetime.now(timezone.utc).year}-"
    used = db.query(func.count(RecordChangeRequest.id)).filter(
        RecordChangeRequest.number.like(f"{prefix}%")
    ).scalar() or 0
    return f"{prefix}{used + 1:04d}"


def _name(user: Optional[User]) -> str:
    return (user.full_name or user.username) if user else "Unknown user"


def _record_event(
    db: Session,
    request: RecordChangeRequest,
    actor: User,
    kind: str,
    summary: str,
    detail: Optional[str] = None,
) -> None:
    db.add(RecordEvent(
        record_id=request.record_id,
        actor_id=actor.id,
        kind=kind,
        summary=summary,
        detail=detail,
    ))
    db.commit()
