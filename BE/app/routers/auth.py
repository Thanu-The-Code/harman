"""
Authentication Router
Handles login, logout, user management, and authentication endpoints
"""

from datetime import timedelta, datetime
from typing import Optional
import json
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator

from ..database import get_db
from ..models import Department, Role, User
from ..schemas import ManagedUserCreate, UserCreate, UserResponse, UserUpdate
from ..services import account_rules
from ..services.auth_service import (
    InactiveAccountError,
    AuthService, get_current_user_from_session, get_current_user_flexible,
    require_admin_flexible, ACCESS_TOKEN_EXPIRE_MINUTES
)
from ..config import get_settings

router = APIRouter()

# Pydantic models
#
# UserCreate, UserUpdate and UserResponse live in app/schemas.py and are
# imported above. They were previously duplicated here, and the duplicates
# silently shadowed the real ones: a field added to the schema never reached
# this router, so /api/auth/me kept returning a user without their department
# or their approval permissions. One definition, in one place.
class LoginUser(BaseModel):
    username: str
    full_name: Optional[str] = None
    is_admin: bool
    role_names: list[str]


class Token(BaseModel):
    access_token: str
    token_type: str
    must_change_password: Optional[bool] = False
    user: LoginUser


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _new_password(cls, v):
        return account_rules.check_password(v)

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login", response_model=Token)
async def login(
    request: Request,
    response: Response,
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """Login endpoint"""
    auth_service = AuthService(db)

    try:
        user = auth_service.authenticate_user(login_data.username, login_data.password)
    except InactiveAccountError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Ask an administrator to reactivate it.",
        )
    if not user:
        auth_service.log_audit_event(
            user_id=None,
            action="login_failed",
            details={"username": login_data.username},
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get settings for the token lifetime and production mode
    settings = get_settings(db)

    # Create JWT token. ACCESS_TOKEN_EXPIRE_MINUTES lets a sign-in last a
    # shift; the module constant is only the fallback.
    expire_minutes = settings.access_token_expire_minutes or ACCESS_TOKEN_EXPIRE_MINUTES
    access_token_expires = timedelta(minutes=expire_minutes)
    access_token = auth_service.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    # Create session
    session_token = auth_service.create_session(
        user,
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent")
    )

    # Set session cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        max_age=24 * 60 * 60,  # 24 hours
        httponly=True,
        secure=settings.production_mode,  # Secure cookies in production
        samesite="lax"
    )

    # Log successful login
    auth_service.log_audit_event(
        user_id=user.id,
        action="login_success",
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent")
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "must_change_password": user.must_change_password,
        "user": {
            "username": user.username,
            "full_name": user.full_name,
            "is_admin": user.is_admin,
            "role_names": user.role_names,
        },
    }

@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_session)
):
    """Logout endpoint"""
    auth_service = AuthService(db)

    # Get session token from cookie
    session_token = request.cookies.get("session_token")
    if session_token:
        auth_service.invalidate_session(session_token)
    # and the bearer token this browser holds: it must not work after signing out
    bearer = request.headers.get("authorization", "")
    if bearer.lower().startswith("bearer "):
        auth_service.revoke_token(bearer[7:].strip())

    # Clear session cookie
    response.delete_cookie(key="session_token")

    # Log logout
    if current_user:
        auth_service.log_audit_event(
            user_id=current_user.id,
            action="logout",
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )

    return {"message": "Successfully logged out"}

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user_flexible)):
    """Get current user information"""
    return current_user

@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user_flexible),
    db: Session = Depends(get_db)
):
    """Change user password"""
    auth_service = AuthService(db)

    # Verify current password
    if not current_user.verify_password(password_data.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Set new password
    current_user.set_password(password_data.new_password)
    current_user.must_change_password = False  # Clear the flag
    db.commit()

    # every sign-in made with the old password ends; this one continues with a new token
    auth_service.revoke_all_tokens(current_user.id)
    token = auth_service.create_access_token(
        data={"sub": current_user.username},
        expires_delta=timedelta(minutes=get_settings().access_token_expire_minutes or ACCESS_TOKEN_EXPIRE_MINUTES))

    # Log password change
    auth_service.log_audit_event(
        user_id=current_user.id,
        action="password_changed"
    )

    return {"message": "Password changed successfully", "access_token": token, "token_type": "bearer"}

@router.get("/check-session")
async def check_session(
    current_user: User = Depends(get_current_user_from_session),
    db: Session = Depends(get_db)
):
    """Check if session is valid"""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )

    return {
        "valid": True,
        "user": {
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "is_admin": current_user.is_admin
        }
    }

