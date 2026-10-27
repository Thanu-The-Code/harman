"""Read-side operations for the full template revision repository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models_qms import Format
from . import format_service as fmts


class TemplateRepositoryService:
    """Build the repository view containing every revision of each template."""

    def __init__(self, db: Session):
        self._db = db

    def list_templates(self) -> dict:
        """Return grouped revision metadata for the admin Template Repo."""
        templates = []
        for versions in fmts.revision_groups(self._db):
            latest = versions[-1]
            released = next(
                (version for version in reversed(versions)
                 if version.status == fmts.ACTIVE),
                None,
            )
            templates.append({
                "id": latest.id,
                "code": latest.code,
                "title": latest.title,
                "team": {
                    "id": latest.team.id,
                    "code": latest.team.code,
                    "name": latest.team.name,
                } if latest.team else None,
                "frequency": latest.frequency,
                "frequency_label": fmts.FREQUENCY_LABELS.get(
                    latest.frequency, latest.frequency
                ),
                "latest_version": self._version_summary(latest),
                "released_version": (
                    self._version_summary(released) if released else None
                ),
                "version_count": len(versions),
                "versions": [
                    self._version_summary(version)
                    for version in reversed(versions)
                ],
            })
        return {"templates": templates, "total": len(templates)}

    @staticmethod
    def _version_summary(fmt: Format) -> dict:
        return {
            "id": fmt.id,
            "revision": fmt.revision,
            "revision_of": fmt.revision_of,
            "title": fmt.title,
            "status": fmt.status,
            "effective_date": fmt.effective_date,
            "created_at": fmt.created_at,
            "approval_status": next(
                (review.status for review in reversed(fmt.reviews)
                 if review.status in ("pending", "rejected")),
                None,
            ),
        }
