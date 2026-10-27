"""Role permissions and migration away from previously seeded system roles."""
from __future__ import annotations

import json

from loguru import logger
from sqlalchemy.orm import Session

from ..models import Role, User

# These roles were created by earlier versions of the application. Keep their
# definitions here only so the one-time startup migration can remove them.
READ = [
    "documents.read", "correspondents.read", "doctypes.read", "tags.read",
    "settings.read", "search.read",
]

CONTRIBUTE = READ + [
    "documents.create", "documents.update",
    "correspondents.create", "correspondents.update",
    "doctypes.create", "tags.create", "tags.update",
]

# name -> (description, permissions)
STANDARD_ROLES: dict[str, tuple[str, list[str]]] = {
    "reader": (
        "Can find and read documents, but not change or approve them.",
        READ,
    ),
    "contributor": (
        "Can add documents, correct their details, and send them for approval. Cannot approve.",
        CONTRIBUTE,
    ),
    "approver": (
        "Can view documents and act on approval steps addressed to them.",
        READ + ["documents.approve"],
    ),
    "signatory": (
        "An approver who may also apply a signature, binding the company.",
        READ + ["documents.approve", "documents.sign"],
    ),

    # ------------------------------------------------------------------ QMS
    #
    # The four responsibilities named in the client's record process flow.
    # They are roles rather than account types because one person can hold
    # more than one - a Process Owner for one format is routinely a CFT
    # member on another - and account_type is single-valued.
    "process_owner": (
        "Calls a blank format, fills the record, approves it if it is within "
        "specification, and takes the final decision.",
        CONTRIBUTE + [
            "documents.approve", "documents.sign",
            "records.create", "records.fill", "records.approve",
            "formats.read", "change_requests.create",
        ],
    ),
    "overall_process_owner": (
        "Approves records after the Process Owner, receives N-ok flags, and "
        "files approved records into the server's date and month folders.",
        CONTRIBUTE + [
            "documents.approve", "documents.sign", "documents.publish",
            "records.approve", "records.store",
            "formats.read", "change_requests.create",
        ],
    ),
    "cft_member": (
        "A Quality CFT member: takes part in the joint review of a record "
        "against its target date.",
        READ + [
            "documents.approve", "documents.sign",
            "records.review", "formats.read", "change_requests.create",
        ],
    ),
    "qms_coordinator": (
        "Approves every document change request before a format is altered or "
        "a new format is generated.",
        CONTRIBUTE + [
            "documents.approve", "documents.sign",
            "formats.read", "formats.manage",
            "change_requests.create", "change_requests.approve",
        ],
    ),
}

# The QMS roles, kept apart from the four generic ones. `apply_role` swaps a
# user between the generic roles as their approve/sign flags change; it must
# never take a QMS role away, because that is a deliberate appointment made by
# an administrator and has nothing to do with those two flags.
QMS_ROLES = {
    "process_owner", "overall_process_owner", "cft_member", "qms_coordinator",
}

LEGACY_ROLE_NAMES = set(STANDARD_ROLES) | {"admin", "editor", "viewer"}


def ensure_standard_roles(db: Session) -> int:
    """Compatibility no-op: built-in roles are no longer created."""
    return 0


def remove_legacy_roles(db: Session) -> int:
    """Remove seeded roles and make role assignments the source of user access."""
    legacy_roles = db.query(Role).filter(Role.name.in_(LEGACY_ROLE_NAMES)).all()
    for role in legacy_roles:
        for user in list(role.users):
            user.roles.remove(role)
        db.delete(role)

    changed_users = 0
    for user in db.query(User).all():
        if user.is_admin:
            continue
        role_permissions: set[str] = set()
        for role in user.roles:
            if not role.permissions:
                continue
            try:
                permissions = json.loads(role.permissions)
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(
                    f"Role '{role.name}' contains invalid permission data"
                ) from exc
            if not isinstance(permissions, list) or not all(
                isinstance(permission, str) for permission in permissions
            ):
                raise ValueError(
                    f"Role '{role.name}' contains invalid permission data"
                )
            role_permissions.update(permissions)

        can_approve = bool(
            role_permissions
            & {
                "documents.approve",
                "records.approve",
                "change_requests.approve",
            }
        )
        can_sign = "documents.sign" in role_permissions
        if (
            user.account_type != "employee"
            or user.can_approve != can_approve
            or user.can_sign != can_sign
        ):
            user.account_type = "employee"
            user.can_approve = can_approve
            user.can_sign = can_sign
            changed_users += 1

    if legacy_roles or changed_users:
        db.commit()
        logger.info(
            f"Removed {len(legacy_roles)} legacy role(s) and synchronized "
            f"{changed_users} user's role-derived authority"
        )
    return len(legacy_roles)


def role_for(user: User) -> str:
    """Which standard role matches this person's approval authority."""
    if user.account_type == "team_member":
        return "contributor"
    if user.can_sign:
        return "signatory"
    if user.can_approve:
        return "approver"
    return "reader"


def apply_role(db: Session, user: User) -> str:
    """
    Preserve the legacy account-type authority mapping without creating roles.

    Explicitly assigned custom roles are authoritative and are never changed.
    """
    wanted = role_for(user)
    if user.roles:
        return wanted

    if user.account_type != "team_member":
        user.account_type = wanted
    db.commit()
    return wanted


def backfill(db: Session) -> int:
    """Compatibility no-op: users now receive an administrator-selected role."""
    return 0