# Admin endpoints
@router.post(
    "/users",
    response_model=UserResponse,
    tags=["People & Teams"],
)
async def create_user(
    user_data: ManagedUserCreate,
    current_user: User = Depends(require_admin_flexible),
    db: Session = Depends(get_db)
):
    """Create new user (admin only)"""
    auth_service = AuthService(db)

    # Check if user already exists
    existing_user = db.query(User).filter(
        (User.username == user_data.username) | (User.email == user_data.email)
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this username or email already exists"
        )

    department = None
    if user_data.department_id:
        department = (
            db.query(Department)
            .filter(Department.id == user_data.department_id)
            .first()
        )
        if not department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Selected department not found.",
            )

    selected_role = db.query(Role).filter(Role.id == user_data.role_id).first()
    if not selected_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Selected role not found",
        )
    if selected_role.name in {"admin", "editor", "viewer"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="System-managed roles cannot be assigned directly",
        )
    from ..services.role_service import STANDARD_ROLES
    if selected_role.name in STANDARD_ROLES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="System-managed standard roles cannot be assigned directly",
        )
    selected_roles = [selected_role]

    account_type = "employee"
    role_permissions = set()
    for role in selected_roles:
        if not role.permissions:
            continue
        try:
            permissions = json.loads(role.permissions)
        except (json.JSONDecodeError, TypeError) as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Role '{role.name}' contains invalid permission data",
            ) from exc
        if not isinstance(permissions, list) or not all(
            isinstance(permission, str) for permission in permissions
        ):
            raise HTTPException(
                status_code=500,
                detail=f"Role '{role.name}' contains invalid permission data",
            )
        role_permissions.update(permissions)
    user = User(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        is_admin=False,
        is_active=True,
        department=department.name if department else None,
        department_id=department.id if department else None,
        job_title=user_data.job_title,
        quality_team_id=None,
        account_type=account_type,
        can_approve=(
            "documents.approve" in role_permissions
            or "records.approve" in role_permissions
            or "change_requests.approve" in role_permissions
        ),
        can_sign="documents.sign" in role_permissions,
    )
    user.set_password(user_data.password)
    user.roles = selected_roles

    db.add(user)
    db.commit()
    db.refresh(user)

    # Log user creation
    auth_service.log_audit_event(
        user_id=current_user.id,
        action="user_created",
        resource_type="user",
        resource_id=user.id,
        details={"username": user.username, "email": user.email}
    )

    return user

@router.get("/users", response_model=list[UserResponse], tags=["People & Teams"])
async def list_users(
    current_user: User = Depends(require_admin_flexible),
    db: Session = Depends(get_db)
):
    """List all users (admin only)"""
    users = db.query(User).all()
    return users

@router.get("/users/{user_id}", response_model=UserResponse, tags=["People & Teams"])
async def get_user(
    user_id: str,
    current_user: User = Depends(require_admin_flexible),
    db: Session = Depends(get_db)
):
    """Get user by ID (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user

@router.put("/users/{user_id}", response_model=UserResponse, tags=["People & Teams"])
async def update_user(
    user_id: str,
    user_data: UserUpdate,
    current_user: User = Depends(require_admin_flexible),
    db: Session = Depends(get_db)
):
    """Update user (admin only)"""
    auth_service = AuthService(db)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Update fields
    update_data = user_data.dict(exclude_unset=True)
    if {"can_approve", "can_sign", "account_type"} & update_data.keys():
        raise HTTPException(
            status_code=409,
            detail="Access and approval permissions are controlled by the assigned role",
        )

    # Handle password separately
    password_reset = bool(update_data.get('password'))
    if password_reset:
        user.set_password(update_data['password'])
    update_data.pop('password', None)

    if "department_id" in update_data:
        department_id = update_data.pop("department_id")
        department = (
            db.query(Department).filter(Department.id == department_id).first()
            if department_id
            else None
        )
        if department_id and not department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Selected department not found.",
            )
        if "department" in update_data and update_data["department"] != (
            department.name if department else None
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Send either department or department_id, not both.",
            )
        user.department_id = department.id if department else None
        user.department = department.name if department else None
    elif "department" in update_data:
        user.department_id = None

    # Update other profile fields; account_type and approval authority are
    # derived from the selected role and cannot be changed independently.
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    if password_reset or update_data.get("is_active") is False:
        auth_service.revoke_all_tokens(user.id)  # reset or closed: their sign-ins end now

    db.refresh(user)

    # Log user update
    auth_service.log_audit_event(
        user_id=current_user.id,
        action="user_updated",
        resource_type="user",
        resource_id=user.id,
        details=update_data
    )

    return user

@router.delete("/users/{user_id}", tags=["People & Teams"])
async def delete_user(
    user_id: str,
    current_user: User = Depends(require_admin_flexible),
    db: Session = Depends(get_db)
):
    """Delete user (admin only)"""
    auth_service = AuthService(db)

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Log user deletion before deleting
    auth_service.log_audit_event(
        user_id=current_user.id,
        action="user_deleted",
        resource_type="user",
        resource_id=user.id,
        details={"username": user.username, "email": user.email}
    )

    db.delete(user)
    db.commit()

    return {"message": "User deleted successfully"}

@router.get("/setup/check")
async def check_setup_status(db: Session = Depends(get_db)):
    """Check if initial setup is complete"""
    user_count = db.query(User).count()
    return {
        "setup_complete": user_count > 0,
        "user_count": user_count
    }

@router.post("/setup/initial-user")
async def create_initial_user(
    request: Request,
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """Create initial admin user during setup"""
    # Check if any users exist
    user_count = db.query(User).count()
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Initial setup already completed"
        )

    auth_service = AuthService(db)

    # Create admin user
    try:
        user = auth_service.create_admin_user(
            username=user_data.username,
            email=user_data.email,
            password=user_data.password,
            full_name=user_data.full_name
        )

        # Log initial setup
        auth_service.log_audit_event(
            user_id=user.id,
            action="initial_setup",
            details={"username": user.username, "email": user.email},
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )

        return {"message": "Initial admin user created successfully", "user_id": user.id}

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )