import hashlib
from pathlib import Path
from loguru import logger

def calculate_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """Calculate hash of a file"""
    hash_obj = hashlib.new(algorithm)
    
    try:
        with open(file_path, "rb") as f:
            # Read file in chunks to handle large files
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        
        file_hash = hash_obj.hexdigest()
        logger.debug(f"Calculated {algorithm} hash for {file_path.name}: {file_hash}")
        return file_hash
        
    except Exception as e:
        logger.error(f"Failed to calculate hash for {file_path}: {e}")
        raise

def calculate_content_hash(content: bytes, algorithm: str = "sha256") -> str:
    """Calculate hash of content bytes"""
    hash_obj = hashlib.new(algorithm)
    hash_obj.update(content)
    return hash_obj.hexdigest()

def verify_file_integrity(file_path: Path, expected_hash: str, algorithm: str = "sha256") -> bool:
    """Verify file integrity against expected hash"""
    try:
        actual_hash = calculate_file_hash(file_path, algorithm)
        is_valid = actual_hash == expected_hash
        
        if not is_valid:
            logger.warning(f"File integrity check failed for {file_path.name}. "
                         f"Expected: {expected_hash}, Got: {actual_hash}")
        
        return is_valid
        
    except Exception as e:
        logger.error(f"Failed to verify file integrity for {file_path}: {e}")
        return False

def get_file_info(file_path: Path) -> dict:
    """Get comprehensive file information"""
    try:
        stat = file_path.stat()
        
        return {
            "name": file_path.name,
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "created": stat.st_ctime,
            "extension": file_path.suffix.lower(),
            "hash": calculate_file_hash(file_path)
        }
    except Exception as e:
        logger.error(f"Failed to get file info for {file_path}: {e}")
        raise


# What a stored file is served as, decided by the server from its extension - never the
# Content-Type its uploader sent, which could call an HTML page "image/png". Only
# documents and pictures are shown in place; text is shown as text, anything else is
# downloaded.
_SHOWN = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp", ".tif": "image/tiff", ".tiff": "image/tiff",
}
_TEXT = {".txt", ".text", ".md", ".markdown", ".csv", ".log"}

# Sent with every stored file: no type guessing. Anything but a PDF is also sandboxed, so
# nothing in it may run scripts (a sandboxed PDF would not open in Chrome's viewer).
SAFE_FILE_HEADERS = {"X-Content-Type-Options": "nosniff"}


def safe_headers(media_type: str) -> dict[str, str]:
    if (media_type or "").startswith("application/pdf"):
        return dict(SAFE_FILE_HEADERS)
    return {**SAFE_FILE_HEADERS, "Content-Security-Policy": "sandbox; default-src 'none'; img-src 'self' data:"}


def served_type(filename: str) -> tuple[str, bool]:
    """(media type, show inline) for a stored file of this name."""
    suffix = Path(filename or "").suffix.lower()
    if suffix in _SHOWN:
        return _SHOWN[suffix], True
    if suffix in _TEXT:
        return "text/plain; charset=utf-8", True
    return "application/octet-stream", False
