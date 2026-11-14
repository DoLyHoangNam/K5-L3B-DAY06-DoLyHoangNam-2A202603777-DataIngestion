"""Real Gemini embedding provider adapter with rate-limit retry and local cache."""
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Protocol

from google import genai
from google.genai import errors, types


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Google Gemini embedding adapter using google-genai SDK."""

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        cache_path: Path | None = None,
    ) -> None:
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL") or "gemini-embedding-001"
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is missing in environment/.env")
        self._client = genai.Client(api_key=key)
        self.total_chars = 0
        self.api_calls = 0

        self._cache_path = cache_path or (
            Path(__file__).resolve().parents[1] / ".cache" / "embeddings_cache.json"
        )
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        if self._cache_path.exists():
            self._cache: dict[str, list[float]] = json.loads(
                self._cache_path.read_text(encoding="utf-8")
            )
        else:
            self._cache = {}

        probe = self._embed_with_retry(["dimension_probe"], "RETRIEVAL_DOCUMENT")
        self.dimensions = len(probe[0])

    def _cache_key(self, text: str, task_type: str) -> str:
        digest = hashlib.sha256(f"{self.model_name}::{task_type}::{text}".encode("utf-8")).hexdigest()
        return digest

    def _save_cache(self) -> None:
        self._cache_path.write_text(
            json.dumps(self._cache), encoding="utf-8"
        )

    def _embed_with_retry(self, texts: list[str], task_type: str) -> list[list[float]]:
        uncached_idx: list[int] = []
        uncached_texts: list[str] = []
        results: list[list[float] | None] = [None] * len(texts)

        for i, t in enumerate(texts):
            k = self._cache_key(t, task_type)
            if k in self._cache:
                results[i] = self._cache[k]
            else:
                uncached_idx.append(i)
                uncached_texts.append(t)

        if uncached_texts:
            for attempt in range(8):
                try:
                    self.total_chars += sum(len(t) for t in uncached_texts)
                    self.api_calls += 1
                    resp = self._client.models.embed_content(
                        model=self.model_name,
                        contents=uncached_texts,
                        config=types.EmbedContentConfig(task_type=task_type),
                    )
                    if len(resp.embeddings) != len(uncached_texts):
                        raise RuntimeError(
                            f"Embedding count mismatch: sent {len(uncached_texts)}, got {len(resp.embeddings)}"
                        )
                    for idx, emb in zip(uncached_idx, resp.embeddings):
                        vec = list(emb.values)
                        results[idx] = vec
                        self._cache[self._cache_key(texts[idx], task_type)] = vec
                    self._save_cache()
                    break
                except errors.ClientError as exc:
                    if exc.code == 429 and attempt < 7:
                        print(f"  [rate-limit 429] sleeping 62s before retry ({attempt + 1}/7)...")
                        time.sleep(62)
                        continue
                    raise

        return [r for r in results if r is not None]

    def embed_documents(self, texts: list[str], batch_size: int = 80) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        total = len(texts)
        for i in range(0, total, batch_size):
            batch = texts[i : i + batch_size]
            vecs = self._embed_with_retry(batch, "RETRIEVAL_DOCUMENT")
            vectors.extend(vecs)
            done = min(i + batch_size, total)
            print(f"  Embedded {done}/{total} chunks")
        return vectors

    def embed_query(self, question: str) -> list[float]:
        return self._embed_with_retry([question], "RETRIEVAL_QUERY")[0]
