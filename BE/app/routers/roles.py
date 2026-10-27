"""Role management and the permissions that can be granted through a role."""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Role, User
from ..services.auth_service import require_admin_flexible
from ..services.role_service import STANDARD_ROLES

router = APIRouter()

PERMISSION_CATALOG = {
    "documents.view": {
        "description": "View documents and released templates",
        "grants": {
            "documents.read", "search.read", "formats.read",
            "correspondents.read", "doctypes.read", "tags.read", "settings.read",
        },
    },
    "records.fill": {
        "description": "Create and fill records, then send them for approval",
        "grants": {
            "documents.create", "documents.update", "records.create", "records.fill",
            "formats.read",
        },
    },
    "templates.create": {
        "description": "Create and edit draft templates, then submit them for approval",
        "grants": {"formats.manage", "formats.read"},
    },
    "approvals.approve": {
        "description": "Approval",
        "grants": {
            "documents.approve", "records.review", "records.approve",
            "documents.sign", "records.store", "change_requests.approve",
            "documents.read", "formats.read",
        },
    },
}
CAPABILITY_KEYS = set(PERMISSION_CATALOG)

MANAGED_ROLE_NAMES = {"admin", "editor", "viewer"} | set(STANDARD_ROLES)


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    permissions: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    permissions: Optional[list[str]] = None


class RoleAssignment(BaseModel):
    role_id: Optional[str] = None
    role_ids: list[str] = Field(default_factory=list)


def _permission_list(role: Role) -> list[str]:
    if not role.permissions:
        return []
    try:
        permissions = json.loads(role.permissions)
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Role '{role.name}' contains invalid permission data",
        ) from exc
    if not isinstance(permissions, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Role '{role.name}' contains invalid permission data",
        )
    stored_permissions = set(item for item in permissions if isinstance(item, str))
    capabilities = stored_permissions & CAPABILITY_KEYS
    capabilities.update(_capabilities_for_permissions(stored_permissions))
    return sorted(capabilities)


def _role_response(role: Role) -> dict:
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "permissions": _permission_list(role),
        "assignable": role.name not in MANAGED_ROLE_NAMES,
        "user_count": len(role.users),
        "created_at": role.created_at,
        "updated_at": role.updated_at,
    }


def _capabilities_for_permissions(permissions: set[str]) -> list[str]:
    if "*" in permissions:
        return sorted(CAPABILITY_KEYS)
    markers = {
        "documents.view": {"documents.read"},
        "records.fill": {
            "records.fill", "documents.create", "documents.update",
        },
        "templates.create": {"formats.manage"},
        "approvals.approve": {
            "documents.approve", "records.review", "records.approve",
            "change_requests.approve",
        },
    }
    return sorted(
        capability for capability, keys in markers.items()
        if permissions & keys
    )


def _validate_permissions(permissions: list[str]) -> list[str]:
    normalized = list(dict.fromkeys(permission.strip() for permission in permissions))
    unknown = sorted(set(normalized) - CAPABILITY_KEYS)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "Unknown permission(s)",
                "unknown_permissions": unknown,
                "available_permissions": sorted(CAPABILITY_KEYS),
            },
        )
    return sorted({
        internal_permission
        for capability in normalized
        for internal_permission in PERMISSION_CATALOG[capability]["grants"]
    })


def _managed_role(role: Role) -> bool:
    return role.name in MANAGED_ROLE_NAMES


def _find_user_roles(db: Session, role_ids: list[str]) -> list[Role]:
    ids = list(dict.fromkeys(role_ids))
    roles = db.query(Role).filter(Role.id.in_(ids)).all() if ids else []
    if len(roles) != len(ids):
        found = {role.id for role in roles}
        missing = [role_id for role_id in ids if role_id not in found]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Role not found", "role_ids": missing},
        )
    return roles


