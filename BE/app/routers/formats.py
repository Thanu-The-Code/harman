"""
The format library API - B1 of the client's record process flow.

Blank formats, the quality teams that own them, the four responsibilities named
on each, and the specification limits that decide ok from N-ok. The rules live
in `format_service`; this layer validates input, shapes output and enforces who
may call what.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Role, User
from ..models_qms import FREQUENCIES, Format, FormatReview, QualityTeam
from ..services import approval_route as routes
from ..services import form_layout as layouts
from ..services import format_service as fmts
from ..services import template_folder_service as folder_service
from ..services.audit_service import log_audit_event
from ..services.auth_service import (
    get_current_user_flexible,
    require_admin_flexible,
)
from ..services.resource_library_service import ResourceLibraryService
from ..services.template_repository_service import TemplateRepositoryService

router = APIRouter()


# ---------------------------------------------------------------- payloads


class FieldPayload(BaseModel):
    """Validate one data-entry field and its measurement specifications."""

    label: str = Field(max_length=200)
    field_type: str = "text"
    unit: Optional[str] = None
    spec_min: Optional[float] = None
    spec_max: Optional[float] = None
    spec_text: Optional[str] = None
    options: Optional[list[str]] = None
    required: bool = True
    help_text: Optional[str] = None


class FormatPayload(BaseModel):
    """Validate the data required to create a form template."""

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "examples": [{
                "code": "QF-PQ-001",
                "title": "In-process dimensional check",
                "frequency": "daily",
                "storage_path": "Teams",
                "fields": [{"label": "Bore diameter", "field_type": "number"}],
            }]
        },
    )

    # blank: the team's next code (format_service.next_code)
    code: str = Field(default="", max_length=60)
    title: str = Field(max_length=200)
    description: Optional[str] = None
    frequency: str = Field(..., examples=["daily"])
    fields: list[FieldPayload] = Field(default_factory=list)
    layout: Optional[list[dict]] = None
    work_instruction_ref: Optional[str] = None
    work_instruction: Optional[str] = None
    storage_path: Optional[str] = None


class FormatUpdatePayload(BaseModel):
    """Validate the editable fields supplied when updating a template."""

    approval_route: Optional[list[dict]] = None
    layout: Optional[list[dict]] = None
    code: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    team_id: Optional[str] = None
    frequency: Optional[str] = None
    work_instruction_ref: Optional[str] = None
    work_instruction: Optional[str] = None
    storage_path: Optional[str] = None
    cft_target_days: Optional[int] = None
    process_owner_id: Optional[str] = None
    overall_process_owner_id: Optional[str] = None
    qms_coordinator_id: Optional[str] = None
    cft_member_ids: Optional[list[str]] = None
    fields: Optional[list[FieldPayload]] = None


class FormatReviewStepPayload(BaseModel):
    """One ordered template-approval step and the people assigned to it."""

    name: str = Field(
        description="Display name for this approval step.",
        examples=["Process Owner approval"],
    )
    reviewer_ids: list[str] = Field(
        description="User IDs of active users allowed to approve.",
        examples=[["user-id-1", "user-id-2"]],
    )
    mode: Literal["any", "all"] = Field(
        default="any",
        description="'any' requires one assigned reviewer; 'all' requires every reviewer.",
        examples=["all"],
    )
    role_id: Optional[str] = None
    due_days: Optional[int] = Field(default=None, ge=1, le=365)


class FormatReviewPayload(BaseModel):
    """Ordered approval steps sent when submitting a draft template for review."""

    steps: list[FormatReviewStepPayload] = Field(
        min_length=1,
        max_length=12,
        description="Approval steps run in order, from first reviewer to final reviewer.",
    )
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


class FormatReviewDecisionPayload(BaseModel):
    """Validate an approval decision and its optional reviewer comment."""

    decision: str
    comment: Optional[str] = Field(default=None, max_length=2000)


class TeamPayload(BaseModel):
    """Validate the identifying and descriptive information for a team."""

    code: str = Field(max_length=20)
    name: str = Field(max_length=120)
    description: Optional[str] = None


class TemplateFolderPayload(BaseModel):
    """Validate a new Template Repo folder and its optional parent."""

    name: str = Field(min_length=1, max_length=100)
    parent_path: Optional[str] = Field(default=None, max_length=500)


def require_formats_read_permission(user: User) -> User:
    """Allow administrators and users with template-read access."""
    if user.is_admin or user.has_permission("formats.read"):
        return user
    raise HTTPException(status_code=403, detail="Permission denied: formats.read")


def require_formats_manage_permission(user: User) -> User:
    """Allow administrators and users with template-management access."""
    if user.is_admin or user.has_permission("formats.manage"):
        return user
    raise HTTPException(status_code=403, detail="Permission denied: formats.manage")


# ----------------------------------------------------------- serialisation


def _person(user: Optional[User]) -> Optional[dict]:
    """Serialize a user into the compact person shape used by format responses."""
    if not user:
        return None
    return {
        "id": user.id,
        "name": user.full_name or user.username,
        "email": user.email,
        "job_title": user.job_title,
        "department": user.department,
    }


def _field_json(field) -> dict:
    """Serialize a template field, including its decoded choices and spec label."""
    import json
    options = None
    if field.options:
        try:
            options = json.loads(field.options)
        except (ValueError, TypeError):
            options = None
    return {
        "id": field.id,
        "order": field.order_index,
        "layout_key": field.layout_key,
        "label": field.label,
        "field_type": field.field_type,
        "unit": field.unit,
        "spec_min": field.spec_min,
        "spec_max": field.spec_max,
        "spec_text": field.spec_text,
        "options": options,
        "required": bool(field.required),
        "help_text": field.help_text,
        # Rendered once, here, so the fill screen and the emails describe a
        # limit the same way.
        "spec_label": _spec_label(field),
    }


def _spec_label(field) -> str:
    """Build the human-readable specification text shown beside a field."""
    if field.spec_text:
        return f"must be {field.spec_text}"
    if field.spec_min is not None and field.spec_max is not None:
        return f"{field.spec_min:g} to {field.spec_max:g}" + (f" {field.unit}" if field.unit else "")
    if field.spec_min is not None:
        return f"min {field.spec_min:g}" + (f" {field.unit}" if field.unit else "")
    if field.spec_max is not None:
        return f"max {field.spec_max:g}" + (f" {field.unit}" if field.unit else "")
    return ""


def _format_json(db: Session, fmt: Format, *, detail: bool = False) -> dict:
    """Serialize a template and optionally include its fields and record count."""
    data = {
        "id": fmt.id,
        "code": fmt.code,
        "title": fmt.title,
        "description": fmt.description,
        "team": {"id": fmt.team.id, "code": fmt.team.code, "name": fmt.team.name}
        if fmt.team else None,
        "frequency": fmt.frequency,
        "frequency_label": fmts.FREQUENCY_LABELS.get(fmt.frequency, fmt.frequency),
        "revision": fmt.revision,
        "revision_of": fmt.revision_of,
        "status": fmt.status,
        "approval_status": next(
            (review.status for review in reversed(fmt.reviews)
             if review.status in ("pending", "rejected")),
            None,
        ),
        "effective_date": fmt.effective_date,
        "work_instruction_ref": fmt.work_instruction_ref,
        "work_instruction": fmt.work_instruction,
        "storage_path": fmt.storage_path,
        "folder_path": fmt.storage_path,
        "storage_preview": " / ".join(fmts.full_storage_path(fmt)),
        "cft_target_days": fmt.cft_target_days,
        "process_owner": _person(fmt.process_owner),
        "overall_process_owner": _person(fmt.overall_process_owner),
        "qms_coordinator": _person(fmt.qms_coordinator),
        "cft_members": [_person(m) for m in fmt.cft_members],
        # The route in force, with each step told who it will actually reach.
        # `is_default` says whether that is the process document's own chain,
        # so the editor can show "following the standard process" rather than
        # four steps somebody might think they configured.
        "approval_route": [
            {**step, "reaches": routes.describe(step, fmt)}
            for step in routes.parse(fmt.approval_route, fmt.cft_target_days)
        ],
        "route_is_default": not fmt.approval_route,
        "layout": layouts.parse(fmt.layout),
        "has_blank": bool(fmt.blank_file_path),
        # Carried so a screen showing the blank in place knows whether to draw
        # it as a picture or as a page, without fetching it to find out.
        "blank_mime": fmt.blank_mime_type,
        "field_count": len(fmt.fields),
        "created_at": fmt.created_at,
        # The Template Builder's "Last Update"; a template never edited was last updated when created.
        "updated_at": fmt.updated_at or fmt.created_at,
        # What still has to be true before it may be released. Empty on an
        # active format.
        "readiness": fmts.readiness(fmt),
    }
    if detail:
        data["fields"] = [_field_json(f) for f in fmt.fields]
        data["record_count"] = fmts.record_count(db, fmt)
    return data


# -------------------------------------------------------------------- teams


@router.get("/starter-layout")
def starter_layout(current_user: User = Depends(require_admin_flexible)):
    """
    A form to start from, shaped like the inspection sheets this replaces.

    The designer opens on this for a template that has never been designed. It
    is a working sheet rather than an empty canvas because the first question
    anybody has in front of a blank designer is what the thing is meant to look
    like - and on a shop floor the answer is nearly always a letterhead, job
    details, a ruled table of characteristics, observations, and signatures.
    """
    from ..services import form_layout as layouts

    return {"layout": layouts.starter()}


@router.get("/next-code")
def next_format_code(team_id: Optional[str] = Query(default=None),
                     db: Session = Depends(get_db),
                     current_user: User = Depends(require_admin_flexible)):
    """The code a new template of this team gets when none is given (Create Template shows it)."""
    return {"code": fmts.next_code(db, team_id)}


@router.get("/stats")
def format_stats(db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user_flexible)):
    """
    Counts for work in progress on the Doc Builder.

    On Verification is a template with a pending approval run. Change Request
    is a draft whose latest review was rejected. Draft is a draft with no
    rejected approval run. Published and historical revisions are excluded.
    """
    everything = db.query(Format).all()

    published = sum(1 for f in everything if f.status == fmts.ACTIVE)
    drafts = [f for f in everything if f.status == "draft"]
    rejected_format_ids = {
        row[0] for row in db.query(FormatReview.format_id)
        .filter(FormatReview.status == "rejected").distinct().all()
    }
    change_requests = sum(1 for f in drafts if f.id in rejected_format_ids)
    pending_approval = sum(1 for f in everything if f.status == "in_review")
    draft_count = len(drafts) - change_requests

    return {
        "total": draft_count + change_requests + pending_approval,
        "published": published,
        "in_approval": pending_approval,
        "on_verification": pending_approval,
        "change_request": change_requests,
        "draft": draft_count,
    }


@router.get("/teams", tags=["People & Teams"])
def list_teams(db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user_flexible)):
    """
    The quality teams, the people on each, and what each team owns.

    Everything the People & Teams screen needs, in one request. The people are
    included because the question that screen exists to answer is "who is on
    this team and what may they do", not "how many templates does it own".
    """
    fmts.ensure_teams(db)
    teams = db.query(QualityTeam).order_by(QualityTeam.code).all()

    everybody = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.full_name, User.username)
        .all()
    )
    by_team: dict[str, list[User]] = {}
    for person in everybody:
        by_team.setdefault(person.quality_team_id or "", []).append(person)

    def described(person: User) -> dict:
        """Return the person fields needed by the People & Teams screen."""
        return {
            "id": person.id,
            "name": person.full_name or person.username,
            "username": person.username,
            "email": person.email,
            "job_title": person.job_title,
            "department": person.department,
            "can_approve": bool(person.can_approve or person.is_admin),
            "can_sign": bool(person.can_sign or person.is_admin),
            "is_admin": bool(person.is_admin),
        }

    return {
        "teams": [
            {
                "id": t.id, "code": t.code, "name": t.name,
                "description": t.description, "is_active": bool(t.is_active),
                "format_count": db.query(Format).filter(
                    Format.team_id == t.id,
                    Format.status.in_([fmts.DRAFT, fmts.ACTIVE]),
                ).count(),
                "people": [described(p) for p in by_team.get(t.id, [])],
            }
            for t in teams
        ],
        # People who belong to no team - administrators, and anyone who only
        # ever sits on a cross-functional review. They are shown separately
        # rather than hidden, because "not on a team" is a real answer.
        "unassigned": [described(p) for p in by_team.get("", [])],
    }


@router.post(
    "/teams",
    tags=["People & Teams"],
    dependencies=[Depends(require_admin_flexible)],
)
def create_team(payload: TeamPayload, db: Session = Depends(get_db)):
    """Create a team after normalizing its code and checking uniqueness."""
    code = payload.code.strip().upper()
    if db.query(QualityTeam).filter(QualityTeam.code == code).first():
        raise HTTPException(status_code=400, detail=f"Team {code} already exists.")
    team = QualityTeam(code=code, name=payload.name.strip(),
                       description=(payload.description or "").strip() or None)
    db.add(team)
    db.commit()
    db.refresh(team)
    return {"id": team.id, "code": team.code, "name": team.name}


@router.put(
    "/teams/{team_id}",
    tags=["People & Teams"],
    dependencies=[Depends(require_admin_flexible)],
)
def update_team(team_id: str, payload: TeamPayload, db: Session = Depends(get_db)):
    """Rename a team, or change what it is for."""
    team = db.query(QualityTeam).filter(QualityTeam.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="That team does not exist.")

    code = payload.code.strip().upper()
    clash = db.query(QualityTeam).filter(
        QualityTeam.code == code, QualityTeam.id != team_id).first()
    if clash:
        raise HTTPException(status_code=400, detail=f"Team {code} already exists.")

    team.code = code
    team.name = payload.name.strip()
    team.description = (payload.description or "").strip() or None
    db.commit()
    db.refresh(team)
    return {"id": team.id, "code": team.code, "name": team.name}


@router.post(
    "/teams/{team_id}/retire",
    tags=["People & Teams"],
    dependencies=[Depends(require_admin_flexible)],
)
def retire_team(team_id: str, db: Session = Depends(get_db)):
    """
    Take a team out of use without deleting it.

    Deleting is not offered. A team that has ever owned a format is named on
    every record raised against it, and removing the row would leave those
    records - which are the evidence somebody may be audited on - pointing at
    nothing. Retiring hides it from the pickers and leaves the history intact.
    """
    team = db.query(QualityTeam).filter(QualityTeam.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="That team does not exist.")

    live = db.query(Format).filter(
        Format.team_id == team_id,
        Format.status.in_([fmts.DRAFT, fmts.ACTIVE]),
    ).count()
    if live:
        raise HTTPException(
            status_code=400,
            detail=(f"{team.name} still owns {live} form template(s) in use. "
                    "Withdraw or move them first."))

    team.is_active = False
    db.commit()
    return {"id": team.id, "is_active": False}


@router.post(
    "/teams/{team_id}/restore",
    tags=["People & Teams"],
    dependencies=[Depends(require_admin_flexible)],
)
def restore_team(team_id: str, db: Session = Depends(get_db)):
    """Put a retired team back into use."""
    team = db.query(QualityTeam).filter(QualityTeam.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="That team does not exist.")
    team.is_active = True
    db.commit()
    return {"id": team.id, "is_active": True}


# ------------------------------------------------------------------ formats


@router.get("")
@router.get("/", include_in_schema=False)
def list_formats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
    team_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    q: str = Query("", max_length=120),
    mine: bool = Query(False, description="Only formats I am the Process Owner of"),
    tab: Optional[str] = Query(None),
):
    """List all revisions to administrators and released formats to others."""
    fmts.ensure_teams(db)
    if current_user.is_admin and tab is not None:
        latest = [versions[-1] for versions in fmts.revision_groups(db)]
        rejected_ids = {
            row[0]
            for row in db.query(FormatReview.format_id)
            .filter(FormatReview.status == "rejected")
            .distinct()
            .all()
        }
        summary = {
            "total_document": 0,
            "on_verification": 0,
            "change_request": 0,
            "draft": 0,
            "published": sum(1 for fmt in latest if fmt.status == fmts.ACTIVE),
        }
        builder_formats = []
        for fmt in latest:
            if fmt.status == "in_review":
                builder_status = "on_verification"
            elif fmt.status == fmts.DRAFT and fmt.id in rejected_ids:
                builder_status = "change_request"
            elif fmt.status == fmts.DRAFT:
                builder_status = "draft"
            else:
                continue
            summary[builder_status] += 1
            if (
                (not team_id or fmt.team_id == team_id)
                and (not mine or fmt.process_owner_id == current_user.id)
                and (
                    not q
                    or q.casefold() in fmt.code.casefold()
                    or q.casefold() in fmt.title.casefold()
                )
            ):
                builder_formats.append(
                    {**_format_json(db, fmt), "builder_status": builder_status}
                )

        summary["total_document"] = (
            summary["on_verification"] + summary["change_request"] + summary["draft"]
        )
        if tab == "draft":
            builder_formats = [
                item for item in builder_formats
                if item["builder_status"] == "draft"
            ]
        elif tab == "on_verification":
            builder_formats = [
                item for item in builder_formats
                if item["builder_status"] == "on_verification"
            ]
        elif tab == "change_request":
            builder_formats = [
                item for item in builder_formats
                if item["builder_status"] == "change_request"
            ]
        elif tab != "all":
            raise HTTPException(status_code=422, detail="Unknown template builder tab.")
        return {
            "formats": builder_formats,
            "frequencies": [
                {
                    "value": frequency,
                    "label": fmts.FREQUENCY_LABELS.get(frequency, frequency),
                }
                for frequency in FREQUENCIES
            ],
            "summary": summary,
            "total": len(builder_formats),
        }

    formats = ResourceLibraryService(db).list_for_user(
        current_user,
        team_id=team_id,
        status=status,
        query=q,
        mine=mine,
    )
    return {
        "formats": [_format_json(db, f) for f in formats],
        "frequencies": [
            {"value": f, "label": fmts.FREQUENCY_LABELS.get(f, f)} for f in FREQUENCIES
        ],
    }


@router.get("/callable")
def callable_formats(db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user_flexible)):
    """
    The formats this person may call and fill (B2).

    Each carries whether a record already exists for the current period, so the
    fill screen can warn before somebody duplicates a check rather than after.
    """
    out = []
    for fmt in fmts.callable_by(db, current_user):
        period = fmts.period_for(fmt.frequency)
        existing = fmts.existing_for_period(db, fmt, period["key"])
        data = _format_json(db, fmt, detail=True)
        data["period"] = {"key": period["key"], "label": period["label"]}
        data["existing_for_period"] = (
            {
                "id": existing.id,
                "number": existing.number,
                "stage": existing.stage,
                "rag": existing.rag_status,
            } if existing else None
        )
        out.append(data)
    return {"formats": out}


@router.get("/people")
def eligible_people_list(db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user_flexible)):
    """
    Who may be appointed to each responsibility, for the pickers on the editor.

    Declared before /{format_id} on purpose: routes are matched in order, and
    otherwise "people" would be read as a format id.

    A step that must be signed cannot be given to somebody who may not sign, so
    the two approval responsibilities are filtered to people who can. The choice
    is made from a list that cannot produce a stuck chain.
    """
    people = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.full_name, User.username)
        .all()
    )
    signers = [p for p in people if p.can_sign or p.is_admin]
    approvers = [p for p in people if p.can_approve or p.is_admin]
    return {
        "process_owner": [_person(p) for p in signers],
        "overall_process_owner": [_person(p) for p in signers],
        "cft_members": [_person(p) for p in approvers],
        "qms_coordinator": [_person(p) for p in approvers],
    }


@router.get("/repository", dependencies=[Depends(require_admin_flexible)])
def format_repository(db: Session = Depends(get_db)):
    """Return templates grouped with all revisions for the admin frontend."""
    repository = TemplateRepositoryService(db).list_templates()
    folders = folder_service.list_folder_tree(db)

    def add_template_lists(nodes: list[dict]) -> None:
        for node in nodes:
            node["templates"] = []
            add_template_lists(node["children"])

    add_template_lists(folders)
    folders_by_path = {
        node["path"].casefold(): node
        for root in folders
        for node in _folder_nodes(root)
    }
    for template in repository["templates"]:
        fmt = fmts.get(db, template["id"])
        if fmt is None or not fmt.storage_path:
            continue
        node = folders_by_path.get(fmt.storage_path.casefold())
        if node is not None:
            node["templates"].append({
                "id": fmt.id,
                "code": fmt.code,
                "title": fmt.title,
                "revision": fmt.revision,
                "status": fmt.status,
            })

    return {**repository, "folders": folders}


def _folder_nodes(node: dict):
    """Yield a folder and all descendants for repository indexing."""
    yield node
    for child in node["children"]:
        yield from _folder_nodes(child)


@router.post(
    "/folders",
    dependencies=[Depends(require_admin_flexible)],
)
def create_template_folder(
    payload: TemplateFolderPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Create a folder in the Template Repo."""
    try:
        folder = folder_service.create_folder(
            db,
            payload.name,
            payload.parent_path,
            created_by=current_user.id,
        )
        db.commit()
        db.refresh(folder)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "id": folder.id,
        "name": folder.name,
        "path": folder.path,
        "parent_path": folder.parent_path,
    }


