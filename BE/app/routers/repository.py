"""
The Document Repository: approved, filed records and the folders they sit in.

Kept apart from `documents.py`, which only serves a record's evidence file.
This router is mounted in `api.py` at `/api/documents/repository`, so the URLs
the front end already calls do not change:

    GET   /api/documents/repository                 browse / search / filter
    PATCH /api/documents/repository/folders/rename  rename a folder
    PUT   /api/documents/repository/folders/pin     pin or unpin a folder
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import ApprovalStep, ApprovalWorkflow, Document, User
from ..models_qms import Record, STAGE_CANCELLED, STAGE_STORED
from ..services import format_service, workflow_service as workflows
from ..services.auth_service import require_permission_flexible
from ..services.document_repository import (
    DocumentRepositoryService,
    FolderConflictError,
    FolderValidationError,
    RepositoryFilters,
)

router = APIRouter()

_REPOSITORY_STAGES = (STAGE_STORED, STAGE_CANCELLED)

# Record events that restate an approval the workflow's own trail already gives
# step by step (who signed, each CFT member); every other event of the record -
# called, hard copy attached, N-OK cleared, filed, a change request - is only here.
_MIRRORED_BY_WORKFLOW = {"submitted", "po_approved", "opo_approved", "cft_reviewed", "final_approved", "reverify"}


def _person_json(user: Optional[User]) -> Optional[dict]:
    if not user:
        return None
    return {
        "id": user.id,
        "name": user.full_name or user.username,
        "email": user.email,
        "job_title": user.job_title,
    }


def _record_trail(record: Record, since: Optional[datetime] = None) -> list[dict]:
    """The record's own history, in the shape of a workflow event.

    Its approval events are left out from `since` (when the current approval began),
    as that approval's own trail gives them; earlier rounds - before a return for
    correction - exist only here and are kept.
    """
    def utc(value: Optional[datetime]) -> Optional[datetime]:
        return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value

    # "submitted" is written a moment before the approval it starts
    bound = utc(since) - timedelta(seconds=5) if since is not None else None

    def restated(event) -> bool:
        return (bound is not None and event.kind in _MIRRORED_BY_WORKFLOW
                and (event.created_at is None or utc(event.created_at) >= bound))

    return [
        {
            "id": event.id,
            "step_id": None,
            "kind": event.kind,
            "summary": event.summary,
            "detail": event.detail,
            "by": _person_json(event.actor),
            "at": event.created_at,
        }
        for event in (record.events or [])
        if not restated(event)
    ]


def _by_time(events: list[dict]) -> list[dict]:
    return sorted(events, key=lambda event: (
        event["at"].replace(tzinfo=timezone.utc)
        if event["at"] and event["at"].tzinfo is None
        else event["at"]
    ) or datetime.min.replace(tzinfo=timezone.utc))


def _repository_record(db: Session, record_id: str) -> Record:
    record = (
        db.query(Record)
        .options(
            joinedload(Record.format),
            joinedload(Record.team),
            joinedload(Record.document).joinedload(Document.doctype),
            joinedload(Record.filler),
            joinedload(Record.storer),
            joinedload(Record.workflow)
            .joinedload(ApprovalWorkflow.steps)
            .joinedload(ApprovalStep.assignees),
        )
        .filter(Record.id == record_id, Record.stage.in_(_REPOSITORY_STAGES))
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Filed repository record not found")
    return record


class RenameFolderRequest(BaseModel):
    """Folder to rename (path as returned by the folder tree) and its new name."""

    folder_path: str = Field(..., min_length=1, max_length=500)
    new_name: str = Field(..., min_length=1, max_length=100)


class PinFolderRequest(BaseModel):
    """Folder to pin or unpin for the current user."""

    folder_path: str = Field(..., min_length=1, max_length=500)
    pinned: bool = True


@router.get(
    "",
    summary="Document Repository",
    description="Browse finally approved documents in their folder hierarchy.",
)
def document_repository(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
    search: Optional[str] = Query(None, max_length=200),
    folder_path: Optional[str] = Query(None, max_length=500),
    team_id: Optional[str] = Query(None),
    format_id: Optional[str] = Query(None),
    filed_date: Optional[date] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    """List finally approved documents filed in the document repository.

    The router validates HTTP inputs; repository filtering and response shaping
    are handled by the repository service.
    """
    filters = RepositoryFilters(
        search=search,
        folder_path=folder_path,
        team_id=team_id,
        format_id=format_id,
        filed_date=filed_date,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return DocumentRepositoryService(db, user_id=current_user.id).list_documents(filters)


@router.get(
    "/{record_id}/summary",
    summary="Repository document summary",
    description="Return metadata and completion information for a filed record.",
    dependencies=[Depends(require_permission_flexible("documents.read"))],
)
def repository_document_summary(
    record_id: str,
    db: Session = Depends(get_db),
):
    """Return the document and record metadata used by the repository detail view."""
    record = _repository_record(db, record_id)
    fmt = record.format
    document = record.document
    values = record.values or []
    completed_items = sum(
        1 for value in values
        if value.value is not None and str(value.value).strip()
    )

    return {
        "record_id": record.id,
        "record_number": record.number,
        "document": {
            "id": document.id,
            "title": document.title or document.original_filename or document.filename,
            "filename": document.original_filename or document.filename,
            "document_type": (
                document.doctype.name if document.doctype else None
            ),
            "summary": document.summary,
            "file_size": document.file_size,
            "mime_type": document.mime_type,
            "version": document.version or "0.1",
            "created_at": document.created_at,
            "file_url": f"/api/documents/{document.id}/file",
            "download_url": f"/api/documents/{document.id}/download",
        } if document else None,
        "summary": {
            "name": fmt.title if fmt else record.number,
            "code": fmt.code if fmt else None,
            # the revision the record was filled against (a later revision does not change it)
            "revision": record.format_revision or (fmt.revision if fmt else None),
            "document_type": (
                format_service.FREQUENCY_LABELS.get(fmt.frequency, fmt.frequency)
                if fmt else None
            ),
            "department": record.team.name if record.team else None,
            "filled_by": _person_json(record.filler),
            "filled_on": record.filled_at,
            "filed_by": _person_json(record.storer),
            "filed_on": record.stored_at,
            "total_items": len(values),
            "completed_items": completed_items,
            "completion_percent": (
                round(completed_items / len(values) * 100) if values else 0
            ),
            "fields": [
                {
                    "id": value.id,
                    "label": value.label,
                    "value": value.value,
                    "unit": value.unit,
                    "specification": value.spec_text,
                    "in_spec": value.in_spec,
                }
                for value in values
            ],
        },
    }


@router.get(
    "/{record_id}/approval-timeline",
    summary="Repository approval timeline",
    description="Return workflow assignments, decisions, comments, and activity.",
    dependencies=[Depends(require_permission_flexible("documents.read"))],
)
def repository_approval_timeline(
    record_id: str,
    db: Session = Depends(get_db),
):
    """Return each approval step and its recorded decisions for a filed record."""
    record = _repository_record(db, record_id)
    workflow = record.workflow
    if not workflow:
        return {
            "record_id": record.id,
            "workflow": None,
            "current_assignment": None,
            "steps": [],
            "events": _by_time(_record_trail(record)),
        }

    current = workflows.current_step(workflow)
    current_assignees = (
        workflows.outstanding(current) or list(current.assignees or [])
        if current else []
    )
    steps = []
    for step in workflow.steps or []:
        decisions = [
            {
                "action": decision.action,
                "by": _person_json(decision.user),
                "at": decision.decided_at,
                "comment": decision.comment,
                "reason": decision.reason,
                "signature": (
                    {
                        "name": decision.signature.name,
                        "designation": decision.signature.designation,
                        "signed_at": decision.signature.signed_at,
                    }
                    if decision.signature else None
                ),
            }
            for decision in (step.decisions or [])
        ]
        steps.append({
            "id": step.id,
            "order": step.order_index + 1,
            "name": step.name,
            "status": step.status,
            "stage": step.qms_stage,
            "department": step.department,
            "role": step.role,
            "assigned_to": [
                _person_json(person) for person in (step.assignees or [])
            ],
            "due_at": step.due_date,
            "decided_at": step.decided_at,
            "decided_by": _person_json(step.decider),
            "comment": step.comment,
            "reason": step.reason,
            "signature": (
                {
                    "name": step.signature.name,
                    "designation": step.signature.designation,
                    "signed_at": step.signature.signed_at,
                }
                if step.signature else None
            ),
            "decisions": decisions,
        })

    events = [
        {
            "id": event.id,
            "step_id": event.step_id,
            "kind": event.kind,
            "summary": event.summary,
            "detail": event.detail,
            "by": _person_json(event.actor),
            "at": event.created_at,
        }
        for event in (workflow.events or [])
    ]
    # the approval, and around it what happened to the record: filed, changed afterwards (RCR)
    events = _by_time(events + _record_trail(record, since=workflow.started_at or workflow.created_at))

    return {
        "record_id": record.id,
        "workflow": {
            "id": workflow.id,
            "status": workflow.status,
            "priority": workflow.priority,
            "submitted_by": _person_json(workflow.creator),
            "submitted_on": workflow.started_at or workflow.created_at,
            "completed_on": workflow.completed_at,
        },
        "current_assignment": {
            "step_id": current.id,
            "step_name": current.name,
            "assigned_to": [
                _person_json(person) for person in current_assignees
            ],
            "due_at": current.due_date,
        } if current else None,
        "steps": steps,
        "events": events,
    }


@router.patch(
    "/folders/rename",
    summary="Rename a repository folder",
    description="Renames a folder and every filed record beneath it.",
)
def rename_repository_folder(
    body: RenameFolderRequest,
    db: Session = Depends(get_db),
    # "documents.write" is a placeholder: use whichever existing permission
    # should be allowed to manage folders.
    current_user: User = Depends(require_permission_flexible("documents.write")),
):
    """Rename a folder, rewriting the path of every record filed under it."""
    try:
        return DocumentRepositoryService(db).rename_folder(
            body.folder_path, body.new_name
        )
    except FolderValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except FolderConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.put(
    "/folders/pin",
    summary="Pin or unpin a repository folder",
    description="Pins are personal and only change the current user's folder tree.",
)
def pin_repository_folder(
    body: PinFolderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """Pin or unpin a folder for the signed-in user."""
    user_id = getattr(current_user, "id", None)
    if not user_id:
        # Pins belong to a person, so an anonymous or placeholder caller cannot pin.
        raise HTTPException(status_code=401, detail="Sign in to pin folders.")
    try:
        return DocumentRepositoryService(db).set_folder_pinned(
            user_id, body.folder_path, body.pinned
        )
    except FolderValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))