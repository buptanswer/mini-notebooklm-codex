from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings
from app.schemas.rerank_api import TextRerankRequest, TextRerankResponse


@dataclass(slots=True)
class RerankResultItem:
    index: int
    relevance_score: float


@dataclass(slots=True)
class RerankResult:
    items: list[RerankResultItem]
    total_tokens: int | None = None
    request_id: str | None = None


class DashScopeRerankClient:
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
            headers={
                "Authorization": f"Bearer {self.settings.dashscope_api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(60.0, connect=30.0, read=60.0, write=60.0),
            follow_redirects=True,
        )

    def __enter__(self) -> "DashScopeRerankClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_n: int | None = None,
        instruct: str | None = None,
    ) -> RerankResult:
        if not documents:
            return RerankResult(items=[])

        request_payload = TextRerankRequest(
            model=self.settings.rerank_model,
            input={
                "query": query,
                "documents": documents,
                "instruct": instruct,
            },
            parameters={
                "top_n": top_n or min(self.settings.rerank_top_n, len(documents)),
                "return_documents": False,
            },
        )
        response = self._post_with_retry(
            self.settings.dashscope_rerank_base,
            content=request_payload.model_dump_json(exclude_none=True),
        )
        response.raise_for_status()
        parsed = TextRerankResponse.model_validate(response.json())

        return RerankResult(
            items=[
                RerankResultItem(
                    index=item.index,
                    relevance_score=item.relevance_score,
                )
                for item in parsed.output.results
            ],
            total_tokens=parsed.usage.total_tokens if parsed.usage else None,
            request_id=parsed.request_id,
        )

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
        raise RuntimeError("rerank request failed without a response")