@router.get(
    "/folders",
    dependencies=[Depends(require_admin_flexible)],
)
def list_template_folders(db: Session = Depends(get_db)):
    """Return the Template Repo folder tree."""
    return {"folders": folder_service.list_folder_tree(db)}


@router.get("/approvers")
def eligible_approvers(
    role_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """List active approvers, optionally restricted to users assigned a role."""
    people_query = db.query(User).filter(User.is_active.is_(True))
    if role_id:
        role = db.query(Role).filter(Role.id == role_id).first()
        if role is None:
            raise HTTPException(status_code=404, detail="Role not found.")
        people_query = people_query.filter(User.roles.any(Role.id == role_id))
    else:
        people_query = people_query.filter(
            (User.can_approve.is_(True))
            | (User.can_sign.is_(True))
            | (User.is_admin.is_(True))
        )
    people = people_query.order_by(User.full_name, User.username).all()
    return [_person(person) for person in people]


@router.get("/approvals/mine")
def my_format_approvals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """List pending template-review steps assigned to the current user."""
    reviews = (
        db.query(FormatReview)
        .filter(FormatReview.status == "pending")
        .order_by(FormatReview.created_at.desc())
        .all()
    )
    approvals = []
    for review in reviews:
        state = json.loads(review.steps_json)
        steps = state.get("steps", [])
        if review.current_step >= len(steps):
            continue
        current_step = steps[review.current_step]
        if current_user.id not in current_step["reviewer_ids"]:
            continue
        if any(
            decision["user_id"] == current_user.id
            for decision in current_step.get("decisions", [])
        ):
            continue
        fmt = fmts.get(db, review.format_id)
        if fmt is None:
            continue
        approvals.append({
            "format_id": fmt.id,
            "code": fmt.code,
            "title": fmt.title,
            "review": _format_review_json(db, review, current_user),
        })
    return {"count": len(approvals), "approvals": approvals}


def _is_pending_reviewer(db: Session, fmt: Format, user: User) -> bool:
    """Somebody asked to approve a draft has to be able to read it."""
    for review in db.query(FormatReview).filter(
        FormatReview.format_id == fmt.id,
        FormatReview.status == "pending",
    ).all():
        steps = json.loads(review.steps_json).get("steps", [])
        if any(user.id in step.get("reviewer_ids", []) for step in steps):
            return True
    return False


@router.get("/{format_id}")
def get_format(format_id: str, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user_flexible)):
    """Return one template with its details and previous revision chain."""
    fmt = fmts.get(db, format_id)
    if not fmt:
        raise HTTPException(status_code=404, detail="Format not found")
    if (not current_user.is_admin and fmt.status != fmts.ACTIVE
            and not _is_pending_reviewer(db, fmt, current_user)):
        # historical revisions are for administrators; a link to one (an older
        # notification) is told where the form is now rather than just "not found"
        raise HTTPException(status_code=404, detail=(
            f"{fmt.code} rev {fmt.revision} has been replaced by a newer revision. "
            "Open the current one from the Resources Library."
            if fmt.status == fmts.SUPERSEDED else "Format not found"))

    data = _format_json(db, fmt, detail=True)
    latest_review = db.query(FormatReview).filter(
        FormatReview.format_id == fmt.id,
    ).order_by(FormatReview.created_at.desc()).first()
    data["approval"] = (
        _format_review_json(db, latest_review, current_user)
        if latest_review
        else {"status": "none", "can_act": False, "steps": []}
    )
    if current_user.is_admin:
        # Only administrators can inspect the historical revision chain.
        chain, cursor = [], fmt
        while cursor and cursor.revision_of:
            cursor = fmts.get(db, cursor.revision_of)
            if not cursor:
                break
            chain.append({"id": cursor.id, "revision": cursor.revision,
                          "status": cursor.status, "effective_date": cursor.effective_date})
        data["previous_revisions"] = chain
        for versions in fmts.revision_groups(db):
            if any(version.id == fmt.id for version in versions):
                data["versions"] = []
                for version in reversed(versions):
                    version_data = _format_json(db, version, detail=True)
                    version_review = db.query(FormatReview).filter(
                        FormatReview.format_id == version.id,
                    ).order_by(FormatReview.created_at.desc()).first()
                    version_data["approval"] = (
                        _format_review_json(db, version_review, current_user)
                        if version_review
                        else {"status": "none", "can_act": False, "steps": []}
                    )
                    data["versions"].append(version_data)
                break
    else:
        data["previous_revisions"] = []
    return data


