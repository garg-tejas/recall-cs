"""add pgvector document chunk embeddings

Revision ID: f8a9b0c1d2e3
Revises: e2f3a4b5c6d7
Create Date: 2026-05-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'f8a9b0c1d2e3'
down_revision: Union[str, Sequence[str], None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column('document_chunks', sa.Column('embedding_vector', Vector(384), nullable=True))
    op.add_column('document_chunks', sa.Column('embedding_model', sa.String(length=128), nullable=True))
    op.add_column('document_chunks', sa.Column('embedding_content_hash', sa.String(length=64), nullable=True))
    op.create_index(
        op.f('ix_document_chunks_embedding_model'),
        'document_chunks',
        ['embedding_model'],
        unique=False,
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_vector
        ON document_chunks USING ivfflat (embedding_vector vector_cosine_ops)
        WITH (lists = 100)
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_vector")
    op.drop_index(op.f('ix_document_chunks_embedding_model'), table_name='document_chunks')
    op.drop_column('document_chunks', 'embedding_content_hash')
    op.drop_column('document_chunks', 'embedding_model')
    op.drop_column('document_chunks', 'embedding_vector')
