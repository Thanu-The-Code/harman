"""
The record API - boxes B2 through B8 of the client's record process flow.

Calling a format, filling it (on screen or by scanning the paper copy through
OCR), submitting it for approval, closing the N-ok flag, and filing the
approved record into its date- or month-wise folder.

The approval decisions themselves are not here. A record's chain is an ordinary
ApprovalWorkflow, so it is decided through `/api/workflow`, which keeps My
Tasks, Tracking and signatures working on records exactly as on any other
document. What this router owns is everything either side of that chain.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Document, User, ApprovalWorkflow
from ..models_qms import Record, RecordFieldValue
from ..services import approval_route as routes
from ..services import form_layout as layouts
from ..services import format_service as fmts
from ..services import notification_service as notify
from ..services import record_change_request_service as rcrs
from ..services import record_service as recs
from ..services import workflow_service as wf
from ..services.file_utils import safe_headers, served_type
from ..services.audit_service import log_audit_event
from ..services.auth_service import get_current_user_flexible

router = APIRouter()


# ---------------------------------------------------------------- payloads


class ValuePayload(BaseModel):
    id: Optional[str] = None
    # Where the value sits on a designed form (see form_layout.to_fields).
    layout_key: Optional[str] = None
    label: Optional[str] = None
    value: Optional[str] = None
    remark: Optional[str] = None


class FillPayload(BaseModel):
    values: list[ValuePayload] = Field(default_factory=list)


class CallPayload(BaseModel):
    format_id: str
    entry_mode: str = "digital"       # digital | hardcopy


class SubmitPayload(BaseModel):
    document_id: Optional[str] = None
    approval_overrides: Optional[dict[str, list[str]]] = None


class NokPayload(BaseModel):
    note: str = ""


class ReverifyPayload(BaseModel):
    reason: str


class ReturnPayload(BaseModel):
    reason: str


class OpinionPayload(BaseModel):
    agrees: bool
    comment: str = ""


# ----------------------------------------------------------- serialisation


STAGE_LABELS = {
    recs.STAGE_FILLING: "Being filled",
    recs.STAGE_PO: "With the Process Owner",
    recs.STAGE_OPO: "With the Overall Process Owner",
    recs.STAGE_CFT: "CFT joint review",
    recs.STAGE_FINAL: "Final decision",
    recs.STAGE_STORED: "Filed on the server",
    recs.STAGE_CANCELLED: "Cancelled",
}


class RecordAccessPolicy:
    """Resolve the actions the current user may take on a record."""

    @staticmethod
    def permissions(record: Record, viewer: Optional[User]) -> dict:
        if not viewer:
            return {}
        fmt = record.format
        # the people chosen at submission hold the role, else the format's
        is_po = viewer.id in recs.process_owner_ids(record)
        is_opo = viewer.id in recs.overall_process_owner_ids(record)
        is_record_filler = record.filled_by == viewer.id
        admin = bool(viewer.is_admin)
        may_fill = is_po or is_record_filler or admin

        return {
            "fill": record.stage == recs.STAGE_FILLING and may_fill,
            "submit": record.stage == recs.STAGE_FILLING and may_fill,
            "clear_nok": bool(record.nok_flagged_at and not record.nok_cleared_at
                              and (is_opo or admin)),
            "send_back": record.stage == recs.STAGE_FINAL and (is_po or admin),
            "return_for_correction": (
                record.stage in (recs.STAGE_PO, recs.STAGE_OPO)
                and (is_po or is_opo or admin)
            ),
            # Saving readings. While the record is being filled that is the
            # same people as filling it - otherwise a format that leaves its
            # Process Owner to be chosen at submission could be called and
            # submitted but never filled. Corrections during a re-verification
            # stay with the Process Owner.
            "amend": bool(
                (record.stage == recs.STAGE_FILLING and may_fill)
                or (record.stage == recs.STAGE_CFT
                    and (record.reverify_count or 0) > 0
                    and (is_po or admin))
            ),
            "store": bool(
                record.stage not in (recs.STAGE_STORED, recs.STAGE_CANCELLED)
                and (is_opo or admin)
                and record.workflow
                and record.workflow.status in (wf.APPROVED, wf.PUBLISHED)
                and not (record.nok_flagged_at and not record.nok_cleared_at)
            ),
            # raising a record change request (the RCR service's own rule)
            "request_change": rcrs.can_raise(record, viewer),
        }


class RecordPresenter:
    """Format record data for API responses, separate from route handling."""

    @staticmethod
    def person(user: Optional[User]) -> Optional[dict]:
        if not user:
            return None
        return {"id": user.id, "name": user.full_name or user.username,
                "email": user.email, "job_title": user.job_title}

    @staticmethod
    def value_json(row) -> dict:
        field = row.field
        options = None
        if field is not None and field.options:
            try:
                options = json.loads(field.options)
            except (TypeError, ValueError):
                options = None
        return {
            "id": row.id,
            "field_id": row.field_id,
            "layout_key": row.layout_key,
            "order": row.order_index,
            "label": row.label,
            "field_type": row.field_type,
            "options": options,
            "required": bool(field.required) if field is not None else True,
            "help_text": field.help_text if field is not None else None,
            "unit": row.unit,
            "spec_min": row.spec_min,
            "spec_max": row.spec_max,
            "spec_text": row.spec_text,
            "spec_label": recs.spec_label(row),
            "value": row.value,
            "numeric_value": row.numeric_value,
            "in_spec": row.in_spec,
            "remark": row.remark,
        }

    @staticmethod
    def attachment_json(attachment) -> dict:
        """One supporting photograph or document, as the screens read it."""
        return {
            "id": attachment.id,
            "filename": attachment.filename,
            "caption": attachment.caption,
            "mime_type": attachment.mime_type,
            "size": attachment.file_size,
            "is_image": bool((attachment.mime_type or "").startswith("image/")),
            "uploaded_by": RecordPresenter.person(attachment.uploader),
            "uploaded_at": attachment.uploaded_at,
            "href": f"/api/records/{attachment.record_id}/attachments/{attachment.id}",
        }

    @staticmethod
    def record_json(
        db: Session,
        record: Record,
        viewer: Optional[User] = None,
        *,
        detail: bool = False,
    ) -> dict:
        fmt = record.format
        data = {
            "id": record.id,
            "number": record.number,
            "format": {
                "id": fmt.id, "code": fmt.code, "title": fmt.title,
                "frequency": fmt.frequency,
                "frequency_label": fmts.FREQUENCY_LABELS.get(
                    fmt.frequency, fmt.frequency
                ),
                "work_instruction_ref": fmt.work_instruction_ref,
                "work_instruction": fmt.work_instruction,
                "layout": layouts.parse(fmt.layout),
            } if fmt else None,
            "format_revision": record.format_revision,
            "team": {"id": record.team.id, "code": record.team.code,
                     "name": record.team.name} if record.team else None,
            "period_key": record.period_key,
            "period_label": record.period_label,
            "entry_mode": record.entry_mode,
            "stage": record.stage,
            "stage_label": STAGE_LABELS.get(record.stage, record.stage),
            "observation_status": record.observation_status,
            "rag": record.rag_status,
            "rag_label": recs.rag_label(record),
            "cft_objection": record.cft_objection,
            "nok_summary": record.nok_summary,
            "nok_flagged_at": record.nok_flagged_at,
            "nok_flagged_to": RecordPresenter.person(record.flagged_to),
            "nok_cleared_at": record.nok_cleared_at,
            "nok_open": bool(record.nok_flagged_at and not record.nok_cleared_at),
            "cft_target_date": record.cft_target_date,
            "reverify_count": record.reverify_count or 0,
            "filled_by": RecordPresenter.person(record.filler),
            "filled_at": record.filled_at,
            "submitted_at": record.submitted_at,
            "document_id": record.document_id,
            "workflow_id": record.workflow_id,
            "approval_overrides": json.loads(record.approval_overrides)
            if record.approval_overrides else {},
            "workflow_status": record.workflow.status if record.workflow else None,
            "storage_path": record.storage_path,
            "stored_at": record.stored_at,
            "stored_by": RecordPresenter.person(record.storer),
            "created_at": record.created_at,
            "can": RecordAccessPolicy.permissions(record, viewer),
            "awaiting": RecordPresenter.awaiting_json(record),
            "value_count": len(record.values or []),
        }

        if detail:
            data["values"] = [
                RecordPresenter.value_json(value) for value in record.values
            ]
            data["missing"] = recs.missing_required(record)
            # back with its Process Owner after a return for correction: who, when and why
            returned = next((e for e in reversed(record.events or []) if e.kind == "returned"), None)
            data["returned"] = ({
                "by": RecordPresenter.person(returned.actor),
                "at": returned.created_at,
                "reason": returned.detail,
            } if returned and record.stage == recs.STAGE_FILLING else None)
            data["attachments"] = [
                RecordPresenter.attachment_json(attachment)
                for attachment in record.attachments
            ]
            data["events"] = [
                {
                    "id": event.id,
                    "kind": event.kind,
                    "summary": event.summary,
                    "detail": event.detail,
                    "actor": RecordPresenter.person(event.actor),
                    "at": event.created_at,
                }
                for event in record.events
            ]
            data["responsibilities"] = {
                "process_owner": (
                    RecordPresenter.person(fmt.process_owner) if fmt else None
                ),
                "overall_process_owner": (
                    RecordPresenter.person(fmt.overall_process_owner)
                    if fmt else None
                ),
                "cft_members": (
                    [RecordPresenter.person(member) for member in fmt.cft_members]
                    if fmt else []
                ),
                "qms_coordinator": (
                    RecordPresenter.person(fmt.qms_coordinator) if fmt else None
                ),
            }
            if record.approval_overrides:
                try:
                    overrides = json.loads(record.approval_overrides)
                    people = db.query(User).filter(
                        User.id.in_({
                            person_id
                            for ids in overrides.values()
                            for person_id in ids
                        })
                    ).all()
                    by_id = {person.id: person for person in people}
                    data["responsibilities"] = {
                        "process_owner": RecordPresenter.person(
                            by_id.get((overrides.get("process_owner") or [None])[0])
                        ) or data["responsibilities"]["process_owner"],
                        "overall_process_owner": RecordPresenter.person(
                            by_id.get(
                                (overrides.get("overall_process_owner") or [None])[0]
                            )
                        ) or data["responsibilities"]["overall_process_owner"],
                        "cft_members": [
                            RecordPresenter.person(by_id[person_id])
                            for person_id in overrides.get("cft_members", [])
                            if person_id in by_id
                        ] or data["responsibilities"]["cft_members"],
                        "qms_coordinator": RecordPresenter.person(
                            by_id.get(
                                (overrides.get("qms_coordinator") or [None])[0]
                            )
                        ) or data["responsibilities"]["qms_coordinator"],
                    }
                except (TypeError, ValueError):
                    pass
            data["route"] = RecordPresenter.route_json(
                fmt, data["responsibilities"]
            )
            data["storage_preview"] = " / ".join(
                fmts.full_storage_path(fmt, record.period_start or record.created_at)
            ) if fmt else None

        return data

    @staticmethod
    def route_json(fmt, responsibilities: dict) -> list[dict]:
        """Present the approval route and the people addressed at each step."""
        if not fmt:
            return []

        steps = routes.parse(fmt.approval_route, fmt.cft_target_days)

        def people_for(step: dict) -> list[dict]:
            addressed_to = step.get("addressed_to")
            if addressed_to == routes.ROLE_CFT:
                return list(responsibilities.get("cft_members") or [])
            role = {
                routes.ROLE_PROCESS_OWNER: "process_owner",
                routes.ROLE_OVERALL_PROCESS_OWNER: "overall_process_owner",
                routes.ROLE_QMS_COORDINATOR: "qms_coordinator",
            }.get(addressed_to)
            if role:
                person = responsibilities.get(role)
                return [person] if person else []
            return []

        return [
            {
                "order": index + 1,
                "name": step.get("name"),
                "stage": step.get("stage"),
                "addressed_to": step.get("addressed_to"),
                "mode": step.get("mode"),
                "requires_signature": bool(step.get("requires_signature")),
                "days": step.get("days"),
                "people": people_for(step),
            }
            for index, step in enumerate(steps)
        ]

    @staticmethod
    def awaiting_json(record: Record) -> Optional[dict]:
        """Present the active workflow step and the people who still owe a response."""
        workflow = getattr(record, "workflow", None)
        if not workflow:
            return None

        step = next(
            (candidate for candidate in (workflow.steps or [])
             if candidate.status == wf.CURRENT),
            None,
        )
        if step is None:
            return None

        people = wf.outstanding(step) or list(step.assignees or [])
        return {
            "step": step.name,
            "stage": step.qms_stage,
            "people": [RecordPresenter.person(person) for person in people],
            "due": step.due_date,
            "overdue": wf.is_overdue(step),
        }

    @staticmethod
    def specification_label(value) -> str:
        if value.spec_min is not None and value.spec_max is not None:
            return f"{value.spec_min} - {value.spec_max}"
        if value.spec_max is not None:
            return f"max {value.spec_max}"
        if value.spec_min is not None:
            return f"min {value.spec_min}"
        return ""


def _load(db: Session, record_id: str) -> Record:
    record = recs.get(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


# ------------------------------------------------------------------ listing


@router.get("")
@router.get("/", include_in_schema=False)
def list_records(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
    team_id: Optional[str] = Query(None),
    format_id: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
    rag: Optional[str] = Query(None),
    observation: Optional[str] = Query(None),
    mine: bool = Query(False),
    # My Forms asks a different question from the register's "only mine": not
    # "what did I fill" but "what do I have a stake in", which includes the
    # records waiting on my signature.
    involving: bool = Query(False),
    limit: int = Query(200, ge=1, le=1000),
):
    """
    The record register, which is also what Tracking reads.

    Statuses are refreshed before the list is built: one of the red conditions
    is a target date going by, so a record can turn red overnight with nobody
    touching it.
    """
    recs.refresh_all_statuses(db)
    if involving:
        found = recs.involving(db, current_user, limit=limit)
        if stage:
            found = [r for r in found if r.stage == stage]
    else:
        found = recs.list_records(
            db, team_id=team_id, format_id=format_id, stage=stage, rag=rag,
            observation=observation, mine_for=current_user if mine else None,
            limit=limit,
        )
    return {
        "records": [
            RecordPresenter.record_json(db, record, current_user)
            for record in found
        ],
        "stats": recs.stats(db, team_id=team_id),
        "rag_labels": recs.RAG_LABELS,
        "stage_labels": STAGE_LABELS,
    }


@router.get("/stats")
def record_stats(db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user_flexible),
                 team_id: Optional[str] = Query(None)):
    recs.refresh_all_statuses(db)
    return recs.stats(db, team_id=team_id)


@router.get("/documents-listing")
def my_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
    tab: Literal["verification", "draft"] = Query("verification"),
    q: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> dict:
    """
    The My Documents table needs only each record's summary, not its filled
    fields; keeping this separate avoids loading the heavier detail payload.
    """
    recs.refresh_all_statuses(db)
    records, total, counts, departments = recs.list_my_documents(
        db, current_user, tab, q, team_id, page, page_size
    )

    items = []
    for record in records:
        approved_steps = [
            step for step in (record.workflow.steps or [])
            if step.status == wf.APPROVED
        ] if record.workflow else []
        last_approval_step = max(
            approved_steps,
            key=lambda step: (
                (
                    step.decided_at.replace(tzinfo=timezone.utc)
                    if step.decided_at and step.decided_at.tzinfo is None
                    else step.decided_at
                ) or datetime.min.replace(tzinfo=timezone.utc),
                step.order_index,
            ),
            default=None,
        )
        last_update = (
            record.updated_at
            or max(
                (event.created_at for event in record.events if event.created_at),
                default=None,
            )
            or record.created_at
        )
        items.append({
            "id": record.id,
            "number": record.number,
            "document_name": record.format.title,
            "department": (
                {"id": record.team.id, "name": record.team.name}
                if record.team else None
            ),
            "type": fmts.FREQUENCY_LABELS.get(
                record.format.frequency, record.format.frequency
            ),
            "frequency": record.format.frequency,
            "start_on": record.period_start,
            "last_update": last_update,
            "last_approval": (
                {
                    "order": last_approval_step.order_index + 1,
                    "name": last_approval_step.name,
                    "by": (
                        last_approval_step.decider.full_name
                        or last_approval_step.decider.username
                    ) if last_approval_step.decider else None,
                }
                if last_approval_step else None
            ),
            "stage": record.stage,
            "stage_label": STAGE_LABELS.get(record.stage, record.stage),
            "rag": record.rag_status,
            "workflow_id": record.workflow_id,
            "document_id": record.document_id,
            "awaiting": RecordPresenter.awaiting_json(record),
            "can": RecordAccessPolicy.permissions(record, current_user),
        })

    return {
        "tab": tab,
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
        "counts": counts,
        "departments": departments,
    }


@router.get("/{record_id}")
def get_record(record_id: str, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user_flexible)):
    record = _load(db, record_id)
    recs.refresh_status(record)
    db.commit()
    return RecordPresenter.record_json(db, record, current_user, detail=True)


# -------------------------------------------------------------- B2: call it


@router.get("/preview/{format_id}")
def preview_format(format_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user_flexible)):
    """
    A blank of this format, shaped like a record but not saved as one.

    Opening a template from Resource used to call it, which raised a real
    record the moment the page loaded - so a template that somebody looked at
    and closed left a half-filled record in the register, and a published
    template meant to be used many times could only be opened once per period
    before the screen started reusing what was there.

    Nothing here is written. The record is created on the first act that means
    to keep it: saving a draft, attaching a scan, or submitting.

    The values carry `new-<n>` in place of an id, where n is the row's position
    on the form. That is what lets the browser hand back what somebody typed
    once the real rows exist and have real ids.
    """
    fmt = fmts.get(db, format_id)
    if not fmt:
        raise HTTPException(status_code=404, detail="Format not found")
    if fmt.status != fmts.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail=f"{fmt.code} is {fmt.status}. Only a released template can be filled.")

    period = fmts.period_for(fmt.frequency)

    # Built in memory and never added to the session. `no_autoflush` keeps a
    # query made further down from quietly writing this to the database.
    with db.no_autoflush:
        record = Record(
            number="",
            format_id=fmt.id,
            format_revision=fmt.revision,
            team_id=fmt.team_id,
            period_key=period["key"],
            period_label=period["label"],
            period_start=period["start"],
            period_end=period["end"],
            entry_mode="digital",
            stage=recs.STAGE_FILLING,
            rag_status="yellow",
            filled_by=current_user.id,
        )
        record.format = fmt
        record.team = fmt.team
        record.filler = current_user
        record.values = [
            RecordFieldValue(
                id=f"new-{field.order_index}",
                field_id=field.id,
                order_index=field.order_index,
                label=field.label,
                field_type=field.field_type,
                unit=field.unit,
                spec_min=field.spec_min,
                spec_max=field.spec_max,
                spec_text=field.spec_text,
                layout_key=field.layout_key,
            )
            for field in fmt.fields
        ]

        data = RecordPresenter.record_json(db, record, current_user, detail=True)

    # Said plainly, so nothing downstream has to infer it from a blank number.
    data["id"] = None
    data["unsaved"] = True
    data["format_id"] = fmt.id
    return data


@router.post("/call")
def call_format(payload: CallPayload, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user_flexible)):
    """B2 - "Process Owner will call the format which is being to be filled"."""
    fmt = fmts.get(db, payload.format_id)
    if not fmt:
        raise HTTPException(status_code=404, detail="Format not found")
    try:
        record = recs.call_format(db, fmt, current_user,
                                  entry_mode=payload.entry_mode)
    except recs.RecordError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    log_audit_event(db, current_user.id, "record.called", "record", record.id,
                    {"format": fmt.code, "period": record.period_key})
    return RecordPresenter.record_json(db, record, current_user, detail=True)


# -------------------------------------------------------------- B3: fill it


@router.put("/{record_id}/values")
def save_values(record_id: str, payload: FillPayload,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user_flexible)):
    """
    B3 - record the readings. Each is judged against its specification as it
    is saved, so the person filling it sees an out-of-spec value immediately
    rather than being told about it after they have submitted.
    """
    record = _load(db, record_id)
    if not RecordAccessPolicy.permissions(record, current_user).get("amend"):
        raise HTTPException(
            status_code=403,
            detail="Only this format's Process Owner may fill the record, and "
                   "only while it is being filled or back for re-verification.")
    try:
        record = recs.save_values(
            db, record, current_user, [v.model_dump() for v in payload.values])
    except recs.RecordError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RecordPresenter.record_json(db, record, current_user, detail=True)


@router.get("/{record_id}/attachments")
def list_attachments(record_id: str, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user_flexible)):
    """The supporting photographs and documents on one record."""
    record = _load(db, record_id)
    return {
        "attachments": [
            RecordPresenter.attachment_json(attachment)
            for attachment in record.attachments
        ]
    }


@router.post("/{record_id}/attachments")
async def add_attachment(
    record_id: str,
    file: UploadFile = File(...),
    caption: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """
    Attach a photograph or a document to a record.

    Not the same thing as the scanned sheet, which is the record itself and
    lives in `document_id`. These are what somebody adds beside it - the defect
    photographed at the machine, the gauge's calibration certificate, a
    supplier's test report - and there can be any number of them.

    Kept beside the record rather than ingested into the document repository:
    a photograph of a scratched housing is not a document anybody searches for
    by name, and putting it in the repository would only mean every search for
    the process it belongs to returned somebody's phone photo.
    """
    from pathlib import Path
    from uuid import uuid4

    from ..models_qms import RecordAttachment

    record = _load(db, record_id)
    if not RecordAccessPolicy.permissions(record, current_user).get("fill"):
        raise HTTPException(
            status_code=403,
            detail="Only this format's Process Owner may add to the record.")

    settings = get_settings(db)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="That file is empty.")
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(status_code=400, detail="That file is too large.")

    suffix = Path(file.filename or "photo.jpg").suffix.lower().lstrip(".")
    if suffix not in settings.allowed_extensions_list:
        raise HTTPException(
            status_code=400,
            detail=f"'{suffix}' files are not accepted. Allowed: "
                   + ", ".join(settings.allowed_extensions_list))

    folder = Path(settings.storage_folder) / "records" / record.id / "attachments"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{uuid4().hex}.{suffix}"
    target.write_bytes(content)

    attachment = RecordAttachment(
        record_id=record.id,
        filename=file.filename or target.name,
        file_path=str(target),
        mime_type=served_type(target.name)[0],  # from the extension, not what the browser claimed
        file_size=len(content),
        caption=(caption or "").strip() or None,
        uploaded_by=current_user.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    recs.log_event(db, record, current_user, "attachment",
                   f"{current_user.full_name or current_user.username} attached "
                   f"{attachment.filename}"
                   + (f" - {attachment.caption}" if attachment.caption else ""))

    return RecordPresenter.attachment_json(attachment)


@router.get("/{record_id}/attachments/{attachment_id}")
def open_attachment(record_id: str, attachment_id: str,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user_flexible)):
    """
    The file itself, drawn in place rather than downloaded.

    Inline because these are looked at, not filed: a photograph of a defect is
    opened to be seen, and handing somebody a download when they clicked a
    thumbnail is a worse answer than showing it.
    """
    from pathlib import Path

    from fastapi.responses import FileResponse

    from ..models_qms import RecordAttachment

    _load(db, record_id)
    attachment = (db.query(RecordAttachment)
                  .filter(RecordAttachment.id == attachment_id,
                          RecordAttachment.record_id == record_id)
                  .first())
    if not attachment:
        raise HTTPException(status_code=404, detail="That attachment does not exist.")

    path = Path(attachment.file_path)
    if not path.exists():
        raise HTTPException(status_code=404,
                            detail="The file is missing from storage.")
    media_type, inline = served_type(path.name)  # the stored type is not trusted (older uploads)
    return FileResponse(
        str(path),
        media_type=media_type,
        filename=attachment.filename,
        content_disposition_type="inline" if inline else "attachment",
        headers=safe_headers(media_type),
    )


@router.delete("/{record_id}/attachments/{attachment_id}")
def remove_attachment(record_id: str, attachment_id: str,
                      db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user_flexible)):
    """
    Take one off the record.

    The file goes with it. An attachment is not part of the approved record -
    it is supporting material somebody chose to add - so removing one before
    the record is filed is housekeeping rather than a change to the evidence.
    """
    from pathlib import Path

    from ..models_qms import RecordAttachment

    record = _load(db, record_id)
    if not RecordAccessPolicy.permissions(record, current_user).get("fill"):
        raise HTTPException(
            status_code=403,
            detail="Only this format's Process Owner may change the record.")

    attachment = (db.query(RecordAttachment)
                  .filter(RecordAttachment.id == attachment_id,
                          RecordAttachment.record_id == record_id)
                  .first())
    if not attachment:
        raise HTTPException(status_code=404, detail="That attachment does not exist.")

    name = attachment.filename
    Path(attachment.file_path).unlink(missing_ok=True)
    db.delete(attachment)
    db.commit()

    recs.log_event(db, record, current_user, "attachment",
                   f"{current_user.full_name or current_user.username} removed {name}")
    return {"removed": attachment_id}


@router.post("/{record_id}/scan")
async def attach_hard_copy(
    record_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """
    Attach the filled paper record and read it (B3, hard-copy route).

    This is the digitisation the client asked for: the form is filled on paper
    exactly as it is today, photographed or scanned, and the text is extracted
    by the same OCR pipeline every other document goes through. The extracted
    text comes back with the response so the person can copy readings across
    into the fields rather than retyping the whole sheet.
    """
    record = _load(db, record_id)
    if not RecordAccessPolicy.permissions(record, current_user).get("fill"):
        raise HTTPException(
            status_code=403,
            detail="Only this format's Process Owner may fill the record.")

    settings = get_settings(db)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="That file is empty.")
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(status_code=400, detail="That file is too large.")

    from ..services import evidence_service as evidence

    suffix = Path(file.filename or "scan.pdf").suffix.lower().lstrip(".")
    refusal = evidence.scan_refusal(file.filename or "scan.pdf", settings)
    if refusal:
        raise HTTPException(status_code=400, detail=refusal)

    # Deliberately NOT the staging folder. `file_watcher` monitors that, and
    # would pick this file up and process it in its own session while this
    # request is still reading it - two sessions racing over one document row,
    # for the twenty seconds OCR takes. The loser finds the row gone and the
    # operator is told their scan is corrupt.
    scan_dir = Path(settings.data_folder) / "scans"
    scan_dir.mkdir(parents=True, exist_ok=True)
    scan_path = scan_dir / f"{record.number}-{uuid4().hex[:8]}.{suffix}"
    scan_path.write_bytes(content)

    from ..services.file_utils import calculate_file_hash

    # The capture pipeline refuses a file it has already ingested, and returns
    # nothing to say why. For a record that distinction matters: the same
    # sheet re-attached to the same record is routine, the same sheet attached
    # to two different records is a data-integrity problem, and an unreadable
    # file is neither. Work out which before calling it, so the person holding
    # the scanner is told the truth.
    refusal = evidence.content_refusal(scan_path)
    if refusal:
        scan_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=refusal)

    digest = calculate_file_hash(scan_path)
    twin = db.query(Document).filter(Document.file_hash == digest).first()

    if twin:
        owner = recs.by_document(db, twin.id)
        if owner and owner.id != record.id:
            scan_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"That exact file is already the evidence for {owner.number}. "
                    "Two records cannot share one sheet - scan the sheet that "
                    "belongs to this record."
                ),
            )
        # Either it is already this record's evidence, or it is an unattached
        # document. Both are fine: attach it and do not ingest it twice.
        scan_path.unlink(missing_ok=True)
        document = twin
    else:
        try:
            document = evidence.ingest(db, scan_path, title=record.number)
        except evidence.EvidenceError as exc:
            scan_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            logger.error(f"Could not read the scan for {record.number}: {exc}")
            raise HTTPException(
                status_code=500,
                detail="The scan could not be read. Check the file and try again.")

    # The upload was a courier, not the record. `ingest` has already moved the
    # file into storage under the document's own name, so the copy here is
    # finished with.
    scan_path.unlink(missing_ok=True)

    record.entry_mode = "hardcopy"
    record.document_id = document.id
    document.title = f"{record.number} - {record.format.title}" if record.format \
        else record.number
    recs.log_event(db, record, current_user, "scanned",
                   f"{current_user.full_name or current_user.username} attached "
                   f"the filled hard copy ({file.filename})")
    db.commit()
    db.refresh(record)

    # What the sheet appears to say, matched against this format's own fields.
    # Offered as suggestions the Process Owner confirms - never written to the
    # record, because an engine that misreads 25.02 as 26.02 must not be able
    # to put an out-of-specification reading in without anybody looking.
    suggestions = []
    tables = []
    try:
        import json

        from ..services.record_extraction import suggest_values
        from ..services.paddle_ocr import StructuredDocument, Region

        if document.layout_json:
            raw = json.loads(document.layout_json)
            recovered = StructuredDocument(
                regions=[Region(**{k: (tuple(v) if k == "bbox" else v)
                                   for k, v in r.items()}) for r in raw["regions"]],
                pages=raw.get("pages", 1),
                engine=raw.get("engine", "paddle"),
                mean_confidence=raw.get("mean_confidence"),
            )
            tables = [t.html for t in recovered.tables]
            suggestions = [s.to_dict() for s in
                           suggest_values(recovered, list(record.values))]
    except Exception as exc:
        logger.warning(f"Could not read the sheet's structure: {exc}")

    return {
        "record": RecordPresenter.record_json(
            db, record, current_user, detail=True
        ),
        "document_id": document.id,
        "ocr_status": document.ocr_status,
        "ocr_engine": document.ocr_engine,
        "ocr_confidence": document.ocr_confidence,
        # What the OCR read, so the readings can be transferred without
        # retyping the sheet. Capped: this goes into a textarea, not a file.
        "text": (document.full_text or "")[:20000],
        # The tables it recovered, still tables.
        "tables": tables,
        # And what those tables appear to say for each field on this record.
        "suggestions": suggestions,
    }


# ------------------------------------------------------- B3/B4: submit it


@router.post("/{record_id}/submit")
def submit_record(record_id: str, payload: SubmitPayload,
                  db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user_flexible)):
    """
    Close filling and open the approval chain built from the format.

    Fires the chart's first trigger to the Process Owner, and - if anything was
    out of specification - the N-ok flag to the Overall Process Owner at the
    same moment rather than when the chain eventually reaches them.
    """
    record = _load(db, record_id)
    if not RecordAccessPolicy.permissions(record, current_user).get("submit"):
        raise HTTPException(
            status_code=403,
            detail="Only this format's Process Owner may submit the record.")

    document = None
    if payload.document_id:
        document = db.query(Document).filter(
            Document.id == payload.document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="That document was not found.")
        # this record's own hard copy, or an upload nothing uses yet - never another
        # record's document: its approval would move onto this record and strand it
        owner = recs.by_document(db, document.id)
        in_use = db.query(ApprovalWorkflow.id).filter(ApprovalWorkflow.document_id == document.id).first()
        if (owner is not None and owner.id != record.id) or (owner is None and in_use):
            raise HTTPException(
                status_code=400,
                detail="That document is not this record's hard copy. Attach the scan to this "
                       "record first.")

    try:
        record = recs.submit(db, record, current_user, document=document,
                     approval_overrides=payload.approval_overrides)
    except (recs.RecordError, wf.WorkflowError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    log_audit_event(db, current_user.id, "record.submitted", "record", record.id,
                    {"observation": record.observation_status})
    return RecordPresenter.record_json(db, record, current_user, detail=True)


# ----------------------------------------------------------- B5: the flag


@router.post("/{record_id}/nok/clear")
def clear_nok(record_id: str, payload: NokPayload,
              db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user_flexible)):
    """
    The Overall Process Owner records the action taken on an N-ok observation.

    Until this happens the record stays red and cannot be filed, because the
    chart raises the flag "for further action" and filing it unactioned would
    bury exactly the thing the flag exists to surface.
    """
    record = _load(db, record_id)
    try:
        record = recs.clear_nok_flag(db, record, current_user, payload.note)
    except recs.RecordError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    log_audit_event(db, current_user.id, "record.nok_cleared", "record", record.id,
                    {"note": payload.note})
    return RecordPresenter.record_json(db, record, current_user, detail=True)


# ------------------------------------------------------ D1 "No": reverify


@router.post("/{record_id}/reverify")
def send_back(record_id: str, payload: ReverifyPayload,
              db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user_flexible)):
    """
    The chart's "No" branch: back to the CFT, not out of the process.

    Also reachable by rejecting the final decision through the workflow API,
    which routes here. Both doors lead to the same room deliberately - an
    approver rejecting from My Tasks must get the loop, not a dead end.
    """
    record = _load(db, record_id)
    try:
        record = recs.send_back_for_reverification(
            db, record, current_user, payload.reason)
    except recs.RecordError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    log_audit_event(db, current_user.id, "record.reverify", "record", record.id,
                    {"reason": payload.reason, "round": record.reverify_count})
    return RecordPresenter.record_json(db, record, current_user, detail=True)


@router.post("/{record_id}/return")
def return_for_correction(record_id: str, payload: ReturnPayload,
                          db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user_flexible)):
    """
    B4 - the record was not within specification condition, so it goes back.

    The chart draws no exit that discards a record. Returning it unlocks the
    readings and lets the same record be corrected and resubmitted, rather than
    forcing somebody to raise a second one for the same period.
    """
    record = _load(db, record_id)
    try:
        record = recs.return_for_correction(db, record, current_user, payload.reason)
    except recs.RecordError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    log_audit_event(db, current_user.id, "record.returned", "record", record.id,
                    {"reason": payload.reason})
    return RecordPresenter.record_json(db, record, current_user, detail=True)


@router.post("/{record_id}/cft-opinion")
def cft_opinion(record_id: str, payload: OpinionPayload,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user_flexible)):
    """
    B6 - a CFT member's answer on the joint review.

    An objection is recorded and carried to the final decision rather than
    ending the process: the chart has one decision point, and this is not it.
    """
    record = _load(db, record_id)
    try:
        record = recs.record_cft_opinion(
            db, record, current_user, agrees=payload.agrees, comment=payload.comment)
    except recs.RecordError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    log_audit_event(db, current_user.id,
                    "record.cft_agreed" if payload.agrees else "record.cft_objected",
                    "record", record.id, {"comment": payload.comment})
    return RecordPresenter.record_json(db, record, current_user, detail=True)


# ------------------------------------------------------------ B8: store it


@router.post("/{record_id}/store")
def store_record(record_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user_flexible)):
    """
    B8 - file the approved record into its date- or month-wise folder.

    The folder chain is created on demand from the format's frequency, so
    nobody maintains a folder tree by hand and a new year needs no setup.
    """
    record = _load(db, record_id)
    try:
        record = recs.store(db, record, current_user)
    except recs.RecordError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    log_audit_event(db, current_user.id, "record.stored", "record", record.id,
                    {"path": record.storage_path})
    return RecordPresenter.record_json(db, record, current_user, detail=True)


# ------------------------------------------------------------ the storage view


@router.get("/storage/tree")
def storage_tree(db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user_flexible),
                 team_id: Optional[str] = Query(None)):
    """
    Everything filed on the server, grouped the way it was filed (B8).

    Built from the records rather than by walking the folder table, so the view
    always matches what the process actually did.
    """
    stored = recs.list_records(
        db, team_id=team_id, stage=recs.STAGE_STORED, limit=1000)

    tree: dict[str, dict] = {}
    for record in stored:
        path = record.storage_path or "Unfiled"
        node = tree.setdefault(path, {"path": path, "records": []})
        node["records"].append({
            "id": record.id,
            "number": record.number,
            "format": record.format.code if record.format else None,
            "period": record.period_label,
            "observation": record.observation_status,
            "rag": record.rag_status,
            "stored_at": record.stored_at,
            "stored_by": RecordPresenter.person(record.storer),
            "document_id": record.document_id,
        })

    return {
        "folders": sorted(tree.values(), key=lambda n: n["path"]),
        "total": len(stored),
    }


# ---------------------------------------------------------- notifications


@router.get("/notifications/mine")
def my_notifications(db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user_flexible),
                     unread_only: bool = Query(False),
                     limit: int = Query(50, ge=1, le=200)):
    """
    The triggers addressed to this person, in the product as well as by email.

    The chart asks for email. Showing the same triggers here costs nothing and
    means the process still moves on a day the mail server is down.
    """
    rows = notify.for_user(db, current_user, limit=limit, unread_only=unread_only)
    return {
        "notifications": [
            {
                "id": n.id, "kind": n.kind, "subject": n.subject, "body": n.body,
                "related_type": n.related_type, "related_id": n.related_id,
                "status": n.status, "read": n.read_at is not None,
                "created_at": n.created_at, "sent_at": n.sent_at,
            }
            for n in rows
        ],
        "unread": notify.unread_count(db, current_user),
    }


@router.get("/{record_id}/sheet")
def record_sheet(record_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user_flexible)):
    """
    The finished record: the form as designed, filled in, and signed.

    One request rather than three, because a printed record whose readings and
    whose signatures came from different fetches could disagree with itself
    between sections - and a quality record that contradicts itself is worth
    less than none.

    Signatures come from the approval steps, never from anything typed into the
    form. The image, the name and the designation are all frozen at the moment
    of signing: somebody who signed as Head of Process Quality keeps saying so
    after they move on.
    """
    from ..models import ApprovalStep, Signature

    record = _load(db, record_id)
    fmt = record.format

    steps = []
    workflow = record.workflow
    current_step = None
    if workflow:
        for step in sorted(workflow.steps or [], key=lambda s: s.order_index or 0):
            signature = None
            if step.signature_id:
                row = (db.query(Signature)
                       .filter(Signature.id == step.signature_id).first())
                if row:
                    signature = {
                        "name": row.name,
                        "designation": row.designation,
                        "data_url": row.data_url,
                        "signed_at": row.signed_at,
                    }

            decided_by = None
            if step.decided_by:
                person = db.query(User).filter(User.id == step.decided_by).first()
                if person:
                    decided_by = person.full_name or person.username

            assigned_to = wf.outstanding(step) or list(step.assignees or [])
            if step.status == wf.CURRENT:
                current_step = step

            steps.append({
                "name": step.name,
                "order": (step.order_index or 0) + 1,
                "status": step.status,
                "requires_signature": bool(step.requires_signature),
                "stage": step.qms_stage,
                "department": step.department,
                "role": step.role,
                "approval_mode": step.approval_mode or "any",
                "assigned_to": [
                    RecordPresenter.person(person) for person in assigned_to
                ],
                "due_date": step.due_date,
                "overdue": wf.is_overdue(step),
                "approved_by": [
                    RecordPresenter.person(decision.user)
                    for decision in (step.decisions or [])
                    if decision.action == "approved"
                ],
                "decided_by": decided_by,
                "decided_at": step.decided_at,
                "comment": step.comment,
                "reason": step.reason,
                "signature": signature,
            })

    current_assignees = (
        wf.outstanding(current_step) or list(current_step.assignees or [])
        if current_step else []
    )
    submission_event = next(
        (event for event in reversed(record.events or [])
         if event.kind == "submitted"),
        None,
    )
    values = record.values or []
    total_items = len(values)
    completed_items = sum(
        1 for value in values
        if value.value is not None and str(value.value).strip()
    )
    document = record.document

    return {
        "record": {
            "id": record.id,
            "number": record.number,
            "entry_mode": record.entry_mode,
            "period": record.period_label,
            "stage": record.stage,
            "observation": record.observation_status,
            "nok_summary": record.nok_summary,
            "rag": record.rag_status,
            "filled_by": (record.filler.full_name or record.filler.username)
                         if record.filler else None,
            "filled_at": record.filled_at,
            "submitted_at": record.submitted_at,
            "stored_at": record.stored_at,
            "storage_path": record.storage_path,
            "document_id": record.document_id,
            "format_revision": record.format_revision,
            "total_items": total_items,
            "completed_items": completed_items,
        },
        "format": {
            "code": fmt.code,
            "title": fmt.title,
            "work_instruction_ref": fmt.work_instruction_ref,
            "team": record.team.name if record.team else None,
        } if fmt else None,
        "document": {
            "id": document.id,
            "title": document.title or document.original_filename or document.filename,
            "filename": document.original_filename or document.filename,
            "document_type": document.doctype.name if document.doctype else None,
            "file_size": document.file_size,
            "mime_type": document.mime_type,
            "created_at": document.created_at,
            "preview_info_url": f"/api/documents/{document.id}/preview-info",
            "file_url": f"/api/documents/{document.id}/file",
            "download_url": f"/api/documents/{document.id}/download",
        } if document else None,
        "approval": {
            "workflow_id": workflow.id,
            "status": workflow.status,
            "priority": workflow.priority,
            "submitted_by": RecordPresenter.person(
                submission_event.actor if submission_event else record.filler
            ),
            "submitted_at": record.submitted_at or workflow.started_at,
            "current_step": current_step.name if current_step else None,
            "assigned_to": [
                RecordPresenter.person(person) for person in current_assignees
            ],
            "progress": {
                "completed": sum(1 for step in steps if step["status"] == wf.APPROVED),
                "total": len(steps),
            },
        } if workflow else None,
        # The sheet as it was designed. Empty for a template built before the
        # designer existed, and the page falls back to a plain table.
        "layout": layouts.parse(fmt.layout) if fmt else [],
        "values": [
            {
                "id": value.id,
                "label": value.label,
                "value": value.value,
                "unit": value.unit,
                "specification": (
                    value.spec_text
                    or RecordPresenter.specification_label(value)
                ),
                "in_spec": value.in_spec,
                "remark": value.remark,
            }
            for value in sorted(values, key=lambda v: v.order_index or 0)
        ],
        "approvals": steps,
    }


@router.post("/{record_id}/refresh-generated-evidence")
def refresh_generated_evidence(
    record_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Repair an old digital evidence PDF only when it contains the old blank marker."""
    import re

    from PyPDF2 import PdfReader
    from ..services.evidence_service import generated_sheet

    record = _load(db, record_id)
    if record.entry_mode != "digital" or not record.document_id:
        return {"document_id": record.document_id, "refreshed": False}

    old_document = db.query(Document).filter(
        Document.id == record.document_id
    ).first()
    if not old_document or not old_document.file_path:
        return {"document_id": record.document_id, "refreshed": False}

    evidence_folder = (
        Path(get_settings(db).storage_folder) / "evidence" / "generated"
    ).resolve()
    old_path = Path(old_document.file_path).resolve()
    try:
        old_path.relative_to(evidence_folder)
    except ValueError:
        return {"document_id": record.document_id, "refreshed": False}

    if old_path.suffix.lower() != ".pdf" or not old_path.is_file():
        return {"document_id": record.document_id, "refreshed": False}

    try:
        old_text = "\n".join(page.extract_text() or "" for page in PdfReader(str(old_path)).pages)
    except Exception as exc:
        logger.warning(f"Could not inspect generated evidence for {record.number}: {exc}")
        return {"document_id": record.document_id, "refreshed": False}

    if "&nbsp;" not in re.sub(r"\s+", "", old_text):
        return {"document_id": record.document_id, "refreshed": False}

    new_document = generated_sheet(db, record)
    record.document_id = new_document.id
    db.commit()
    db.refresh(record)
    log_audit_event(
        db,
        current_user.id,
        "record.evidence_refreshed",
        "record",
        record.id,
        {"old_document_id": old_document.id, "new_document_id": new_document.id},
    )
    return {"document_id": new_document.id, "refreshed": True}


