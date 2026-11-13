"""Choose a real embedding provider (API or local) and implement this contract."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import error, request

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Embedder:
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder(Embedder):
    """OpenAI-compatible embedding adapter used by the starter pipeline."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.base_url = (
            os.getenv("OPENAI_BASE_URL")
            or os.getenv("OPENROUTER_BASE_URL")
            or "https://api.openai.com/v1"
        )
        self.api_key = (
            os.getenv("OPENAI_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("GEMINI_API_KEY")
        )
        if not self.api_key:
            raise ValueError("No API key configured for embeddings. Set OPENAI_API_KEY or OPENROUTER_API_KEY in starter/.env.")
        self.dimensions = 0

    def _request_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        endpoint = self.base_url.rstrip("/") + "/embeddings"
        payload = {"model": self.model_name, "input": texts}
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Embedding request failed: {detail}") from exc

        data = payload.get("data", [])
        if not data:
            raise RuntimeError("Embedding provider returned no data.")
        vectors = []
        for item in data:
            embedding = item.get("embedding")
            if embedding is None:
                raise RuntimeError("Embedding provider response missing 'embedding'.")
            vectors.append([float(v) for v in embedding])
        if self.dimensions == 0 and vectors:
            self.dimensions = len(vectors[0])
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._request_embeddings(texts)
        if len(vectors) != len(texts):
            raise RuntimeError("Embedding count mismatch between request and response.")
        return vectors

    def embed_query(self, question: str) -> list[float]:
        vectors = self._request_embeddings([question])
        return vectors[0]
