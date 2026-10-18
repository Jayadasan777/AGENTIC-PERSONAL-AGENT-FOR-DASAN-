"""Embedding provider abstraction and implementations.

Supports:
- ``MockEmbeddingProvider``: Fast, deterministic, zero-cost embedding generator using
  feature hashing and L2 unit normalization. Ideal for testing and CI.
- ``OllamaEmbeddingProvider``: Local Ollama /api/embeddings or /api/embed client.
- ``get_embedding_provider()``: Factory choosing provider based on application Settings.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from backend.app.core.config import get_settings


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute the cosine similarity between two float vectors.

    cos_sim(v1, v2) = (v1 . v2) / (||v1|| * ||v2||)
    Returns float in range [-1.0, 1.0].
    """
    if len(v1) != len(v2) or not v1:
        return 0.0

    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


class BaseEmbeddingProvider(ABC):
    """Abstract base class for text embedding models."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimensionality."""

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for a single text string."""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of text strings."""


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic, zero-cost embedding provider using token-hash random projection.

    Produces unit-normalized vectors where identical texts yield identical embeddings,
    and texts with overlapping tokens yield positive cosine similarity.
    """

    def __init__(self, dimension: int = 384) -> None:
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def _embed_sync(self, text: str) -> list[float]:
        cleaned = text.lower().strip()
        raw_tokens = re.findall(r"\w+", cleaned)
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "as",
            "in",
            "for",
            "over",
            "and",
            "or",
            "to",
            "at",
            "does",
            "do",
            "did",
            "which",
            "what",
            "how",
            "who",
            "user",
            "of",
            "by",
            "with",
            "from",
        }
        tokens = []
        for t in raw_tokens:
            if t not in stop_words and len(t) > 2:
                # Lightweight suffix stripping for basic stemming
                if t.endswith("ing") and len(t) > 5:
                    t = t[:-3]
                elif t.endswith("ed") and len(t) > 4:
                    t = t[:-2]
                elif t.endswith("es") and len(t) > 4:
                    t = t[:-2]
                elif t.endswith("s") and len(t) > 3:
                    t = t[:-1]
                tokens.append(t)

        if not tokens:
            tokens = raw_tokens or ["<empty>"]

        vec = [0.0] * self._dim

        for token in tokens:
            # Deterministic hash of the token
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            # Distribute across vector dimensions using chunks of the digest
            for i in range(min(len(digest) // 2, self._dim)):
                idx = (int.from_bytes(digest[i * 2 : (i + 1) * 2], "big")) % self._dim
                # Determine sign from least significant bit
                sign = 1.0 if (digest[i] & 1) else -1.0
                vec[idx] += sign

        # L2 normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0.0:
            vec = [x / norm for x in vec]
        else:
            vec[0] = 1.0

        return vec

    async def embed_text(self, text: str) -> list[float]:
        return self._embed_sync(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_sync(t) for t in texts]


class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    """Ollama local embedding provider connecting via HTTP."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        dimension: int = 384,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._dim = dimension
        self.timeout = timeout

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed_text(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            embedding = data.get("embedding", [])
            return [float(x) for x in embedding]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_text(t) for t in texts]


def get_embedding_provider() -> BaseEmbeddingProvider:
    """Factory returning the configured embedding provider."""
    settings = get_settings()
    if settings.EMBEDDING_PROVIDER == "mock":
        return MockEmbeddingProvider(dimension=settings.EMBEDDING_DIM)
    if settings.EMBEDDING_PROVIDER == "ollama":
        return OllamaEmbeddingProvider(
            base_url=settings.MODEL_BASE_URL,
            model=settings.EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIM,
        )
    return MockEmbeddingProvider(dimension=settings.EMBEDDING_DIM)
