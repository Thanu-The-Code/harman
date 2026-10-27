"""
Web links that let somebody answer an approval from their inbox.

The process document asks for a trigger email at four points. An email that only
says "there is something waiting for you, please sign in and find it" is barely
better than no email: the person is on the shop floor, on a phone, and the
distance between reading the message and answering it is where approvals go to
die. So each notification carries a link that opens the record and asks the
question directly.

The link is deliberately narrow. It is bound to one step, one record and one
person; it expires; it is spent when a decision is recorded through it; and it
signs nobody in. Somebody who forwards their link has given away one decision on
one record, not their account - and the decision is still recorded against their
name, which is the part that matters for an audit.

Every check is made against the live state of the step at the moment the link
is opened, not against anything baked into the token. A step that has already
been answered, escalated to somebody else, or cancelled makes every link to it
useless immediately, without anything having to go and revoke them.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ApprovalStep, User
from ..models_qms import ApprovalLink, Record

# Long enough that guessing is not a strategy: 32 bytes of randomness, which is
# 256 bits, in a URL-safe alphabet.
TOKEN_BYTES = 32

# How long a link stays good. Long enough to survive a weekend and a night
# shift, short enough that a forwarded email does not stay live for a month.
DEFAULT_DAYS = 14


class LinkError(Exception):
    """The link cannot be used, with a reason worth showing the person holding it."""


def issue(db: Session, *, record: Record, step: ApprovalStep, user: User,
          purpose: str = "", days: int = DEFAULT_DAYS) -> ApprovalLink:
    """
    Mint a link for one person to answer one step.

    Reuses a link that is still good rather than minting a second. A person who
    is reminded twice should be able to use either email, and two live links to
    the same decision is one more than anybody needs.
    """
    existing = (
        db.query(ApprovalLink)
        .filter(
            ApprovalLink.step_id == step.id,
            ApprovalLink.user_id == user.id,
            ApprovalLink.used_at.is_(None),
            ApprovalLink.revoked_at.is_(None),
        )
        .first()
    )
    if existing and existing.expires_at > datetime.now():
        return existing

    link = ApprovalLink(
        token=secrets.token_urlsafe(TOKEN_BYTES),
        record_id=record.id,
        workflow_id=step.workflow_id,
        step_id=step.id,
        user_id=user.id,
        purpose=purpose or None,
        expires_at=datetime.now() + timedelta(days=max(1, days)),
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def url_for(link: ApprovalLink) -> str:
    """The address to put in the email."""
    base = (get_settings().app_base_url or "http://127.0.0.1:8000").rstrip("/")
    return f"{base}/approve/{link.token}"


def resolve(db: Session, token: str) -> ApprovalLink:
    """
    The link behind a token, if it can still be used.

    Raises `LinkError` with something the person can act on. The messages are
    written for somebody who has just opened an email and has no idea what a
    workflow step is, so each says what happened and what to do instead.
    """
    link = db.query(ApprovalLink).filter(ApprovalLink.token == token).first()
    if not link:
        raise LinkError(
            "This link is not valid. It may have been mistyped, or the record "
            "it pointed at may have been withdrawn.")

    if link.revoked_at:
        raise LinkError(
            "This link has been withdrawn. The approval was reassigned to "
            "somebody else, or the record was recalled.")

    if link.used_at:
        raise LinkError(
            f"This link has already been used to record a decision "
            f"({link.used_action or 'answered'}). Each link works once.")

    if link.expires_at <= datetime.now():
        raise LinkError(
            "This link has expired. Ask for it to be sent again, or sign in "
            "and answer it from My Approvals.")

    return link


def step_of(db: Session, link: ApprovalLink) -> ApprovalStep:
    """
    The step this link answers, checked against the live process.

    Every reason a link stops working is discovered here rather than stored on
    the link, so a step that has moved on invalidates its links the moment it
    moves - nothing has to go and hunt them down.
    """
    step = db.query(ApprovalStep).filter(ApprovalStep.id == link.step_id).first()
    if not step:
        raise LinkError(
            "The approval this link pointed at no longer exists. The record may "
            "have been recalled and restarted.")

    if step.status != "current":
        raise LinkError(
            "This approval has already moved on — somebody else answered it, or "
            "it was returned for correction. Nothing more is needed from you.")

    assignees = {a.id for a in (step.assignees or [])}
    if assignees and link.user_id not in assignees:
        raise LinkError(
            "This approval has been reassigned to somebody else, so this link "
            "no longer works.")

    return step


def spend(db: Session, link: ApprovalLink, action: str, source: str = "") -> None:
    """Mark a link used. Called only after the decision itself is recorded."""
    link.used_at = datetime.now()
    link.used_action = (action or "")[:40] or None
    link.used_from = (source or "")[:200] or None
    db.commit()


def revoke_for_step(db: Session, step_id: str, reason: str = "") -> int:
    """
    Kill every live link to a step.

    Used when a step is escalated to somebody else. The check in `step_of`
    would refuse those links anyway, but revoking them makes the intent
    explicit in the audit trail rather than leaving it as a side effect.
    """
    live = (
        db.query(ApprovalLink)
        .filter(
            ApprovalLink.step_id == step_id,
            ApprovalLink.used_at.is_(None),
            ApprovalLink.revoked_at.is_(None),
        )
        .all()
    )
    for link in live:
        link.revoked_at = datetime.now()
    if live:
        db.commit()
        logger.info(f"Revoked {len(live)} approval link(s) for step {step_id}: {reason}")
    return len(live)


def live_for_record(db: Session, record_id: str) -> list[ApprovalLink]:
    """Every link still outstanding on a record, for showing on Tracking."""
    return (
        db.query(ApprovalLink)
        .filter(
            ApprovalLink.record_id == record_id,
            ApprovalLink.used_at.is_(None),
            ApprovalLink.revoked_at.is_(None),
            ApprovalLink.expires_at > datetime.now(),
        )
        .order_by(ApprovalLink.created_at.desc())
        .all()
    )
