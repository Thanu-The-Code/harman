"""Read-side operations for the latest template revisions in the Resource Library."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..models import User
from ..models_qms import Format
from . import format_service as fmts


class ResourceLibraryService:
    """Select the latest revision for each template visible in the library."""

    def __init__(self, db: Session):
        self._db = db

    def list_for_user(
        self,
        user: User,
        *,
        team_id: Optional[str] = None,
        status: Optional[str] = None,
        query: str = "",
        mine: bool = False,
    ) -> list[Format]:
        """Return one latest revision per template, respecting library access."""
        fmts.ensure_teams(self._db)
        if not user.is_admin and status not in (None, fmts.ACTIVE):
            return []

        requested_status = status if user.is_admin else fmts.ACTIVE
        latest_ids = {
            versions[-1].id
            for versions in fmts.revision_groups(self._db)
        }
        formats = fmts.list_formats(
            self._db,
            team_id=team_id,
            status=requested_status,
            query=query,
            owner=user if mine else None,
        )
        return [fmt for fmt in formats if fmt.id in latest_ids]
