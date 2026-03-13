from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import PageSpan, StrictBaseModel


ChunkType = Literal["paragraph", "list", "code", "image", "table", "equation"]


class ChunkAssetRef(StrictBaseModel):
    asset_id: str
    asset_type: str
    path: str


class ParentChunkMetadata(StrictBaseModel):
    page_headers: list[str] = Field(default_factory=list)
    page_footers: list[str] = Field(default_factory=list)
    page_numbers: list[str] = Field(default_factory=list)
    orphan_footnote_ids: list[str] = Field(default_factory=list)


class ParentChunk(StrictBaseModel):
    parent_chunk_id: str
    doc_id: str
    section_id: str
    header_path: list[str] = Field(min_length=1)
    title: str | None = None
    page_span: PageSpan
    block_ids: list[str] = Field(min_length=1)
    text_for_generation: str = Field(min_length=1)
    assets: list[ChunkAssetRef] = Field(default_factory=list)
    metadata: ParentChunkMetadata = Field(default_factory=ParentChunkMetadata)


class ChildChunkMetadata(StrictBaseModel):
    page_numbers: list[str] = Field(default_factory=list)
    code_language: str | None = None
    is_atomic: bool = False
    is_atomic_fragment: bool = False
    fragment_index: int | None = None
    fragment_total: int | None = None
    enrichment_status: Literal["none", "ready", "partial_failed"] = "none"

    @model_validator(mode="after")
    def validate_fragment_fields(self) -> "ChildChunkMetadata":
        if self.is_atomic_fragment:
            if self.fragment_index is None or self.fragment_total is None:
                raise ValueError("atomic fragment metadata requires index and total")
        return self


class ChildChunk(StrictBaseModel):
    child_chunk_id: str
    parent_chunk_id: str
    doc_id: str
    section_id: str
    header_path: list[str] = Field(min_length=1)
    chunk_type: ChunkType
    page_span: PageSpan
    source_block_ids: list[str] = Field(min_length=1)
    embedding_text: str = Field(min_length=1)
    retrieval_text: str = Field(min_length=1)
    assets: list[ChunkAssetRef] = Field(default_factory=list)
    metadata: ChildChunkMetadata = Field(default_factory=ChildChunkMetadata)
