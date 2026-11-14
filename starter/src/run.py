"""End-to-end Day 06 pipeline: ingest, chunk (A/B/C), embed, store, evaluate."""
import json
import os
import statistics
import time
from pathlib import Path

from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_corpus_from_manifest
from .models import Chunk
from .store import PgVectorStore


def _chunk_stats(strategy: str, chunks: list[Chunk], ingest_seconds: float) -> dict:
    lengths = [len(c.text) for c in chunks]
    return {
        "strategy": strategy,
        "chunk_count": len(chunks),
        "total_chars": sum(lengths),
        "min_len": min(lengths) if lengths else 0,
        "median_len": int(statistics.median(lengths)) if lengths else 0,
        "max_len": max(lengths) if lengths else 0,
        "ingest_seconds": round(ingest_seconds, 2),
    }


def main() -> None:
    starter_dir = Path(__file__).resolve().parents[1]
    project_root = starter_dir.parent
    load_dotenv(starter_dir / ".env")

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL missing in starter/.env")

    manifest_path = project_root / "data" / "manifest.json"
    questions_path = project_root / "benchmark" / "questions.json"
    results_dir = project_root / "results"
    results_dir.mkdir(exist_ok=True)

    # 1. Load corpus and validate >= 30 content pages
    pages, page_logs = load_corpus_from_manifest(manifest_path, project_root)
    if len(pages) < 30:
        raise RuntimeError(f"Expected >= 30 content pages, got {len(pages)}")
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    print(f"Loaded {len(pages)} content pages and {len(questions)} benchmark questions.")

    # 2. Build strategies A (fixed 500/50), B (paragraph <=800), C (B + metadata filter)
    chunks_a = [c for p in pages for c in fixed_size(p, size=500, overlap=50, strategy="A")]
    chunks_b = [c for p in pages for c in by_paragraph(p, max_size=800, strategy="B")]
    chunks_c = [c for p in pages for c in by_paragraph(p, max_size=800, strategy="C")]

    # 3. Initialize real embedder and pgvector store
    embedder = MyEmbedder()
    store = PgVectorStore(database_url=db_url, dimensions=embedder.dimensions)
    store.create_schema()
    print(f"Embedder: {embedder.model_name} ({embedder.dimensions} dims) | Store: pgvector exact cosine")

    # Embed and store A
    t0 = time.perf_counter()
    vecs_a = embedder.embed_documents([c.text for c in chunks_a])
    store.upsert("A", chunks_a, vecs_a)
    t_a = time.perf_counter() - t0

    # Embed and store B; reuse identical text embeddings for C (B and C share identical chunking)
    t0 = time.perf_counter()
    vecs_b = embedder.embed_documents([c.text for c in chunks_b])
    store.upsert("B", chunks_b, vecs_b)
    t_b = time.perf_counter() - t0

    t0 = time.perf_counter()
    store.upsert("C", chunks_c, vecs_b)
    t_c = time.perf_counter() - t0

    # Verify idempotent re-ingest (no duplicate rows)
    count_before = store.count_chunks("B")
    store.upsert("B", chunks_b, vecs_b)
    count_after = store.count_chunks("B")
    assert count_before == count_after, f"Duplicate rows on re-ingest: {count_before} -> {count_after}"

    chunk_stats = [
        _chunk_stats("A", chunks_a, t_a),
        _chunk_stats("B", chunks_b, t_b),
        _chunk_stats("C", chunks_c, t_c),
    ]

    # 4. Embed all benchmark queries once (same model & vectors for A, B, C)
    query_vectors = {q["id"]: embedder.embed_query(q["question"]) for q in questions}

    # 5. Evaluate A, B, C and save full top-3 traces
    all_traces: list[dict] = []
    for strat, use_filter in [("A", False), ("B", False), ("C", True)]:
        strat_traces: list[dict] = []
        for q in questions:
            flt = q.get("filter") if use_filter else None
            hits = store.search(strat, query_vectors[q["id"]], top_k=3, filters=flt)
            trace = evaluate_query(strat, q, hits, applied_filter=flt)
            strat_traces.append(trace)
            all_traces.append(trace)

        trace_file = results_dir / f"traces_{strat}.jsonl"
        trace_file.write_text(
            "\n".join(json.dumps(t, ensure_ascii=False) for t in strat_traces) + "\n",
            encoding="utf-8",
        )

    metrics = summarize(all_traces)
    (results_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (results_dir / "chunk_stats.json").write_text(
        json.dumps(chunk_stats, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    ingest_log = {
        "content_pages": len(pages),
        "empty_or_error_pages": page_logs,
        "embedder_model": embedder.model_name,
        "dimensions": embedder.dimensions,
        "api_calls": embedder.api_calls,
        "total_embedded_chars": embedder.total_chars,
        "reingest_idempotency_check": {"strategy": "B", "before": count_before, "after": count_after},
    }
    (results_dir / "ingest_log.json").write_text(
        json.dumps(ingest_log, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n=== SUMMARY ===")
    for k, m in metrics.items():
        print(f"{k:8s} | Hit@1: {m['hit1_ratio']} ({m['hit1_pct']}%) | Hit@3: {m['hit3_ratio']} ({m['hit3_pct']}%)")
    print("\n=== CHUNK STATS ===")
    for s in chunk_stats:
        print(s)


if __name__ == "__main__":
    main()