def _sync_role_authority(user: User) -> None:
    user.can_approve = (
        user.has_permission("documents.approve")
        or user.has_permission("records.approve")
        or user.has_permission("change_requests.approve")
    )
    user.can_sign = user.has_permission("documents.sign")


@router.get("/permissions")
def list_permissions(
    current_user: User = Depends(require_admin_flexible),
):
    """List permissions that may be assigned to a role."""
    return [
        {"key": key, "description": details["description"]}
        for key, details in PERMISSION_CATALOG.items()
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_role(
    role_data: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    """Create a custom role and grant it a set of permissions."""
    name = role_data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Role name cannot be blank")
    if name.lower() in MANAGED_ROLE_NAMES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This role name is reserved for a system-managed role",
        )

    role = Role(
        name=name,
        description=role_data.description,
        permissions=json.dumps(_validate_permissions(role_data.permissions)),
    )
    db.add(role)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A role with this name already exists",
        ) from exc
    db.refresh(role)
    return _role_response(role)


@router.get("")
def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    """List all roles, including their permissions and assigned user counts."""
    return [_role_response(role) for role in db.query(Role).order_by(Role.name).all()]


@router.get("/{role_id}")
def get_role(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return _role_response(role)


@router.put("/{role_id}")
def update_role(
    role_id: str,
    role_data: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if _managed_role(role):
        raise HTTPException(
            status_code=409,
            detail="System-managed roles cannot be edited",
        )

    updates = role_data.model_dump(exclude_unset=True)
    if "name" in updates:
        if updates["name"] is None:
            raise HTTPException(status_code=422, detail="Role name cannot be null")
        name = updates["name"].strip()
        if not name:
            raise HTTPException(status_code=422, detail="Role name cannot be blank")
        if name.lower() in MANAGED_ROLE_NAMES:
            raise HTTPException(
                status_code=409,
                detail="This role name is reserved for a system-managed role",
            )
        role.name = name
    if "description" in updates:
        role.description = updates["description"]
    if "permissions" in updates:
        if updates["permissions"] is None:
            raise HTTPException(
                status_code=422,
                detail="permissions must be a list; use an empty list to clear it",
            )
        role.permissions = json.dumps(_validate_permissions(updates["permissions"]))
        for user in role.users:
            _sync_role_authority(user)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A role with this name already exists",
        ) from exc
    db.refresh(role)
    return _role_response(role)


@router.delete("/{role_id}")
def delete_role(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if _managed_role(role):
        raise HTTPException(
            status_code=409,
            detail="System-managed roles cannot be deleted",
        )
    if role.users:
        raise HTTPException(
            status_code=409,
            detail="Remove this role from all users before deleting it",
        )
    db.delete(role)
    db.commit()
    return {"message": "Role deleted successfully"}


@router.put("/users/{user_id}")
def assign_user_roles(
    user_id: str,
    assignment: RoleAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    """Replace a user's selected roles and synchronize approval authority."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if assignment.role_id and assignment.role_ids:
        raise HTTPException(status_code=422, detail="Send role_id or role_ids, not both")
    requested_role_ids = (
        [assignment.role_id] if assignment.role_id else assignment.role_ids
    )
    if len(set(requested_role_ids)) > 1:
        raise HTTPException(status_code=422, detail="Select exactly one role per user")
    selected_roles = _find_user_roles(db, requested_role_ids)
    if any(role.name in {"admin", "editor", "viewer"} for role in selected_roles):
        raise HTTPException(
            status_code=409,
            detail="System-managed roles cannot be assigned directly",
        )
    if any(role.name in MANAGED_ROLE_NAMES for role in selected_roles):
        raise HTTPException(status_code=409, detail="System-managed roles cannot be assigned directly")

    user.roles = selected_roles
    user.account_type = "employee"
    _sync_role_authority(user)
    db.commit()
    db.refresh(user)
    return {
        "user_id": user.id,
        "roles": [_role_response(role) for role in user.roles],
        "effective_permissions": _capabilities_for_permissions(
            set(user.permissions)
        ),
    }