@router.post("", dependencies=[Depends(require_admin_flexible)])
@router.post("/", dependencies=[Depends(require_admin_flexible)],
             include_in_schema=False)
def create_format(payload: FormatPayload, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user_flexible)):
    """Create a template through the format service and return its full details."""
    try:
        fmt = fmts.create_format(db, current_user, payload.model_dump())
    except fmts.FormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _format_json(db, fmt, detail=True)


@router.put("/{format_id}", dependencies=[Depends(require_admin_flexible)])
def update_format(format_id: str, payload: FormatUpdatePayload,
                  db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user_flexible)):
    """Apply supplied changes to a template and return the updated details."""
    fmt = fmts.get(db, format_id)
    if not fmt:
        raise HTTPException(status_code=404, detail="Format not found")
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if payload.fields is not None:
        data["fields"] = [f.model_dump() for f in payload.fields]
    try:
        fmt = fmts.update_format(db, fmt, current_user, data)
    except fmts.FormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _format_json(db, fmt, detail=True)


@router.post("/{format_id}/activate", dependencies=[Depends(require_admin_flexible)])
def activate_format(format_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user_flexible)):
    """Release an approved draft into use."""
    fmt = fmts.get(db, format_id)
    if not fmt:
        raise HTTPException(status_code=404, detail="Format not found")
    approved_review = db.query(FormatReview).filter(
        FormatReview.format_id == format_id,
        FormatReview.status == "approved",
    ).first()
    if fmt.status != fmts.ACTIVE and not approved_review:
        problems = fmts.readiness(fmt)
        if problems:
            raise HTTPException(
                status_code=400,
                detail=f"Format {fmt.code} is not ready to be released:\n- " + "\n- ".join(problems),
            )
        raise HTTPException(status_code=400, detail="Send this template for approval before releasing it.")
    try:
        fmt = fmts.activate(db, fmt, current_user)
    except fmts.FormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _format_json(db, fmt, detail=True)


