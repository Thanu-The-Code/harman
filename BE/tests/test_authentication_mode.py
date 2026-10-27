import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.database import Base
from app.models import User
from app.routers.formats import TeamPayload, create_team
from app.services.auth_service import get_current_user_flexible, require_admin_flexible


def _request_without_credentials():
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/documents",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
        }
    )


def test_api_auth_can_be_disabled_for_local_requests(monkeypatch):
    monkeypatch.setenv("AUTHENTICATION_ENABLED", "false")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    try:
        with session_factory() as db:
            admin = User(
                username="admin",
                email="admin@example.com",
                full_name="Local Admin",
                is_admin=True,
                is_active=True,
            )
            admin.set_password("unused")
            db.add(admin)
            db.commit()

            current_user = asyncio.run(
                get_current_user_flexible(
                    _request_without_credentials(),
                    db,
                    credentials=None,
                )
            )

            assert current_user.id == admin.id
            assert current_user.is_admin
            assert current_user.has_permission("documents.read")
    finally:
        engine.dispose()


def test_api_auth_bypass_works_without_any_user_accounts(monkeypatch):
    monkeypatch.setenv("AUTHENTICATION_ENABLED", "false")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    try:
        with session_factory() as db:
            current_user = asyncio.run(
                get_current_user_flexible(
                    _request_without_credentials(),
                    db,
                    credentials=None,
                )
            )

            assert current_user.id is None
            assert current_user.is_admin
            assert current_user.has_permission("documents.read")
            assert db.query(User).count() == 0

            require_admin_flexible(current_user)
            created = create_team(
                TeamPayload(code="OPS", name="Operations"),
                db=db,
            )

            assert created["code"] == "OPS"
            assert db.query(User).count() == 0
    finally:
        engine.dispose()
