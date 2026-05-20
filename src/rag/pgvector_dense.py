"""pgvector-backed dense semantic retriever."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import List, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg.types.json import Json
from sentence_transformers import SentenceTransformer

from .dense import EMBEDDING_MODEL
from .index import ChunkRecord

logger = logging.getLogger(__name__)

VECTOR_DIMENSION = 384


def _database_url_for_psycopg(raw_url: str) -> str:
    """Convert the app's async SQLAlchemy URL into a libpq-compatible URL."""
    parts = urlsplit(raw_url)
    scheme = parts.scheme.split("+", 1)[0]
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if query.pop("ssl", None) == "require":
        query.setdefault("sslmode", "require")
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _chunk_hash(chunk: ChunkRecord) -> str:
    payload = {
        "book_id": chunk.book_id,
        "header_path": chunk.header_path,
        "chunk_type": chunk.chunk_type,
        "key_terms": chunk.key_terms,
        "text": chunk.text,
        "potential_questions": chunk.potential_questions,
        "subject": chunk.subject,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _vector_literal(values) -> str:
    return "[" + ",".join(f"{float(value):.8f}" for value in values) + "]"


@dataclass
class PgVectorDenseIndex:
    """Dense semantic retrieval index persisted in PostgreSQL pgvector."""

    model: SentenceTransformer
    database_url: str

    @classmethod
    def from_chunks(cls, chunks: List[ChunkRecord]) -> "PgVectorDenseIndex":
        raw_database_url = os.getenv("DATABASE_URL")
        if not raw_database_url:
            raise RuntimeError("DATABASE_URL is required for pgvector dense search")

        model = SentenceTransformer(EMBEDDING_MODEL)
        dimension = model.get_sentence_embedding_dimension()
        if dimension != VECTOR_DIMENSION:
            raise RuntimeError(
                f"EMBEDDING_MODEL={EMBEDDING_MODEL} emits {dimension} dimensions; "
                f"pgvector schema expects {VECTOR_DIMENSION}."
            )

        index = cls(model=model, database_url=_database_url_for_psycopg(raw_database_url))
        index.sync_chunks(chunks)
        return index

    def sync_chunks(self, chunks: List[ChunkRecord]) -> None:
        """Upsert chunk metadata and fill missing/stale vectors."""
        chunk_by_id = {chunk.id: chunk for chunk in chunks}
        hash_by_id = {chunk.id: _chunk_hash(chunk) for chunk in chunks}

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                for chunk in chunks:
                    cur.execute(
                        """
                        INSERT INTO document_chunks (
                            id,
                            book_id,
                            header_path,
                            chunk_type,
                            key_terms,
                            text,
                            potential_questions,
                            subject,
                            embedding_model,
                            embedding_content_hash
                        )
                        VALUES (
                            %(id)s,
                            %(book_id)s,
                            %(header_path)s,
                            %(chunk_type)s,
                            %(key_terms)s,
                            %(text)s,
                            %(potential_questions)s,
                            %(subject)s,
                            %(embedding_model)s,
                            %(embedding_content_hash)s
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            book_id = EXCLUDED.book_id,
                            header_path = EXCLUDED.header_path,
                            chunk_type = EXCLUDED.chunk_type,
                            key_terms = EXCLUDED.key_terms,
                            text = EXCLUDED.text,
                            potential_questions = EXCLUDED.potential_questions,
                            subject = EXCLUDED.subject,
                            embedding_vector = CASE
                                WHEN document_chunks.embedding_model IS DISTINCT FROM EXCLUDED.embedding_model
                                  OR document_chunks.embedding_content_hash IS DISTINCT FROM EXCLUDED.embedding_content_hash
                                THEN NULL
                                ELSE document_chunks.embedding_vector
                            END,
                            embedding_model = EXCLUDED.embedding_model,
                            embedding_content_hash = EXCLUDED.embedding_content_hash
                        """,
                        {
                            "id": chunk.id,
                            "book_id": chunk.book_id,
                            "header_path": chunk.header_path,
                            "chunk_type": chunk.chunk_type,
                            "key_terms": Json(chunk.key_terms),
                            "text": chunk.text,
                            "potential_questions": Json(chunk.potential_questions),
                            "subject": chunk.subject,
                            "embedding_model": EMBEDDING_MODEL,
                            "embedding_content_hash": hash_by_id[chunk.id],
                        },
                    )

                cur.execute(
                    """
                    SELECT id
                    FROM document_chunks
                    WHERE embedding_model = %s
                      AND embedding_vector IS NULL
                      AND id = ANY(%s)
                    ORDER BY id
                    """,
                    (EMBEDDING_MODEL, list(chunk_by_id)),
                )
                missing_ids = [row[0] for row in cur.fetchall()]

                if missing_ids:
                    logger.info("Encoding %s document chunks for pgvector", len(missing_ids))
                    texts = [chunk_by_id[chunk_id].text for chunk_id in missing_ids]
                    embeddings = self.model.encode(
                        texts,
                        batch_size=64,
                        show_progress_bar=True,
                        convert_to_numpy=True,
                        normalize_embeddings=True,
                    )
                    for chunk_id, embedding in zip(missing_ids, embeddings):
                        cur.execute(
                            """
                            UPDATE document_chunks
                            SET embedding_vector = %s::vector
                            WHERE id = %s
                            """,
                            (_vector_literal(embedding), chunk_id),
                        )

                cur.execute("ANALYZE document_chunks")
            conn.commit()

    def search(self, query: str, top_k: int = 5) -> List[Tuple[ChunkRecord, float]]:
        """Search for top-k chunks with pgvector cosine similarity."""
        query_embedding = self.model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True,
        )[0]

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id,
                        book_id,
                        header_path,
                        chunk_type,
                        key_terms,
                        text,
                        potential_questions,
                        subject,
                        1 - (embedding_vector <=> %s::vector) AS score
                    FROM document_chunks
                    WHERE embedding_model = %s
                      AND embedding_vector IS NOT NULL
                    ORDER BY embedding_vector <=> %s::vector
                    LIMIT %s
                    """,
                    (
                        _vector_literal(query_embedding),
                        EMBEDDING_MODEL,
                        _vector_literal(query_embedding),
                        top_k,
                    ),
                )
                rows = cur.fetchall()

        return [
            (
                ChunkRecord(
                    id=row[0],
                    book_id=row[1],
                    header_path=row[2],
                    chunk_type=row[3],
                    key_terms=row[4] or [],
                    text=row[5],
                    potential_questions=row[6] or [],
                    subject=row[7],
                ),
                float(row[8]),
            )
            for row in rows
        ]
