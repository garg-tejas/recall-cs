# syntax=docker/dockerfile:1

FROM python:3.12-slim

WORKDIR /app

# Install system deps (for sentence-transformers, asyncpg, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reproducible Python dependency resolution
RUN pip install --no-cache-dir uv

# Copy dependency files and install with lock file for reproducibility
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra cpu

# Copy application code
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY data/ ./data/
COPY scripts/ ./scripts/

# Ensure uv's venv binaries are on PATH
ENV PATH="/app/.venv/bin:$PATH"

# Expose FastAPI port
EXPOSE 8000

# Run migrations then start server
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.api.main:app --host 0.0.0.0 --port 8000"]
