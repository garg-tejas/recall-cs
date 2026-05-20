from src.rag.index import ChunkRecord
from src.rag.pgvector_dense import _chunk_hash, _database_url_for_psycopg


def test_database_url_for_psycopg_converts_asyncpg_and_ssl() -> None:
    raw = "postgresql+asyncpg://user:pass@example.com:25060/appdb?ssl=require"

    converted = _database_url_for_psycopg(raw)

    assert converted == "postgresql://user:pass@example.com:25060/appdb?sslmode=require"


def test_chunk_hash_changes_when_content_changes() -> None:
    chunk = ChunkRecord(
        id="cn:1",
        book_id="cn",
        header_path="Networks > Routing",
        chunk_type="section",
        key_terms=["routing"],
        text="Distance vector routing exchanges route tables.",
        potential_questions=["What is distance vector routing?"],
        subject="cn",
    )
    changed = ChunkRecord(
        **{
            **chunk.__dict__,
            "text": "Link state routing floods topology information.",
        }
    )

    assert _chunk_hash(chunk) != _chunk_hash(changed)
