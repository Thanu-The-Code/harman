from __future__ import annotations

from typing import Optional

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from ..models import User


class ProcessScreenAccessService:
    """Centralizes access rules for the project’s root-level process screens."""

    ADMIN_ONLY_PATHS = {"/formats"}
    SCREEN_PATHS = {
        "/formats",
        "/records",
        "/records/new",
        "/storage",
        "/change-requests",
        "/track",
        "/tasks",
    }

    def resolve(self, request: Request, path: str, user: Optional[User] = None) -> Response:
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        if path in self.ADMIN_ONLY_PATHS and not user.is_admin:
            return RedirectResponse(url="/tasks", status_code=302)
        return HTMLResponse(self._render_html(path), media_type="text/html")

    def _render_html(self, path: str) -> str:
        label = path.strip("/") or "home"
        return (
            "<html><body style='font-family:sans-serif;padding:24px;'>"
            f"<h1>{label}</h1>"
            "<p>This is the project process screen.</p>"
            "<p>The API surface remains under /api/*.</p>"
            "</body></html>"
        )
