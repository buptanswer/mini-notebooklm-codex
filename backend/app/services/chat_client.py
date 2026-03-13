from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Iterator

import httpx

from app.core.config import Settings, get_settings
from app.schemas.chat_api import ChatCompletionRequest, ChatCompletionResponse, ChatMessage


@dataclass(slots=True)
class ChatResult:
    content: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    response_id: str | None = None


@dataclass(slots=True)
class ChatStreamChunk:
    content_delta: str = ""
    reasoning_delta: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    response_id: str | None = None
    done: bool = False


class DashScopeChatClient:
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
            base_url=self.settings.dashscope_chat_base.rstrip("/"),
            headers={
                "Authorization": f"Bearer {self.settings.dashscope_api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(300.0, connect=30.0, read=300.0, write=60.0),
            follow_redirects=True,
        )

    def __enter__(self) -> "DashScopeChatClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def chat(
        self,
        messages: list[ChatMessage | dict],
        *,
        model: str | None = None,
        temperature: float | None = None,
    ) -> ChatResult:
        normalized_messages = [
            item if isinstance(item, ChatMessage) else ChatMessage.model_validate(item)
            for item in messages
        ]
        request_payload = ChatCompletionRequest(
            model=model or self.settings.qa_model,
            messages=normalized_messages,
            temperature=temperature,
        )
        response = self._post_with_retry(
            "/chat/completions",
            content=request_payload.model_dump_json(exclude_none=True),
        )
        response.raise_for_status()
        parsed = ChatCompletionResponse.model_validate(response.json())
        if not parsed.choices:
            raise ValueError("chat completion returned no choices")

        content = self._flatten_content(parsed.choices[0].message.content)
        return ChatResult(
            content=content,
            model=parsed.model,
            prompt_tokens=parsed.usage.prompt_tokens if parsed.usage else None,
            completion_tokens=parsed.usage.completion_tokens if parsed.usage else None,
            total_tokens=parsed.usage.total_tokens if parsed.usage else None,
            response_id=parsed.id,
        )

    def stream_chat(
        self,
        messages: list[ChatMessage | dict],
        *,
        model: str | None = None,
        temperature: float | None = None,
    ) -> Iterator[ChatStreamChunk]:
        normalized_messages = [
            item if isinstance(item, ChatMessage) else ChatMessage.model_validate(item)
            for item in messages
        ]
        request_payload = ChatCompletionRequest(
            model=model or self.settings.qa_model,
            messages=normalized_messages,
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
        )
        yielded_any_chunk = False
        for attempt in range(1, 4):
            try:
                with self.client.stream(
                    "POST",
                    "/chat/completions",
                    content=request_payload.model_dump_json(exclude_none=True),
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            yield ChatStreamChunk(done=True)
                            return
                        data = json.loads(payload)
                        usage = data.get("usage") or {}
                        choices = data.get("choices") or []
                        delta = choices[0].get("delta", {}) if choices else {}
                        yielded_any_chunk = True
                        yield ChatStreamChunk(
                            content_delta=self._flatten_content(delta.get("content")),
                            reasoning_delta=delta.get("reasoning_content"),
                            prompt_tokens=usage.get("prompt_tokens"),
                            completion_tokens=usage.get("completion_tokens"),
                            total_tokens=usage.get("total_tokens"),
                            response_id=data.get("id"),
                            done=False,
                        )
                return
            except httpx.HTTPStatusError as exc:
                if yielded_any_chunk or not self._should_retry(attempt, response=exc.response):
                    raise
                time.sleep(float(attempt))
            except httpx.RequestError:
                if yielded_any_chunk or not self._should_retry(attempt, response=None):
                    raise
                time.sleep(float(attempt))

    def _flatten_content(self, content: str | list[dict] | None) -> str:
        if isinstance(content, str):
            return content.strip()
        if not content:
            return ""

        text_parts: list[str] = []
        for item in content:
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())
        return "\n".join(text_parts).strip()

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
                if not self._should_retry(attempt, response=None):
                    raise
                time.sleep(float(attempt))
        if last_error is not None:
            raise last_error
        raise RuntimeError("chat request failed without a response")

    def _should_retry(
        self,
        attempt: int,
        *,
        response: httpx.Response | None,
    ) -> bool:
        if attempt >= 3:
            return False
        if response is None:
            return True
        return response.status_code in self._retryable_status_codes
