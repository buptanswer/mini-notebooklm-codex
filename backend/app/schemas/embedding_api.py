from pydantic import Field

from app.schemas.common import StrictBaseModel


class EmbeddingRequest(StrictBaseModel):
    model: str
    input: list[str] = Field(min_length=1)
    dimensions: int | None = None
    encoding_format: str = "float"


class EmbeddingUsage(StrictBaseModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingItem(StrictBaseModel):
    index: int
    embedding: list[float]
    object: str


class EmbeddingResponse(StrictBaseModel):
    id: str | None = None
    object: str
    data: list[EmbeddingItem]
    model: str
    created: int | None = None
    usage: EmbeddingUsage | None = None
