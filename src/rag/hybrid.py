"""
Hybrid searcher combining BM25 and dense retrieval with RRF fusion.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .bm25 import BM25Index
from .config import RAGConfig
from .context_window import build_book_index, expand_with_neighbors
from .dense import DenseIndex
from .pgvector_dense import PgVectorDenseIndex
from .hyde import HydeGenerator
from .index import ChunkRecord
from .query_rewriter import QueryRewriter
from .query_understanding import (
    analyze,
    chunk_about_concept,
    chunk_negates_concept,
)
from .reranker import CrossEncoderReranker
from .retriever import RetrievalResult
from .rrf_merger import rrf_merge

logger = logging.getLogger(__name__)

DEFINITION_BOOST = 1.5
NEGATIVE_PENALTY = 0.25


@dataclass
class HybridSearcher:
    """Hybrid searcher combining BM25 and dense retrieval."""

    bm25_index: BM25Index
    dense_index: DenseIndex
    config: RAGConfig
    reranker: CrossEncoderReranker | None = None
    chunks: List[ChunkRecord] | None = None
    query_rewriter: QueryRewriter | None = None
    hyde_generator: HydeGenerator | None = None
    _hyde_disabled: bool = False

    @classmethod
    def from_chunks(
        cls,
        chunks: List[ChunkRecord],
        *,
        config: RAGConfig | None = None,
        use_reranker: bool | None = None,
        use_context_expansion: bool = False,
        use_hyde: bool | None = None,
    ) -> "HybridSearcher":
        """Create a HybridSearcher from chunks."""
        if config is None:
            config = RAGConfig()
        else:
            config = dataclasses.replace(config)

        if use_reranker is not None:
            config.use_reranker = use_reranker
        if use_hyde is not None:
            config.use_hyde = use_hyde

        bm25 = BM25Index.from_chunks(chunks)
        if config.use_pgvector:
            try:
                dense = PgVectorDenseIndex.from_chunks(chunks)
                logger.info("Using PostgreSQL pgvector dense retrieval")
            except Exception as e:
                if config.require_pgvector:
                    raise RuntimeError("pgvector dense retrieval is required but unavailable") from e
                logger.warning("pgvector dense retrieval unavailable; using local dense index: %s", e)
                dense = DenseIndex.from_chunks(chunks)
        else:
            dense = DenseIndex.from_chunks(chunks)
        reranker = CrossEncoderReranker() if config.use_reranker else None
        stored_chunks = chunks if use_context_expansion else None
        rewriter = QueryRewriter() if config.use_query_rewriting else None
        hyde_gen: HydeGenerator | None = None
        hyde_disabled = False
        if config.use_hyde:
            try:
                hyde_gen = HydeGenerator.from_env()
            except Exception as e:
                logger.warning("HYDE disabled (initialization failed): %s", e)
                hyde_disabled = True
        return cls(
            bm25_index=bm25,
            dense_index=dense,
            config=config,
            reranker=reranker,
            chunks=stored_chunks,
            query_rewriter=rewriter,
            _hyde_disabled=hyde_disabled,
            hyde_generator=hyde_gen,
        )

    def search(
        self,
        query: str,
        top_k: int | None = None,
        *,
        intent=None,
        subject: str | None = None,
    ) -> List[RetrievalResult]:
        """
        Search for top-k chunks matching the query.

        Implements the Retriever protocol.
        """
        if top_k is None:
            top_k = self.config.top_k

        if intent is None:
            intent = analyze(query)

        candidate_k = max(top_k * 3, self.config.candidate_k)

        if self.query_rewriter is not None:
            rewritten = self.query_rewriter.rewrite(query)
            bm25_query = rewritten["bm25_query"]
            dense_query = rewritten["semantic_query"]
        else:
            bm25_query = query
            dense_query = query

        dense_input = dense_query
        if (
            self.config.use_hyde
            and self.hyde_generator is not None
            and not self._hyde_disabled
        ):
            try:
                hyde_answer = self.hyde_generator.generate_hypothetical_answer(
                    query,
                    subject=subject,
                )
                if hyde_answer:
                    dense_input = hyde_answer
            except Exception as e:
                logger.warning("HYDE error, falling back to normal dense search: %s", e)
                self._hyde_disabled = True

        bm25_results = self.bm25_index.search(bm25_query, top_k=candidate_k)
        dense_results = self.dense_index.search(dense_input, top_k=candidate_k)

        bm25_ids = [(c.id, s) for c, s in bm25_results]
        dense_ids = [(c.id, s) for c, s in dense_results]

        merged = rrf_merge([bm25_ids, dense_ids], k=candidate_k)

        id_to_chunk: Dict[str, ChunkRecord] = {
            c.id: c for c, _ in bm25_results + dense_results
        }

        scored: List[Tuple[ChunkRecord, float]] = []
        for cid, score in merged:
            if cid not in id_to_chunk:
                continue
            ch = id_to_chunk[cid]

            if ch.chunk_type in ("exercise", "references", "bibliography", "citations"):
                continue

            header_lower = ch.header_path.lower()

            if any(
                marker in header_lower
                for marker in (
                    "references",
                    "selected bibliography",
                    "bibliography",
                    "further reading",
                    "appendix",
                    "exercises",
                    "review questions",
                )
            ):
                continue

            if getattr(intent, "negative_signals", None):
                prefix_text = (ch.header_path + " " + ch.text[:200]).lower()
                if any(sig in prefix_text for sig in intent.negative_signals):
                    continue

            s = score

            if intent.concept and chunk_negates_concept(ch, intent.concept):
                s *= NEGATIVE_PENALTY

            if intent.is_definition_seeking and ch.chunk_type == "definition":
                if intent.concept is None or chunk_about_concept(ch, intent.concept):
                    s *= DEFINITION_BOOST

            if getattr(intent, "is_procedural", False) and ch.chunk_type in (
                "algorithm",
                "section",
            ):
                s *= 1.10

            if getattr(intent, "is_comparative", False) and ch.chunk_type in (
                "protocol",
                "comparison",
                "section",
            ):
                s *= 1.05

            scored.append((ch, s))

        if self.reranker is not None:
            reranked = self.reranker.rerank(query, scored)
            scored = reranked[:top_k]
        else:
            scored.sort(key=lambda x: x[1], reverse=True)
            scored = scored[:top_k]

        results: List[RetrievalResult] = []
        for chunk, score in scored:
            source = "reranked" if self.reranker else "hybrid"
            results.append(RetrievalResult(chunk=chunk, score=score, source=source))

        return results

    def search_raw(
        self, query: str, top_k: int = 5, *, intent=None
    ) -> List[Tuple[ChunkRecord, float]]:
        """Search and return raw (chunk, score) tuples for backward compatibility."""
        results = self.search(query, top_k=top_k, intent=intent)
        return [(r.chunk, r.score) for r in results]

    def search_with_context(
        self, query: str, top_k: int = 5, *, intent=None, window: int = 1
    ) -> List[ChunkRecord]:
        """
        Search and expand results with neighboring chunks from the same book.

        Returns a list of ChunkRecord (no scores) that includes the top-k results
        plus their neighbors within the specified window.
        """
        if self.chunks is None:
            raise ValueError(
                "Context expansion requires chunks to be stored. "
                "Use from_chunks(..., use_context_expansion=True)"
            )

        raw_results = self.search_raw(query, top_k=top_k, intent=intent)
        by_book = build_book_index(self.chunks)
        expanded = expand_with_neighbors(raw_results, by_book=by_book, window=window)
        return expanded
