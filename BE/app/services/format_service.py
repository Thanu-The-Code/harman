"""
The format library (B1), and everything that follows from a format's frequency.

A format is a blank form held on the server, filled at a stated frequency. That
frequency is the most load-bearing field in the QMS domain: it decides which
period a new record covers, whether "today's check" has been done, and - at B8
- the shape of the date- and month-wise folders an approved record is filed
into. So the period arithmetic lives here, next to the field that drives it,
rather than being re-derived by each caller.

Revision control is the other half of this module. Once a format is active it
is never edited in place. The chart is explicit that a change needs a change
request approved by the QMS Coordinator before execution (B9), so the only way
to alter an active format is `new_revision`, which supersedes the old row and
leaves it readable forever. Records point at the revision they were filled
against, so history cannot be rewritten by a later change.
"""
from __future__ import annotations

import calendar
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..models import User
from ..utils import ist
from ..models_qms import (
    FORMAT_STATUSES,
    FREQUENCIES,
    ChangeRequest,
    Format,
    FormatField,
    QualityTeam,
    Record,
)
from .template_folder_service import ensure_folder_path


class FormatError(ValueError):
    """The request is not allowed by the rules of the format library."""


FREQUENCY_LABELS = {
    "shift": "Every shift",
    "daily": "Daily",
    "weekly": "Weekly",
    "monthly": "Monthly",
    "quarterly": "Quarterly",
    "half_yearly": "Half-yearly",
    "yearly": "Yearly",
    "per_event": "Per event",
}

DRAFT, ACTIVE, SUPERSEDED, WITHDRAWN = FORMAT_STATUSES


# ------------------------------------------------------------------ periods


def period_for(frequency: str, when: Optional[datetime] = None) -> dict:
    """
    Which period a record generated now belongs to.

    `key` is sortable and unique per period, and is what makes "has this
    format been filled for this period yet?" a single indexed lookup rather
    than a date-range scan.

    Periods follow the plant's calendar (IST), not UTC: a check made at 02:00
    on the 25th is the 25th's, where UTC would still say the 24th. `key` and
    `label` are in IST; `start` and `end` are naive UTC, like every stored
    timestamp.
    """
    local = ist.to_ist(when or datetime.utcnow()).replace(tzinfo=None)
    period = _calendar_period(frequency, local)
    period["start"], period["end"] = _utc(period["start"]), _utc(period["end"])
    return period


def _utc(local: datetime) -> datetime:
    """An IST wall-clock time as the naive UTC the database holds."""
    return local.replace(tzinfo=ist.IST).astimezone(timezone.utc).replace(tzinfo=None)


