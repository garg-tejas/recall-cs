FROM python:3.12-slim

WORKDIR /app

# Install system deps + uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:$PATH"

# Copy dependency manifests first for Docker layer caching
COPY pyproject.toml uv.lock ./

# Install deps INCLUDING the cpu extra so torch is available.
# --no-dev keeps it lean; --extra cpu pulls torch from the pytorch-cpu index.
RUN uv sync --frozen --no-dev --extra cpu

# Pre-download ML models so cold starts don't hit HuggingFace.
# Uses the venv python directly to avoid uv run overhead/issues.
RUN /app/.venv/bin/python -c "\
from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('all-MiniLM-L6-v2'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# Copy application code
COPY src/ ./src/
COPY data/ ./data/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/entrypoint.sh ./scripts/entrypoint.sh
RUN chmod +x ./scripts/entrypoint.sh

# Use the virtualenv binaries directly
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

ENTRYPOINT ["./scripts/entrypoint.sh"]
