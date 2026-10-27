"""
Who may hold the approval responsibilities on a record.

A format names its Process Owner, Overall Process Owner and Quality CFT; the
person submitting a record may choose them where the format leaves the choice
open, or change them (somebody is on leave). Either way the choice must give a
real review:

  * everyone chosen is an active person of the format's team who may sign (the
    two owners) or approve (the CFT) - a step addressed to anybody else stops;
  * four eyes: the Overall Process Owner is not the Process Owner, and no CFT
    member is either of them. Otherwise one person approves, clears the N-ok
    flag, agrees the joint review and files the record alone.
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from ..models import User

CHOOSABLE = ("process_owner", "overall_process_owner", "cft_members")
ROLE_NAMES = {
    "process_owner": "Process Owner",
    "overall_process_owner": "Overall Process Owner",
    "cft_members": "Quality CFT",
}


class ApprovalPeopleError(ValueError):
    """The people chosen cannot give the record a proper review."""


def _name(user: Optional[User]) -> str:
    return (user.full_name or user.username) if user else "Somebody"


def separation_problems(po: Iterable[str], opo: Iterable[str], cft: Iterable[str],
                        names: dict[str, str]) -> list[str]:
    """What breaks the four-eyes rule, in words; names: person id -> name."""
    po, opo, cft = set(po), set(opo), set(cft)
    found = []
    for person in po & opo:
        found.append(f"{names.get(person, 'One person')} cannot be both the Process Owner and the "
                     "Overall Process Owner: the second approval would be their own.")
    for person in cft & (po | opo):
        found.append(f"{names.get(person, 'One person')} approves the record already and cannot also "
                     "sit on its Quality CFT review.")
    return found


def format_problems(fmt) -> list[str]:
    """The format's own responsibilities against the four-eyes rule (template readiness)."""
    names = {u.id: _name(u) for u in [fmt.process_owner, fmt.overall_process_owner, *(fmt.cft_members or [])] if u}
    return separation_problems(
        [fmt.process_owner_id] if fmt.process_owner_id else [],
        [fmt.overall_process_owner_id] if fmt.overall_process_owner_id else [],
        [m.id for m in fmt.cft_members or []],
        names,
    )


def validate_overrides(db: Session, fmt, overrides: Optional[dict]) -> dict[str, list[str]]:
    """The people chosen at submission, checked; raises ApprovalPeopleError with the reason."""
    if not overrides:
        overrides = {}
    if not isinstance(overrides, dict):
        raise ApprovalPeopleError("The approvers must be given per responsibility.")
    unknown = [k for k in overrides if k not in CHOOSABLE]
    if unknown:
        raise ApprovalPeopleError(
            "Only the Process Owner, Overall Process Owner and Quality CFT are chosen when a record "
            f"is submitted, not: {', '.join(unknown)}.")

    chosen: dict[str, list[str]] = {}
    ids = {i for v in overrides.values() for i in (v or []) if i}
    people = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()} if ids else {}
    # as the people pickers offer them (formats router, eligible_people): the team's people,
    # or everybody while the team has nobody in it yet
    team_scoped = bool(fmt.team_id) and db.query(User.id).filter(User.quality_team_id == fmt.team_id).first() is not None
    for role, value in overrides.items():
        if value is None:
            continue
        if not isinstance(value, list) or not all(isinstance(i, str) for i in value):
            raise ApprovalPeopleError(f"The {ROLE_NAMES[role]} must be a list of people.")
        value = list(dict.fromkeys(i for i in value if i))
        if role != "cft_members" and len(value) > 1:
            raise ApprovalPeopleError(f"A record has one {ROLE_NAMES[role]}.")
        for person_id in value:
            person = people.get(person_id)
            if person is None or not person.is_active:
                raise ApprovalPeopleError(f"The {ROLE_NAMES[role]} chosen is not an active person.")
            if team_scoped and not person.is_admin and person.quality_team_id != fmt.team_id:
                raise ApprovalPeopleError(f"{_name(person)} is not in this format's quality team.")
            may = person.is_admin or (person.can_approve if role == "cft_members" else person.can_sign)
            if not may:
                raise ApprovalPeopleError(
                    f"{_name(person)} may not {'approve' if role == 'cft_members' else 'sign'} records, "
                    f"so cannot be the {ROLE_NAMES[role]}.")
        if value:
            chosen[role] = value

    # the roles as they will stand on this record: chosen, else the format's
    po = chosen.get("process_owner") or ([fmt.process_owner_id] if fmt.process_owner_id else [])
    opo = chosen.get("overall_process_owner") or ([fmt.overall_process_owner_id] if fmt.overall_process_owner_id else [])
    cft = chosen.get("cft_members") or [m.id for m in fmt.cft_members or []]
    names = {**{u.id: _name(u) for u in people.values()},
             **{u.id: _name(u) for u in [fmt.process_owner, fmt.overall_process_owner, *(fmt.cft_members or [])] if u}}
    problems = separation_problems(po, opo, cft, names)
    if problems:
        raise ApprovalPeopleError(" ".join(problems))
    return chosen