def _calendar_period(frequency: str, when: datetime) -> dict:
    """The period around `when`, a wall-clock time on the plant's calendar."""
    frequency = (frequency or "daily").lower()
    year = when.year

    if frequency in ("shift", "daily"):
        start = when.replace(hour=0, minute=0, second=0, microsecond=0)
        return {
            "key": f"{year:04d}-{when.month:02d}-{when.day:02d}",
            "label": when.strftime("%d %b %Y"),
            "start": start,
            "end": start + timedelta(days=1),
        }

    if frequency == "weekly":
        iso_year, iso_week, iso_day = when.isocalendar()
        start = (when - timedelta(days=iso_day - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        return {
            "key": f"{iso_year:04d}-W{iso_week:02d}",
            "label": f"Week {iso_week}, {iso_year}",
            "start": start,
            "end": start + timedelta(days=7),
        }

    if frequency == "monthly":
        start = when.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last = calendar.monthrange(year, when.month)[1]
        return {
            "key": f"{year:04d}-{when.month:02d}",
            "label": when.strftime("%B %Y"),
            "start": start,
            "end": start.replace(day=last) + timedelta(days=1),
        }

    if frequency == "quarterly":
        quarter = (when.month - 1) // 3 + 1
        first_month = 3 * (quarter - 1) + 1
        start = when.replace(month=first_month, day=1, hour=0, minute=0,
                             second=0, microsecond=0)
        end_month = first_month + 2
        last = calendar.monthrange(year, end_month)[1]
        return {
            "key": f"{year:04d}-Q{quarter}",
            "label": f"Q{quarter} {year}",
            "start": start,
            "end": start.replace(month=end_month, day=last) + timedelta(days=1),
        }

    if frequency == "half_yearly":
        half = 1 if when.month <= 6 else 2
        first_month = 1 if half == 1 else 7
        start = when.replace(month=first_month, day=1, hour=0, minute=0,
                             second=0, microsecond=0)
        end_month = first_month + 5
        last = calendar.monthrange(year, end_month)[1]
        return {
            "key": f"{year:04d}-H{half}",
            "label": f"H{half} {year}",
            "start": start,
            "end": start.replace(month=end_month, day=last) + timedelta(days=1),
        }

    if frequency == "yearly":
        start = when.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return {
            "key": f"{year:04d}",
            "label": str(year),
            "start": start,
            "end": start.replace(year=year + 1),
        }

    # per_event, and anything unrecognised. Every occurrence is its own period,
    # so two records raised the same day never collide.
    return {
        "key": when.strftime("%Y-%m-%dT%H:%M:%S"),
        "label": when.strftime("%d %b %Y %H:%M"),
        "start": when,
        "end": when,
    }


def storage_segments(fmt: Format, when: Optional[datetime] = None) -> list[str]:
    """
    The date- and month-wise folders an approved record is filed into (B8).

    The chart asks for "date wise/month wise folders ... based on record
    generation frequency", so a daily check gets a folder per day and a monthly
    one stops at the month. Filing every frequency the same way would bury a
    monthly summary among three hundred daily folders.

        shift, daily   2026 / 09-Sep / 01
        weekly         2026 / W36
        monthly        2026 / 09-Sep
        quarterly      2026 / Q3
        half-yearly    2026 / H2
        yearly         2026

    A week is deliberately NOT filed under a month. Week 36 of 2026 begins on
    31 August and runs into September, so any month it were put under would be
    wrong for most of its days - and a record filed under August that covers a
    week of September is exactly the kind of thing that cannot be found during
    an audit. The ISO year and week are used together for the same reason: the
    first week of a January belongs to whichever ISO year owns it, not to
    whichever year the Monday happens to fall in.
    """
    when = ist.to_ist(when or datetime.utcnow())  # the plant's calendar, as for periods
    frequency = (fmt.frequency or "daily").lower()
    year = f"{when.year:04d}"
    month = when.strftime("%m-%b")

    if frequency in ("shift", "daily"):
        return [year, month, f"{when.day:02d}"]
    if frequency == "weekly":
        iso_year, iso_week, _ = when.isocalendar()
        return [f"{iso_year:04d}", f"W{iso_week:02d}"]
    if frequency == "monthly":
        return [year, month]
    if frequency == "quarterly":
        return [year, f"Q{(when.month - 1) // 3 + 1}"]
    if frequency == "half_yearly":
        return [year, f"H{1 if when.month <= 6 else 2}"]
    if frequency == "yearly":
        return [year]
    return [year, month]


def storage_root(fmt: Format) -> list[str]:
    """
    The fixed part of the path, above the date folders.

    Uses the format's own `storage_path` when the site has given us one - the
    chart's "given path" - and otherwise builds the obvious default.

    The given path is a folder of the Resources library, which several templates
    can share ("Teams / Process Quality / Inspection Logs"), so each template
    files its records in a folder of its own code under it - records of two
    check sheets never mix in one day's folder.
    """
    if fmt.storage_path:
        parts = [p.strip() for p in re.split(r"[\\/]+", fmt.storage_path) if p.strip()]
        if parts:
            return parts if parts[-1].upper() == (fmt.code or "").upper() else parts + [fmt.code]
    team = fmt.team.name if fmt.team else "Unassigned"
    return ["Records", team, fmt.code]


def full_storage_path(fmt: Format, when: Optional[datetime] = None) -> list[str]:
    return storage_root(fmt) + storage_segments(fmt, when)


# ------------------------------------------------------------------- teams


def ensure_teams(db: Session) -> int:
    """
    The three dedicated quality teams the client is starting with.

    Idempotent, so it is safe on every boot. Names are the obvious ones for a
    manufacturing quality function; an administrator renames them on the
    Formats screen and this will not fight back, because it only ever creates a
    team whose code is missing.
    """
    wanted = [
        ("PQ", "Process Quality",
         "Owns in-process inspection and process control records."),
        ("SQ", "Supplier Quality",
         "Owns incoming inspection and supplier performance records."),
        ("CQ", "Customer Quality",
         "Owns customer complaint, containment and final audit records."),
    ]
    created = 0
    for code, name, description in wanted:
        if db.query(QualityTeam).filter(QualityTeam.code == code).first():
            continue
        db.add(QualityTeam(code=code, name=name, description=description))
        created += 1
    if created:
        db.commit()
        logger.info(f"Created {created} quality team(s)")
    return created


# ----------------------------------------------------------------- formats


CODE_PREFIX = "QF"


def next_code(db: Session, team_id: Optional[str] = None) -> str:
    """The next free code of a team: QF-<team>-NNN, after the highest ever used.

    Every format counts, whatever its status: a withdrawn template's code is not
    handed out again, because its records still carry it.
    """
    team = db.query(QualityTeam).filter(QualityTeam.id == team_id).first() if team_id else None
    prefix = f"{CODE_PREFIX}-{team.code.upper()}-" if team else f"{CODE_PREFIX}-"
    used = [
        int(code[len(prefix):])
        for (code,) in db.query(Format.code).filter(Format.code.like(f"{prefix}%")).all()
        if code[len(prefix):].isdigit()
    ]
    return f"{prefix}{(max(used) if used else 0) + 1:03d}"


def create_format(db: Session, actor: Optional[User], data: dict) -> Format:
    """
    Add a blank format to the library (B1).

    Created as a draft. A draft cannot have records raised against it, which is
    what lets an administrator set the responsibilities and the specification
    limits over several sittings without anyone filling a half-built form.
    """
    # no code given: the team's next one (QF-PQ-004), so two templates never compete for a number
    code = (data.get("code") or "").strip().upper() or next_code(db, data.get("team_id"))

    title = (data.get("title") or "").strip()
    if not title:
        raise FormatError("A format needs a title.")

    frequency = (data.get("frequency") or "daily").strip().lower()
    if frequency not in FREQUENCIES:
        raise FormatError(
            f"'{frequency}' is not a frequency. Choose one of: "
            + ", ".join(FREQUENCIES) + "."
        )

    # A code identifies a format across its revisions, so it may repeat down a
    # revision chain but never across two live formats.
    clash = (
        db.query(Format)
        .filter(Format.code == code, Format.status.in_([DRAFT, ACTIVE]))
        .first()
    )
    if clash:
        raise FormatError(
            f"Format {code} already exists ({clash.title}). Raise a change "
            "request to revise it, or choose another code."
        )

    try:
        storage_path = ensure_folder_path(
            db, data.get("storage_path"), created_by=actor.id if actor else None
        )
    except ValueError as exc:
        raise FormatError(str(exc)) from exc

    fmt = Format(
        code=code,
        title=title,
        description=(data.get("description") or "").strip() or None,
        team_id=data.get("team_id") or None,
        frequency=frequency,
        revision=(data.get("revision") or "00").strip() or "00",
        status=DRAFT,
        work_instruction_ref=(data.get("work_instruction_ref") or "").strip() or None,
        work_instruction=(data.get("work_instruction") or "").strip() or None,
        storage_path=storage_path,
        cft_target_days=_positive_int(data.get("cft_target_days"), 3),
        created_by=actor.id if actor else None,
    )
    _apply_layout(db, fmt, data)
    _apply_responsibilities(db, fmt, data)
    _apply_route(fmt, data)
    db.add(fmt)
    db.flush()
    _apply_fields(db, fmt, data.get("fields") or [])
    db.commit()
    db.refresh(fmt)
    logger.info(f"Format {fmt.code} rev {fmt.revision} created as a draft")
    return fmt


def update_format(db: Session, fmt: Format, actor: Optional[User], data: dict) -> Format:
    """
    Change a format that is still a draft.

    An active format is deliberately immutable here. The chart routes every
    change through a change request approved by the QMS Coordinator before
    execution, and a service that quietly allowed a field limit to be edited
    would make that control a formality.
    """
    if fmt.status != DRAFT:
        raise FormatError(
            f"Format {fmt.code} is {fmt.status} and cannot be edited directly. "
            "Raise a change request to revise it."
        )

    if "code" in data and (data.get("code") or "").strip():
        fmt.code = data["code"].strip().upper()
    if "title" in data and (data.get("title") or "").strip():
        fmt.title = data["title"].strip()
    if "description" in data:
        fmt.description = (data.get("description") or "").strip() or None
    if "team_id" in data:
        fmt.team_id = data.get("team_id") or None
    if "frequency" in data:
        frequency = (data.get("frequency") or "daily").strip().lower()
        if frequency not in FREQUENCIES:
            raise FormatError(f"'{frequency}' is not a frequency.")
        fmt.frequency = frequency
    if "work_instruction_ref" in data:
        fmt.work_instruction_ref = (data.get("work_instruction_ref") or "").strip() or None
    if "work_instruction" in data:
        fmt.work_instruction = (data.get("work_instruction") or "").strip() or None
    if "storage_path" in data:
        try:
            fmt.storage_path = ensure_folder_path(
                db,
                data.get("storage_path"),
                created_by=actor.id if actor else None,
            )
        except ValueError as exc:
            raise FormatError(str(exc)) from exc
    if "cft_target_days" in data:
        fmt.cft_target_days = _positive_int(data.get("cft_target_days"), 3)

    _apply_layout(db, fmt, data)
    _apply_responsibilities(db, fmt, data)
    _apply_route(fmt, data)
    if "fields" in data:
        _apply_fields(db, fmt, data.get("fields") or [], replace=True)

    db.commit()
    db.refresh(fmt)
    return fmt


def activate(db: Session, fmt: Format, actor: Optional[User]) -> Format:
    """
    Release a draft into use, after checking it can actually run.

    The checks are the chart's own requirements. A format with no Process Owner
    has nobody to fill it; one with no CFT cannot have a joint review; one with
    no specification has no way to decide ok from N-ok. Catching that here
    means it is found by the person building the format, not by the operator
    holding a clipboard at six in the morning.
    """
    if fmt.status == ACTIVE:
        return fmt
    if fmt.status in (SUPERSEDED, WITHDRAWN):
        raise FormatError(f"Format {fmt.code} is {fmt.status} and cannot be activated.")
    if fmt.status != DRAFT:
        raise FormatError(
            f"Format {fmt.code} is {fmt.status}; only a draft can be released directly."
        )

    problems = readiness(fmt)
    if problems:
        raise FormatError(
            f"Format {fmt.code} is not ready to be released:\n- "
            + "\n- ".join(problems)
        )

    fmt.status = ACTIVE
    fmt.effective_date = fmt.effective_date or datetime.utcnow()
    db.commit()
    db.refresh(fmt)
    logger.info(f"Format {fmt.code} rev {fmt.revision} activated")
    return fmt


def readiness(fmt: Format) -> list[str]:
    """What still has to be true before this format may be used."""
    problems = []

    # A responsibility may be left blank - the approvers are then chosen on the
    # record at submission. But somebody who *is* named has to be able to act:
    # records raised against an account that has left, or cannot sign a signed
    # step, stop moving with nothing on screen to say why.
    if fmt.process_owner_id:
        if not fmt.process_owner.is_active:
            problems.append(
                f"{_who(fmt.process_owner)} is the Process Owner but their account "
                "is no longer active. Appoint somebody else."
            )
        elif not (fmt.process_owner.can_sign or fmt.process_owner.is_admin):
            problems.append(
                f"{_who(fmt.process_owner)} is the Process Owner but is not "
                "permitted to apply a signature, and the approval steps are signed."
            )
    if fmt.overall_process_owner_id:
        if not fmt.overall_process_owner.is_active:
            problems.append(
                f"{_who(fmt.overall_process_owner)} is the Overall Process Owner "
                "but their account is no longer active. Appoint somebody else."
            )
        elif not (fmt.overall_process_owner.can_sign or fmt.overall_process_owner.is_admin):
            problems.append(
                f"{_who(fmt.overall_process_owner)} is the Overall Process Owner "
                "but is not permitted to apply a signature."
            )
    if fmt.cft_members:
        if not any(m.is_active for m in fmt.cft_members):
            problems.append(
                "Every CFT member's account is inactive, so the joint review has "
                "nobody to open with."
            )
        else:
            gone = [_who(m) for m in fmt.cft_members if not m.is_active]
            if gone:
                problems.append(
                    "These CFT members are no longer active and would hold up every "
                    "joint review: " + ", ".join(gone) + "."
                )
    from . import approval_people

    problems.extend(approval_people.format_problems(fmt))
    if fmt.qms_coordinator_id and not fmt.qms_coordinator.is_active:
        problems.append(
            f"{_who(fmt.qms_coordinator)} is the QMS Coordinator but their "
            "account is no longer active. Appoint somebody else."
        )

    if not fmt.fields:
        problems.append(
            "The format has no fields, so there is nothing to judge ok or N-ok "
            "against."
        )
    # Every fault in the route produces a record that stops moving with nothing
    # on screen to say why. The moment to catch that is here, when the template
    # is released - not when a shift supervisor is waiting on an approval that
    # was never addressed to anybody.
    from . import approval_route as routes

    problems.extend(
        routes.problems(routes.parse(fmt.approval_route, fmt.cft_target_days), fmt,
                        allow_unassigned=True))

    from . import form_layout as layouts

    problems.extend(layouts.problems(layouts.parse(fmt.layout)))

    return problems


def withdraw(db: Session, fmt: Format, actor: Optional[User], reason: str = "") -> Format:
    """Take a format out of use without deleting anything filled against it."""
    if fmt.status == SUPERSEDED:
        raise FormatError("A superseded format is already out of use.")
    fmt.status = WITHDRAWN
    db.commit()
    db.refresh(fmt)
    return fmt


def new_revision(db: Session, fmt: Format, actor: Optional[User],
                 data: Optional[dict] = None,
                 change_request: Optional[ChangeRequest] = None) -> Format:
    """
    Supersede a format with its next revision (B9's "execution").

    The old row is kept exactly as it was and marked superseded. Records that
    were filled against it still point at it and still report its revision
    number, which is the whole reason revisions exist rather than edits.
    """
    data = data or {}
    try:
        storage_path = ensure_folder_path(
            db,
            data.get("storage_path", fmt.storage_path),
            created_by=actor.id if actor else None,
        )
    except ValueError as exc:
        raise FormatError(str(exc)) from exc

    successor = Format(
        code=fmt.code,
        title=(data.get("title") or fmt.title),
        description=data.get("description", fmt.description),
        team_id=data.get("team_id", fmt.team_id),
        frequency=(data.get("frequency") or fmt.frequency),
        revision=_next_revision(fmt.revision),
        revision_of=fmt.id,
        status=DRAFT,
        work_instruction_ref=data.get("work_instruction_ref", fmt.work_instruction_ref),
        work_instruction=data.get("work_instruction", fmt.work_instruction),
        storage_path=storage_path,
        cft_target_days=_positive_int(data.get("cft_target_days"), fmt.cft_target_days),
        process_owner_id=data.get("process_owner_id", fmt.process_owner_id),
        overall_process_owner_id=data.get(
            "overall_process_owner_id", fmt.overall_process_owner_id),
        qms_coordinator_id=data.get("qms_coordinator_id", fmt.qms_coordinator_id),
        # The sheet's design and the route it is approved by come across
        # unchanged unless the request replaces them. A revision is the old
        # template plus the requested change - anything the request is silent
        # about has to survive it, or executing a change request quietly hands
        # the plant a different form to the one they asked to amend.
        layout=data.get("layout_json", fmt.layout),
        approval_route=data.get("approval_route_json", fmt.approval_route),
        blank_file_path=fmt.blank_file_path,
        blank_mime_type=fmt.blank_mime_type,
        blank_file_size=fmt.blank_file_size,
        created_by=actor.id if actor else None,
    )
    successor.cft_members = list(fmt.cft_members)
    db.add(successor)
    db.flush()

    # A request may redesign the sheet or change who approves it. Both go
    # through the same cleaners as an ordinary edit, so a revision cannot end
    # up holding something an edit would have refused.
    _apply_layout(db, successor, data)
    _apply_route(successor, data)

    # Carry the specification forward unless the change request replaces it.
    if data.get("fields"):
        _apply_fields(db, successor, data["fields"])
    else:
        for field in fmt.fields:
            db.add(FormatField(
                format_id=successor.id,
                order_index=field.order_index,
                label=field.label,
                field_type=field.field_type,
                unit=field.unit,
                spec_min=field.spec_min,
                spec_max=field.spec_max,
                spec_text=field.spec_text,
                options=field.options,
                required=field.required,
                help_text=field.help_text,
                layout_key=field.layout_key,
            ))

    fmt.status = SUPERSEDED
    if change_request is not None:
        change_request.resulting_format_id = successor.id
        change_request.status = "implemented"

    db.commit()
    db.refresh(successor)
    logger.info(
        f"Format {fmt.code} revised: {fmt.revision} superseded by {successor.revision}")
    return successor


# ------------------------------------------------------------------ queries


def get(db: Session, format_id: str) -> Optional[Format]:
    return db.query(Format).filter(Format.id == format_id).first()


def list_formats(db: Session, *, team_id: Optional[str] = None,
                 status: Optional[str] = None,
                 owner: Optional[User] = None,
                 query: str = "") -> list[Format]:
    q = db.query(Format)
    if team_id:
        q = q.filter(Format.team_id == team_id)
    if status:
        q = q.filter(Format.status == status)
    if owner is not None:
        q = q.filter(Format.process_owner_id == owner.id)
    if query:
        like = f"%{query.strip()}%"
        q = q.filter((Format.code.ilike(like)) | (Format.title.ilike(like)))
    return q.order_by(Format.code, Format.revision.desc()).all()


def revision_groups(db: Session) -> list[list[Format]]:
    """Return each template's revisions together, ordered from oldest to newest."""
    formats = list_formats(db)
    by_id = {fmt.id: fmt for fmt in formats}
    grouped: dict[str, list[Format]] = {}

    for fmt in formats:
        root = fmt
        visited: set[str] = set()
        while root.revision_of in by_id and root.id not in visited:
            visited.add(root.id)
            root = by_id[root.revision_of]
        grouped.setdefault(root.id, []).append(fmt)

    def revision_order(fmt: Format) -> tuple[str, int]:
        match = re.match(r"^(\D*)(\d+)$", (fmt.revision or "").strip())
        if match:
            return match.group(1), int(match.group(2))
        return (fmt.revision or "", -1)

    return [
        sorted(versions, key=revision_order)
        for _, versions in sorted(
            grouped.items(),
            key=lambda item: (item[1][0].code, item[1][0].title),
        )
    ]


def callable_by(db: Session, user: User) -> list[Format]:
    """
    The formats this person may call and fill (B2).

    The same people `record_service.call_format` lets through: the format's
    Process Owner, anybody of the format's team when it names no Process Owner,
    and anybody holding `records.fill` (administrators included). Listing a
    format the person would then be refused on is worse than not listing it.
    """
    formats = db.query(Format).filter(Format.status == ACTIVE).order_by(Format.code).all()
    if user.has_permission("records.fill"):
        return formats
    return [f for f in formats if f.process_owner_id == user.id or open_to(db, f, user)]


def open_to(db: Session, fmt: Format, user: User) -> bool:
    """A format naming no Process Owner is filled by its own team - by anybody while the
    team has nobody in it yet (as the people pickers offer them)."""
    if fmt.process_owner_id:
        return False
    if not fmt.team_id or user.quality_team_id == fmt.team_id:
        return True
    return db.query(User.id).filter(User.quality_team_id == fmt.team_id).first() is None


def record_count(db: Session, fmt: Format) -> int:
    return db.query(Record).filter(Record.format_id == fmt.id).count()


def existing_for_period(db: Session, fmt: Format, period_key: str) -> Optional[Record]:
    """
    The record already raised for this format and period, if there is one.

    Used to warn - not to forbid. A shift-based check legitimately produces two
    records for one calendar day, and a re-do after a spoiled form is normal.
    Blocking it would send people back to paper.
    """
    return (
        db.query(Record)
        .filter(Record.format_id == fmt.id, Record.period_key == period_key)
        .order_by(func.coalesce(Record.updated_at, Record.created_at).desc())
        .first()
    )


# ------------------------------------------------------------------ helpers


def _apply_layout(db: Session, fmt: Format, data: dict) -> None:
    """
    Store the form's shape, and derive what it records from it.

    A layout is the single source of truth for a template that has one: the
    fields are flattened out of it here rather than taken from a separate list,
    because two lists of the same thing eventually disagree and the one that
    loses is the one the readings are judged against.

    A missing key leaves the layout alone - that is an edit that did not
    mention it. An explicitly empty list clears it, which is how somebody goes
    back to a plain list of fields.
    """
    from . import form_layout as layouts

    if "layout" not in data:
        return

    blocks = layouts.parse(layouts.dump(data.get("layout") or []))
    fmt.layout = layouts.dump(blocks)

    if not blocks:
        return

    # The fields the layout records, replacing whatever was there. Done in the
    # same transaction as the layout so the two can never drift apart.
    data["fields"] = layouts.to_fields(blocks)


def _apply_route(fmt, data: dict) -> None:
    """
    Store the approval route, if one was supplied.

    A missing key leaves the route alone - that is an edit that did not mention
    it. An explicitly empty list clears it, which is how somebody says "go back
    to the process document's four steps".
    """
    from . import approval_route as routes

    if "approval_route" not in data:
        return
    fmt.approval_route = routes.dump(data.get("approval_route") or [])


def _apply_responsibilities(db: Session, fmt: Format, data: dict) -> None:
    for key in ("process_owner_id", "overall_process_owner_id", "qms_coordinator_id"):
        if key in data:
            setattr(fmt, key, data.get(key) or None)

    if "cft_member_ids" in data:
        ids = [i for i in (data.get("cft_member_ids") or []) if i]
        people = (
            db.query(User)
            .filter(User.id.in_(ids), User.is_active.is_(True))
            .all()
            if ids else []
        )
        by_id = {p.id: p for p in people}
        fmt.cft_members = [by_id[i] for i in ids if i in by_id]


def _apply_fields(db: Session, fmt: Format, rows: list, replace: bool = False) -> None:
    if replace:
        for field in list(fmt.fields):
            db.delete(field)
        db.flush()
        fmt.fields = []

    for index, raw in enumerate(rows or []):
        label = (raw.get("label") or "").strip()
        if not label:
            continue
        field_type = (raw.get("field_type") or "text").strip().lower()
        if field_type not in ("text", "number", "select", "date", "boolean"):
            field_type = "text"

        options = raw.get("options")
        if isinstance(options, (list, tuple)):
            options = json.dumps([str(o) for o in options])
        elif options:
            options = json.dumps([o.strip() for o in str(options).split(",") if o.strip()])
        else:
            options = None

        db.add(FormatField(
            format_id=fmt.id,
            order_index=index,
            label=label[:200],
            field_type=field_type,
            unit=(raw.get("unit") or "").strip() or None,
            spec_min=_float_or_none(raw.get("spec_min")),
            spec_max=_float_or_none(raw.get("spec_max")),
            spec_text=(raw.get("spec_text") or "").strip() or None,
            options=options,
            required=bool(raw.get("required", True)),
            help_text=(raw.get("help_text") or "").strip() or None,
            layout_key=(raw.get("layout_key") or "").strip() or None,
        ))
    db.flush()


def _next_revision(current: Optional[str]) -> str:
    """00 to 01, R1 to R2, and anything unparseable to itself plus .1."""
    value = (current or "00").strip()
    match = re.match(r"^(\D*)(\d+)$", value)
    if match:
        prefix, digits = match.groups()
        return f"{prefix}{int(digits) + 1:0{len(digits)}d}"
    return f"{value}.1"


def _who(user) -> str:
    if not user:
        return "Nobody"
    return user.full_name or user.username


def _positive_int(value, fallback: int) -> int:
    try:
        number = int(value)
        return number if number > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def _float_or_none(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
