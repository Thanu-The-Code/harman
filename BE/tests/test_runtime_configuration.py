from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.middleware.rate_limit_middleware import RateLimitMiddleware
from sqlalchemy.engine import make_url


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_settings_read_documented_environment_variables(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("CORS_ORIGINS", "https://records.example.com")
    monkeypatch.setenv("ENVIRONMENT", "production")

    settings = Settings()

    assert settings.database_url == "sqlite:///./data/test.db"
    assert settings.smtp_host == "smtp.example.com"
    assert settings.cors_origins_list == ["https://records.example.com"]
    assert settings.production_mode is True


def test_database_fields_build_encoded_postgres_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATABASE_HOST", "db.example.com")
    monkeypatch.setenv("DATABASE_PORT", "5433")
    monkeypatch.setenv("DATABASE_NAME", "quality_records ")
    monkeypatch.setenv("DATABASE_USER", "paperless")
    monkeypatch.setenv("DATABASE_PASSWORD", "p@ss:word")

    database_url = make_url(Settings(_env_file=None).database_url)

    assert database_url.drivername == "postgresql+psycopg"
    assert database_url.username == "paperless"
    assert database_url.password == "p@ss:word"
    assert database_url.host == "db.example.com"
    assert database_url.port == 5433
    assert database_url.database == "quality_records"


def test_direct_database_url_takes_precedence(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.setenv("DATABASE_PASSWORD", "ignored")

    assert Settings().database_url == "sqlite:///./data/test.db"


def test_database_password_has_no_hard_coded_default(monkeypatch):
    monkeypatch.delenv("DATABASE_PASSWORD", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert Settings(_env_file=None).database_password is None


def test_forwarded_header_is_ignored_for_untrusted_client():
    middleware = RateLimitMiddleware.__new__(RateLimitMiddleware)
    middleware.trusted_proxy_ips = {"127.0.0.1"}
    request = SimpleNamespace(
        client=SimpleNamespace(host="203.0.113.10"),
        headers={"X-Forwarded-For": "198.51.100.7"},
    )

    assert middleware.get_client_ip(request) == "203.0.113.10"


def test_forwarded_header_is_used_for_trusted_proxy():
    middleware = RateLimitMiddleware.__new__(RateLimitMiddleware)
    middleware.trusted_proxy_ips = {"127.0.0.1"}
    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"X-Forwarded-For": "198.51.100.7, 127.0.0.1"},
    )

    assert middleware.get_client_ip(request) == "198.51.100.7"


def _env_example_lines():
    return (REPOSITORY_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()


def test_env_example_only_documents_supported_settings():
    env_keys = {
        line.split("=", 1)[0]
        for line in _env_example_lines()
        if line and not line.startswith("#")
    }
    supported_keys = {name.upper() for name in Settings.model_fields}

    assert env_keys <= supported_keys
    # Credentials and infrastructure belong in .env. How a sheet is read does
    # not - that lives in config/models.json (see the next test).
    assert {
        "SECRET_KEY",
        "DATABASE_URL",
        "TRUSTED_PROXY_IPS",
        # The process sends six trigger notifications, so the mail server is
        # deployment configuration and has to be documented here.
        "SMTP_HOST",
        "APP_BASE_URL",
    } <= env_keys

    # Nothing here may configure a hosted model. The product reads its own
    # sheets, locally, and an API key field in a sample env file is an
    # invitation to paste a real key in for a service nothing will ever call.
    assert not {k for k in env_keys if "OPENAI" in k or "GROQ" in k or "AZURE" in k}


def test_env_example_documents_commented_model_overrides():
    """OCR keys must be present but commented, so models.json stays in force."""
    commented = {
        line.lstrip("#").split("=", 1)[0].strip()
        for line in _env_example_lines()
        if line.startswith("#") and "=" in line
    }
    active = {
        line.split("=", 1)[0]
        for line in _env_example_lines()
        if line and not line.startswith("#")
    }

    for key in ("OCR_ENGINE", "PDF_TEXT_LAYER_FIRST", "PADDLE_ENABLED", "PADDLE_TABLE"):
        assert key in commented, f"{key} should be documented as a commented override"
        assert key not in active, (
            f"{key} is uncommented in .env.example; it would shadow config/models.json"
        )


def test_env_example_and_env_agree_on_model_overrides():
    """The shipped .env must not silently override config/models.json either."""
    env_path = REPOSITORY_ROOT / ".env"
    if not env_path.exists():
        return  # not present in a fresh checkout / CI

    active = {
        line.split("=", 1)[0].strip()
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    for key in ("OCR_ENGINE", "PDF_TEXT_LAYER_FIRST", "PADDLE_ENABLED", "PADDLE_TABLE"):
        assert key not in active, (
            f"{key} is set in .env and would shadow config/models.json"
        )


def test_setup_uses_env_file_without_evaluating_its_contents():
    setup_script = (REPOSITORY_ROOT / "setup.sh").read_text(encoding="utf-8")

    assert "--env-file .env" in setup_script
    assert "export $(" not in setup_script


def test_container_runtime_does_not_start_a_duplicate_chroma_server():
    production_dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    development_dockerfile = (REPOSITORY_ROOT / "Dockerfile.dev").read_text(encoding="utf-8")
    entrypoint = (REPOSITORY_ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")

    assert "supervisor" not in production_dockerfile
    assert "supervisor" not in development_dockerfile
    assert "chromadb.cli" not in entrypoint
    assert "python -m uvicorn" in entrypoint


def test_runtime_dependencies_do_not_pull_unused_local_embedding_stack():
    requirements = (REPOSITORY_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "sentence-transformers" not in requirements


def test_docker_context_excludes_credentials_and_runtime_data():
    dockerignore = (REPOSITORY_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in dockerignore
    assert "data" in dockerignore
    assert "backups" in dockerignore
