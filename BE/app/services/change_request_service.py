"""
Document change requests - B9 of the client's process flow.

The chart's second decision diamond asks whether there is "any change in
existing format/generation of new format". If there is, the answer is not to
edit the format: it is to raise a change request, have the QMS Coordinator
approve it, and only then execute it.

That sequence is enforced here rather than merely encouraged. `format_service`
refuses to edit an active format at all, so this module is the only route by
which a live format is ever revised or a new one released. The two conditions
noted against B9 are the two notifications below: one to the QMS Coordinator
when a request is filed, one back to the Process Owner when it is decided.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import User
from ..models_qms import ChangeRequest, Format
from . import format_service, notification_service as notify, transitions

SUBMITTED, UNDER_REVIEW, APPROVED, REJECTED, IMPLEMENTED = (
    "submitted", "under_review", "approved", "rejected", "implemented"
)

CHANGE_EXISTING, NEW_FORMAT = "change_existing", "new_format"

OPEN_STATUSES = (SUBMITTED, UNDER_REVIEW)


class ChangeRequestError(ValueError):
    """The request is not allowed by the rules of the change control process."""


class ChangeRequestPermissionError(ChangeRequestError):
    """The person is not the one who may take this step."""


# ---------------------------------------------------------------- raising


def create(db: Session, actor: User, data: dict) -> ChangeRequest:
    """
    File a change request (B9, condition 1).

    Either against an existing format, or asking for a brand new one. The
    coordinator is taken from the format when there is one, because change
    control for a format belongs to whoever was appointed to it, not to
    whichever coordinator the person raising it happens to pick.
    """
    kind = (data.get("kind") or CHANGE_EXISTING).strip().lower()
    if kind not in (CHANGE_EXISTING, NEW_FORMAT):
        raise ChangeRequestError(f"'{kind}' is not a kind of change request.")

    title = (data.get("title") or "").strip()
    reason = (data.get("reason") or "").strip()
    proposed = (data.get("proposed_change") or "").strip()

    if not title:
        raise ChangeRequestError("A change request needs a title.")
    if not reason:
        raise ChangeRequestError("Say why the change is needed.")
    if not proposed:
        raise ChangeRequestError("Describe the change being proposed.")

    fmt: Optional[Format] = None
    if kind == CHANGE_EXISTING:
        format_id = data.get("format_id")
        if not format_id:
            raise ChangeRequestError(
                "Say which format is to be changed, or raise this as a request "
                "for a new format instead."
            )
        fmt = db.query(Format).filter(Format.id == format_id).first()
        if not fmt:
            raise ChangeRequestError("That format no longer exists.")
        if fmt.status != format_service.ACTIVE:
            raise ChangeRequestError(
                f"{fmt.code} rev {fmt.revision} is not the current released format. "
                "Raise the request against the current active revision."
            )
        open_already = (
            db.query(ChangeRequest)
            .filter(ChangeRequest.format_id == fmt.id,
                    ChangeRequest.status.in_(OPEN_STATUSES))
            .first()
        )
        if open_already:
            raise ChangeRequestError(
                f"{open_already.number} is already open against {fmt.code}. "
                "Settle that one before raising another."
            )

    coordinator_id = (
        fmt.qms_coordinator_id if fmt else None
    ) or data.get("qms_coordinator_id") or None
    if not fmt and coordinator_id:
        # a new format has no coordinator to inherit: the one named must be one, and
        # not the raiser - otherwise anybody could approve their own new template
        coordinator = db.query(User).filter(User.id == coordinator_id).first()
        if coordinator is None or not coordinator.is_active or not (
                coordinator.is_admin or coordinator.can_approve
                or coordinator.has_permission("change_requests.approve")):
            raise ChangeRequestError("The QMS Coordinator named is not somebody who approves change requests.")
        if actor and coordinator.id == actor.id and not actor.is_admin:
            raise ChangeRequestError("A change request is approved by somebody other than the person raising it.")

    team_id = (fmt.team_id if fmt else None) or data.get("team_id") or None

    request = ChangeRequest(
        number=_next_number(db),
        kind=kind,
        format_id=fmt.id if fmt else None,
        team_id=team_id,
        title=title[:200],
        reason=reason,
        current_state=(data.get("current_state") or "").strip() or None,
        proposed_change=proposed,
        justification=(data.get("justification") or "").strip() or None,
        raised_by=actor.id if actor else None,
        raised_at=datetime.utcnow(),
        qms_coordinator_id=coordinator_id,
        status=SUBMITTED,
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    logger.info(f"Change request {request.number} raised by {_name(actor)}")

    # B9 condition 1: "Document change request filled & mail trigger to QMS
    # coordinator."
    notify.notify(
        db, notify.DCR_SUBMITTED,
        to=request.coordinator,
        subject=f"[{request.number}] change request needs your approval",
        body=_request_body(
            request,
            f"{_name(actor)} has raised a change request.",
            "No format may be altered, and no new format generated, until you "
            "have approved this request.",
        ),
        related_type="change_request", related_id=request.id,
    )
    return request


# --------------------------------------------------------------- deciding


def decide(db: Session, request: ChangeRequest, actor: User, action: str,
           comment: str = "") -> ChangeRequest:
    """
    The QMS Coordinator's decision (B9, condition 2).

    Approving does not itself change anything. It authorises the change; the
    revision is created by `execute`, which is a separate, deliberate act. The
    chart says "approved before execution", and keeping the two apart is what
    makes that ordering real rather than a description.
    """
    action = (action or "").strip().lower()
    if action not in ("approve", "reject"):
        raise ChangeRequestError(f"'{action}' is not a decision.")

    if request.status not in OPEN_STATUSES:
        raise ChangeRequestError(
            f"{request.number} is already {request.status} and cannot be decided again."
        )

    if not _may_decide(request, actor):
        raise ChangeRequestPermissionError(
            "Approving a change request is the QMS Coordinator's act. "
            f"That is {_name(request.coordinator)}."
        )

    if action == "reject" and not (comment or "").strip():
        raise ChangeRequestError("A rejected change request must say why.")

    decided = transitions.claim(
        db, ChangeRequest, request.id, OPEN_STATUSES,
        status=APPROVED if action == "approve" else REJECTED, decided_at=datetime.utcnow(),
        decided_by=actor.id, decision_comment=(comment or "").strip() or None)
    db.refresh(request)
    if not decided:  # somebody decided it a moment ago
        raise ChangeRequestError(f"{request.number} has just been decided ({request.status}).")

    # B9 condition 2: "QMS Coordinator approve the format & trigger to process
    # owner." Rejections are sent too - somebody waiting on a change is owed the
    # answer either way.
    recipients = [request.raiser]
    if request.format and request.format.process_owner:
        recipients.append(request.format.process_owner)

    outcome = "approved" if action == "approve" else "not approved"
    notify.notify(
        db, notify.DCR_DECIDED,
        to=recipients,
        subject=f"[{request.number}] change request {outcome}",
        body=_request_body(
            request,
            f"{_name(actor)} has {outcome} this change request.",
            (f"Comment: {request.decision_comment}\n\n" if request.decision_comment else "")
            + ("The change may now be executed, which will create the next "
               "revision of the format."
               if action == "approve" else
               "The format is unchanged."),
        ),
        related_type="change_request", related_id=request.id,
    )
    return request


def execute(db: Session, request: ChangeRequest, actor: User,
            data: Optional[dict] = None) -> Format:
    """
    Carry out an approved change request.

    For a change to an existing format this supersedes it with the next
    revision; for a new format it creates one. Either way the result starts as
    a draft, so the responsibilities and the specification can be settled
    before anybody fills it, and the request is marked implemented and points
    at what it produced.
    """
    if request.status != APPROVED:
        raise ChangeRequestError(
            f"{request.number} is {request.status}. Only an approved change "
            "request may be executed."
        )
    if not _may_decide(request, actor):
        raise ChangeRequestPermissionError(
            "Executing a change request is the QMS Coordinator's act. "
            f"That is {_name(request.coordinator)}."
        )

    data = data or {}
    # taken before the work: a second click (or a second coordinator) finds it implemented
    if not transitions.claim(db, ChangeRequest, request.id, [APPROVED], status=IMPLEMENTED):
        db.refresh(request)
        raise ChangeRequestError(f"{request.number} has already been executed.")
    db.refresh(request)
    try:
        successor = _carry_out(db, request, actor, data)
    except Exception:
        db.rollback()
        transitions.claim(db, ChangeRequest, request.id, [IMPLEMENTED], status=APPROVED)
        raise

    db.commit()
    db.refresh(request)

    # a new format's draft is designed by an administrator: they are told it is waiting
    designers = (db.query(User).filter(User.is_admin.is_(True), User.is_active.is_(True)).all()
                 if request.kind != CHANGE_EXISTING else [])
    notify.notify(
        db, notify.DCR_DECIDED,
        to=[request.raiser,
            successor.process_owner if successor.process_owner_id else None, *designers],
        subject=f"[{request.number}] executed - {successor.code} rev {successor.revision}",
        body=_request_body(
            request,
            f"{_name(actor)} has executed this change request.",
            f"{successor.code} rev {successor.revision} has been created as a "
            "draft. It has to be released before records can be filled "
            "against it.",
        ),
        related_type="change_request", related_id=request.id,
    )
    logger.info(
        f"Change request {request.number} executed -> "
        f"{successor.code} rev {successor.revision}")
    return successor


def _carry_out(db: Session, request: ChangeRequest, actor: User, data: dict) -> Format:
    """The next revision of the format, or the new format, as a draft."""
    if request.kind == CHANGE_EXISTING:
        if not request.format:
            raise ChangeRequestError("The format this request refers to no longer exists.")
        return format_service.new_revision(
            db, request.format, actor, data, change_request=request)
    else:
        payload = dict(data)
        payload.setdefault("title", request.title)
        payload.setdefault("team_id", request.team_id)
        payload.setdefault("qms_coordinator_id", request.qms_coordinator_id)
        # a blank code is the team's next one (format_service.next_code)
        successor = format_service.create_format(db, actor, payload)
        request.resulting_format_id = successor.id
        request.status = IMPLEMENTED
        return successor


def start_review(db: Session, request: ChangeRequest, actor: User) -> ChangeRequest:
    """The coordinator has picked it up. Purely so the raiser can see movement."""
    if request.status != SUBMITTED:
        return request
    if not _may_decide(request, actor):
        raise ChangeRequestPermissionError("Only the QMS Coordinator may take up a change request.")
    request.status = UNDER_REVIEW
    db.commit()
    db.refresh(request)
    return request


# ---------------------------------------------------------------- queries


def get(db: Session, request_id: str) -> Optional[ChangeRequest]:
    return db.query(ChangeRequest).filter(ChangeRequest.id == request_id).first()


def list_requests(db: Session, *, status: Optional[str] = None,
                  team_id: Optional[str] = None,
                  format_id: Optional[str] = None,
                  for_coordinator: Optional[User] = None,
                  raised_by: Optional[User] = None,
                  limit: int = 200) -> list[ChangeRequest]:
    q = db.query(ChangeRequest)
    if status:
        q = q.filter(ChangeRequest.status == status)
    if team_id:
        q = q.filter(ChangeRequest.team_id == team_id)
    if format_id:
        q = q.filter(ChangeRequest.format_id == format_id)
    if for_coordinator is not None:
        q = q.filter(ChangeRequest.qms_coordinator_id == for_coordinator.id)
    if raised_by is not None:
        q = q.filter(ChangeRequest.raised_by == raised_by.id)
    return (
        q.order_by(ChangeRequest.raised_at.desc())
        .limit(max(1, min(limit, 1000)))
        .all()
    )


def waiting_for(db: Session, user: User) -> list[ChangeRequest]:
    """Change requests this person has to decide."""
    if user.is_admin:
        return [r for r in list_requests(db) if r.status in OPEN_STATUSES]
    return [
        r for r in list_requests(db, for_coordinator=user)
        if r.status in OPEN_STATUSES
    ]


def stats(db: Session) -> dict:
    q = db.query(ChangeRequest)
    return {
        "total": q.count(),
        "submitted": q.filter(ChangeRequest.status == SUBMITTED).count(),
        "under_review": q.filter(ChangeRequest.status == UNDER_REVIEW).count(),
        "approved": q.filter(ChangeRequest.status == APPROVED).count(),
        "rejected": q.filter(ChangeRequest.status == REJECTED).count(),
        "implemented": q.filter(ChangeRequest.status == IMPLEMENTED).count(),
    }


# ---------------------------------------------------------------- helpers


def _may_decide(request: ChangeRequest, actor: User) -> bool:
    if not actor:
        return False
    if actor.is_admin:
        return True
    if request.qms_coordinator_id and request.qms_coordinator_id == actor.id:
        return True
    # A coordinator was never named on the format. Anyone appointed to the role
    # can then take it, rather than leaving the request stranded.
    if not request.qms_coordinator_id:
        return actor.has_permission("change_requests.approve")
    return False


def _next_number(db: Session) -> str:
    """DCR-2026-0001, restarting each year."""
    year = datetime.utcnow().year
    prefix = f"DCR-{year}-"
    used = (
        db.query(func.count(ChangeRequest.id))
        .filter(ChangeRequest.number.like(f"{prefix}%"))
        .scalar()
    ) or 0
    return f"{prefix}{used + 1:04d}"


def _request_body(request: ChangeRequest, lead: str, ask: str) -> str:
    fmt = request.format
    lines = [
        lead,
        "",
        f"Request       {request.number}",
        f"Kind          {'Change to an existing format' if request.kind == CHANGE_EXISTING else 'New format'}",
    ]
    if fmt:
        lines.append(f"Format        {fmt.code} rev {fmt.revision} - {fmt.title}")
    lines += [
        f"Title         {request.title}",
        f"Raised by     {_name(request.raiser)}",
        "",
        f"Reason:\n  {request.reason}",
        "",
        f"Proposed change:\n  {request.proposed_change}",
        "",
        ask,
        "",
        notify.link(f"/change-request/dcr/{request.id}"),  # the request's page (FE App.tsx)
    ]
    return "\n".join(lines)


def _name(user: Optional[User]) -> str:
    if not user:
        return "nobody yet"
    return user.full_name or user.username
