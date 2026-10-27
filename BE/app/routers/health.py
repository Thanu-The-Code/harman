from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any
import os
import psutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from ..database import get_db
from ..config import get_settings
from ..models import Document, User, AuditLog
from ..models_qms import ChangeRequest, Format, Record
from ..services.auth_service import require_admin_flexible

router = APIRouter()


@router.get("/api-counts")
async def api_counts(request: Request) -> Dict[str, Any]:
    """Count documented API operations overall and group them by section."""
    api_methods = {
        "get", "post", "put", "patch", "delete", "options", "head", "trace",
    }
    section_counts: Dict[str, int] = {}
    total = 0

    for path, operations in request.app.openapi()["paths"].items():
        if not path.startswith("/api/"):
            continue
        for method, operation in operations.items():
            if method.lower() not in api_methods:
                continue

            total += 1
            tags = operation.get("tags") or ["Uncategorized"]
            section = tags[0]
            section_counts[section] = section_counts.get(section, 0) + 1

    return {
        "total_apis": total,
        "by_section": dict(sorted(section_counts.items())),
    }


@router.get("/")
async def health_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Comprehensive health check for all system components"""
    health_status = {}

    # 1. Database Health
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        db.commit()

        # What this system actually holds: released formats, the records
        # filled against them, the change requests against those formats, and
        # the scanned sheets the records were filled from.
        health_status["database"] = {
            "status": "healthy",
            "message": "Database connection successful",
            "details": {
                "formats": db.query(Format).count(),
                "records": db.query(Record).count(),
                "change_requests": db.query(ChangeRequest).count(),
                "scanned_sheets": db.query(Document).count(),
            }
        }
    except Exception as e:
        health_status["database"] = {
            "status": "unhealthy",
            "message": f"Database error: {str(e)}",
            "details": {}
        }

    # 2. OCR Service Health
    # what the template import can read: Excel always, PDFs and pictures with the OCR extra
    try:
        from ..ocr.formats import AVAILABLE, OCR_UNAVAILABLE

        health_status["ocr_service"] = {
            "status": "healthy" if not OCR_UNAVAILABLE else "degraded",
            "message": ("Template import reads " + ", ".join(AVAILABLE) + "."
                        + (f" {OCR_UNAVAILABLE}" if OCR_UNAVAILABLE else "")),
            "details": {"formats": list(AVAILABLE)},
        }
    except Exception as exc:  # pragma: no cover - an install without the import package
        health_status["ocr_service"] = {"status": "unhealthy", "message": f"Template import unavailable: {exc}", "details": {}}

    # 3. File System Health
    try:
        settings = get_settings(db)
        folders = {
            "staging": settings.staging_folder,
            "storage": settings.storage_folder,
            "data": settings.data_folder
        }

        folder_status = {}
        all_exist = True
        for name, path in folders.items():
            exists = Path(path).exists()
            writable = os.access(path, os.W_OK) if exists else False
            folder_status[name] = {
                "path": path,
                "exists": exists,
                "writable": writable
            }
            if not exists or not writable:
                all_exist = False

        health_status["file_system"] = {
            "status": "healthy" if all_exist else "warning",
            "message": "All folders accessible" if all_exist else "Some folders missing or not writable",
            "details": folder_status
        }
    except Exception as e:
        health_status["file_system"] = {
            "status": "unhealthy",
            "message": f"File system error: {str(e)}",
            "details": {}
        }

    # 4. Settings/Configuration Health
    try:
        from ..models import Settings as SettingsModel
        settings_count = db.query(SettingsModel).count()

        # Validate the *resolved* settings rather than raw database rows.
        # Model-related keys intentionally live in config/models.json and are
        # absent from the settings table unless an admin overrides them.
        resolved = get_settings(db)
        critical_settings = ["staging_folder", "storage_folder", "data_folder"]
        missing_settings = [
            key for key in critical_settings if not getattr(resolved, key, None)
        ]

        if not missing_settings:
            health_status["configuration"] = {
                "status": "healthy",
                "message": "All critical settings configured",
                "details": {
                    "total_settings": settings_count,
                    "critical_settings": "complete"
                }
            }
        else:
            health_status["configuration"] = {
                "status": "warning",
                "message": "Some critical settings missing",
                "details": {
                    "total_settings": settings_count,
                    "missing": missing_settings
                }
            }
    except Exception as e:
        health_status["configuration"] = {
            "status": "unhealthy",
            "message": f"Configuration error: {str(e)}",
            "details": {}
        }

    # Calculate overall health
    overall_status = "healthy"
    unhealthy_count = 0
    warning_count = 0

    for service, status in health_status.items():
        if status["status"] == "unhealthy":
            unhealthy_count += 1
            overall_status = "unhealthy"
        elif status["status"] == "warning":
            warning_count += 1
            if overall_status == "healthy":
                overall_status = "warning"

    return {
        "status": overall_status,
        "services": health_status,
        "summary": {
            "healthy": len([s for s in health_status.values() if s["status"] == "healthy"]),
            "warning": warning_count,
            "unhealthy": unhealthy_count,
            "total": len(health_status)
        }
    }

@router.get("/simple")
async def simple_health_check() -> Dict[str, str]:
    """Simple health check endpoint"""
    return {"status": "ok"}


@router.get("/metrics")
async def system_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
) -> Dict[str, Any]:
    """System performance and resource metrics (admin only).

    Reveals CPU/RAM/disk usage, user counts, recent login counts and
    process metadata. Anonymous callers should not be able to fingerprint
    the host this way.
    """
    try:
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None

        # Memory metrics
        memory = psutil.virtual_memory()
        memory_mb = memory.total / (1024 * 1024)
        memory_used_mb = memory.used / (1024 * 1024)
        memory_available_mb = memory.available / (1024 * 1024)

        # Disk metrics
        settings = get_settings(db)
        disk_usage = {}

        for name, path in {
            "storage": settings.storage_folder,
            "staging": settings.staging_folder,
            "data": settings.data_folder
        }.items():
            try:
                usage = psutil.disk_usage(path)
                disk_usage[name] = {
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "percent_used": round((usage.used / usage.total) * 100, 1)
                }
            except Exception as e:
                disk_usage[name] = {"error": str(e)}

        # Database metrics
        try:
            doc_count = db.query(Document).count()
            user_count = db.query(User).count()

            # Recent activity (last 24 hours)
            yesterday = datetime.utcnow() - timedelta(days=1)
            recent_docs = db.query(Document).filter(Document.created_at >= yesterday).count()
            recent_logins = db.query(AuditLog).filter(
                AuditLog.action == "login_successful",
                AuditLog.created_at >= yesterday
            ).count()

            db_metrics = {
                "total_documents": doc_count,
                "total_users": user_count,
                "recent_documents_24h": recent_docs,
                "recent_logins_24h": recent_logins
            }
        except Exception as e:
            db_metrics = {"error": str(e)}

        # Process metrics
        process = psutil.Process()
        process_metrics = {
            "pid": process.pid,
            "memory_mb": round(process.memory_info().rss / (1024 * 1024), 2),
            "cpu_percent": process.cpu_percent(),
            "num_threads": process.num_threads(),
            "uptime_seconds": round(time.time() - process.create_time(), 2)
        }

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "system": {
                "cpu": {
                    "percent": cpu_percent,
                    "count": cpu_count,
                    "load_average": load_avg
                },
                "memory": {
                    "total_mb": round(memory_mb, 2),
                    "used_mb": round(memory_used_mb, 2),
                    "available_mb": round(memory_available_mb, 2),
                    "percent_used": memory.percent
                },
                "disk": disk_usage
            },
            "application": {
                "process": process_metrics,
                "database": db_metrics
            }
        }

    except Exception as e:
        return {
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/readiness")
async def readiness_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Kubernetes-style readiness probe"""
    ready = True
    checks = {}

    # Database connectivity
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"ready": True}
    except Exception as e:
        checks["database"] = {"ready": False, "error": str(e)}
        ready = False

    # Required directories
    try:
        settings = get_settings(db)
        for name, path in {
            "staging": settings.staging_folder,
            "storage": settings.storage_folder
        }.items():
            path_obj = Path(path)
            accessible = path_obj.exists() and os.access(path, os.W_OK)
            checks[f"directory_{name}"] = {"ready": accessible, "path": path}
            if not accessible:
                ready = False
    except Exception as e:
        checks["directories"] = {"ready": False, "error": str(e)}
        ready = False

    # Critical configuration
    try:
        settings = get_settings(db)
        has_config = bool(settings.storage_folder and settings.staging_folder)
        checks["configuration"] = {"ready": has_config}
        if not has_config:
            ready = False
    except Exception as e:
        checks["configuration"] = {"ready": False, "error": str(e)}
        ready = False

    return {
        "ready": ready,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/liveness")
async def liveness_check() -> Dict[str, Any]:
    """Kubernetes-style liveness probe"""
    return {
        "alive": True,
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": round(time.time() - psutil.Process().create_time(), 2)
    }


@router.get("/startup")
async def startup_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Kubernetes-style startup probe"""
    startup_complete = True
    checks = {}

    # Database initialized
    try:
        # Check if tables exist by querying a simple table
        user_count = db.query(User).count()
        checks["database_initialized"] = {"complete": True, "user_count": user_count}
    except Exception as e:
        checks["database_initialized"] = {"complete": False, "error": str(e)}
        startup_complete = False

    # Settings loaded
    try:
        settings = get_settings(db)
        checks["settings_loaded"] = {"complete": bool(settings)}
    except Exception as e:
        checks["settings_loaded"] = {"complete": False, "error": str(e)}
        startup_complete = False

    # File system ready
    try:
        settings = get_settings(db)
        staging_ready = Path(settings.staging_folder).exists()
        storage_ready = Path(settings.storage_folder).exists()
        checks["filesystem_ready"] = {
            "complete": staging_ready and storage_ready,
            "staging": staging_ready,
            "storage": storage_ready
        }
        if not (staging_ready and storage_ready):
            startup_complete = False
    except Exception as e:
        checks["filesystem_ready"] = {"complete": False, "error": str(e)}
        startup_complete = False

    return {
        "startup_complete": startup_complete,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/security")
async def security_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
) -> Dict[str, Any]:
    """Security-specific health checks (admin only).

    Exposes user counts, admin counts, recent failed/successful login
    counts, and filesystem permission information that helps an attacker
    enumerate the install. Restricted to admins.
    """
    security_status = {}

    # Authentication status
    try:
        user_count = db.query(User).count()
        active_users = db.query(User).filter(User.is_active).count()
        admin_users = db.query(User).filter(User.is_admin).count()

        security_status["authentication"] = {
            "status": "configured" if user_count > 0 else "not_configured",
            "total_users": user_count,
            "active_users": active_users,
            "admin_users": admin_users
        }
    except Exception as e:
        security_status["authentication"] = {
            "status": "error",
            "error": str(e)
        }

    # Recent security events
    try:
        yesterday = datetime.utcnow() - timedelta(days=1)
        failed_logins = db.query(AuditLog).filter(
            AuditLog.action.like("login_failed%"),
            AuditLog.created_at >= yesterday
        ).count()

        successful_logins = db.query(AuditLog).filter(
            AuditLog.action == "login_successful",
            AuditLog.created_at >= yesterday
        ).count()

        security_status["recent_activity"] = {
            "failed_logins_24h": failed_logins,
            "successful_logins_24h": successful_logins,
            "risk_level": "high" if failed_logins > 10 else "medium" if failed_logins > 5 else "low"
        }
    except Exception as e:
        security_status["recent_activity"] = {
            "error": str(e)
        }

    # File permissions check
    try:
        settings = get_settings(db)
        permissions_status = {}

        for name, path in {
            "staging": settings.staging_folder,
            "storage": settings.storage_folder
        }.items():
            path_obj = Path(path)
            if path_obj.exists():
                stat_info = path_obj.stat()
                permissions = oct(stat_info.st_mode)[-3:]
                permissions_status[name] = {
                    "permissions": permissions,
                    "secure": permissions in ["755", "750", "700"]  # Reasonable secure permissions
                }
            else:
                permissions_status[name] = {"error": "path_not_found"}

        security_status["file_permissions"] = permissions_status
    except Exception as e:
        security_status["file_permissions"] = {
            "error": str(e)
        }

    return {
        "security": security_status,
        "timestamp": datetime.utcnow().isoformat()
    }