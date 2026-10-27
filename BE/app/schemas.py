from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime

from .services import account_rules

# Base schemas
class CorrespondentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = None

class CorrespondentCreate(CorrespondentBase):
    pass

class CorrespondentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = None

class Correspondent(CorrespondentBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

# DocType schemas
class DocTypeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None

class DocTypeCreate(DocTypeBase):
    pass

class DocTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None

class DocType(DocTypeBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

# Tag schemas
class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    color: Optional[str] = Field(None, max_length=7)  # hex color

class TagCreate(TagBase):
    pass

class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    color: Optional[str] = Field(None, max_length=7)

class Tag(TagBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

# Extended schemas with document counts
class CorrespondentWithCount(Correspondent):
    document_count: int = 0

class DocTypeWithCount(DocType):
    document_count: int = 0

class TagWithCount(Tag):
    document_count: int = 0


class DocumentFolderBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    parent_id: Optional[str] = None


class DocumentFolderCreate(DocumentFolderBase):
    pass


class DocumentFolder(DocumentFolderBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class TagAddRequest(BaseModel):
    """
    Tags to put on a document.

    Both spellings are accepted because both were already in use: the Review
    screen sends `tag_names`, the API tests send `tag_name`, and the endpoint
    previously took an untyped dict and read only the singular - so one of the
    two silently failed with a 400 and no clue as to why.
    """
    tag_name: Optional[str] = Field(None, max_length=255)
    tag_names: List[str] = Field(default_factory=list)


class TagAddResponse(BaseModel):
    message: str
    tag_id: Optional[str] = None
    tag_ids: List[str] = Field(default_factory=list)
    added: List[Tag] = Field(default_factory=list)
    already_present: List[Tag] = Field(default_factory=list)
    # The document's full tag list afterwards, so a caller can render the
    # result without a second round trip to find out what it now has.
    tags: List[Tag] = Field(default_factory=list)

# Document schemas
class DocumentBase(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    document_date: Optional[datetime] = None
    is_tax_relevant: bool = False
    reminder_date: Optional[datetime] = None
    notes: Optional[str] = None
    correspondent_id: Optional[str] = None
    doctype_id: Optional[str] = None
    folder_id: Optional[str] = None

class DocumentCreate(DocumentBase):
    filename: str
    file_hash: str
    file_path: str
    file_size: int
    mime_type: str
    original_filename: str

class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    document_date: Optional[datetime] = None
    is_tax_relevant: Optional[bool] = None
    reminder_date: Optional[datetime] = None
    notes: Optional[str] = None
    correspondent_id: Optional[str] = None
    doctype_id: Optional[str] = None
    folder_id: Optional[str] = None
    tag_ids: Optional[List[str]] = None

class Document(DocumentBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    original_filename: str
    file_hash: str
    file_path: str
    file_size: int
    mime_type: str
    full_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    ocr_status: str
    ai_status: str
    vector_status: str = "pending"
    view_count: int = 0
    last_viewed: Optional[datetime] = None

    # Approval fields
    is_approved: bool = False
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None

    # Authoring. `origin` says how the document came to exist, and `version`
    # is what the repository lists; both are surfaced so a list row can show
    # a composed document as what it is without a second request.
    # `source_html` is deliberately absent: it can be large, and only the
    # Studio needs it (via /api/studio/source/{id}).
    origin: Optional[str] = "uploaded"
    template_id: Optional[str] = None
    version: Optional[str] = "0.1"
    revision_of: Optional[str] = None

    created_by_name: Optional[str] = None
    approval_sender: Optional[str] = None
    approver_name: Optional[str] = None
    publisher_name: Optional[str] = None
    correspondent: Optional[Correspondent] = None
    doctype: Optional[DocType] = None
    tags: List[Tag] = []

# AI Extraction schemas
class AIExtractedData(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    document_date: Optional[str] = None  # Will be parsed to datetime
    correspondent_name: Optional[str] = None
    doctype_name: Optional[str] = None
    tag_names: List[str] = []
    is_tax_relevant: bool = False

class DocumentProcessingStatus(BaseModel):
    document_id: str
    filename: str
    ocr_status: str
    ai_status: str
    extracted_data: Optional[AIExtractedData] = None
    suggestions: Optional[dict] = None

# Search schemas
class SearchFilters(BaseModel):
    correspondent_ids: Optional[List[str]] = None
    doctype_ids: Optional[List[str]] = None
    tag_ids: Optional[List[str]] = None
    date_range: Optional[str] = None  # Predefined time periods
    date_from: Optional[str] = None  # Custom date range start (optional)
    date_to: Optional[str] = None    # Custom date range end (optional)
    is_tax_relevant: Optional[bool] = None
    reminder_filter: Optional[str] = None  # "has", "overdue", or "none"

class SearchRequest(BaseModel):
    query: Optional[str] = None
    filters: Optional[SearchFilters] = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    use_semantic_search: bool = True

class SearchResult(BaseModel):
    documents: List[Document]
    total_count: int
    query: Optional[str] = None
    filters: Optional[SearchFilters] = None

# RAG schemas
class RAGRequest(BaseModel):
    question: str = Field(..., min_length=1)
    filters: Optional[SearchFilters] = None
    max_documents: int = Field(default=5, ge=1, le=20)
    document_ids: Optional[List[str]] = None  # For manual document selection

class RAGResponse(BaseModel):
    answer: str
    sources: List[Document]
    confidence: Optional[float] = None

# File upload schemas
class FileUploadResponse(BaseModel):
    message: str
    document_id: Optional[str] = None
    status: str
    # The name the file was actually stored under. Uploads are sanitised, and a
    # clash gets a "_1" suffix, so this is rarely the name that was sent. The
    # Document row is created later by the watcher and takes this as its
    # original_filename, which is how a caller finds the record it just made.
    filename: Optional[str] = None
    folder: Optional[str] = None

class StagingFile(BaseModel):
    filename: str
    size: int
    created_at: datetime
    status: str  # pending, processing, completed, error

# Settings schemas
class SettingBase(BaseModel):
    key: str
    value: Optional[str] = None
    description: Optional[str] = None

class SettingCreate(SettingBase):
    pass

class SettingUpdate(BaseModel):
    value: Optional[str] = None
    description: Optional[str] = None

class Setting(SettingBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

# Extended Settings schemas
class ExtendedSettingsResponse(BaseModel):
    """What the Settings screen shows. Deployment, not models.

    Every field here configures something that runs on this machine or the
    network around it - where files live, how a sheet is read, where the
    trigger notifications are posted. Nothing configures a hosted service,
    because nothing calls one.
    """

    # How a scanned sheet is read
    ocr_engine: str = "auto"
    pdf_text_layer_first: bool = True

    # Database
    database_url: str = "sqlite:///./data/documents.db"

    # Folder Settings
    root_folder: str = "."
    staging_folder: str = "./data/staging"
    data_folder: str = "./data"
    storage_folder: str = "./data/storage"
    logs_folder: str = "./data/logs"

    # OCR Settings
    tesseract_path: str = "/usr/bin/tesseract"
    poppler_path: str = "/usr/bin"

    # File Settings
    max_file_size: str = "100MB"
    allowed_extensions: str = "pdf,png,jpg,jpeg,tiff,bmp,txt,text,md,markdown"

    # Security Settings
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Logging
    log_level: str = "INFO"

class ExtendedSettingsUpdate(BaseModel):
    # How a scanned sheet is read
    ocr_engine: Optional[str] = None
    pdf_text_layer_first: Optional[bool] = None

    # Database
    database_url: Optional[str] = None

    # Folder Settings
    root_folder: Optional[str] = None
    staging_folder: Optional[str] = None
    data_folder: Optional[str] = None
    storage_folder: Optional[str] = None
    logs_folder: Optional[str] = None

    # OCR Settings
    tesseract_path: Optional[str] = None
    poppler_path: Optional[str] = None

    # File Settings
    max_file_size: Optional[str] = None
    allowed_extensions: Optional[str] = None

    # Security Settings
    secret_key: Optional[str] = None
    algorithm: Optional[str] = None
    access_token_expire_minutes: Optional[int] = None

    # Logging
    log_level: Optional[str] = None

class ExportConfigResponse(BaseModel):
    """Payload returned by GET /api/settings/export."""
    version: str = "1.0"
    exported_at: datetime
    settings: dict = {}

class AIProviderStatus(BaseModel):
    provider: str
    configured: bool
    errors: List[str] = []
    warnings: List[str] = []
    models: dict = {}

# User schemas (for auth)
class UserCreate(BaseModel):
    username: str
    email: str
    full_name: Optional[str] = None
    password: str
    is_admin: bool = False
    # Where they sit, so approval steps addressed to a department reach them.
    department: Optional[str] = None
    job_title: Optional[str] = None
    # The two approval permissions. Approving and signing are separate
    # authorities: a clerk may verify, only a signatory may bind.
    can_approve: bool = True
    can_sign: bool = False
    account_type: Optional[str] = None  # Legacy fallback when role_id is omitted.
    # The quality team they belong to, if any.
    quality_team_id: Optional[str] = None
    # role_id is the role selected for this user; role_ids remains for clients
    # that already send a list, but user creation accepts only one role.
    role_id: Optional[str] = None
    role_ids: List[str] = Field(default_factory=list)

    @field_validator("password")
    @classmethod
    def _password(cls, v):
        return account_rules.check_password(v)

    @field_validator("username")
    @classmethod
    def _username(cls, v):
        return account_rules.check_username(v)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return account_rules.check_email(v)


class ManagedUserCreate(BaseModel):
    """Minimal request for creating a user with an administrator-defined role."""

    username: str = Field(..., min_length=1, max_length=50)
    email: str = Field(..., min_length=1, max_length=255)
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    role_id: str = Field(..., min_length=1, description="ID of the selected role")
    department_id: Optional[str] = Field(
        default=None,
        description="ID of a department created through the department API.",
    )
    job_title: Optional[str] = Field(default=None, max_length=120)

    @field_validator("password")
    @classmethod
    def _password(cls, v):
        return account_rules.check_password(v)

    @field_validator("username")
    @classmethod
    def _username(cls, v):
        return account_rules.check_username(v)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return account_rules.check_email(v)


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    password: Optional[str] = None
    department: Optional[str] = None
    department_id: Optional[str] = None
    job_title: Optional[str] = None
    can_approve: Optional[bool] = None
    can_sign: Optional[bool] = None
    account_type: Optional[str] = None
    quality_team_id: Optional[str] = None

    @field_validator("password")
    @classmethod
    def _password(cls, v):
        return account_rules.check_password(v)

    @field_validator("username")
    @classmethod
    def _username(cls, v):
        return account_rules.check_username(v)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return account_rules.check_email(v)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    full_name: Optional[str]
    is_active: bool
    is_admin: bool
    permissions: List[str] = Field(default_factory=list)
    role_ids: List[str] = Field(default_factory=list)
    role_names: List[str] = Field(default_factory=list)
    account_type: Optional[str] = None
    department: Optional[str] = None
    department_id: Optional[str] = None
    job_title: Optional[str] = None
    can_approve: Optional[bool] = True
    can_sign: Optional[bool] = False
    quality_team_id: Optional[str] = None
    last_login: Optional[datetime]
    created_at: datetime

# Approval schemas
class DocumentApprovalRequest(BaseModel):
    approved: bool

class DocumentApprovalResponse(BaseModel):
    success: bool
    message: str
    document_id: str
    is_approved: bool
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None

# Generic API Response
class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None
