# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Use /app as WORKDIR so venv paths match the runtime stage exactly.
# If builder used a different path (e.g. /build), .venv/bin shebang lines
# would point to the wrong Python interpreter in the runtime image.
WORKDIR /app

# Copy dependency files first (layer cache)
COPY pyproject.toml uv.lock ./

# Install dependencies (not the project itself yet)
RUN uv sync --frozen --no-install-project --no-dev

# Copy source and install the project itself
COPY README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Install runtime OS deps: neonize needs libstdc++ and libmagic
RUN apt-get update && apt-get install -y --no-install-recommends \
    libstdc++6 \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtualenv and source from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Copy alembic migration files
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Storage and logs directories (will be mounted as volumes)
RUN mkdir -p /app/storage /app/logs

# Activate venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src"

# Non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8077

CMD ["python", "-m", "whatsapp_platform"]
