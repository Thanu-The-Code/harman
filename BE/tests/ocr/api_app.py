"""The OCR router mounted on a bare app at /ocr, signed in as an administrator.

The HTTP tests exercise app/routers/ocr.py itself (routing, status codes, the worker thread);
sign-in and the database are covered elsewhere, so both are stubbed here.
"""
from fastapi import FastAPI

from app.database import get_db
from app.routers import ocr as ocr_router
from app.services.auth_service import get_current_user_flexible


class _Admin:
    id = 1
    is_admin = True

    def has_permission(self, _permission):
        return True


class _NoDatabase:
    """Swallows the audit entry the template endpoint writes."""

    def add(self, *_):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass

    def refresh(self, *_):
        pass

    def close(self):
        pass


app = FastAPI()
app.include_router(ocr_router.router, prefix="/ocr")
app.dependency_overrides[get_current_user_flexible] = lambda: _Admin()
app.dependency_overrides[get_db] = lambda: _NoDatabase()
