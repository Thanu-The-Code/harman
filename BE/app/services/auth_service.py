"""
Authentication and Authorization Service
Handles user authentication, session management, and RBAC
"""

import secrets
import uuid
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, status, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import User, Session as UserSession, AuditLog
from ..database import get_db
from ..utils.logging_config import log_security_event
from loguru import logger

# Security configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


def _token_lifetime_minutes() -> int:
    """How long a sign-in token lasts (ACCESS_TOKEN_EXPIRE_MINUTES in the environment)."""
    from ..config import get_settings

    return get_settings().access_token_expire_minutes or ACCESS_TOKEN_EXPIRE_MINUTES
SESSION_EXPIRE_HOURS = 24

def get_secret_key(db: Session) -> str:
    """Get JWT secret key from database settings"""
    from ..config import get_settings
    settings = get_settings(db)
    # Generate a secure random key if not set
    if not hasattr(settings, 'jwt_secret_key') or not settings.jwt_secret_key:
        secret_key = secrets.token_urlsafe(32)
        # Save to database
        from ..models import Settings
        setting = db.query(Settings).filter(Settings.key == "jwt_secret_key").first()
        if not setting:
            setting = Settings(key="jwt_secret_key", value=secret_key, description="JWT secret key for authentication")
            db.add(setting)
        else:
            setting.value = secret_key
        db.commit()
        return secret_key
    return settings.jwt_secret_key

security = HTTPBearer(auto_error=False)


class InactiveAccountError(Exception):
    """The right password for an account an administrator has deactivated."""

class AuthService:
    """Authentication and Authorization Service"""

    def __init__(self, db: Session):
        self.db = db

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        # jti / iat: so a token can be revoked (signed out) before it expires
        now = datetime.now(timezone.utc)  # aware: a naive time's timestamp() would be local time
        # iat is whole seconds; "iat_us" says exactly when, so a token issued the moment
        # after a revocation (a password change) is told apart from one just before it
        to_encode.update({"exp": expire, "iat": now, "iat_us": int(now.timestamp() * 1_000_000),
                          "jti": uuid.uuid4().hex})
        secret_key = get_secret_key(self.db)
        encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
        return encoded_jwt

    def _claims(self, token: str) -> Optional[dict]:
        """The token's claims if it is genuine, unexpired and not revoked."""
        try:
            payload = jwt.decode(token, get_secret_key(self.db), algorithms=[ALGORITHM],
                                 options={"require_exp": True, "require_sub": True})
        except JWTError:
            return None
        from ..models import TokenRevocation, User as UserModel

        jti = payload.get("jti")
        if jti and self.db.query(TokenRevocation.id).filter(TokenRevocation.jti == jti).first():
            return None
        issued = (payload["iat_us"] / 1_000_000 if payload.get("iat_us") is not None
                  else payload.get("iat"))
        user = self.db.query(UserModel.id).filter(UserModel.username == payload["sub"]).first()
        if user is not None:
            cutoff = (self.db.query(func.max(TokenRevocation.revoked_before))
                      .filter(TokenRevocation.user_id == user.id).scalar())
            # a token without iat predates revocation; it cannot be shown to be newer
            if cutoff and (issued is None or datetime.utcfromtimestamp(issued) < cutoff):
                return None
        return payload

    def verify_token(self, token: str) -> Optional[str]:
        """Verify JWT token and return username"""
        claims = self._claims(token)
        return claims.get("sub") if claims else None

    def revoke_token(self, token: str) -> None:
        """Sign this one token out (it stays revoked until it would have expired)."""
        from ..models import TokenRevocation

        claims = self._claims(token)
        if not claims or not claims.get("jti"):
            return
        self.db.add(TokenRevocation(jti=claims["jti"], expires_at=datetime.utcfromtimestamp(claims["exp"])))
        self._forget_expired()
        self.db.commit()

    def revoke_all_tokens(self, user_id: str) -> None:
        """Every token this person holds now stops counting (password changed, account closed)."""
        from ..models import TokenRevocation

        now = datetime.utcnow()
        self.db.add(TokenRevocation(user_id=user_id, revoked_before=now,
                                    expires_at=now + timedelta(minutes=_token_lifetime_minutes())))
        self._forget_expired()
        self.db.commit()

    def _forget_expired(self) -> None:
        from ..models import TokenRevocation

        self.db.query(TokenRevocation).filter(TokenRevocation.expires_at < datetime.utcnow()).delete()

    def authenticate_user(self, username: str, password: str, ip_address: str = None, user_agent: str = None) -> Optional[User]:
        """Authenticate user with username/password"""
        user = self.db.query(User).filter(
            (User.username == username) | (User.email == username)
        ).first()

        if not user:
            # Log failed login attempt - user not found
            log_security_event(
                event_type="login_failed_user_not_found",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"attempted_username": username[:50]}  # Truncate for security
            )
            logger.warning(f"Login attempt with non-existent username: {username[:20]}...")
            return None

        if not user.verify_password(password):
            # Log failed login attempt - wrong password
            log_security_event(
                event_type="login_failed_wrong_password",
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"username": user.username}
            )
            logger.warning(f"Failed login attempt for user: {user.username}")
            return None

        if not user.is_active:
            # Log failed login attempt - inactive user
            log_security_event(
                event_type="login_failed_inactive_user",
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"username": user.username}
            )
            logger.warning(f"Login attempt for inactive user: {user.username}")
            # the password was right, so saying why reveals nothing to somebody guessing
            raise InactiveAccountError(user.username)

        # Successful authentication
        log_security_event(
            event_type="login_successful",
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"username": user.username}
        )
        logger.info(f"Successful login for user: {user.username}")

        # Update last login
        user.last_login = datetime.utcnow()
        self.db.commit()

        return user

    def create_session(self, user: User, ip_address: str = None, user_agent: str = None) -> str:
        """Create user session"""
        session_token = secrets.token_urlsafe(32)

        session = UserSession(
            user_id=user.id,
            session_token=session_token,
            expires_at=datetime.utcnow() + timedelta(hours=SESSION_EXPIRE_HOURS),
            ip_address=ip_address,
            user_agent=user_agent
        )

        self.db.add(session)
        self.db.commit()

        return session_token

    def get_session(self, session_token: str) -> Optional[UserSession]:
        """Get valid session"""
        session = self.db.query(UserSession).filter(
            UserSession.session_token == session_token,
            UserSession.expires_at > datetime.utcnow()
        ).first()

        return session

    def invalidate_session(self, session_token: str):
        """Invalidate session"""
        session = self.db.query(UserSession).filter(
            UserSession.session_token == session_token
        ).first()

        if session:
            self.db.delete(session)
            self.db.commit()

    def cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        self.db.query(UserSession).filter(
            UserSession.expires_at <= datetime.utcnow()
        ).delete()
        self.db.commit()

    def log_audit_event(self, user_id: str, action: str, resource_type: str = None,
                       resource_id: str = None, details: dict = None,
                       ip_address: str = None, user_agent: str = None):
        """Log audit event"""
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=ip_address,
            user_agent=user_agent
        )

        self.db.add(audit_log)
        self.db.commit()

    def create_default_roles(self):
        """Compatibility no-op: roles are created by an administrator."""
        return None

    def create_admin_user(self, username: str, email: str, password: str, full_name: str = None) -> User:
        """Create admin user"""
        # Check if user already exists
        existing_user = self.db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()

        if existing_user:
            raise ValueError("User with this username or email already exists")

        # Create user
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            is_admin=True,
            is_active=True
        )
        user.set_password(password)

        self.db.add(user)
        self.db.flush()  # Get the user ID

        self.db.commit()
        return user

