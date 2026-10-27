"""Tests for config/models.json loading in the backend-only project.

The repository no longer includes OCR-specific runtime config, so the config
file is treated as a generic backend settings overlay and the tests assert the
minimal behavior still required for stable configuration loading.
"""
import json

from app.config import Settings
from app.services import model_config as mc


def write_config(tmp_path, payload) -> str:
    path = tmp_path / "models.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_repository_config_file_is_valid_json():
    config = mc.load_model_config(force=True)
    assert isinstance(config, dict)


def test_missing_config_file_falls_back_to_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_CONFIG_FILE", str(tmp_path / "absent.json"))
    mc.reset_model_config()

    assert mc.load_model_config() == {}


def test_malformed_config_file_falls_back_to_defaults(monkeypatch, tmp_path):
    path = tmp_path / "models.json"
    path.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setenv("MODEL_CONFIG_FILE", str(path))
    mc.reset_model_config()

    assert mc.load_model_config() == {}


def test_config_file_is_reloaded_when_it_changes(monkeypatch, tmp_path):
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"app": {"name": "demo"}}), encoding="utf-8")
    monkeypatch.setenv("MODEL_CONFIG_FILE", str(path))
    mc.reset_model_config()

    assert mc.load_model_config()["app"]["name"] == "demo"

    path.write_text(json.dumps({"app": {"name": "updated"}}), encoding="utf-8")
    import os as _os

    stat = path.stat()
    _os.utime(path, (stat.st_atime, stat.st_mtime + 10))

    assert mc.load_model_config()["app"]["name"] == "updated"


def test_model_keys_are_never_seeded_into_the_database(tmp_path):
    """The backend-only project should never seed OCR-era keys."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Base, Settings as SettingsModel
    from app.utils.init_settings import MODEL_CONFIG_KEYS, initialize_default_settings

    engine = create_engine(f"sqlite:///{tmp_path / 'seed.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        created = initialize_default_settings(db)
        stored = {row.key for row in db.query(SettingsModel).all()}

    leaked = stored & MODEL_CONFIG_KEYS
    assert not leaked, f"config keys must not be seeded: {sorted(leaked)}"
    assert not set(created) & MODEL_CONFIG_KEYS

    assert "staging_folder" in stored
    assert "storage_folder" in stored


def test_every_model_config_key_is_a_real_settings_field():
    from app.utils.init_settings import MODEL_CONFIG_KEYS

    unknown = MODEL_CONFIG_KEYS - set(Settings.model_fields.keys())
    assert not unknown, f"MODEL_CONFIG_KEYS lists unknown fields: {unknown}"


def test_overrides_and_model_config_keys_agree():
    from app.utils.init_settings import MODEL_CONFIG_KEYS

    missing = set(mc.as_settings_overrides()) - MODEL_CONFIG_KEYS
    assert not missing, (
        "these keys come from models.json but are not protected from seeding: "
        f"{sorted(missing)}"
    )


def test_as_settings_overrides_is_flat_and_complete():
    overrides = mc.as_settings_overrides()
    assert overrides == {}
