"""
What the plant looks like this month: the numbers behind the dashboard.

Every count on the reporting screen is worked out here, once. The alternative -
each tile counting for itself in the router, and the table behind it counting
again in the browser - is how a dashboard ends up saying 14 in one place and 12
in another, and a quality report that contradicts itself is worse than none.

Two definitions do all the work, and both are stated here rather than assumed:

    **An inspection** is a Record. Not a format, not a period - one filled
    instance of one format. "Total inspections" is therefore how many records
    exist in the window, which is the only reading of it that can be tied back
    to rows somebody can open.

    **Pending** means raised and not yet filed: everything between B2 and B8,
    however far along the chain it is. A record waiting on the CFT is pending
    in exactly the sense a plant manager means - the paperwork is not finished.

The one thing here that is not a count is `pending_inspections`, which answers
a different question: which *periods* have gone by with nothing raised at all.
A format filled daily and missed on Tuesday leaves no record to count, so the
absence has to be derived from the calendar rather than read from the table.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..utils import ist

from ..models import User
from ..models_qms import (
    NOT_OK, OK, STAGE_STORED, Format, QualityTeam, Record,
)
from . import capa_service as capa
from . import format_service as fmts
from . import notification_service as notify

# How far back the trend runs when nobody says. Twelve buckets is what fits a
# strip of bars without them becoming stripes.
DEFAULT_BUCKETS = 12


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _window(days: int) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    return end - timedelta(days=days), end


def _date_window(value: date) -> tuple[datetime, datetime]:
    start = datetime.combine(value, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _period_window(period: str) -> tuple[datetime, datetime]:
    """Today, this month or this year on the plant's calendar (IST), as UTC bounds."""
    now = ist.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        start = today.replace(day=1)
    elif period == "year":
        start = today.replace(month=1, day=1)
    else:
        start = today
    return start.astimezone(timezone.utc), now.astimezone(timezone.utc) + timedelta(microseconds=1)


def _previous_window(period: str, start: datetime,
                     end: datetime) -> tuple[datetime, datetime]:
    if period == "month":
        previous_end = start
        previous_start = (start - timedelta(days=1)).replace(day=1)
        return previous_start, previous_end
    if period == "year":
        return start.replace(year=start.year - 1), start
    span = end - start
    return start - span, start


def _at(record: Record) -> datetime:
    """
    When an inspection happened.

    Submission is the moment the inspection was *done*; a record that has been
    sitting in an approval queue for a week still belongs to the day somebody
    stood at the machine with it. Falls back to creation for a draft nobody has
    submitted yet.
    """
    return _aware(record.submitted_at or record.created_at
                  or datetime.now(timezone.utc))


# ------------------------------------------------------------------ the page


def dashboard(db: Session, *, days: int = 90,
              team_id: Optional[str] = None,
              inspection_date: Optional[date] = None,
              period: str = "today") -> dict:
    """Everything the reporting screen shows, in one query pass."""
    start, end = (_date_window(inspection_date) if inspection_date
                  else _period_window(period) if period in {"today", "month", "year"}
                  else _window(days))

    query = db.query(Record)
    if team_id:
        query = query.filter(Record.team_id == team_id)
    all_records = query.all()
    records = [r for r in all_records if start <= _at(r) < end]
    previous_start, previous_end = _previous_window(period, start, end)
    previous_records = [r for r in all_records
                        if previous_start <= _at(r) < previous_end]

    completed = [r for r in records if r.stage == STAGE_STORED]
    pending = [r for r in records if r.stage != STAGE_STORED]
    failed = [r for r in records if r.observation_status == NOT_OK]

    def counts(rows: list[Record]) -> dict[str, int]:
        return {
            "total": len(rows),
            "completed": sum(1 for r in rows if r.stage == STAGE_STORED),
            "pending": sum(1 for r in rows if r.stage != STAGE_STORED),
            "failed": sum(1 for r in rows if r.observation_status == NOT_OK),
        }

    current_counts = counts(records)
    previous_counts = counts(previous_records)

    def change(key: str) -> Optional[float]:
        previous = previous_counts[key]
        current = current_counts[key]
        if previous == 0:
            return 0.0 if current == 0 else 100.0
        return round((current - previous) * 100 / previous, 1)

    recent = [{
        "id": record.id,
        "number": record.number,
        "department": record.team.name if record.team else "-",
        "type": record.format.title if record.format else "-",
        "date": _at(record),
        "inspector": (record.filler.full_name or record.filler.username)
        if record.filler else "-",
        "status": "Completed" if record.stage == STAGE_STORED else (
            "Failed" if record.observation_status == NOT_OK else "Pending"),
    } for record in sorted(records, key=_at, reverse=True)[:5]]

    return {
        "window": {"days": days, "from": start, "to": end,
               "inspection_date": inspection_date},
        "totals": {
            "total": len(records),
            "completed": len(completed),
            "pending": len(pending),
            "failed": len(failed),
            # The share that passed first time. A percentage is what a plant
            # manager actually compares month to month; the counts above are
            # what they click into. Only records with readings to judge count:
            # a change request with no limits on it neither passed nor failed.
            "pass_rate": _pass_rate(records),
            "growth": {key: change(key) for key in current_counts},
        },
        "by_department": by_department(db, records),
        "recent": recent,
        "trend": trend(records, 1 if inspection_date else days,
                buckets=1 if inspection_date or period == "today" else DEFAULT_BUCKETS,
                start=start, end=end),
        "actions": capa.summary(db, team_id=team_id),
        "overdue_actions": [capa.to_dict(a) for a in
                            capa.listing(db, team_id=team_id, overdue_only=True)[:10]],
        "missed": missed_periods(db, team_id=team_id),
    }


