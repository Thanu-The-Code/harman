from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from .database import get_db
from starlette.exceptions import HTTPException as StarletteHTTPException
import os
import sys
import uvicorn

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from .routers.api import API_TAGS, register_api_routers
from .services.backup_scheduler import backup_scheduler
from .middleware.error_handler import ErrorHandler
from .config import get_settings
from .middleware.rate_limit_middleware import RateLimitProtect
from .services.process_screen_service import ProcessScreenAccessService

app_settings = get_settings()

app = FastAPI(
    # the API reference is for developers: not served by a production deployment
    docs_url=None if app_settings.production_mode else "/docs",
    redoc_url=None if app_settings.production_mode else "/redoc",
    openapi_url=None if app_settings.production_mode else "/openapi.json",
    title="Paperless Factory",
    description=(
        "Paperless Factory backend for the document lifecycle: Template Builder, "
        "Resources Library, My Documents, Document Repository, and People & Teams."
    ),
    version="1.1.0",
    openapi_tags=API_TAGS,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
    # Readable by the frontend on another origin: the download file name and
    # the signature count on stamped previews.
    expose_headers=["Content-Disposition", "X-Signature-Count"],
)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Standard protections on every response; a file's own stricter headers are kept."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if not request.url.path.startswith(("/docs", "/redoc")):
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'self'")
    return response


app.add_exception_handler(HTTPException, ErrorHandler.http_exception_handler)
app.add_exception_handler(RequestValidationError, ErrorHandler.validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, ErrorHandler.starlette_exception_handler)
app.add_exception_handler(Exception, ErrorHandler.general_exception_handler)

rate_limit = RateLimitProtect(
    default_limit=100,
    window_seconds=60,
    login_limit=5,
    login_window_seconds=300,
    trusted_proxy_ips=app_settings.trusted_proxy_ips_list,
)
rate_limit.init_app(app)

register_api_routers(app)


@app.on_event("startup")
async def startup_event():
    """Initialize the application on startup."""
    print("Paperless Factory API starting...")
    print("📊 Backend-only mode: API documentation is available at /docs")

    try:
        backup_scheduler.configure(enabled=False)
        print("📦 Backup scheduler initialized (disabled by default)")
    except Exception as exc:
        print(f"⚠️  Could not initialize backup scheduler: {exc}")

    from .database import init_db

    init_db()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown."""
    try:
        backup_scheduler.stop()
        print("📦 Backup scheduler stopped")
    except Exception as exc:
        print(f"⚠️  Error stopping backup scheduler: {exc}")


process_screen_service = ProcessScreenAccessService()


@app.get("/", include_in_schema=False)
async def read_root():
    """Expose the backend entry point and docs location."""
    return {
        "message": "Paperless Factory API is running.",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json",
    }


@app.get("/health", tags=["Platform Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "message": "Paperless Factory backend is running"}


@app.get("/formats", include_in_schema=False)
@app.get("/records", include_in_schema=False)
@app.get("/records/new", include_in_schema=False)
@app.get("/storage", include_in_schema=False)
@app.get("/change-requests", include_in_schema=False)
@app.get("/track", include_in_schema=False)
@app.get("/tasks", include_in_schema=False)

async def process_screen(request: Request, db=Depends(get_db)):
    """Serve the root-level project screens using the same access rules as the workflow."""
    from .services.auth_service import get_user_from_session_token

    user = get_user_from_session_token(request, db)
    return process_screen_service.resolve(request, request.url.path, user)


@app.get("/{path:path}", include_in_schema=False)
async def catch_all(path: str):
    """Return a JSON 404 for unknown API paths."""
    raise HTTPException(status_code=404, detail=f"Route '/{path}' not found. See /docs for the API surface.")


if __name__ == "__main__":
    host = os.getenv("DOCUMENT_MANAGER_HOST", "127.0.0.1")
    uvicorn.run("app.main:app", host=host, port=8000, reload=True)
