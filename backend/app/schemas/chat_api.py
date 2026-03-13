from typing import Any

from pydantic import Field

from app.schemas.common import StrictBaseModel


class ChatImageUrl(StrictBaseModel):
    url: str


class ChatMessageContentPart(StrictBaseModel):
    type: str
    text: str | None = None
    image_url: ChatImageUrl | None = None


class ChatMessage(StrictBaseModel):
    role: str
    content: str | list[ChatMessageContentPart]


class ChatCompletionRequest(StrictBaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float | None = None
    stream: bool | None = None
    stream_options: dict[str, Any] | None = None


class ChatChoiceMessage(StrictBaseModel):
    role: str
    content: str | list[dict[str, Any]] | None = None
    reasoning_content: str | None = None


class ChatChoice(StrictBaseModel):
    index: int
    message: ChatChoiceMessage
    finish_reason: str | None = None
    logprobs: dict[str, Any] | None = None


class ChatTokenDetails(StrictBaseModel):
    reasoning_tokens: int | None = None
    text_tokens: int | None = None
    image_tokens: int | None = None


class ChatCompletionUsage(StrictBaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    prompt_tokens_details: ChatTokenDetails | None = None
    completion_tokens_details: ChatTokenDetails | None = None


class ChatCompletionResponse(StrictBaseModel):
    id: str | None = None
    object: str
    created: int | None = None
    model: str
    system_fingerprint: str | None = None
    choices: list[ChatChoice] = Field(default_factory=list)
    usage: ChatCompletionUsage | None = None