def _pass_rate(records: list[Record]) -> Optional[float]:
    judged = [r for r in records if r.observation_status in (OK, NOT_OK)]
    if not judged:
        return None
    return round(100 * sum(1 for r in judged if r.observation_status == OK) / len(judged), 1)


def by_department(db: Session, records: list[Record]) -> list[dict]:
    """
    Department-wise inspection status.

    Every team that owns a record in the window gets a row, whether or not it
    has anything outstanding - a department with nothing pending is a result
    worth seeing, and dropping it makes the chart look like the department
    stopped existing.
    """
    buckets: dict[str, dict] = {}
    for record in records:
        team = record.team
        key = team.id if team else ""
        row = buckets.setdefault(key, {
            "id": team.id if team else None,
            "name": team.name if team else "Unassigned",
            "code": team.code if team else None,
            "total": 0, "completed": 0, "pending": 0, "failed": 0,
        })
        row["total"] += 1
        if record.stage == STAGE_STORED:
            row["completed"] += 1
        else:
            row["pending"] += 1
        if record.observation_status == NOT_OK:
            row["failed"] += 1

    return sorted(buckets.values(), key=lambda r: (-r["total"], r["name"]))


def trend(records: list[Record], days: int,
          buckets: int = DEFAULT_BUCKETS,
          start: Optional[datetime] = None,
          end: Optional[datetime] = None) -> list[dict]:
    """
    Inspections over time, in equal buckets across the window.

    Bucketed by division rather than by calendar month so the shape of the
    chart does not change with the window somebody picked.

    Each bucket is split three ways *that cannot overlap*: passed, failed, and
    not yet judged. That matters because the obvious split - completed against
    failed - double counts. A record can be both: an out-of-specification
    reading that went through the CFT and was filed anyway is completed and
    failed at the same time, and stacking those two produces a bar taller than
    the number of inspections it claims to draw.
    """
    if start is None or end is None:
        start, end = _window(days)
    if buckets < 1:
        buckets = 1
    span = (end - start) / buckets

    out = []
    for index in range(buckets):
        opened = start + span * index
        closed = opened + span
        inside = [r for r in records if opened <= _at(r) < closed]
        passed = sum(1 for r in inside if r.observation_status == OK)
        failed = sum(1 for r in inside if r.observation_status == NOT_OK)
        out.append({
            "from": opened,
            "to": closed,
            "label": opened.strftime("%d %b"),
            "total": len(inside),
            "passed": passed,
            "failed": failed,
            # Nothing on it to judge: no reading with a limit filled in (a
            # request form, or a sheet not yet filled). Part of the total, so
            # the three add up to the bar.
            "open": len(inside) - passed - failed,
            "completed": sum(1 for r in inside if r.stage == STAGE_STORED),
        })
    return out


# --------------------------------------------------------- what is not there


def missed_periods(db: Session, *, team_id: Optional[str] = None,
                   limit: int = 25) -> list[dict]:
    """
    Active formats whose current period has no record at all.

    This is the reading of "pending inspections" that a count of rows cannot
    give: a daily check that nobody started leaves nothing behind to count. So
    it is derived from the format's own frequency instead - what should have
    been raised by now, against what was.
    """
    query = db.query(Format).filter(Format.status == fmts.ACTIVE)
    if team_id:
        query = query.filter(Format.team_id == team_id)

    out = []
    for fmt in query.order_by(Format.code).all():
        if (fmt.frequency or "").lower() == "per_event":
            continue  # raised when something happens: there is no period to have missed
        period = fmts.period_for(fmt.frequency)
        if fmts.existing_for_period(db, fmt, period["key"]):
            continue
        out.append({
            "format": {"id": fmt.id, "code": fmt.code, "title": fmt.title},
            "team": ({"id": fmt.team.id, "name": fmt.team.name}
                     if fmt.team else None),
            "frequency": fmt.frequency,
            "frequency_label": fmts.FREQUENCY_LABELS.get(fmt.frequency, fmt.frequency),
            "period": period["label"],
            "period_key": period["key"],
            "owner": ({"id": fmt.process_owner.id,
                       "name": fmt.process_owner.full_name or fmt.process_owner.username}
                      if fmt.process_owner else None),
        })
        if len(out) >= limit:
            break
    return out


def sweep_pending(db: Session) -> int:
    """
    Tell each Process Owner the check they owe has not been started.

    Raised once per format and period - the notification carries
    "<format id>:<period key>" as what it is about, so opening the dashboard
    five times in an afternoon does not send five emails. Like the overdue
    sweep in `capa_service`, this runs from the screens that would report it
    anyway rather than from a background job, so the alert does not depend on a
    thread being alive.
    """
    raised = 0
    for missed in missed_periods(db, limit=200):
        owner_id = (missed.get("owner") or {}).get("id")
        if not owner_id:
            continue
        about = f"{missed['format']['id']}:{missed['period_key']}"
        if notify.already_raised(db, notify.INSPECTION_PENDING, "format", about):
            continue

        owner = db.query(User).filter(User.id == owner_id).first()
        if not owner:
            continue

        notify.notify(
            db, notify.INSPECTION_PENDING, to=owner,
            subject=f"[{missed['format']['code']}] inspection pending for "
                    f"{missed['period']}",
            body=(f"{missed['format']['code']} - {missed['format']['title']}\n"
                  f"{missed['frequency_label']}, for {missed['period']}\n\n"
                  "No record has been raised for this period yet.\n\n"
                  + notify.link(f"/records/new?format={missed['format']['id']}")),
            related_type="format", related_id=about,
        )
        raised += 1
    return raised
