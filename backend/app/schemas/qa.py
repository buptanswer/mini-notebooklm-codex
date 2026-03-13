from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import BBoxPage, StrictBaseModel


class AskRequest(StrictBaseModel):
    question: str = Field(min_length=1, max_length=4000)
    vector_top_k: int | None = Field(default=None, ge=1, le=50)
    keyword_top_k: int | None = Field(default=None, ge=1, le=50)
    fused_top_k: int | None = Field(default=None, ge=1, le=50)
    rerank_top_n: int | None = Field(default=None, ge=1, le=20)
    max_sources: int | None = Field(default=None, ge=1, le=10)
    max_assets: int | None = Field(default=None, ge=1, le=8)


class SourceAnchorBlock(StrictBaseModel):
    block_id: str
    block_type: str
    page_idx: int = Field(ge=0)
    bbox_page: BBoxPage | None = None


class SourceAsset(StrictBaseModel):
    asset_id: str
    asset_type: str
    relative_path: str
    absolute_path: str


class AnswerSource(StrictBaseModel):
    source_id: str
    child_chunk_id: str
    parent_chunk_id: str
    document_id: str
    source_sha1: str | None = None
    source_filename: str
    document_title: str | None = None
    header_path: list[str] = Field(default_factory=list)
    page_start: int = Field(ge=0)
    page_end: int = Field(ge=0)
    page_width: float | None = Field(default=None, ge=0)
    page_height: float | None = Field(default=None, ge=0)
    source_block_ids: list[str] = Field(default_factory=list)
    quote: str
    parent_context: str
    origin_pdf_path: str | None = None
    ir_path: str | None = None
    bundle_root: str | None = None
    review_status: Literal["pending", "ok", "needs_review"] = "ok"
    assets: list[SourceAsset] = Field(default_factory=list)
    anchor_blocks: list[SourceAnchorBlock] = Field(default_factory=list)


class RetrievalTraceHit(StrictBaseModel):
    child_chunk_id: str
    source_filename: str
    chunk_type: str
    channels: list[str] = Field(default_factory=list)
    vector_rank: int | None = None
    keyword_rank: int | None = None
    vector_score: float | None = None
    keyword_score: float | None = None
    fusion_score: float
    rerank_score: float | None = None
    page_start: int = Field(ge=0)
    page_end: int = Field(ge=0)


class AnswerUsage(StrictBaseModel):
    retrieval_candidates: int
    reranked_candidates: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class AskResponse(StrictBaseModel):
    knowledge_base_id: str
    question: str
    answer: str
    answer_model: str
    rerank_model: str
    embedding_model: str
    generated_at: datetime
    sources: list[AnswerSource] = Field(default_factory=list)
    retrieval_trace: list[RetrievalTraceHit] = Field(default_factory=list)
    usage: AnswerUsage
