"""The signed-in user's approval queue for QMS records."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import User
from ..models_qms import Format, QualityTeam, Record, RecordEvent, STAGE_FILLING
from ..services import workflow_service as workflows
from ..services.auth_service import get_current_user_flexible

router = APIRouter()

Tab = Literal["overdue", "pending", "returned"]


def _is_overdue(due_at: Optional[datetime], now: datetime) -> bool:
    if due_at is None:
        return False
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    return due_at < now


def _returned_records_query(db: Session, user: User):
    query = (
        db.query(Record)
        .join(Format, Record.format_id == Format.id)
        .outerjoin(QualityTeam, Record.team_id == QualityTeam.id)
        .filter(
            Record.stage == STAGE_FILLING,
            Record.workflow_id.is_(None),
            Record.events.any(RecordEvent.kind == "returned"),
        )
    )
    if not user.is_admin:
        query = query.filter(
            or_(
                Record.filled_by == user.id,
                and_(
                    Record.filled_by.is_(None),
                    Format.process_owner_id == user.id,
                ),
            )
        )
    return query


def _approval_tasks(db: Session, user: User, tab: Tab):
    now = datetime.now(timezone.utc)
    candidates = workflows.tasks_for(db, user)

    if tab == "overdue":
        return [
            (workflow, step)
            for workflow, step in candidates
            if _is_overdue(step.due_date, now)
        ]
    if tab == "pending":
        # everything waiting on this person, overdue included: an overdue approval is the
        # one that most needs to be on the list (Overdue is the subset past its due date)
        return list(candidates)
    return []


def _approval_query(db: Session, tasks: list[tuple], search: Optional[str],
                    department: Optional[str]):
    step_by_workflow = {
        workflow.id: step for workflow, step in tasks
    }
    workflow_ids = list(step_by_workflow)
    if not workflow_ids:
        return None, step_by_workflow

    query = (
        db.query(Record)
        .join(Format, Record.format_id == Format.id)
        .outerjoin(QualityTeam, Record.team_id == QualityTeam.id)
        .options(
            joinedload(Record.filler),
            joinedload(Record.format),
            joinedload(Record.team),
        )
        .filter(Record.workflow_id.in_(workflow_ids))
    )
    if search and search.strip():
        query = query.filter(
            or_(
                Format.title.ilike(f"%{search.strip()}%"),
                Record.number.ilike(f"%{search.strip()}%"),
            )
        )
    if department:
        query = query.filter(QualityTeam.name == department)
    return query, step_by_workflow


@router.get("")
def list_my_approvals(
    tab: Tab = Query("pending"),
    search: Optional[str] = Query(None, description="Format or record title"),
    department: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_flexible),
):
    if tab == "returned":
        query = _returned_records_query(db, user)
        if search and search.strip():
            query = query.filter(
                or_(
                    Format.title.ilike(f"%{search.strip()}%"),
                    Record.number.ilike(f"%{search.strip()}%"),
                )
            )
        if department:
            query = query.filter(QualityTeam.name == department)
        total = query.count()
        rows = (
            query.options(
                joinedload(Record.filler),
                joinedload(Record.format),
                joinedload(Record.team),
            )
            .order_by(Record.updated_at.desc(), Record.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        items = [
            {
                "record_id": record.id,
                "step_id": None,
                "document_name": record.format.title,
                "department": record.team.name if record.team else None,
                "assigned_by": (
                    record.filler.full_name or record.filler.username
                    if record.filler else None
                ),
                "submitted_on": record.submitted_at,
                "due_at": None,
                "stage": record.stage,
            }
            for record in rows
        ]
    else:
        tasks = _approval_tasks(db, user, tab)
        query, step_by_workflow = _approval_query(db, tasks, search, department)
        total = query.count() if query is not None else 0
        rows = (
            query.order_by(
                Record.workflow_id,
                Record.id.desc(),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
            if query is not None else []
        )
        items = []
        for record in rows:
            step = step_by_workflow[record.workflow_id]
            items.append({
                "record_id": record.id,
                "step_id": step.id,
                "document_name": record.format.title,
                "department": record.team.name if record.team else None,
                "assigned_by": (
                    record.filler.full_name or record.filler.username
                    if record.filler else None
                ),
                "submitted_on": record.submitted_at,
                "due_at": step.due_date,
                "stage": record.stage,
            })

    counts = {}
    for name in ("overdue", "pending"):
        tasks = _approval_tasks(db, user, name)
        query, _ = _approval_query(db, tasks, None, None)
        counts[name] = query.count() if query is not None else 0
    counts["returned"] = _returned_records_query(db, user).count()

    return {
        "tab": tab,
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": max(1, math.ceil(total / per_page)),
        "counts": counts,
    }


@router.get("/departments")
def approval_departments(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_flexible),
):
    """Department options represented by teams in the user's approval queue."""
    tasks = workflows.tasks_for(db, user)
    workflow_ids = [workflow.id for workflow, _ in tasks]
    if not workflow_ids:
        return []
    return [
        row[0]
        for row in (
            db.query(QualityTeam.name)
            .join(Record, Record.team_id == QualityTeam.id)
            .filter(Record.workflow_id.in_(workflow_ids))
            .distinct()
            .order_by(QualityTeam.name)
            .all()
        )
    ]
