"""
Corrective and preventive actions, and whether anybody has finished them.

A quality system that only records findings is a filing cabinet. The value is
in the second half: a reading failed, somebody was made responsible, a date was
set, and either it was done or it was not. This module owns that half.

Three rules shape everything here:

    **An action never decides anything.** Raising one does not set the record's
    N-ok flag and closing one does not clear it. The chart gives that decision
    to the Overall Process Owner at B5, and a list of actions must not be able
    to route around a decision the process reserves for a person.

    **Overdue is derived, never stored.** A due date and the clock are enough.
    A stored flag would be wrong for however long it took a job to run, and
    "wrong for a while" is not a state a quality report may have.

    **The alert fires once.** `overdue_notified_at` is the only thing written
    by the sweep, so a person is told the day it slips and not every time a
    page is opened.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import User
from ..models_qms import (
    ACTION_CLOSED, ACTION_CORRECTIVE, ACTION_KINDS, ACTION_OPEN,
    CorrectiveAction, Format, QualityTeam, Record,
)
from . import notification_service as notify


class ActionError(Exception):
    """Something the person asking is not allowed to do, said plainly."""


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    """
    A datetime that can be compared with `now()`.

    SQLite hands back naive datetimes whatever the column says, and comparing
    one with an aware one raises. Everything stored here is UTC, so saying so
    is the whole fix.
    """
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ reading


def is_overdue(action: CorrectiveAction, at: Optional[datetime] = None) -> bool:
    """Open, dated, and the date has gone."""
    if action.status != ACTION_OPEN or not action.due_date:
        return False
    return _aware(action.due_date) < (at or now())


def get(db: Session, action_id: str) -> Optional[CorrectiveAction]:
    return db.query(CorrectiveAction).filter(CorrectiveAction.id == action_id).first()


def for_record(db: Session, record_id: str) -> list[CorrectiveAction]:
    return (db.query(CorrectiveAction)
            .filter(CorrectiveAction.record_id == record_id)
            .order_by(CorrectiveAction.created_at)
            .all())


def listing(db: Session, *, status: Optional[str] = None,
            kind: Optional[str] = None, owner: Optional[User] = None,
            team_id: Optional[str] = None, record_id: Optional[str] = None,
            overdue_only: bool = False) -> list[CorrectiveAction]:
    """Every action, narrowed the ways the screens ask for."""
    query = db.query(CorrectiveAction).join(Record, CorrectiveAction.record_id == Record.id)
    if status:
        query = query.filter(CorrectiveAction.status == status)
    if kind:
        query = query.filter(CorrectiveAction.kind == kind)
    if owner is not None:
        query = query.filter(CorrectiveAction.owner_id == owner.id)
    if team_id:
        query = query.filter(Record.team_id == team_id)
    if record_id:
        query = query.filter(CorrectiveAction.record_id == record_id)

    rows = query.order_by(CorrectiveAction.due_date.is_(None),
                          CorrectiveAction.due_date,
                          CorrectiveAction.created_at.desc()).all()
    if overdue_only:
        moment = now()
        rows = [r for r in rows if is_overdue(r, moment)]
    return rows


# ------------------------------------------------------------------ writing


def raise_action(db: Session, record: Record, actor: Optional[User], data: dict
                 ) -> CorrectiveAction:
    """
    Record what is being done about a finding.

    Deliberately permissive about who may raise one: anybody who can see the
    record can say what was done about it, because the alternative is that the
    person who actually quarantined the batch cannot write it down. Closing one
    is where the permission lives.
    """
    text = (data.get("action") or "").strip()
    if not text:
        raise ActionError("Say what is being done about it.")

    kind = (data.get("kind") or ACTION_CORRECTIVE).strip().lower()
    if kind not in ACTION_KINDS:
        kind = ACTION_CORRECTIVE

    owner = None
    owner_id = (data.get("owner_id") or "").strip() or None
    if owner_id:
        owner = db.query(User).filter(User.id == owner_id).first()
        if not owner:
            raise ActionError("That person is not in the directory.")

    action = CorrectiveAction(
        record_id=record.id,
        kind=kind,
        finding=(data.get("finding") or "").strip() or None,
        action=text,
        root_cause=(data.get("root_cause") or "").strip() or None,
        owner_id=owner.id if owner else None,
        due_date=_parse_date(data.get("due_date")),
        raised_by=actor.id if actor else None,
        status=ACTION_OPEN,
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    _log(db, record, actor,
         f"{kind.capitalize()} action raised: {text[:120]}")

    if owner:
        notify.notify(
            db, notify.ACTION_ASSIGNED, to=owner,
            subject=f"{kind.capitalize()} action on {record.number}",
            body=_body(record, action,
                       "You have been made responsible for an action."),
            related_type="corrective_action", related_id=action.id,
        )
    return action


def close_action(db: Session, action: CorrectiveAction, actor: Optional[User],
                 note: str = "") -> CorrectiveAction:
    """
    Mark it done.

    Only the person it belongs to, the person who raised it, or an
    administrator. Anyone else closing somebody's action is how a quality
    system ends up with nothing open and nothing done.
    """
    if action.status == ACTION_CLOSED:
        raise ActionError("That action is already closed.")

    allowed = {action.owner_id, action.raised_by} - {None}
    if actor and not actor.is_admin and allowed and actor.id not in allowed:
        raise ActionError(
            "Only the person this action belongs to, or whoever raised it, "
            "may close it.")

    action.status = ACTION_CLOSED
    action.closure_note = (note or "").strip() or None
    action.closed_by = actor.id if actor else None
    action.closed_at = now()
    db.commit()
    db.refresh(action)

    _log(db, action.record, actor,
         f"Action closed: {action.action[:120]}")
    return action


def reopen(db: Session, action: CorrectiveAction, actor: Optional[User]
           ) -> CorrectiveAction:
    """Put a closed action back. Kept because closing one by mistake happens."""
    if action.status == ACTION_OPEN:
        return action
    action.status = ACTION_OPEN
    action.closed_at = None
    action.closed_by = None
    # It may well be past its date again, and the person should be told again.
    action.overdue_notified_at = None
    db.commit()
    db.refresh(action)
    _log(db, action.record, actor, f"Action reopened: {action.action[:120]}")
    return action


def update_action(db: Session, action: CorrectiveAction, actor: Optional[User],
                  data: dict) -> CorrectiveAction:
    """Change an open action - who owns it, when it is due, what it says."""
    if action.status == ACTION_CLOSED:
        raise ActionError("Reopen it before changing it.")

    if "action" in data:
        text = (data.get("action") or "").strip()
        if not text:
            raise ActionError("Say what is being done about it.")
        action.action = text
    if "finding" in data:
        action.finding = (data.get("finding") or "").strip() or None
    if "root_cause" in data:
        action.root_cause = (data.get("root_cause") or "").strip() or None
    if "kind" in data:
        kind = (data.get("kind") or "").strip().lower()
        if kind in ACTION_KINDS:
            action.kind = kind

    told = False
    if "owner_id" in data:
        owner_id = (data.get("owner_id") or "").strip() or None
        if owner_id and owner_id != action.owner_id:
            owner = db.query(User).filter(User.id == owner_id).first()
            if not owner:
                raise ActionError("That person is not in the directory.")
            action.owner_id = owner.id
            told = True
        elif not owner_id:
            action.owner_id = None

    if "due_date" in data:
        action.due_date = _parse_date(data.get("due_date"))
        # A new date is a new deadline, so the alert is owed again.
        action.overdue_notified_at = None

    db.commit()
    db.refresh(action)

    if told and action.owner:
        notify.notify(
            db, notify.ACTION_ASSIGNED, to=action.owner,
            subject=f"{action.kind.capitalize()} action on {action.record.number}",
            body=_body(action.record, action,
                       "You have been made responsible for an action."),
            related_type="corrective_action", related_id=action.id,
        )
    return action


# ------------------------------------------------------------------- sweeps


def sweep_overdue(db: Session) -> list[CorrectiveAction]:
    """
    Tell people their action has slipped, once.

    Called from the screens that would report it anyway - the dashboard and the
    notification list - rather than from a background job. That is a deliberate
    trade: this product ships to plants that run it on one machine, and a
    scheduler thread that has to be alive for a quality alert to exist is a
    worse promise than one that fires the first time anybody looks. The write
    is idempotent, so being called from three places costs nothing.
    """
    moment = now()
    slipped = [a for a in db.query(CorrectiveAction)
               .filter(CorrectiveAction.status == ACTION_OPEN,
                       CorrectiveAction.due_date.isnot(None),
                       CorrectiveAction.overdue_notified_at.is_(None)).all()
               if is_overdue(a, moment)]

    for action in slipped:
        action.overdue_notified_at = moment
        if action.owner:
            notify.notify(
                db, notify.ACTION_OVERDUE, to=action.owner,
                subject=f"Overdue: {action.kind} action on {action.record.number}",
                body=_body(action.record, action,
                           "This action is past the date it was due."),
                related_type="corrective_action", related_id=action.id,
            )
    if slipped:
        db.commit()
        logger.info("capa: %d action(s) reported overdue", len(slipped))
    return slipped


# -------------------------------------------------------------- the numbers


def summary(db: Session, *, team_id: Optional[str] = None) -> dict:
    """
    Open, closed, overdue and the split by kind.

    Counted here rather than in the dashboard router so that the number on the
    tile and the rows behind it can never disagree about what "open" means.
    """
    rows = listing(db, team_id=team_id)
    moment = now()
    overdue = [r for r in rows if is_overdue(r, moment)]
    open_rows = [r for r in rows if r.status == ACTION_OPEN]

    return {
        "total": len(rows),
        "open": len(open_rows),
        "closed": len(rows) - len(open_rows),
        "overdue": len(overdue),
        "corrective": sum(1 for r in rows if r.kind == ACTION_CORRECTIVE),
        "preventive": sum(1 for r in rows if r.kind != ACTION_CORRECTIVE),
        # Closed on time, as a share of everything closed. The one number that
        # says whether the second half of the quality system actually works.
        "closed_on_time": sum(
            1 for r in rows
            if r.status == ACTION_CLOSED and r.due_date and r.closed_at
            and _aware(r.closed_at) <= _aware(r.due_date)),
    }


# ------------------------------------------------------------------ helpers


def _parse_date(value) -> Optional[datetime]:
    """A date from a form, as UTC. Anything unreadable means no date."""
    if not value:
        return None
    if isinstance(value, datetime):
        return _aware(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return _aware(parsed)


def _body(record: Record, action: CorrectiveAction, lead: str) -> str:
    bits = [lead, "", f"Record: {record.number}"]
    if action.finding:
        bits.append(f"Finding: {action.finding}")
    bits.append(f"Action: {action.action}")
    if action.due_date:
        bits.append(f"Due: {_aware(action.due_date).strftime('%d %b %Y')}")
    bits.append("")
    bits.append(notify.link(f"/track?record={record.id}"))
    return "\n".join(bits)


def _log(db: Session, record: Optional[Record], actor: Optional[User],
         summary_text: str) -> None:
    """Leave it on the record's own trail, where an auditor reads."""
    if record is None:
        return
    from ..models_qms import RecordEvent

    db.add(RecordEvent(
        record_id=record.id,
        actor_id=actor.id if actor else None,
        kind="action",
        summary=summary_text,
    ))
    db.commit()


def to_dict(action: CorrectiveAction) -> dict:
    """One action, as every screen reads it."""
    record = action.record
    return {
        "id": action.id,
        "record_id": action.record_id,
        "record_number": record.number if record else None,
        "team": ({"id": record.team.id, "name": record.team.name}
                 if record and record.team else None),
        "format": ({"code": record.format.code, "title": record.format.title}
                   if record and record.format else None),
        "kind": action.kind,
        "finding": action.finding,
        "action": action.action,
        "root_cause": action.root_cause,
        "owner": ({"id": action.owner.id,
                   "name": action.owner.full_name or action.owner.username}
                  if action.owner else None),
        "due_date": action.due_date,
        "status": action.status,
        "overdue": is_overdue(action),
        "closure_note": action.closure_note,
        "raised_by": ({"id": action.raiser.id,
                       "name": action.raiser.full_name or action.raiser.username}
                      if action.raiser else None),
        "raised_at": action.raised_at,
        "closed_at": action.closed_at,
        "closed_by": ({"id": action.closer.id,
                       "name": action.closer.full_name or action.closer.username}
                      if action.closer else None),
    }