@router.post(
    "/{format_id}/publish-without-approval",
    dependencies=[Depends(require_admin_flexible)],
)
def publish_format_without_approval(
    format_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Publish a ready draft directly, recording the approval bypass in audit."""
    fmt = fmts.get(db, format_id)
    if not fmt:
        raise HTTPException(status_code=404, detail="Format not found")
    pending_review = db.query(FormatReview).filter(
        FormatReview.format_id == format_id,
        FormatReview.status == "pending",
    ).first()
    if pending_review:
        raise HTTPException(
            status_code=409,
            detail="This template has an approval in progress; finish or reject it first.",
        )
    if fmt.status != fmts.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Only a draft template can be published without approval.",
        )

    try:
        fmt = fmts.activate(db, fmt, current_user)
    except fmts.FormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    log_audit_event(
        db,
        current_user.id,
        "format.published_without_approval",
        "format",
        fmt.id,
        {"code": fmt.code, "revision": fmt.revision, "approval_bypassed": True},
    )
    return {**_format_json(db, fmt, detail=True), "published_without_approval": True}


def _format_review_json(db: Session, review: FormatReview, user: User) -> dict:
    """Serialize a template review, reviewer decisions, and current user's access."""
    state = json.loads(review.steps_json)
    steps = state.get("steps", [])
    current = steps[review.current_step] if review.status == "pending" and review.current_step < len(steps) else None
    people = {
        person.id: person.full_name or person.username
        for person in db.query(User).filter(
            User.id.in_([reviewer_id for step in steps for reviewer_id in step["reviewer_ids"]])
        ).all()
    } if steps else {}
    decision_comments = [
        {
            "step": step["name"],
            "decision": decision["decision"],
            "comment": decision.get("comment"),
            "reviewer": people.get(decision["user_id"], "Former user"),
            "at": decision.get("at"),
        }
        for step in steps
        for decision in step["decisions"]
    ]
    return {
        "id": review.id,
        "format_id": review.format_id,
        "status": review.status,
        "current_step": review.current_step,
        "submitted_by": {
            "id": review.submitter.id,
            "name": review.submitter.full_name or review.submitter.username,
        } if review.submitter else None,
        "submitted_at": review.created_at,
        "completed_at": review.completed_at,
        "priority": state.get("priority", "normal"),
        "can_act": bool(current and user.id in current["reviewer_ids"] and not any(
            decision["user_id"] == user.id for decision in current["decisions"]
        )),
        "decision_comments": decision_comments,
        "steps": [
            {
                "name": step["name"],
                "mode": step["mode"],
                "reviewer_ids": step["reviewer_ids"],
                "role_id": step.get("role_id"),
                "role_name": step.get("role_name"),
                "due_days": step.get("due_days"),
                "reviewers": [people.get(reviewer_id, "Former user") for reviewer_id in step["reviewer_ids"]],
                "decisions": [
                    {
                        **decision,
                        "reviewer": people.get(decision["user_id"], "Former user"),
                    }
                    for decision in step["decisions"]
                ],
            }
            for step in steps
        ],
    }


@router.post("/{format_id}/submit-approval", dependencies=[Depends(require_admin_flexible)])
def submit_format_approval(
    format_id: str,
    payload: FormatReviewPayload = Body(
        ...,
        openapi_examples={
            "process_owner_then_cft": {
                "summary": "Process Owner followed by a joint CFT review",
                "description": (
                    "The Process Owner approves first. Both CFT members must "
                    "approve the second step because its mode is 'all'."
                ),
                "value": {
                    "steps": [
                        {
                            "name": "Process Owner approval",
                            "reviewer_ids": ["process-owner-user-id"],
                            "mode": "any",
                        },
                        {
                            "name": "CFT joint review",
                            "reviewer_ids": ["cft-user-id-1", "cft-user-id-2"],
                            "mode": "all",
                        },
                    ]
                },
            }
        },
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Start template approval after checking readiness and reviewer eligibility."""
    fmt = fmts.get(db, format_id)
    if not fmt:
        raise HTTPException(status_code=404, detail="Format not found")
    if fmt.status != fmts.DRAFT:
        raise HTTPException(status_code=400, detail="Only a draft template can be sent for approval.")
    active_review = db.query(FormatReview).filter(
        FormatReview.format_id == format_id,
        FormatReview.status == "pending",
    ).first()
    if active_review:
        raise HTTPException(status_code=409, detail="This template already has an approval in progress.")

    record_route = routes.parse(fmt.approval_route, fmt.cft_target_days)
    if not any(step.get("requires_signature") for step in record_route):
        # Older builder versions accidentally saved the template-review list as
        # the record route, without a signed final decision. Restore the
        # process-standard route rather than blocking release on that stale UI
        # payload.
        fmt.approval_route = None

    readiness = fmts.readiness(fmt)
    if readiness:
        raise HTTPException(status_code=400, detail="Complete template requirements first:\n- " + "\n- ".join(readiness))

    steps = []
    for index, raw in enumerate(payload.steps):
        name = raw.name.strip()
        reviewer_ids = list(dict.fromkeys(item for item in raw.reviewer_ids if item))
        mode = raw.mode
        if not name or not reviewer_ids or mode not in ("any", "all"):
            raise HTTPException(status_code=400, detail=f"Approval step {index + 1} needs a name and at least one reviewer.")
        people = db.query(User).filter(
            User.id.in_(reviewer_ids), User.is_active.is_(True)
        ).all()
        if len(people) != len(reviewer_ids) or any(
            not (person.can_approve or person.can_sign or person.is_admin)
            for person in people
        ):
            raise HTTPException(status_code=400, detail=f"Approval step '{name}' contains someone who cannot approve.")
        role = None
        if raw.role_id:
            role = db.query(Role).filter(Role.id == raw.role_id).first()
            if role is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Approval step '{name}' references an unknown role.",
                )
            if any(role not in person.roles for person in people):
                raise HTTPException(
                    status_code=400,
                    detail=f"Approval step '{name}' includes someone who does not have the selected role.",
                )
        steps.append({
            "name": name[:120],
            "reviewer_ids": reviewer_ids,
            "mode": mode,
            "decisions": [],
            "role_id": role.id if role else None,
            "role_name": role.name if role else None,
            "due_days": raw.due_days,
        })

    review = FormatReview(
        format_id=fmt.id,
        status="pending",
        steps_json=json.dumps({"steps": steps, "priority": payload.priority}),
        current_step=0,
        submitted_by=current_user.id,
        created_at=datetime.now(timezone.utc),
    )
    fmt.status = "in_review"
    db.add(review)
    db.commit()
    db.refresh(review)

    from ..services.notification_service import notify

    first_reviewers = [
        person for person in db.query(User).filter(User.id.in_(steps[0]["reviewer_ids"])).all()
    ]
    notify(
        db,
        "format.approval.requested",
        to=first_reviewers,
        subject=f"Template approval requested: {fmt.title}",
        body=f"{current_user.full_name or current_user.username} submitted {fmt.code} for template approval.",
        related_type="format",
        related_id=fmt.id,
    )
    log_audit_event(db, current_user.id, "format.approval.submitted", "format", fmt.id,
                    {"review_id": review.id, "steps": len(steps)})
    return _format_review_json(db, review, current_user)


@router.get("/{format_id}/approval")
def get_format_approval(
    format_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Return the latest approval status, including completed decisions/comments."""
    if not fmts.get(db, format_id):
        raise HTTPException(status_code=404, detail="Format not found")
    review = db.query(FormatReview).filter(
        FormatReview.format_id == format_id,
    ).order_by(FormatReview.created_at.desc()).first()
    if not review:
        return {"status": "none", "can_act": False, "steps": []}
    return _format_review_json(db, review, current_user)


@router.get("/{format_id}/approval/history")
def get_format_approval_history(
    format_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Return every approval round for a template, newest first."""
    if not fmts.get(db, format_id):
        raise HTTPException(status_code=404, detail="Format not found")

    reviews = (
        db.query(FormatReview)
        .filter(FormatReview.format_id == format_id)
        .order_by(FormatReview.created_at.desc())
        .all()
    )
    return {
        "format_id": format_id,
        "total": len(reviews),
        "latest_status": reviews[0].status if reviews else "none",
        "reviews": [
            _format_review_json(db, review, current_user)
            for review in reviews
        ],
    }


@router.post("/{format_id}/approval/decision")
def decide_format_approval(
    format_id: str,
    payload: FormatReviewDecisionPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Record the current reviewer’s decision and advance or complete approval."""
    if payload.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Decision must be approve or reject.")
    if payload.decision == "reject" and not (payload.comment or "").strip():
        raise HTTPException(
            status_code=400,
            detail="A rejection must include a comment explaining why.",
        )
    fmt = fmts.get(db, format_id)
    review = db.query(FormatReview).filter(
        FormatReview.format_id == format_id,
        FormatReview.status == "pending",
    ).order_by(FormatReview.created_at.desc()).first()
    if not fmt or not review:
        raise HTTPException(status_code=404, detail="There is no pending template approval.")

    state = json.loads(review.steps_json)
    steps = state["steps"]
    if review.current_step >= len(steps):
        raise HTTPException(status_code=409, detail="This approval is already complete.")
    current = steps[review.current_step]
    if current_user.id not in current["reviewer_ids"]:
        raise HTTPException(status_code=403, detail="This approval step is assigned to someone else.")
    if any(item["user_id"] == current_user.id for item in current["decisions"]):
        raise HTTPException(status_code=409, detail="You have already responded to this step.")

    current["decisions"].append({
        "user_id": current_user.id,
        "decision": payload.decision,
        "comment": (payload.comment or "").strip() or None,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    if payload.decision == "reject":
        review.status = "rejected"
        review.completed_at = datetime.now(timezone.utc)
        fmt.status = fmts.DRAFT
    else:
        step_complete = current["mode"] == "any" or len(current["decisions"]) == len(current["reviewer_ids"])
        if step_complete:
            review.current_step += 1
            if review.current_step == len(steps):
                review.status = "approved"
                review.completed_at = datetime.now(timezone.utc)
                fmt.status = fmts.DRAFT
                try:
                    fmts.activate(db, fmt, current_user)
                except fmts.FormatError as exc:
                    db.rollback()
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

    review.steps_json = json.dumps(state)
    db.commit()
    db.refresh(review)
    log_audit_event(db, current_user.id, f"format.approval.{payload.decision}", "format", fmt.id,
                    {"review_id": review.id, "step": review.current_step + 1,
                     "comment": payload.comment})

    # the author hears the outcome: returned with the reviewer's comment, or released
    if review.status in ("rejected", "approved") and review.submitted_by:
        from ..services.notification_service import notify

        author = db.query(User).filter(User.id == review.submitted_by).first()
        who = current_user.full_name or current_user.username
        if author and author.id != current_user.id:
            notify(
                db,
                "format.approval.rejected" if review.status == "rejected" else "format.released",
                to=author,
                subject=(f"Template returned for changes: {fmt.code} {fmt.title}" if review.status == "rejected"
                         else f"Template released: {fmt.code} rev {fmt.revision} {fmt.title}"),
                body=(f"{who} returned {fmt.code} for changes.\n\nComment: {(payload.comment or '').strip()}"
                      if review.status == "rejected"
                      else f"{who} approved {fmt.code} rev {fmt.revision}. It is released in the Resources Library."),
                related_type="format",
                related_id=fmt.id,
            )

    if review.status == "pending" and review.current_step < len(steps):
        from ..services.notification_service import notify

        next_step = steps[review.current_step]
        next_people = db.query(User).filter(User.id.in_(next_step["reviewer_ids"])).all()
        notify(
            db,
            "format.approval.requested",
            to=next_people,
            subject=f"Template approval requested: {fmt.title}",
            body=f"The previous approval step is complete. Review {fmt.code}: {next_step['name']}.",
            related_type="format",
            related_id=fmt.id,
        )
    return {"review": _format_review_json(db, review, current_user), "format": _format_json(db, fmt, detail=True)}


@router.post("/{format_id}/withdraw", dependencies=[Depends(require_admin_flexible)])
def withdraw_format(format_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user_flexible)):
    """Withdraw a template from use through the format service."""
    fmt = fmts.get(db, format_id)
    if not fmt:
        raise HTTPException(status_code=404, detail="Format not found")
    try:
        fmt = fmts.withdraw(db, fmt, current_user)
    except fmts.FormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _format_json(db, fmt, detail=True)


@router.post("/{format_id}/blank", dependencies=[Depends(require_admin_flexible)])
async def upload_blank(format_id: str, file: UploadFile = File(...),
                       db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user_flexible)):
    """
    Attach the blank form itself (B1) - the PDF or scan people print and fill.

    Held beside the format rather than in the document repository: a blank is
    not a record, and letting it into the repository would put an empty form in
    every search result for the process it belongs to.
    """
    from pathlib import Path

    from ..config import get_settings

    fmt = fmts.get(db, format_id)
    if not fmt:
        raise HTTPException(status_code=404, detail="Format not found")
    if fmt.status not in (fmts.DRAFT, fmts.ACTIVE):
        raise HTTPException(status_code=400,
                            detail=f"Format {fmt.code} is {fmt.status}.")

    settings = get_settings(db)
    content = await file.read()
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(status_code=400, detail="That file is too large.")

    suffix = Path(file.filename or "blank.pdf").suffix.lower().lstrip(".")
    if suffix not in settings.allowed_extensions_list:
        raise HTTPException(
            status_code=400,
            detail=f"'{suffix}' files are not accepted. Allowed: "
                   + ", ".join(settings.allowed_extensions_list),
        )

    folder = Path(settings.storage_folder) / "formats" / fmt.id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"blank.{suffix}"
    target.write_bytes(content)

    fmt.blank_file_path = str(target)
    fmt.blank_mime_type = file.content_type or "application/octet-stream"
    fmt.blank_file_size = len(content)
    db.commit()
    db.refresh(fmt)
    return _format_json(db, fmt, detail=True)


@router.get("/{format_id}/blank")
def download_blank(format_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user_flexible),
                   inline: bool = Query(False, description="Render in place rather than download")):
    """
    The blank form, for somebody about to fill one on paper.

    `inline=1` asks the browser to draw it where it sits instead of saving it.
    Resources shows the blank in the panel beside the list, and a download
    disposition there hands somebody a file when all they did was click a row.
    """
    from pathlib import Path

    from fastapi.responses import FileResponse

    fmt = fmts.get(db, format_id)
    if not fmt or not fmt.blank_file_path:
        raise HTTPException(status_code=404, detail="This format has no blank form attached.")
    path = Path(fmt.blank_file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="The blank form is missing from storage.")
    from ..services.file_utils import safe_headers, served_type

    media_type, viewable = served_type(path.name)
    return FileResponse(
        str(path),
        media_type=media_type,
        filename=f"{fmt.code}-rev{fmt.revision}{path.suffix}",
        content_disposition_type="inline" if inline and viewable else "attachment",
        headers=safe_headers(media_type),
    )


@router.get("/{format_id}/people")
def eligible_people(format_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user_flexible)):
    """
    Who may be appointed to each responsibility on this format.

    A step that must be signed cannot be given to somebody who may not sign, so
    the two approval responsibilities are filtered to people who can, and the
    choice is made from a list that cannot produce a stuck chain.
    """
    fmt = fmts.get(db, format_id)
    if not fmt:
        raise HTTPException(status_code=404, detail="Format not found")

    people = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.full_name, User.username)
        .all()
    )
    if fmt.team_id:
        team_people = [p for p in people if p.quality_team_id == fmt.team_id or p.is_admin]
        if team_people:
            people = team_people
    signers = [p for p in people if p.can_sign or p.is_admin]
    approvers = [p for p in people if p.can_approve or p.is_admin]
    return {
        "process_owner": [_person(p) for p in signers],
        "overall_process_owner": [_person(p) for p in signers],
        "cft_members": [_person(p) for p in approvers],
        "qms_coordinator": [_person(p) for p in approvers],
    }