# Dependency to get current user from token
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current user from JWT token"""
    if not _authentication_enabled():
        return _get_auth_bypass_user(db)

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_exception

    try:
        auth_service = AuthService(db)
        username = auth_service.verify_token(credentials.credentials)
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise credentials_exception

    return user

# Dependency to get current user from session
def get_user_from_session_token(
    request: Request,
    db: Session
) -> Optional[User]:
    """Get current user from session cookie (without FastAPI dependency)"""
    session_token = request.cookies.get("session_token")
    if not session_token:
        return None

    auth_service = AuthService(db)
    session = auth_service.get_session(session_token)
    if not session:
        return None

    user = db.query(User).filter(User.id == session.user_id).first()
    if not user or not user.is_active:
        return None

    return user

async def get_current_user_from_session(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current user from session cookie (FastAPI dependency)"""
    if not _authentication_enabled():
        return _get_auth_bypass_user(db)
    return get_user_from_session_token(request, db)


def _authentication_enabled() -> bool:
    from ..config import get_settings

    return get_settings().authentication_enabled


def _get_auth_bypass_user(db: Session) -> User:
    user = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.is_admin.desc(), User.id)
        .first()
    )
    if user is not None and user.is_admin:
        return user

    # Authentication-off mode uses an ephemeral administrator-shaped
    # principal. It is deliberately not persisted or usable to log in; null
    # identity fields let audit/ownership columns remain explicitly anonymous.
    return User(
        id=None,
        username="unauthenticated-local-api",
        email="unauthenticated-local-api@localhost",
        full_name="Unauthenticated local API request",
        hashed_password="",
        is_active=True,
        is_admin=True,
        account_type="administrator",
        can_approve=True,
        can_sign=True,
    )


# Flexible authentication that supports both JWT and session
async def get_current_user_flexible(
    request: Request,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))
) -> User:
    """Get current user from either JWT token or session cookie"""
    if not _authentication_enabled():
        return _get_auth_bypass_user(db)

    user = None

    # Try JWT authentication first
    if credentials:
        try:
            auth_service = AuthService(db)
            username = auth_service.verify_token(credentials.credentials)
            if username:
                user = db.query(User).filter(User.username == username).first()
                if user and user.is_active:
                    return user
        except Exception:
            pass  # Fall through to session authentication

    # Try session authentication
    user = get_user_from_session_token(request, db)
    if user and user.is_active:
        return user

    # Neither authentication method worked
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

# Permission checker dependency
def require_permission(permission: str):
    """Dependency factory for permission checking"""
    def permission_checker(current_user: User = Depends(get_current_user)):
        if not current_user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}"
            )
        return current_user
    return permission_checker

# Flexible permission checker that supports both JWT and session authentication
def require_permission_flexible(permission: str):
    """Dependency factory for permission checking with flexible authentication"""
    def permission_checker(current_user: User = Depends(get_current_user_flexible)):
        if not current_user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}"
            )
        return current_user
    return permission_checker

def require_document_delete_flexible(
    current_user: User = Depends(get_current_user_flexible),
) -> User:
    # Allow document deletion only to upload-and-edit users or administrators."
    if current_user.is_admin or (
        current_user.has_permission("documents.create")
        and current_user.has_permission("documents.update")
    ):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Document deletion requires upload and edit access",
    )

# Admin only dependency
def require_admin(current_user: User = Depends(get_current_user)):
    """Dependency for admin-only endpoints"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

def require_admin_flexible(current_user: User = Depends(get_current_user_flexible)):
    """Dependency for admin-only endpoints with flexible authentication"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user