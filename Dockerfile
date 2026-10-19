# ==============================================================================
# AURA AGENTIC SYSTEM: Multi-Stage Hardened Production Dockerfile
# ==============================================================================
# Stage 1: Build virtualenv and install dependencies
# Stage 2: Minimal hardened non-root runtime with healthcheck
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Builder
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy package definitions and install dependencies
COPY pyproject.toml .
RUN pip install --upgrade pip setuptools wheel && \
    pip install .

# ------------------------------------------------------------------------------
# Stage 2: Production Hardened Runtime
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Create low-privilege system group and user
RUN groupadd -g 10001 aura && \
    useradd -u 10001 -g aura -s /bin/bash -m aura

# Install minimal runtime libraries (libpq for postgres, curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtualenv from builder
COPY --from=builder --chown=aura:aura /opt/venv /opt/venv

# Copy application source tree and configurations
COPY --chown=aura:aura alembic.ini .
COPY --chown=aura:aura alembic/ ./alembic/
COPY --chown=aura:aura backend/ ./backend/
COPY --chown=aura:aura scripts/ ./scripts/

# Create data directories with proper permissions
RUN mkdir -p /app/data /app/logs && \
    chown -R aura:aura /app/data /app/logs

# Switch to non-root user
USER aura

# Expose internal API port
EXPOSE 8000

# Container healthcheck testing /api/v1/health
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Production command with uvicorn
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
