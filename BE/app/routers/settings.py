from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Dict, Any
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime

from ..database import get_db
from ..models import Settings as SettingsModel, User
from ..schemas import ExtendedSettingsResponse, ExtendedSettingsUpdate, ExportConfigResponse
from pydantic import BaseModel
from ..config import get_settings, reset_settings
from ..services.auth_service import require_permission_flexible, require_admin_flexible
from ..utils.init_settings import initialize_default_settings

router = APIRouter()

@router.get("/health/")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint for settings"""
    try:
        # Try to query settings to ensure DB connection works
        settings_count = db.query(SettingsModel).count()
        return {
            "status": "healthy",
            "settings_count": settings_count,
            "message": "Settings service is operational"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "message": "Settings service has issues"
        }

@router.get("/")
def get_all_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible)
):
    """Get all settings from database"""
    settings = db.query(SettingsModel).all()
    return settings

@router.get("/extended")
def get_extended_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
) -> ExtendedSettingsResponse:
    """Get all settings with additional computed values (admin only).

    Admin-only because it answers with the ``secret_key`` in clear. This
    previously required only ``settings.read``, which the default editor role
    grants - so any editor could read it.
    """
    try:
        config = get_settings(db)

        return ExtendedSettingsResponse(
            ocr_engine=config.ocr_engine,
            pdf_text_layer_first=config.pdf_text_layer_first,
            database_url=config.database_url,
            root_folder=config.root_folder if config.root_folder else str(Path.cwd()),
            staging_folder=config.staging_folder,
            storage_folder=config.storage_folder,
            data_folder=config.data_folder,
            logs_folder=config.logs_folder,
            tesseract_path=config.tesseract_path,
            poppler_path=config.poppler_path,
            max_file_size=config.max_file_size,
            allowed_extensions=config.allowed_extensions,
            log_level=config.log_level,
            secret_key=config.secret_key,
            algorithm=config.algorithm,
            access_token_expire_minutes=config.access_token_expire_minutes,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/extended")
@router.post("/extended")
def update_extended_settings(
    updates: ExtendedSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible)
) -> Dict[str, Any]:
    """Update multiple settings at once"""
    from loguru import logger
    
    try:
        update_dict = updates.dict(exclude_unset=True)
        
        logger.info(f"Extended settings update received: {list(update_dict.keys())}")
        
        if not update_dict:
            return {"message": "No updates provided"}
        
        # Log API key updates specifically
        if 'openai_api_key' in update_dict:
            key_value = update_dict['openai_api_key']
            logger.info(f"OpenAI API key in update: length={len(key_value) if key_value else 0}, empty={not key_value}")
        
        # Save each non-None setting to database
        for key, value in update_dict.items():
            if value is not None:
                # Skip empty API keys to avoid overwriting existing ones
                if key.endswith('_api_key') and not value:
                    logger.info(f"Skipping empty API key update for {key}")
                    continue
                save_setting_to_db(db, key, str(value))
        
        # Reset settings to reload from database
        reset_settings()
        
        # Create folders if paths were updated
        if any(key in update_dict for key in ["root_folder", "staging_folder", "storage_folder", "data_folder", "logs_folder"]):
            from ..services.folder_setup import setup_folders
            setup_folders()
        
        return {
            "message": "Settings updated successfully",
            "updated_fields": list(update_dict.keys()),
            "restart_required": False
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/config/file-settings")
def update_file_settings(
    file_settings: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    """Update file handling settings (admin only).

    Changing upload size limits or allowed extensions affects the system's
    security posture, so this is restricted to admins.
    """
    max_size = file_settings.get("max_file_size")
    extensions = file_settings.get("allowed_extensions")
    
    if max_size:
        save_setting_to_db(db, "max_file_size", max_size, "Maximum file size for uploads")
    
    if extensions:
        save_setting_to_db(db, "allowed_extensions", extensions, "Comma-separated list of allowed file extensions")
    
    return {"message": "File settings updated successfully"}

@router.post("/config/ocr-tools")
def update_ocr_tools(
    ocr_tools: Dict[str, str],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    """Update OCR tool paths (admin only).

    These paths point at executables that the server invokes; allowing
    unauthenticated callers to change them would be a remote-code-execution
    primitive.
    """
    tesseract_path = ocr_tools.get("tesseract_path")
    poppler_path = ocr_tools.get("poppler_path")
    
    if tesseract_path:
        # Verify tesseract exists
        if not Path(tesseract_path).exists():
            raise HTTPException(status_code=400, detail=f"Tesseract not found at: {tesseract_path}")
        save_setting_to_db(db, "tesseract_path", tesseract_path, "Path to Tesseract OCR binary")
    
    if poppler_path:
        # Verify poppler exists
        if not Path(poppler_path).exists():
            raise HTTPException(status_code=400, detail=f"Poppler tools not found at: {poppler_path}")
        save_setting_to_db(db, "poppler_path", poppler_path, "Path to Poppler tools directory")
    
    return {"message": "OCR tool paths updated successfully"}

@router.post("/config/folders")
def update_folder_paths(
    folders: Dict[str, str],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    """Update folder paths (admin only).

    Storage/staging/data folders control where uploaded documents live;
    changing them could be used to redirect writes or hijack stored files.
    """
    updated = []
    
    for key in ["root_folder", "staging_folder", "storage_folder", "data_folder", "logs_folder"]:
        if key in folders and folders[key]:
            save_setting_to_db(db, key, folders[key])
            updated.append(key)
    
    # Create folders if they don't exist
    if updated:
        from ..services.folder_setup import setup_folders
        setup_folders()
    
    return {"message": f"Updated folders: {', '.join(updated)}", "updated": updated}

@router.get("/export")
def export_configuration(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
) -> ExportConfigResponse:
    """Export all configuration settings (admin only).

    The settings table contains the OpenAI/Azure API keys and the JWT
    secret in cleartext. Without admin authentication this endpoint
    leaks every credential the application uses.
    """
    try:
        # Get all settings from database
        db_settings = db.query(SettingsModel).all()
        settings_dict = {setting.key: setting.value for setting in db_settings}

        return ExportConfigResponse(
            version="1.0",
            exported_at=datetime.now(),
            settings=settings_dict
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/import")
async def import_configuration(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
) -> Dict[str, Any]:
    """Import configuration from JSON file (admin only).

    Without authentication, an anonymous attacker could overwrite every
    setting (including API keys, JWT secret, admin-controlled paths) by
    POSTing a crafted JSON payload.
    """
    try:
        # Read and parse JSON file
        content = await file.read()
        config_data = json.loads(content)
        
        if "settings" not in config_data:
            raise HTTPException(status_code=400, detail="Invalid configuration file format")
        
        # Import settings
        imported_count = 0
        for key, value in config_data["settings"].items():
            save_setting_to_db(db, key, value)
            imported_count += 1
        
        # Reset settings to reload from database
        reset_settings()
        
        return {
            "message": f"Successfully imported {imported_count} settings",
            "imported_count": imported_count,
            "restart_required": False
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/backup")
async def backup_system(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
) -> Dict[str, str]:
    """Create a full system backup (admin only).

    The exported backup contains all configuration settings, including the
    cleartext OpenAI/Azure API keys and the JWT secret.
    """
    try:
        backup_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = Path("data/backups") / backup_id
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Export configuration
        db_settings = db.query(SettingsModel).all()
        settings_dict = {setting.key: setting.value for setting in db_settings}
        
        config_data = {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "settings": settings_dict
        }
        
        with open(backup_dir / "config.json", "w") as f:
            json.dump(config_data, f, indent=2)
        
        # Create backup info
        info = {
            "backup_id": backup_id,
            "created_at": datetime.now().isoformat(),
            "system_version": "1.0.0"
        }
        
        with open(backup_dir / "backup_info.json", "w") as f:
            json.dump(info, f, indent=2)
        
        # Create zip file
        zip_path = Path("data/backups") / f"backup_{backup_id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in backup_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(backup_dir))
        
        # Clean up temporary directory
        shutil.rmtree(backup_dir)
        
        return {
            "backup_id": backup_id,
            "file_path": str(zip_path),
            "message": "Backup created successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/backup/{backup_id}")
def download_backup(
    backup_id: str,
    current_user: User = Depends(require_admin_flexible),
):
    """Download a backup file (admin only).

    The backup archive contains every configuration setting (including
    OpenAI/Azure keys and the JWT secret), so this must require admin
    authentication. The backup_id is also validated to prevent path
    traversal: the resolved path must stay inside data/backups, and the
    id is constrained to a safe character set.
    """
    import re

    # Restrict backup_id to a safe character set; the timestamp generator
    # above only emits digits and underscores, so this is sufficient.
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", backup_id):
        raise HTTPException(status_code=400, detail="Invalid backup id")

    backups_base = Path("data/backups").resolve()
    zip_path = (backups_base / f"backup_{backup_id}.zip").resolve()

    # Ensure the resolved path stays inside the backups directory.
    try:
        zip_path.relative_to(backups_base)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid backup id")

    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"docmanager_backup_{backup_id}.zip"
    )

@router.get("/logs/download")
def download_logs(
    current_user: User = Depends(require_admin_flexible),
):
    """Download all log files as a zip archive (admin only).

    Logs typically include request paths, user identifiers, IP addresses
    and error stack traces, all of which are sensitive operational data.
    """
    try:
        # Create a temporary directory for the zip file
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create timestamp for filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_filename = f"logs_{timestamp}.zip"
            zip_path = temp_path / zip_filename
            
            # Get logs directory
            logs_dir = Path("data/logs")
            if not logs_dir.exists():
                raise HTTPException(status_code=404, detail="Logs directory not found")
            
            # Create zip file with all logs
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # Add all log files
                for log_file in logs_dir.glob("*.log"):
                    zf.write(log_file, f"data/logs/{log_file.name}")
                
                # Add rotated/compressed logs
                for log_file in logs_dir.glob("*.log.*"):
                    zf.write(log_file, f"data/logs/{log_file.name}")
                
                # Add system info
                system_info = {
                    "exported_at": datetime.now().isoformat(),
                    "logs_directory": str(logs_dir.absolute()),
                    "log_files": [f.name for f in logs_dir.glob("*.log*")]
                }
                
                info_path = temp_path / "logs_info.json"
                with open(info_path, "w") as f:
                    json.dump(system_info, f, indent=2)
                
                zf.write(info_path, "logs_info.json")
            
            # Create a persistent copy before returning
            output_dir = Path("data/temp_downloads")
            output_dir.mkdir(exist_ok=True)
            output_path = output_dir / zip_filename
            shutil.copy2(zip_path, output_path)
            
            # Schedule cleanup after response
            def cleanup():
                try:
                    if output_path.exists():
                        output_path.unlink()
                except Exception:
                    pass
            
            import threading
            timer = threading.Timer(60.0, cleanup)  # Clean up after 60 seconds
            timer.start()
            
            return FileResponse(
                path=output_path,
                media_type="application/zip",
                filename=f"document_manager_logs_{timestamp}.zip",
                headers={
                    "Content-Disposition": f"attachment; filename=document_manager_logs_{timestamp}.zip"
                }
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create logs archive: {str(e)}")

@router.post("/initialize-defaults")
def initialize_default_settings_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible)
):
    """Initialize missing default settings in the database"""
    try:
        created_settings = initialize_default_settings(db)
        
        if created_settings:
            return {
                "message": f"Successfully initialized {len(created_settings)} default settings",
                "created_settings": list(created_settings.keys())
            }
        else:
            return {
                "message": "All default settings already exist in database",
                "created_settings": []
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize default settings: {str(e)}")