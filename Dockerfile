# syntax=docker/dockerfile:1

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install uv for fast, reproducible Python dependency resolution
RUN pip install --no-cache-dir uv

# Copy dependency files and install with lock file for reproducibility
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra cpu --no-dev --no-cache

# Copy application code
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY entrypoint.sh ./
COPY data/ ./data/
COPY scripts/ ./scripts/

# Ensure uv's venv binaries are on PATH
ENV PATH="/app/.venv/bin:$PATH"

# App Platform can inject PORT; entrypoint defaults to 8000 locally.
EXPOSE 8000

# Run migrations then start server via entrypoint script.
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh
CMD ["sh", "./entrypoint.sh"]
