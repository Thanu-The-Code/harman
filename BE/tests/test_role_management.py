from fastapi.testclient import TestClient
from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import ApprovalStep, Role, User
from app.routers.formats import (
    require_formats_manage_permission,
    require_formats_read_permission,
)
from app.services.workflow_service import can_act


def test_legacy_role_migration_preserves_custom_roles_and_does_not_reseed():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    from app.services.auth_service import AuthService
    from app.services.role_service import ensure_standard_roles, remove_legacy_roles

    with session_factory() as db:
        legacy_role = Role(
            name="reader",
            description="Old built-in reader role",
            permissions='["documents.read"]',
        )
        custom_role = Role(
            name="Quality CFT",
            description="Administrator-created role",
            permissions='["documents.read", "documents.approve", "documents.sign"]',
        )
        admin_role = Role(
            name="admin",
            description="Old built-in admin role",
            permissions='["*"]',
        )
        legacy_user = User(
            username="legacy",
            email="legacy@example.com",
            hashed_password="hashed",
            account_type="signatory",
            can_approve=True,
            can_sign=True,
        )
        custom_user = User(
            username="custom",
            email="custom@example.com",
            hashed_password="hashed",
            account_type="signatory",
            can_approve=False,
            can_sign=False,
        )
        admin_user = User(
            username="admin",
            email="admin@example.com",
            hashed_password="hashed",
            is_admin=True,
        )
        legacy_user.roles.append(legacy_role)
        custom_user.roles.append(custom_role)
        admin_user.roles.append(admin_role)
        db.add_all([legacy_user, custom_user, admin_user])
        db.commit()
        legacy_user_id = legacy_user.id
        custom_user_id = custom_user.id
        admin_user_id = admin_user.id
        custom_role_id = custom_role.id

        assert remove_legacy_roles(db) == 2
        AuthService(db).create_default_roles()
        assert ensure_standard_roles(db) == 0

        assert db.query(Role).filter(Role.name.in_(["reader", "admin"])).count() == 0
        assert db.query(Role).filter(Role.id == custom_role_id).one().name == "Quality CFT"
        assert db.query(Role).count() == 1

        migrated_legacy = db.query(User).filter(User.id == legacy_user_id).one()
        assert migrated_legacy.roles == []
        assert migrated_legacy.account_type == "employee"
        assert migrated_legacy.can_approve is False
        assert migrated_legacy.can_sign is False

        migrated_custom = db.query(User).filter(User.id == custom_user_id).one()
        assert [role.id for role in migrated_custom.roles] == [custom_role_id]
        assert migrated_custom.account_type == "employee"
        assert migrated_custom.can_approve is True
        assert migrated_custom.can_sign is True

        migrated_admin = db.query(User).filter(User.id == admin_user_id).one()
        assert migrated_admin.is_admin is True
        assert migrated_admin.roles == []
    engine.dispose()


