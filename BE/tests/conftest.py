"""Shared test fixtures.

Tests must never pick up the developer's real ``.env`` - the folder paths in it
point at a working install - so the env file is disabled for the whole session
and the settings caches are reset between tests.
"""
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Must be set before app.config is imported anywhere.
os.environ.setdefault("DOCUMENT_MANAGER_ENV_FILE", "")


@pytest.fixture(autouse=True)
def clean_settings_cache():
    """Reset the settings and model-config caches around every test."""
    from app.config import reset_settings
    from app.services.model_config import reset_model_config

    reset_settings()
    reset_model_config()
    yield
    reset_settings()
    reset_model_config()


@pytest.fixture
def ocr_settings():
    """Backward-compatible fixture name retained for older tests."""
    from app.config import Settings

    return Settings()
