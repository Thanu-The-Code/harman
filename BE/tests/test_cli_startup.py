import asyncio
import sys
from types import SimpleNamespace

import cli
from app import database
from app import main as app_main


def test_serve_initializes_database_before_loading_settings(monkeypatch):
    events = []
    settings = SimpleNamespace(
        staging_folder="./data/staging",
        data_folder="./data",
        storage_folder="./data/storage",
    )

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def load_settings(_db):
        events.append("settings")
        return settings

    monkeypatch.setattr(cli, "init_db", lambda: events.append("init_db"))
    monkeypatch.setattr(cli, "get_settings", load_settings)
    monkeypatch.setattr(database, "SessionLocal", Session)
    monkeypatch.setitem(
        sys.modules,
        "uvicorn",
        SimpleNamespace(run=lambda *_args, **_kwargs: events.append("uvicorn")),
    )

    cli.serve()

    assert events == ["init_db", "settings", "uvicorn"]


def test_app_startup_waits_for_database_initialization(monkeypatch):
    events = []
    monkeypatch.setattr(
        app_main.backup_scheduler,
        "configure",
        lambda **_kwargs: events.append("scheduler"),
    )
    monkeypatch.setattr(database, "init_db", lambda: events.append("init_db"))

    asyncio.run(app_main.startup_event())

    assert events == ["scheduler", "init_db"]
