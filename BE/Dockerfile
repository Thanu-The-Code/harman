# Paperless Factory backend - production image
# Multi-stage build: compile dependencies in one stage, ship only the venv.
# The frontend is deployed separately; this image is the API alone.

# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y \
    build-essential \
    libmagic-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt requirements-ocr.txt ./

# WITH_OCR=true adds PDF / image reading to template import (PaddleOCR, OpenCV;
# about 1 GB). Without it the OCR service offers Excel only.
#   docker build --build-arg WITH_OCR=true -t paperless-factory-api .
ARG WITH_OCR=false
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    if [ "$WITH_OCR" = "true" ]; then pip install --no-cache-dir -r requirements-ocr.txt; fi

# Stage 2: Runtime image
FROM python:3.12-slim AS runtime

ARG WITH_OCR=false
RUN apt-get update && apt-get install -y \
    # File type detection (python-magic)
    libmagic1 \
    # pg_dump for app/utils/backup.py
    postgresql-client \
    # Health check
    curl \
    # what OpenCV and Paddle load at run time, when the image reads scans
    && if [ "$WITH_OCR" = "true" ]; then apt-get install -y libgl1 libglib2.0-0 libgomp1; fi \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Non-root user; UID 1000 matches the owner of the mounted data folder.
RUN groupadd -r -g 1000 appuser && \
    useradd -r -u 1000 -g appuser -m -d /home/appuser -s /bin/bash appuser

WORKDIR /app

COPY --chown=appuser:appuser app/ ./app/
# Model configuration. Mount over this path to change it without a rebuild:
#   -v $(pwd)/config:/app/config
COPY --chown=appuser:appuser config/ ./config/
COPY --chown=appuser:appuser cli.py ./
COPY --chown=appuser:appuser docker-entrypoint.sh ./

RUN mkdir -p data/logs data/staging data/storage data/uploads data/backups && \
    chmod +x docker-entrypoint.sh && \
    chown -R appuser:appuser /app

USER appuser

# With OCR, the first scan downloads the PP-OCRv5 models (~20 MB) to
# /home/appuser/.paddlex; mount a volume there to keep them across restarts.
# DATABASE_URL is deliberately not set here; it comes from the server's .env.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    TRUSTED_PROXY_IPS=127.0.0.1

LABEL description="Paperless Factory backend API"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
