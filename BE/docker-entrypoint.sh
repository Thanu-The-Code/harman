#!/bin/bash
# Docker entrypoint script for the Paperless Factory backend

set -e

echo "🚀 Starting Paperless Factory backend..."

echo "📁 Creating directories..."
mkdir -p /app/data /app/data/logs /app/data/staging /app/data/storage /app/data/uploads /app/data/backups

# Check required environment variables for production
if [ "${ENVIRONMENT:-production}" = "production" ]; then
    if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "MUST-BE-SET-IN-PRODUCTION" ]; then
        echo "⚠️  ERROR: SECRET_KEY must be set in production!"
        echo "Generate a secure key with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
        exit 1
    fi
fi

if [ -f /app/config/models.json ]; then
    echo "🧠 Model configuration: /app/config/models.json"
else
    echo "⚠️  /app/config/models.json missing; using built-in model defaults."
fi

# PostgreSQL runs in its own container and may still be starting. Wait for it
# rather than letting the app crash on its first query. Tables are created by
# init_db() when the app starts.
echo "⏳ Waiting for the database..."
python - <<'EOF'
import sys, time
from sqlalchemy import create_engine, text
from app.config import get_settings

url = get_settings().database_url
engine = create_engine(url)
for attempt in range(30):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Database is reachable")
        sys.exit(0)
    except Exception as exc:
        print(f"   database not ready ({type(exc).__name__}), retrying...")
        time.sleep(2)
print("⚠️  ERROR: could not reach the database after 60 seconds. Check DATABASE_URL.")
sys.exit(1)
EOF

echo "✅ Initialization complete"

uvicorn_args=(
    app.main:app
    --host 0.0.0.0
    --port 8000
    --proxy-headers
    --forwarded-allow-ips "${TRUSTED_PROXY_IPS:-127.0.0.1}"
)

if [ "${ENVIRONMENT:-production}" = "development" ]; then
    uvicorn_args+=(--reload)
fi

exec python -m uvicorn "${uvicorn_args[@]}"
