"""Class-based notification subsystem with injectable delivery channels."""
from __future__ import annotations

import smtplib
import threading
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
import re
from typing import Iterable, Optional, Protocol, Sequence

from loguru import logger
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import SessionLocal
from ..models import User
from ..models_qms import Notification

# Notification kinds are stable application-level identifiers.
RECORD_SUBMITTED = "record.submitted"
RECORD_PO_APPROVED = "record.po_approved"
RECORD_NOK_FLAGGED = "record.nok_flagged"
RECORD_CFT_REVIEW = "record.cft_review"
RECORD_REVERIFY = "record.reverify"
RECORD_STORED = "record.stored"
DCR_SUBMITTED = "dcr.submitted"
DCR_DECIDED = "dcr.decided"
RECORD_CHANGE_REQUEST_SUBMITTED = "record_change_request.submitted"
RECORD_CHANGE_REQUEST_DECIDED = "record_change_request.decided"
RECORD_CHANGE_REQUEST_IMPLEMENTED = "record_change_request.implemented"
INSPECTION_PENDING = "inspection.pending"
INSPECTION_COMPLETED = "inspection.completed"
INSPECTION_FAILED = "inspection.failed"
ACTION_ASSIGNED = "action.assigned"
ACTION_OVERDUE = "action.overdue"

KINDS = [
    RECORD_SUBMITTED, RECORD_PO_APPROVED, RECORD_NOK_FLAGGED, RECORD_CFT_REVIEW,
    RECORD_REVERIFY, RECORD_STORED, DCR_SUBMITTED, DCR_DECIDED,
    RECORD_CHANGE_REQUEST_SUBMITTED, RECORD_CHANGE_REQUEST_DECIDED,
    RECORD_CHANGE_REQUEST_IMPLEMENTED,
    INSPECTION_PENDING, INSPECTION_COMPLETED, INSPECTION_FAILED,
    ACTION_ASSIGNED, ACTION_OVERDUE,
]

QUEUED, SENT, FAILED, SKIPPED = "queued", "sent", "failed", "skipped"
EMAIL_BRAND = "Harman Paperless Drive"
_NO_SMTP_CONFIGURED = (
    "No SMTP host configured; notification recorded but not emailed."
)


@dataclass(frozen=True)
class DeliveryResult:
    """Result of attempting to deliver one notification."""

    notification_id: str
    error: Optional[str] = None


class NotificationDeliveryChannel(Protocol):
    """Contract for adding delivery channels without changing orchestration."""

    def is_available(self, settings: Settings) -> bool:
        """Return whether this channel is configured."""
        ...

    def unavailable_reason(self, settings: Settings) -> str:
        """Describe why this channel cannot currently deliver."""
        ...

    def send_batch(
        self,
        notifications: Sequence[Notification],
        settings: Settings,
    ) -> Sequence[DeliveryResult]:
        """Deliver notifications and return one result per notification."""
        ...


