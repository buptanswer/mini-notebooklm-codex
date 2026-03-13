from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings
from app.schemas.embedding_api import EmbeddingRequest, EmbeddingResponse


@dataclass(slots=True)
class EmbeddingBatchResult:
    vectors: list[list[float]]
    model: str
    total_tokens: int


class DashScopeEmbeddingClient:
    _retryable_status_codes = {408, 409, 425, 429, 500, 502, 503, 504}

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if not self.settings.dashscope_api_key:
            raise ValueError(
                "DASHSCOPE_API_KEY or ALIBABA_CLOUD_ACCESS_KEY_SECRET is required"
            )

        self._owns_client = http_client is None
        self.client = http_client or httpx.Client(
            base_url=self.settings.dashscope_embedding_base.rstrip("/"),
            headers={
                "Authorization": f"Bearer {self.settings.dashscope_api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(60.0, connect=30.0, read=60.0, write=60.0),
            follow_redirects=True,
        )

    def __enter__(self) -> "DashScopeEmbeddingClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def embed_texts(self, texts: list[str]) -> EmbeddingBatchResult:
        if not texts:
            return EmbeddingBatchResult(vectors=[], model=self.settings.embedding_model, total_tokens=0)

        all_vectors: list[list[float]] = []
        total_tokens = 0

        for batch in self._batched(texts, self.settings.embedding_batch_size):
            request_payload = EmbeddingRequest(
                model=self.settings.embedding_model,
                input=batch,
                dimensions=self.settings.embedding_dimensions,
            )
            response = self._post_with_retry(
                "/embeddings",
                content=request_payload.model_dump_json(by_alias=True, exclude_none=True),
            )
            response.raise_for_status()
            parsed = EmbeddingResponse.model_validate(response.json())
            ordered_items = sorted(parsed.data, key=lambda item: item.index)
            expected_indices = list(range(len(batch)))
            actual_indices = [item.index for item in ordered_items]
            if actual_indices != expected_indices:
                raise ValueError(
                    f"embedding response indices mismatch: expected {expected_indices}, got {actual_indices}"
                )

            vectors = [item.embedding for item in ordered_items]
            expected_dimensions = self.settings.embedding_dimensions
            if any(len(vector) != expected_dimensions for vector in vectors):
                raise ValueError(
                    f"embedding vector dimension mismatch: expected {expected_dimensions}"
                )
            all_vectors.extend(vectors)
            if parsed.usage is not None:
                total_tokens += parsed.usage.total_tokens

        return EmbeddingBatchResult(
            vectors=all_vectors,
            model=self.settings.embedding_model,
            total_tokens=total_tokens,
        )

    def _batched(self, texts: list[str], batch_size: int) -> list[list[str]]:
        return [texts[index : index + batch_size] for index in range(0, len(texts), batch_size)]

    def _post_with_retry(self, url: str, *, content: str) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = self.client.post(url, content=content)
                if response.status_code in self._retryable_status_codes and attempt < 3:
                    time.sleep(float(attempt))
                    continue
                return response
            except httpx.RequestError as exc:
                last_error = exc
                if attempt >= 3:
                    raise
                time.sleep(float(attempt))
        if last_error is not None:
            raise last_error
        raise RuntimeError("embedding request failed without a response")
