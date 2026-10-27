"""Configuration loader for backend settings.

The project no longer includes an OCR subsystem, so the model-config file is
kept for generic app-level overrides but does not define OCR settings.
"""
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "models.json"

DEFAULT_CONFIG: Dict[str, Any] = {}

_lock = threading.Lock()
_cache: Optional[Dict[str, Any]] = None
_cache_mtime: Optional[float] = None
_cache_path: Optional[Path] = None


def get_config_path() -> Path:
    override = os.getenv("MODEL_CONFIG_FILE")
    if override:
        return Path(override).expanduser()
    return _DEFAULT_CONFIG_PATH


def _strip_readme(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_readme(v) for k, v in value.items() if not k.startswith("_")}
    return value


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_model_config(force: bool = False) -> Dict[str, Any]:
    global _cache, _cache_mtime, _cache_path

    path = get_config_path()

    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None

    with _lock:
        if not force and _cache is not None and _cache_path == path and _cache_mtime == mtime:
            return _cache

        merged = json.loads(json.dumps(DEFAULT_CONFIG))

        if mtime is None:
            logger.info(f"Model config file not found at {path}; using built-in defaults")
        else:
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
                if not isinstance(raw, dict):
                    raise ValueError("top-level value must be a JSON object")
                merged = _deep_merge(merged, _strip_readme(raw))
                logger.info(f"Loaded model configuration from {path}")
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                logger.error(f"Failed to read model config {path}: {exc}. Using built-in defaults.")

        _cache = merged
        _cache_mtime = mtime
        _cache_path = path
        return _cache


def reset_model_config() -> None:
    global _cache, _cache_mtime, _cache_path
    with _lock:
        _cache = None
        _cache_mtime = None
        _cache_path = None


def as_settings_overrides() -> Dict[str, Any]:
    """Return backend settings overrides from config/models.json.

    This project no longer stores OCR-related model options in the settings
    object, so the override map remains empty unless future backend config
    entries are added.
    """
    return {}
