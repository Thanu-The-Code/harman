"""Activity Log API: return recorded events and summary data.

Reads the `audit_logs` table that application routes write to. Events are
returned only when they have actually been recorded.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, User
from ..services.auth_service import require_permission_flexible

router = APIRouter()

MODULES_BY_RESOURCE_TYPE = {
    "document": "My Documents",
    "record": "My Documents",
    "workflow": "My Documents",
    "format": "Template Builder",
    "change_request": "Change Request",
    "record_change_request": "Change Request",
    "user": "People & Teams",
    "session": "People & Teams",
    "corrective_action": "Corrective Actions",
    "repository": "Doc Repository",
    "settings": "Settings",
    "backup": "Backup & Recovery",
    "security": "Security",
}
MODULE_CHOICES = sorted({*MODULES_BY_RESOURCE_TYPE.values(), "Other", "System"})


def _module_expression():
    return case(
        MODULES_BY_RESOURCE_TYPE,
        value=AuditLog.resource_type,
        else_=case(
            (AuditLog.resource_type.is_(None), "System"),
            else_="Other",
        ),
    )


def _module_for_event(resource_type: Optional[str]) -> str:
    if resource_type is None:
        return "System"
    return MODULES_BY_RESOURCE_TYPE.get(resource_type, "Other")


# How each recorded action reads to a person, and how it should be coloured.
# Anything not listed falls back to the raw action name rather than being
# dressed up as something it is not.
ACTIONS = {
    "document.upload":          ("Document uploaded", "capture", ""),
    "document.download":        ("Document downloaded", "download", ""),
    "document.compose":         ("Document written in the Studio", "compose", ""),
    "document.revise":          ("New version saved", "compose", ""),
    "document.publish":         ("Document published", "send", "accent"),
    "document.version.restore": ("Earlier version restored", "history", "warn"),
    "workflow.approve":         ("Approved", "check", "accent"),
    "workflow.reject":          ("Rejected", "x", "danger"),
    "workflow.changes":         ("Sent back for changes", "refresh", "warn"),
    "user_created":             ("Person added", "users", ""),
    "user_updated":             ("Person updated", "users", ""),
    "user_deleted":             ("Person removed", "users", "danger"),
    # These are the exact strings the auth service writes.
    "login_success":            ("Signed in", "user", ""),
    "login_failed":             ("Failed sign-in", "alert", "danger"),
    "logout":                   ("Signed out", "logout", ""),
    "initial_setup":            ("System set up", "settings", "accent"),
    "password_changed":         ("Password changed", "key", ""),
    # the quality process
    "record.called":            ("Record started", "capture", ""),
    "record.submitted":         ("Record submitted for approval", "send", "accent"),
    "record.nok_cleared":       ("N-OK flag cleared", "check", "warn"),
    "record.stored":            ("Record filed", "check", "accent"),
    "workflow.objected":        ("CFT objection", "x", "danger"),
    "workflow.returned":        ("Returned for correction", "refresh", "warn"),
    "workflow.reverify":        ("Sent back for re-verification", "refresh", "warn"),
    "format.imported_from_document": ("Template imported from a document", "capture", ""),
    "format.approval.submitted": ("Template sent for approval", "send", ""),
    "format.approval.approve":  ("Template approved", "check", "accent"),
    "format.approval.reject":   ("Template returned for changes", "refresh", "warn"),
    "change_request.created":   ("Change request raised", "send", ""),
    "change_request.approve":   ("Change request approved", "check", "accent"),
    "change_request.reject":    ("Change request not approved", "x", "danger"),
    "change_request.executed":  ("Change request carried out", "check", "accent"),
    "record_change_request.created":     ("Record change requested", "send", ""),
    "record_change_request.approved":    ("Record change approved", "check", "accent"),
    "record_change_request.not_approved": ("Record change not approved", "x", "danger"),
    "record_change_request.implemented": ("Record change implemented", "check", "accent"),
    "record_change_request.assigned":    ("Record change assigned", "users", ""),
    "record_change_request.edited":      ("Record change edited", "compose", ""),
    "record.returned":          ("Returned for correction", "refresh", "warn"),
    "record.reverify":          ("Sent back for re-verification", "refresh", "warn"),
    "format.published_without_approval": ("Template released without approval", "send", "warn"),
    "format.released":          ("Template released", "check", "accent"),
    "document.view":            ("Document opened", "info", ""),
    "document.quarantine":      ("Document quarantined", "alert", "danger"),
    "action.raised":            ("Corrective action raised", "alert", "warn"),
    "action.updated":           ("Corrective action updated", "compose", ""),
    "action.closed":            ("Corrective action closed", "check", "accent"),
    "action.reopened":          ("Corrective action reopened", "refresh", "warn"),
    "admin_user_updated":       ("Person updated", "users", ""),
    "default_admin_created":    ("Administrator account created", "settings", "accent"),
    "signature.designation":    ("Signature title changed", "compose", ""),
    "backup.create":            ("Backup made", "history", ""),
    "backup.create_manual":     ("Backup made", "history", ""),
    "backup.create_manual_failed": ("Backup failed", "alert", "danger"),
    "backup.restore":           ("Backup restored", "history", "warn"),
    "backup.delete":            ("Backup deleted", "history", "warn"),
    "backup.configure":         ("Backup schedule changed", "settings", ""),
    "security.scan":            ("Security scan", "settings", ""),
}

# Sign-ins are each person's own business: others see them only as administrators.
AUTH_ACTIONS = ("login_success", "login_failed", "logout", "password_changed")


def _subjects(db: Session, events) -> dict[str, str]:
    """What each entry is about, by the name people use: REC-..., DCR-..., QF-PQ-002."""
    from ..models import ApprovalWorkflow
    from ..models_qms import ChangeRequest, Format, Record, RecordChangeRequest

    wanted: dict[str, set] = {}
    for e in events:
        if e.resource_type and e.resource_id:
            wanted.setdefault(e.resource_type, set()).add(e.resource_id)
    out: dict[str, str] = {}
    for model, kind, name in ((Record, "record", lambda r: r.number),
                              (ChangeRequest, "change_request", lambda r: r.number),
                              (RecordChangeRequest, "record_change_request", lambda r: r.number),
                              (Format, "format", lambda f: f"{f.code} rev {f.revision} · {f.title}")):
        ids = wanted.get(kind)
        if ids:
            out.update({row.id: name(row) for row in db.query(model).filter(model.id.in_(ids)).all()})
    if wanted.get("workflow"):
        records = db.query(Record).filter(Record.workflow_id.in_(wanted["workflow"])).all()
        out.update({r.workflow_id: r.number for r in records})
        rest = wanted["workflow"] - {r.workflow_id for r in records}
        if rest:
            out.update({w.id: w.name for w in db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id.in_(rest)).all()})
    return out


def _describe(action: str) -> tuple[str, str, str]:
    return ACTIONS.get(action, (action.replace("_", " ").replace(".", " · "), "info", ""))


@router.get("/", include_in_schema=False)
@router.get("")
def list_events(
    q: Optional[str] = None,
    action: Optional[str] = None,
    module: Optional[str] = Query(default=None, max_length=100),
    work_only: bool = Query(default=False, description="Leave out sign-ins (the dashboard's recent activity)."),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    days: int = Query(default=30, ge=1, le=365),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    limit: Optional[int] = Query(
        default=None,
        ge=1,
        le=1000,
        deprecated=True,
        description="Legacy result limit; use page and page_size instead.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """List filtered audit events, newest first, with page metadata."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")

    query = (
        db.query(AuditLog)
        .outerjoin(User, AuditLog.user_id == User.id)
    )

    if date_from or date_to:
        if date_from:
            query = query.filter(
                AuditLog.created_at >= datetime.combine(date_from, time.min)
            )
        if date_to:
            query = query.filter(
                AuditLog.created_at < datetime.combine(date_to + timedelta(days=1), time.min)
            )
    else:
        since = datetime.utcnow() - timedelta(days=days)
        query = query.filter(AuditLog.created_at >= since)

    if action:
        query = query.filter(AuditLog.action.in_([a.strip() for a in action.split(",")]))
    if not current_user.is_admin:
        query = query.filter(or_(AuditLog.action.notin_(AUTH_ACTIONS), AuditLog.user_id == current_user.id))
    if work_only:
        query = query.filter(AuditLog.action.notin_(AUTH_ACTIONS))

    if module:
        query = query.filter(_module_expression() == module)

    if q:
        needle = f"%{q.strip().lower()}%"
        query = query.filter(or_(
            func.lower(AuditLog.action).like(needle),
            func.lower(AuditLog.details).like(needle),
            func.lower(AuditLog.resource_type).like(needle),
            func.lower(User.full_name).like(needle),
            func.lower(User.username).like(needle),
        ))

    total = query.order_by(None).count()
    effective_page_size = limit if limit is not None else page_size
    events = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * effective_page_size)
        .limit(effective_page_size)
        .all()
    )

    # Resolve document ids to titles in one query rather than showing a UUID.
    # An audit row that says "6e22f5b9-21e0-…" tells the reader nothing.
    from ..models import Document

    doc_ids = set()
    parsed = []
    for e in events:
        try:
            detail = json.loads(e.details) if e.details else {}
        except (TypeError, ValueError):
            detail = {}
        parsed.append(detail)
        for key in ("document_id",):
            if detail.get(key):
                doc_ids.add(detail[key])
        if e.resource_type == "document" and e.resource_id:
            doc_ids.add(e.resource_id)

    titles = {}
    if doc_ids:
        for d in db.query(Document).filter(Document.id.in_(doc_ids)).all():
            titles[d.id] = d.title or d.original_filename or d.filename
    titles.update(_subjects(db, events))

    out = []
    for e, detail in zip(events, parsed):
        label, icon, tone = _describe(e.action)

        # An entry outlives the account that made it. Saying "System" for a
        # removed person would misattribute what they did.
        if e.user:
            who = e.user.full_name or e.user.username
        elif e.user_id:
            who = "Removed account"
        else:
            who = "System"

        subject = (
            detail.get("title")
            or titles.get(detail.get("document_id") or "")
            or titles.get(e.resource_id or "")
            or detail.get("filename")
            or detail.get("username")
            or ""
        )

        out.append({
            "id": e.id,
            "action": e.action,
            "label": label,
            "icon": icon,
            "tone": tone,
            "module": _module_for_event(e.resource_type),
            "user": who,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "summary": subject,
            "ip_address": e.ip_address if current_user.is_admin else None,
            "at": e.created_at,
        })

    return {
        "events": out,
        "count": len(out),
        "days": days,
        "date_from": date_from,
        "date_to": date_to,
        "pagination": {
            "page": page,
            "page_size": effective_page_size,
            "total": total,
            "total_pages": (total + effective_page_size - 1) // effective_page_size,
        },
    }


@router.get("/modules")
def list_modules(
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """Return the module values available for Activity Log filtering."""
    return {"modules": MODULE_CHOICES}


@router.get("/summary")
def summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """Counts per action and the number of distinct people, over the window."""
    since = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.query(AuditLog.action, func.count(AuditLog.id))
        .filter(AuditLog.created_at >= since)
        .group_by(AuditLog.action)
        .order_by(func.count(AuditLog.id).desc())
        .all()
    )

    # Distinct accounts that acted. Counted from the log rather than from the
    # user table, so somebody who has since been removed still counts: they did
    # act, and the record of it stands.
    accounts = (
        db.query(func.count(func.distinct(AuditLog.user_id)))
        .filter(AuditLog.created_at >= since, AuditLog.user_id.isnot(None))
        .scalar() or 0
    )

    return {
        "days": days,
        "total": sum(n for _, n in rows),
        "people": accounts,
        "actions": [
            {"action": a, "label": _describe(a)[0], "count": n} for a, n in rows
        ],
    }