@router.get("/notifications/outbox")
def notification_outbox(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
    limit: int = Query(60, ge=1, le=300),
):
    """
    Every trigger the system has written, newest first.

    Administrators only: the bodies carry single-use approval links addressed to
    other people, and a list of everybody's links is not something to hand round.

    `status` is the honest answer about delivery - "sent" when a mail server
    took it, "skipped" when none is configured, "failed" with the reason when
    one refused it. On an installation without SMTP every row reads "skipped",
    and the link inside the body still works.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="The outbox is for administrators. Your own notifications are "
                   "on your approvals screen.")

    from ..models_qms import Notification

    rows = (
        db.query(Notification)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "mail_configured": bool(get_settings(db).mail_available),
        "notifications": [
            {
                "id": n.id,
                "kind": n.kind,
                "subject": n.subject,
                "body": n.body,
                "to_email": n.to_email or (n.recipient.email if n.recipient else None),
                "to_name": (n.recipient.full_name or n.recipient.username)
                           if n.recipient else None,
                "status": n.status,
                "error": n.error,
                "related_type": n.related_type,
                "related_id": n.related_id,
                "created_at": n.created_at,
                "sent_at": n.sent_at,
            }
            for n in rows
        ],
    }


class MarkReadPayload(BaseModel):
    ids: Optional[list[str]] = None  # none: every notification


@router.post("/notifications/read")
def mark_notifications_read(payload: MarkReadPayload, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user_flexible)):
    ids = payload.ids or None
    changed = notify.mark_read(db, current_user, ids)
    return {"marked": changed, "unread": notify.unread_count(db, current_user)}
