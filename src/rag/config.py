"""
Configuration for RAG retrieval pipeline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _default_require_pgvector() -> bool:
    return os.getenv("APP_ENV", "").strip().lower() == "production"


@dataclass
class RAGConfig:
    """Configuration for RAG retrieval."""

    use_hyde: bool = True
    use_reranker: bool = True
    use_query_rewriting: bool = True
    use_pgvector: bool = _env_flag("RAG_USE_PGVECTOR", True)
    require_pgvector: bool = _env_flag("RAG_REQUIRE_PGVECTOR", _default_require_pgvector())
    top_k: int = 5
    candidate_k: int = 20
