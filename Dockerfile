# Multi-stage build: uv-managed deps → slim API-only runtime image.
# The TUI is NOT meant to run inside this container — it connects over HTTP.

# ---- Builder: resolve + compile deps with uv ----
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Layer 1: dependencies only (cached until pyproject/uv.lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project

# Layer 2: project source (invalidates only on source change)
COPY app ./app
RUN uv sync --no-dev

# ---- Runtime: minimal python, venv copied in ----
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    UVICORN_HOST="0.0.0.0" \
    UVICORN_PORT="8333" \
    ALERTS_DB_PATH="/app/data/alerts.db"

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY app ./app

# Non-root user for defense in depth; /app/data persists via named volume
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8333

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8333"]