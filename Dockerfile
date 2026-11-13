# syntax=docker/dockerfile:1

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Bootstrap the packaging trust store with the PSF-published wheel/hash.
RUN python -m pip install --no-cache-dir "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70" \
    && python -m pip install --no-cache-dir "certifi>=2026.10.19" "uv==0.13.4"

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
