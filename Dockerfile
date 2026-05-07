# ── Aegis Backend — Railway entry point ──────────────────────────────────────
# Railway builds from the repo root; this file copies from aegis-backend/.
# The aegis-backend/Dockerfile is used for local docker compose.
FROM python:3.12-slim

WORKDIR /app

# System dependencies (libpq for psycopg2, gcc for C extensions)
RUN apt-get update && apt-get install -y \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached layer)
COPY aegis-backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY aegis-backend/ .

# Non-root user for security
RUN useradd -m -u 1000 aegis && chown -R aegis:aegis /app
USER aegis

EXPOSE 8000

# $PORT is injected by Railway at runtime
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