class NotificationRepository:
    """Owns persistence and queries for notification records."""

    def __init__(self, db: Session):
        self._db = db

    def create(
        self,
        kind: str,
        recipients: Iterable[Optional[User]],
        *,
        subject: str,
        body: str,
        related_type: Optional[str] = None,
        related_id: Optional[str] = None,
    ) -> list[Notification]:
        rows = [
            Notification(
                kind=kind,
                subject=subject[:400],
                body=body,
                to_user_id=getattr(person, "id", None),
                to_email=(getattr(person, "email", None) or "").strip() or None,
                related_type=related_type,
                related_id=related_id,
                status=QUEUED,
            )
            for person in recipients
        ]
        self._db.add_all(rows)
        self._db.commit()
        for row in rows:
            self._db.refresh(row)
        return rows

    def already_raised(self, kind: str, related_type: str,
                       related_id: str) -> bool:
        """Has this alert been recorded for this related item?"""
        return self._db.query(Notification.id).filter(
            Notification.kind == kind,
            Notification.related_type == related_type,
            Notification.related_id == related_id,
        ).first() is not None

    def for_user(self, user: User, *, limit: int = 50,
                 unread_only: bool = False) -> list[Notification]:
        """Return this person's notifications, newest first."""
        query = self._db.query(Notification).filter(
            Notification.to_user_id == user.id
        )
        if unread_only:
            query = query.filter(Notification.read_at.is_(None))
        return (
            query.order_by(Notification.created_at.desc())
            .limit(max(1, min(limit, 200)))
            .all()
        )

    def unread_count(self, user: User) -> int:
        return (
            self._db.query(Notification)
            .filter(
                Notification.to_user_id == user.id,
                Notification.read_at.is_(None),
            )
            .count()
        )

    def mark_read(
        self,
        user: User,
        notification_ids: Optional[list[str]] = None,
    ) -> int:
        """Mark selected notifications, or all of this person's, as read."""
        query = self._db.query(Notification).filter(
            Notification.to_user_id == user.id,
            Notification.read_at.is_(None),
        )
        if notification_ids:
            query = query.filter(Notification.id.in_(notification_ids))

        now = datetime.utcnow()
        rows = query.all()
        for row in rows:
            row.read_at = now
        if rows:
            self._db.commit()
        return len(rows)

    def by_ids(self, notification_ids: list[str]) -> list[Notification]:
        if not notification_ids:
            return []
        return self._db.query(Notification).filter(
            Notification.id.in_(notification_ids)
        ).all()

    def update_delivery(
        self,
        notification_ids: list[str],
        *,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        for row in self.by_ids(notification_ids):
            row.status = status
            row.error = error[:900] if error else None
            if status == SENT:
                row.sent_at = datetime.utcnow()
        self._db.commit()


class NotificationMessageFormatter:
    """Creates notification links and user-facing message bodies."""

    def __init__(self, settings_provider=get_settings):
        self._settings_provider = settings_provider

    def link(self, path: str) -> str:
        base = (self._settings_provider().app_base_url or "").rstrip("/")
        return f"{base}{path}"

    def record_body(self, record, lead: str, ask: str) -> str:
        """Format a record alert consistently for email and the inbox."""
        fmt = record.format
        lines = [
            lead,
            "",
            f"Record        {record.number}",
            f"Format        {fmt.code} rev {record.format_revision or fmt.revision} - {fmt.title}"
            if fmt else f"Record        {record.number}",
            f"Period        {record.period_label or record.period_key or '-'}",
            f"Observations  {'N-ok - out of specification' if record.observation_status == 'not_ok' else 'ok - within specification'}"
            if record.observation_status else "Observations  not yet evaluated",
        ]
        if record.cft_target_date:
            lines.append(f"Target date   {record.cft_target_date:%d %b %Y}")
        lines += [
            "",
            ask,
            "",
            self.link(f"/track?record={record.id}"),
        ]
        return "\n".join(lines)


class NotificationEmailTemplate:
    """Render notification content as email-client-friendly HTML."""

    _URL_PATTERN = re.compile(r"https?://[^\s<>]+")
    _TRAILING_URL_PUNCTUATION = ".,;:!?)]}"

    def render(self, notification: Notification) -> str:
        subject = escape(notification.subject or "Notification")
        kind = escape(notification.kind.replace(".", " ").replace("_", " ").title())
        body = self._format_body(notification.body or notification.subject or "")

        brand = escape(EMAIL_BRAND)
        return f"""\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{subject}</title>
  </head>
  <body style="margin:0;padding:0;background-color:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#1e293b;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#f1f5f9;padding:32px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:600px;background-color:#ffffff;border-radius:12px;overflow:hidden;">
            <tr>
              <td style="padding:24px 32px;background-color:#17365d;color:#ffffff;">
                <div style="font-size:13px;font-weight:bold;letter-spacing:1px;text-transform:uppercase;color:#bfdbfe;">{brand}</div>
                <div style="margin-top:8px;font-size:13px;color:#e2e8f0;">{kind}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:32px;">
                <h1 style="margin:0 0 20px;font-size:24px;line-height:1.3;color:#0f172a;">{subject}</h1>
                <div style="border-left:4px solid #0ea5e9;background-color:#f8fafc;padding:20px 22px;border-radius:4px;font-size:15px;line-height:1.7;color:#334155;overflow-wrap:anywhere;">
                  {body}
                </div>
              </td>
            </tr>
            <tr>
              <td style="padding:18px 32px;background-color:#f8fafc;border-top:1px solid #e2e8f0;font-size:12px;line-height:1.5;color:#64748b;">
                This is an automated notification from {brand}. Please do not reply to this email.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""

    def _format_body(self, body: str) -> str:
        parts: list[str] = []
        cursor = 0
        for match in self._URL_PATTERN.finditer(body):
            parts.append(escape(body[cursor:match.start()]).replace("\n", "<br>\n"))
            url = match.group()
            safe_url = url.rstrip(self._TRAILING_URL_PUNCTUATION)
            trailing = url[len(safe_url):]
            escaped_url = escape(safe_url, quote=True)
            parts.append(
                f'<a href="{escaped_url}" style="color:#0369a1;text-decoration:underline;">'
                f"{escape(safe_url)}</a>{escape(trailing)}"
            )
            cursor = match.end()
        parts.append(escape(body[cursor:]).replace("\n", "<br>\n"))
        return "".join(parts)


class SMTPNotificationChannel:
    """Sends notification batches by SMTP."""

    def __init__(self, template: Optional[NotificationEmailTemplate] = None):
        self._template = template or NotificationEmailTemplate()

    def is_available(self, settings: Settings) -> bool:
        return settings.mail_available

    def unavailable_reason(self, settings: Settings) -> str:
        return _NO_SMTP_CONFIGURED

    def send_batch(
        self,
        notifications: Sequence[Notification],
        settings: Settings,
    ) -> Sequence[DeliveryResult]:
        if not notifications:
            return []

        server = self._connect(settings)
        results: list[DeliveryResult] = []
        try:
            for notification in notifications:
                try:
                    server.send_message(self._compose(settings, notification))
                    results.append(DeliveryResult(notification.id))
                except Exception as exc:
                    logger.warning(
                        f"Notification {notification.kind} to "
                        f"{notification.to_email} failed: {exc}"
                    )
                    results.append(
                        DeliveryResult(notification.id, str(exc)[:900])
                    )
        finally:
            try:
                server.quit()
            except Exception:
                pass
        return results

    @staticmethod
    def _connect(settings: Settings) -> smtplib.SMTP:
        server = smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout,
        )
        server.ehlo()
        if settings.smtp_use_tls:
            server.starttls()
            server.ehlo()
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        return server

    def _compose(self, settings: Settings, notification: Notification) -> EmailMessage:
        message = EmailMessage()
        sender = settings.smtp_from or settings.smtp_username
        message["From"] = formataddr((EMAIL_BRAND, sender))
        message["To"] = notification.to_email
        if settings.notifications_copy_to:
            message["Cc"] = settings.notifications_copy_to
        message["Subject"] = notification.subject
        message.set_content(notification.body or notification.subject)
        message.add_alternative(
            self._template.render(notification),
            subtype="html",
        )
        return message


class NotificationDeliveryService:
    """Owns channel selection and best-effort background delivery."""

    def __init__(
        self,
        channel: NotificationDeliveryChannel,
        *,
        settings_provider=get_settings,
        session_factory=SessionLocal,
        thread_factory=threading.Thread,
    ):
        self._channel = channel
        self._settings_provider = settings_provider
        self._session_factory = session_factory
        self._thread_factory = thread_factory

    def dispatch(
        self,
        db: Session,
        notification_ids: list[str],
        *,
        channel: Optional[NotificationDeliveryChannel] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        if not notification_ids:
            return
        selected_channel = channel or self._channel
        current_settings = settings or self._settings_provider()
        try:
            available = selected_channel.is_available(current_settings)
        except Exception as exc:
            logger.warning(f"Could not check notification delivery channel: {exc}")
            NotificationRepository(db).update_delivery(
                notification_ids, status=FAILED, error=str(exc)
            )
            return

        if not available:
            NotificationRepository(db).update_delivery(
                notification_ids,
                status=SKIPPED,
                error=selected_channel.unavailable_reason(current_settings),
            )
            return

        self._thread_factory(
            target=self._deliver_batch,
            args=(notification_ids, selected_channel),
            daemon=True,
            name="notification-delivery",
        ).start()

    def _deliver_batch(
        self,
        notification_ids: list[str],
        channel: NotificationDeliveryChannel,
    ) -> None:
        """Deliver using a fresh database session owned by this worker."""
        db = self._session_factory()
        try:
            repository = NotificationRepository(db)
            notifications = repository.by_ids(notification_ids)
            if not notifications:
                return

            settings = self._settings_provider()
            try:
                available = channel.is_available(settings)
            except Exception as exc:
                logger.warning(f"Could not check notification delivery channel: {exc}")
                repository.update_delivery(
                    notification_ids, status=FAILED, error=str(exc)
                )
                return
            if not available:
                repository.update_delivery(
                    notification_ids,
                    status=SKIPPED,
                    error=channel.unavailable_reason(settings),
                )
                return

            try:
                results = channel.send_batch(notifications, settings)
            except Exception as exc:
                logger.warning(f"Notification delivery channel failed: {exc}")
                repository.update_delivery(
                    notification_ids, status=FAILED, error=str(exc)
                )
                return

            results_by_id = {
                result.notification_id: result for result in results
            }
            for notification in notifications:
                result = results_by_id.get(notification.id)
                if result is None:
                    notification.status = FAILED
                    notification.error = "Delivery channel returned no result."
                elif result.error:
                    notification.status = FAILED
                    notification.error = result.error[:900]
                else:
                    notification.status = SENT
                    notification.sent_at = datetime.utcnow()
                    notification.error = None
            db.commit()
        except Exception as exc:  # pragma: no cover - defensive thread boundary
            logger.error(f"Notification delivery thread failed: {exc}")
        finally:
            db.close()


class NotificationService:
    """Coordinates notification creation and delivery."""

    def __init__(
        self,
        *,
        channel: Optional[NotificationDeliveryChannel] = None,
        repository_factory=NotificationRepository,
        formatter: Optional[NotificationMessageFormatter] = None,
        delivery_service: Optional[NotificationDeliveryService] = None,
        settings_provider=get_settings,
    ):
        self._channel = channel or SMTPNotificationChannel()
        self._repository_factory = repository_factory
        self._formatter = formatter or NotificationMessageFormatter(
            settings_provider
        )
        self._delivery_service = delivery_service or NotificationDeliveryService(
            self._channel, settings_provider=settings_provider
        )
        self._settings_provider = settings_provider

    def notify(
        self,
        db: Session,
        kind: str,
        *,
        to: Optional[User] | Iterable[Optional[User]] = None,
        subject: str,
        body: str,
        related_type: Optional[str] = None,
        related_id: Optional[str] = None,
        record=None,
        step=None,
        send: bool = True,
        channel: Optional[NotificationDeliveryChannel] = None,
    ) -> list[Notification]:
        """
        Persist one row per recipient, then optionally deliver it.

        ``record`` and ``step`` remain accepted for existing callers. Email
        bodies intentionally do not include single-use approval links.
        """
        people = self._as_list(to)
        if not people:
            logger.warning(
                f"Notification '{kind}' has no recipient; recording it anyway"
            )
            people = [None]

        rows = self._repository_factory(db).create(
            kind,
            people,
            subject=subject,
            body=body,
            related_type=related_type,
            related_id=related_id,
        )
        if send:
            deliverable_ids = [row.id for row in rows if row.to_email]
            if deliverable_ids:
                self._delivery_service.dispatch(
                    db,
                    deliverable_ids,
                    channel=channel,
                    settings=self._settings_provider(),
                )
        return rows

    def link(self, path: str) -> str:
        return self._formatter.link(path)

    def record_body(self, record, lead: str, ask: str) -> str:
        return self._formatter.record_body(record, lead, ask)

    @staticmethod
    def _as_list(
        recipients: Optional[User] | Iterable[Optional[User]],
    ) -> list[Optional[User]]:
        if recipients is None:
            return []
        if isinstance(recipients, User):
            return [recipients]
        seen: set[str] = set()
        people: list[Optional[User]] = []
        for person in recipients:
            if person is None:
                continue
            if person.id in seen:
                continue
            seen.add(person.id)
            people.append(person)
        return people


# Preserve the established module-level API while routing it through the
# class-based service. Existing callers can migrate to the class incrementally.
_default_service = NotificationService()


def notify(*args, **kwargs) -> list[Notification]:
    return _default_service.notify(*args, **kwargs)


def already_raised(db: Session, kind: str, related_type: str,
                   related_id: str) -> bool:
    return NotificationRepository(db).already_raised(kind, related_type, related_id)


def for_user(db: Session, user: User, *, limit: int = 50,
             unread_only: bool = False) -> list[Notification]:
    return NotificationRepository(db).for_user(
        user, limit=limit, unread_only=unread_only
    )


def unread_count(db: Session, user: User) -> int:
    return NotificationRepository(db).unread_count(user)


def mark_read(
    db: Session,
    user: User,
    notification_ids: Optional[list[str]] = None,
) -> int:
    return NotificationRepository(db).mark_read(user, notification_ids)


def link(path: str) -> str:
    return _default_service.link(path)


def record_body(record, lead: str, ask: str) -> str:
    return _default_service.record_body(record, lead, ask)


__all__ = [
    "ACTION_ASSIGNED",
    "ACTION_OVERDUE",
    "DCR_DECIDED",
    "DCR_SUBMITTED",
    "DeliveryResult",
    "EMAIL_BRAND",
    "FAILED",
    "INSPECTION_COMPLETED",
    "INSPECTION_FAILED",
    "INSPECTION_PENDING",
    "KINDS",
    "NotificationDeliveryChannel",
    "NotificationDeliveryService",
    "NotificationEmailTemplate",
    "NotificationMessageFormatter",
    "NotificationRepository",
    "NotificationService",
    "QUEUED",
    "RECORD_CFT_REVIEW",
    "RECORD_NOK_FLAGGED",
    "RECORD_PO_APPROVED",
    "RECORD_REVERIFY",
    "RECORD_STORED",
    "RECORD_SUBMITTED",
    "SENT",
    "SKIPPED",
    "SMTPNotificationChannel",
    "already_raised",
    "for_user",
    "link",
    "mark_read",
    "notify",
    "record_body",
    "unread_count",
]