def test_role_crud_and_assignment_grant_permissions(monkeypatch):
    monkeypatch.setenv("AUTHENTICATION_ENABLED", "false")
    create_user_schema = app.openapi()["components"]["schemas"]["ManagedUserCreate"]
    assert set(create_user_schema["properties"]) == {
        "username",
        "email",
        "full_name",
        "password",
        "role_id",
        "department_id",
        "job_title",
    }
    assert set(create_user_schema["required"]) == {
        "username",
        "email",
        "full_name",
        "password",
        "role_id",
    }

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        created = client.post(
            "/api/roles",
            json={
                "name": "quality reviewer",
                "description": "Can review and approve records",
                "permissions": ["documents.view", "approvals.approve"],
            },
        )
        assert created.status_code == 201
        role = created.json()
        assert role["assignable"] is True
        assert role["permissions"] == ["approvals.approve", "documents.view"]
        full_access = client.post(
            "/api/roles",
            json={
                "name": "Full Workflow Access",
                "description": "All custom-role capabilities",
                "permissions": [
                    "documents.view",
                    "records.fill",
                    "templates.create",
                    "approvals.approve",
                ],
            },
        )
        assert full_access.status_code == 201, full_access.text
        assert full_access.json()["permissions"] == [
            "approvals.approve",
            "documents.view",
            "records.fill",
            "templates.create",
        ]
        permission_options = client.get("/api/roles/permissions").json()
        assert [item["key"] for item in permission_options] == [
            "documents.view",
            "records.fill",
            "templates.create",
            "approvals.approve",
        ]
        approval_option = next(
            item for item in permission_options
            if item["key"] == "approvals.approve"
        )
        assert approval_option["description"] == "Approval"

        department_response = client.post(
            "/api/departments",
            json={"name": "Quality Assurance"},
        )
        assert department_response.status_code == 201, department_response.text
        department = department_response.json()
        assert department["name"] == "Quality Assurance"
        assert client.get("/api/departments").json()["departments"] == [department]
        duplicate_department = client.post(
            "/api/departments",
            json={"name": "quality assurance"},
        )
        assert duplicate_department.status_code == 409

        invalid_role = client.post(
            "/api/roles",
            json={"name": "bad role", "permissions": ["documents.delete"]},
        )
        assert invalid_role.status_code == 422
        assert all(
            not system_role["assignable"]
            for system_role in client.get("/api/roles").json()
            if system_role["name"] in {"reader", "approver", "signatory"}
        )

        missing_role = client.post(
            "/api/auth/users",
            json={
                "username": "role-required",
                "email": "role-required@example.com",
                "full_name": "Role Required",
                "password": "SafePass123!",
            },
        )
        assert missing_role.status_code == 422

        user_response = client.post(
            "/api/auth/users",
            json={
                "username": "reviewer",
                "email": "reviewer@example.com",
                "full_name": "Quality Reviewer",
                "password": "SafePass123!",
                "role_id": role["id"],
                "department_id": department["id"],
                "job_title": "Quality Engineer",
            },
        )
        assert user_response.status_code == 200, user_response.text
        assert user_response.json()["full_name"] == "Quality Reviewer"
        assert user_response.json()["department"] == "Quality Assurance"
        assert user_response.json()["department_id"] == department["id"]
        assert user_response.json()["job_title"] == "Quality Engineer"
        user_id = user_response.json()["id"]
        assert role["id"] in user_response.json()["role_ids"]
        assert "documents.approve" in user_response.json()["permissions"]
        assert "documents.sign" in user_response.json()["permissions"]
        assert "documents.read" in user_response.json()["permissions"]

        login_response = client.post(
            "/api/auth/login",
            json={"username": "reviewer", "password": "SafePass123!"},
        )
        assert login_response.status_code == 200, login_response.text
        login_body = login_response.json()
        login_user = login_body["user"]
        assert login_body["access_token"]
        assert login_body["token_type"] == "bearer"
        assert login_user == {
            "username": "reviewer",
            "full_name": "Quality Reviewer",
            "is_admin": False,
            "role_names": ["quality reviewer"],
        }
        assert "id" not in login_user
        assert "role_ids" not in login_user
        assert "permissions" not in login_user

        linked_department_delete = client.delete(
            f"/api/departments/{department['id']}"
        )
        assert linked_department_delete.status_code == 409

        unused_department = client.post(
            "/api/departments",
            json={"name": "Unused Department"},
        )
        assert unused_department.status_code == 201, unused_department.text
        deleted_department = client.delete(
            f"/api/departments/{unused_department.json()['id']}"
        )
        assert deleted_department.status_code == 200
        assert deleted_department.json()["message"] == "Department deleted successfully."
        missing_department = client.delete(
            f"/api/departments/{unused_department.json()['id']}"
        )
        assert missing_department.status_code == 404

        with session_factory() as db:
            user = db.query(User).filter(User.id == user_id).one()
            assert user.department == "Quality Assurance"
            assert user.department_id == department["id"]
            assert user.job_title == "Quality Engineer"
            assert user.has_permission("documents.approve")
            assert user.has_permission("documents.sign")
            assert user.has_permission("formats.read")
            assert user.can_approve
            assert user.can_sign
            signed_step = ApprovalStep(
                name="Approval requiring signature",
                status="current",
                requires_signature=True,
            )
            assert can_act(user, signed_step) == (True, "")
            assert require_formats_read_permission(user) is user
            with pytest.raises(HTTPException) as exc_info:
                require_formats_manage_permission(user)
            assert exc_info.value.status_code == 403

        blocked_delete = client.delete(f"/api/roles/{role['id']}")
        assert blocked_delete.status_code == 409

        updated = client.put(
            f"/api/roles/{role['id']}",
            json={"permissions": ["records.fill"]},
        )
        assert updated.status_code == 200
        with session_factory() as db:
            user = db.query(User).filter(User.id == user_id).one()
            assert user.has_permission("records.fill")
            assert not user.has_permission("documents.approve")
            assert not user.can_approve
            assert not user.can_sign
            assert can_act(
                user,
                ApprovalStep(
                    name="Approval requiring signature",
                    status="current",
                    requires_signature=True,
                ),
            )[0] is False

        reassigned = client.put(
            f"/api/roles/users/{user_id}",
            json={"role_id": role["id"]},
        )
        assert reassigned.status_code == 200
        assert "records.fill" in reassigned.json()["effective_permissions"]

        unassigned = client.put(
            f"/api/roles/users/{user_id}",
            json={"role_ids": []},
        )
        assert unassigned.status_code == 200
        with session_factory() as db:
            user = db.query(User).filter(User.id == user_id).one()
            assert not user.has_permission("records.fill")
            with pytest.raises(HTTPException) as exc_info:
                require_formats_manage_permission(user)
            assert exc_info.value.status_code == 403

        deleted = client.delete(f"/api/roles/{role['id']}")
        assert deleted.status_code == 200

        template_role = client.post(
            "/api/roles",
            json={
                "name": "Template Author",
                "permissions": ["templates.create"],
            },
        )
        assert template_role.status_code == 201
        assert template_role.json()["permissions"] == ["templates.create"]
        template_assigned = client.put(
            f"/api/roles/users/{user_id}",
            json={"role_id": template_role.json()["id"]},
        )
        assert template_assigned.status_code == 200
        with session_factory() as db:
            user = db.query(User).filter(User.id == user_id).one()
            assert user.has_permission("formats.manage")
            assert require_formats_manage_permission(user) is user
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
