from pydantic import Field

from app.schemas.common import StrictBaseModel


class TextRerankInput(StrictBaseModel):
    query: str
    documents: list[str] = Field(min_length=1)
    instruct: str | None = None


class TextRerankParameters(StrictBaseModel):
    top_n: int | None = Field(default=None, ge=1)
    return_documents: bool = False


class TextRerankRequest(StrictBaseModel):
    model: str
    input: TextRerankInput
    parameters: TextRerankParameters = Field(default_factory=TextRerankParameters)


class TextRerankDocument(StrictBaseModel):
    text: str | None = None


class TextRerankResult(StrictBaseModel):
    index: int = Field(ge=0)
    relevance_score: float
    document: TextRerankDocument | None = None


class TextRerankOutput(StrictBaseModel):
    results: list[TextRerankResult] = Field(default_factory=list)


class TextRerankUsage(StrictBaseModel):
    total_tokens: int | None = None


class TextRerankResponse(StrictBaseModel):
    request_id: str | None = None
    output: TextRerankOutput
    usage: TextRerankUsage | None = None
