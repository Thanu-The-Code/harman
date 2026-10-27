import os
import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL
from typing import Optional, Any
from sqlalchemy.orm import Session

class Settings(BaseSettings):
    app_name: str = "Paperless Factory"
    template_builder_label: str = "Template Builder"
    resources_library_label: str = "Resources Library"
    my_documents_label: str = "My Documents"
    document_repository_label: str = "Document Repository"
    people_and_teams_label: str = "People & Teams"

    # Database
    database_host: Optional[str] = "localhost"  
    database_port: int = 5432
    database_name: str = "paperless_factory"
    database_user: str = "postgres"
    database_password: Optional[str] = None
    database_url: Optional[str] = None

    # File paths
    root_folder: Optional[str] = None
    staging_folder: str = "./data/staging"
    data_folder: str = "./data"
    storage_folder: str = "./data/storage"
    logs_folder: str = "./data/logs"
    backup_folder: str = "./data/backups"

    # File settings
    max_file_size: str = "100MB"
    allowed_extensions: str = "pdf,png,jpg,jpeg,tiff,bmp,txt,text,md,markdown"

    # Security
    # Do NOT ship a static, well-known default secret_key. Anything signed
    # with this key would be forgeable by anyone who has read the source.
    # When unset, a per-process random key is generated; admins should
    # configure a stable value via the database settings table (the
    # DatabaseSettings loader will override this).
    secret_key: str = secrets.token_urlsafe(32)
    jwt_secret_key: Optional[str] = None  # JWT secret key for authentication
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    environment: str = "development"
    production_mode: bool = False  # Set to True in production for secure cookies
    # fail closed: a deployment that lost its .env must not run open as an administrator
    authentication_enabled: bool = True
    cors_origins: str = "http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000"
    trusted_proxy_ips: str = "127.0.0.1,::1"

    # Logging
    log_level: str = "INFO"

    # ------------------------------------------------------------------ mail
    #
    # The document flow asks for trigger emails at the approval checkpoints in
    # the Paperless Factory process, including the approval and review stages.
    #
    # Every one of those is recorded in the `notifications` table before any
    # attempt to send. With no host configured the notification is marked
    # "skipped" rather than "failed": the process still runs, the trail is
    # still complete, and nobody is blocked waiting for a mail server.
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: bool = True
    smtp_from: Optional[str] = None
    smtp_from_name: str = "Paperless Factory"
    smtp_timeout: int = 20
    # The address every trigger is copied to, if the site wants one place to
    # watch the process from. Optional.
    notifications_copy_to: Optional[str] = None
    # Where links in the emails point.
    app_base_url: str = "http://127.0.0.1:8000"

    # AI Service
    # Security
    # Do NOT ship a static, well-known default secret_key. Anything signed
    # with this key would be forgeable by anyone who has read the source.
    # When unset, a per-process random key is generated; admins should
    # configure a stable value via the database settings table (the
    # DatabaseSettings loader will override this).
    secret_key: str = secrets.token_urlsafe(32)
    jwt_secret_key: Optional[str] = None  # JWT secret key for authentication
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    environment: str = "development"
    production_mode: bool = False  # Set to True in production for secure cookies
    cors_origins: str = "http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000"
    trusted_proxy_ips: str = "127.0.0.1,::1"

    # Logging
    log_level: str = "INFO"

    # ------------------------------------------------------------------ mail
    #
    # The document flow asks for trigger emails at the approval checkpoints in
    # the Paperless Factory process, including the approval and review stages.
    #
    # Every one of those is recorded in the `notifications` table before any
    # attempt to send. With no host configured the notification is marked
    # "skipped" rather than "failed": the process still runs, the trail is
    # still complete, and nobody is blocked waiting for a mail server.
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: bool = True
    smtp_from: Optional[str] = None
    smtp_from_name: str = "Paperless Factory"
    smtp_timeout: int = 20
    # The address every trigger is copied to, if the site wants one place to
    # watch the process from. Optional.
    notifications_copy_to: Optional[str] = None
    # Where links in the emails point.
    app_base_url: str = "http://127.0.0.1:8000"

    model_config = SettingsConfigDict(
        # Runtime values may be supplied by Docker/Kubernetes environment
        # variables, or by a local .env file for development. Real environment
        # variables take precedence over .env; database-backed settings then
        # override both.
        case_sensitive=False,
        env_file=os.getenv("DOCUMENT_MANAGER_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        env_prefix=""
    )

    def model_post_init(self, __context: Any) -> None:
        self.database_url = self.database_url or self._build_database_url()

        # Apply config/models.json on top of the code defaults, but never on
        # top of an explicitly supplied value (env var or constructor kwarg).
        # Effective precedence: code default < models.json < env < database.
        self._apply_model_config_defaults()

        # Keep the existing ENVIRONMENT=production setup contract while still
        # allowing an explicit PRODUCTION_MODE value to override it.
        if "production_mode" not in self.model_fields_set:
            self.production_mode = self.environment.lower() == "production"

    def _build_database_url(self) -> str:
        url = URL.create(
            "postgresql+psycopg",
            username=self.database_user or "postgres",
            password=self.database_password,
            host=self.database_host or "localhost",
            port=self.database_port,
            database=(self.database_name or "paperless_factory").strip(),
        )
        return url.render_as_string(hide_password=False)

    def _apply_model_config_defaults(self) -> None:
        """Overlay values from ``config/models.json`` onto unset fields."""
        try:
            from .services.model_config import as_settings_overrides

            overrides = as_settings_overrides()
        except Exception as exc:  # pragma: no cover - defensive only
            from loguru import logger

            logger.warning(f"Could not apply model config defaults: {exc}")
            return

        for key, value in overrides.items():
            if key in self.model_fields_set:
                continue  # explicit env/kwarg wins
            if not hasattr(self, key):
                continue
            try:
                object.__setattr__(self, key, value)
            except Exception:  # pragma: no cover - defensive only
                continue

    @property
    def allowed_extensions_list(self) -> list:
        return [ext.strip().lower() for ext in self.allowed_extensions.split(",")]

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def trusted_proxy_ips_list(self) -> list[str]:
        return [ip.strip() for ip in self.trusted_proxy_ips.split(",") if ip.strip()]

    @property
    def max_file_size_bytes(self) -> int:
        size_str = self.max_file_size.upper()
        if size_str.endswith("MB"):
            return int(size_str[:-2]) * 1024 * 1024
        elif size_str.endswith("GB"):
            return int(size_str[:-2]) * 1024 * 1024 * 1024
        else:
            return int(size_str)

    @property
    def data_dir(self) -> str:
        return self.data_folder

    @property
    def mail_available(self) -> bool:
        """True when a trigger email can actually leave the building."""
        return bool(self.smtp_host and (self.smtp_from or self.smtp_username))

class DatabaseSettings(Settings):
    """Settings that loads configuration from database"""

    def __init__(self, db: Session = None, **kwargs):
        # Load defaults, .env and runtime environment variables first.
        # Persisted application settings take precedence when a database is
        # available.
        super().__init__(**kwargs)

        # Then override with database values if available
        if db:
            self._load_from_database(db)

    def _load_from_database(self, db: Session):
        """Load settings from database"""
        from .models import Settings as SettingsModel

        # Get all settings from database
        db_settings = db.query(SettingsModel).all()

        # Convert to dict
        settings_dict = {setting.key: setting.value for setting in db_settings}

        # Update instance attributes
        for key, value in settings_dict.items():
            if hasattr(self, key):
                # Try to preserve type
                attr_value = getattr(self, key)
                try:
                    if isinstance(attr_value, bool):
                        setattr(self, key, str(value).lower() in ('true', '1', 'yes'))
                    elif isinstance(attr_value, int):
                        setattr(self, key, int(value))
                    elif isinstance(attr_value, float):
                        setattr(self, key, float(value))
                    else:
                        # For optional string fields, don't set empty strings
                        if value or not key.endswith('_api_key'):
                            setattr(self, key, value)
                except (ValueError, AttributeError, TypeError):
                    setattr(self, key, value)

    def save_to_database(self, db: Session, key: str, value: Any):
        """Save a single setting to database"""
        from .models import Settings as SettingsModel

        # Check if setting exists
        setting = db.query(SettingsModel).filter(SettingsModel.key == key).first()

        if setting:
            setting.value = str(value)
        else:
            setting = SettingsModel(key=key, value=str(value))
            db.add(setting)

        db.commit()

    def save_all_to_database(self, db: Session):
        """Save all current settings to database"""

        # Get all fields
        for field_name, field_value in self.__dict__.items():
            if not field_name.startswith('_'):
                self.save_to_database(db, field_name, field_value)

# Global settings instance
_settings = None

def get_settings(db: Session = None) -> Settings:
    """Get settings instance, optionally loading from database"""
    global _settings

    # If db is provided, always create fresh instance to get latest values
    if db:
        return DatabaseSettings(db=db)

    # Otherwise use cached instance
    if _settings is None:
        _settings = Settings()

    return _settings

def reset_settings():
    """Reset the global settings instance"""
    global _settings
    _settings = None

    # Also drop the model-config cache so an edited config/models.json is
    # picked up by the next get_settings() call.
    try:
        from .services.model_config import reset_model_config

        reset_model_config()
    except Exception:  # pragma: no cover - defensive only
        pass
