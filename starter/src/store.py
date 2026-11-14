"""Store and search vectors using PostgreSQL + pgvector (exact cosine distance)."""
import json
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .models import Chunk

ALLOWED_FILTER_KEYS = {"year", "section", "document_id"}


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{float(x):.8g}" for x in vec) + "]"


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        if int(dimensions) <= 0:
            raise ValueError(f"Invalid dimensions: {dimensions}")
        self.database_url = database_url
        self.dimensions = int(dimensions)

    def create_schema(self) -> None:
        """Create chunks table with vector column and metadata indexes."""
        ddl = f"""
        CREATE EXTENSION IF NOT EXISTS vector;
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            strategy TEXT NOT NULL,
            document_id TEXT NOT NULL,
            source TEXT NOT NULL,
            page INTEGER NOT NULL,
            year INTEGER,
            section TEXT,
            metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            text TEXT NOT NULL,
            embedding vector({self.dimensions}) NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_strategy_filters
            ON chunks (strategy, year, section);
        """
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Upsert chunks idempotently and prune obsolete chunks for re-ingested docs."""
        if len(chunks) != len(vectors):
            raise ValueError(f"Length mismatch: {len(chunks)} chunks vs {len(vectors)} vectors")
        for i, v in enumerate(vectors):
            if len(v) != self.dimensions:
                raise ValueError(
                    f"Vector {i} has {len(v)} dims, expected {self.dimensions}"
                )

        by_doc: dict[str, list[str]] = {}
        for c in chunks:
            by_doc.setdefault(c.document_id, []).append(c.chunk_id)

        upsert_sql = """
        INSERT INTO chunks (
            chunk_id, strategy, document_id, source, page, year, section, metadata, text, embedding
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::vector)
        ON CONFLICT (chunk_id) DO UPDATE SET
            strategy = EXCLUDED.strategy,
            document_id = EXCLUDED.document_id,
            source = EXCLUDED.source,
            page = EXCLUDED.page,
            year = EXCLUDED.year,
            section = EXCLUDED.section,
            metadata = EXCLUDED.metadata,
            text = EXCLUDED.text,
            embedding = EXCLUDED.embedding;
        """

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                for doc_id, keep_ids in by_doc.items():
                    cur.execute(
                        "DELETE FROM chunks WHERE strategy = %s AND document_id = %s AND NOT (chunk_id = ANY(%s))",
                        (strategy, doc_id, keep_ids),
                    )
                rows = [
                    (
                        c.chunk_id,
                        strategy,
                        c.document_id,
                        c.source,
                        c.page,
                        c.metadata.get("year"),
                        c.metadata.get("section"),
                        json.dumps(c.metadata, ensure_ascii=False),
                        c.text,
                        _vec_literal(vec),
                    )
                    for c, vec in zip(chunks, vectors)
                ]
                cur.executemany(upsert_sql, rows)
            conn.commit()

    def count_chunks(self, strategy: str) -> int:
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM chunks WHERE strategy = %s", (strategy,))
                return int(cur.fetchone()[0])

    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Filter permitted metadata in SQL, rank by exact cosine distance, return top-k."""
        if len(query_vector) != self.dimensions:
            raise ValueError(
                f"Query vector has {len(query_vector)} dims, expected {self.dimensions}"
            )

        clauses = ["strategy = %s"]
        params: list[Any] = [strategy]
        if filters:
            for key, val in filters.items():
                if key not in ALLOWED_FILTER_KEYS:
                    raise ValueError(f"Unsupported filter key: {key}")
                clauses.append(f"{key} = %s")
                params.append(val)

        q_lit = _vec_literal(query_vector)
        where_sql = " AND ".join(clauses)
        sql = f"""
        SELECT
            chunk_id,
            document_id,
            source,
            page,
            year,
            section,
            metadata,
            text,
            (embedding <=> %s::vector) AS distance,
            1.0 - (embedding <=> %s::vector) AS similarity
        FROM chunks
        WHERE {where_sql}
        ORDER BY embedding <=> %s::vector ASC
        LIMIT %s
        """
        exec_params = [q_lit, q_lit, *params, q_lit, int(top_k)]
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, exec_params)
                return [dict(r) for r in cur.fetchall()]
