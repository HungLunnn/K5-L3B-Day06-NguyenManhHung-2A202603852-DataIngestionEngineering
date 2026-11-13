"""Store and search vectors using PostgreSQL + pgvector."""
from __future__ import annotations

from typing import Any
import json

import psycopg

from .models import Chunk


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        """Keep database configuration and validate the model dimension count."""
        if dimensions <= 0:
            raise ValueError("dimensions must be a positive integer")
        self.database_url = database_url
        self.dimensions = int(dimensions)

    def create_schema(self) -> None:
        """Create the vector table and supporting indexes."""
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS vector_chunks (
                        id TEXT PRIMARY KEY,
                        strategy TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        source TEXT NOT NULL,
                        page INTEGER NOT NULL,
                        chunk_id TEXT NOT NULL,
                        text TEXT NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{{}}',
                        embedding vector({self.dimensions}) NOT NULL
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_vector_chunks_strategy ON vector_chunks(strategy)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_vector_chunks_metadata ON vector_chunks USING GIN(metadata)"
                )
                try:
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_vector_chunks_hnsw ON vector_chunks USING hnsw (embedding vector_cosine_ops)"
                    )
                except Exception:
                    pass
            connection.commit()

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Insert or update chunks and remove stale entries for the same strategy."""
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        if not chunks:
            return

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM vector_chunks WHERE strategy = %s", (strategy,))
                for chunk, vector in zip(chunks, vectors):
                    if len(vector) != self.dimensions:
                        raise ValueError(
                            f"Dimension mismatch for {chunk.chunk_id}: expected {self.dimensions}, got {len(vector)}"
                        )
                    metadata = dict(chunk.metadata)
                    metadata.setdefault("document_id", chunk.document_id)
                    metadata.setdefault("source", chunk.source)
                    metadata.setdefault("page", chunk.page)
                    row_id = f"{strategy}:{chunk.chunk_id}"
                    cursor.execute(
                        """
                        INSERT INTO vector_chunks (
                            id, strategy, document_id, source, page, chunk_id, text, metadata, embedding
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            strategy = EXCLUDED.strategy,
                            document_id = EXCLUDED.document_id,
                            source = EXCLUDED.source,
                            page = EXCLUDED.page,
                            chunk_id = EXCLUDED.chunk_id,
                            text = EXCLUDED.text,
                            metadata = EXCLUDED.metadata,
                            embedding = EXCLUDED.embedding
                        """,
                        (
                            row_id,
                            strategy,
                            chunk.document_id,
                            chunk.source,
                            chunk.page,
                            chunk.chunk_id,
                            chunk.text,
                            json.dumps(metadata),
                            vector,
                        ),
                    )
            connection.commit()

    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return top-k chunks matching the selected metadata filters."""
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if len(query_vector) != self.dimensions:
            raise ValueError(
                f"Query vector dimension mismatch: expected {self.dimensions}, got {len(query_vector)}"
            )

        filters = filters or {}
        sql = """
            SELECT chunk_id, document_id, source, page, text, metadata,
                   1 - (embedding <=> %s::vector) AS score
            FROM vector_chunks
            WHERE strategy = %s
        """
        params: list[Any] = [query_vector, strategy]

        for key, value in filters.items():
            sql += " AND metadata ->> %s = %s"
            params.extend([key, str(value)])

        sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
        params.extend([query_vector, top_k])

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            chunk_id, document_id, source, page, text, metadata, score = row
            result.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "source": source,
                    "page": page,
                    "text": text,
                    "score": float(score),
                    "metadata": metadata,
                }
            )
        return result
