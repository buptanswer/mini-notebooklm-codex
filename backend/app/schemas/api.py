from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import StrictBaseModel


class HealthStatus(StrictBaseModel):
    status: Literal["ok", "degraded"]
    timestamp: datetime
    storage_ready: bool
    database_ready: bool
    qdrant_ready: bool
    warnings: list[str] = Field(default_factory=list)


class BootstrapStatus(StrictBaseModel):
    storage_ready: bool
    database_ready: bool
    qdrant_ready: bool
    warnings: list[str] = Field(default_factory=list)


class StorageStatus(StrictBaseModel):
    storage_root: str
    sqlite_path: str
    qdrant_mode: Literal["local", "remote"]
    qdrant_location: str
    qdrant_collection: str
    qdrant_vector_size: int


class SystemCounts(StrictBaseModel):
    knowledge_bases: int
    documents: int
    tasks: int
    child_chunks: int


class ArchitectureModule(StrictBaseModel):
    key: str
    name: str
    summary: str
    status: Literal["ready", "warning", "planned"]


class RoadmapStage(StrictBaseModel):
    key: str
    name: str
    status: Literal["completed", "next", "planned"]
    summary: str


class SystemOverview(StrictBaseModel):
    app_name: str
    api_prefix: str
    debug: bool
    bootstrap: BootstrapStatus
    storage: StorageStatus
    counts: SystemCounts
    architecture: list[ArchitectureModule]
    roadmap: list[RoadmapStage]


class KnowledgeBaseCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class KnowledgeBaseUpdateRequest(StrictBaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class KnowledgeBaseSummary(StrictBaseModel):
    id: str
    name: str
    slug: str
    description: str | None = None
    status: str
    storage_root: str
    document_count: int
    task_count: int
    created_at: datetime
    updated_at: datetime


class DocumentFileSummary(StrictBaseModel):
    id: str
    knowledge_base_id: str
    source_filename: str
    source_format: str
    source_path: str
    source_relative_path: str
    source_sha1: str | None = None
    document_title: str | None = None
    bundle_root: str | None = None
    origin_pdf_path: str | None = None
    ir_path: str | None = None
    enriched_ir_path: str | None = None
    parsing_status: str
    chunking_status: str
    indexing_status: str
    review_status: Literal["pending", "ok", "needs_review"]
    parser_warning_count: int
    unknown_block_count: int
    parent_chunk_count: int = 0
    child_chunk_count: int = 0
    review_summary: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class PipelineJobSummary(StrictBaseModel):
    id: str
    knowledge_base_id: str | None = None
    document_id: str | None = None
    stage: str
    state: str
    attempts: int
    error_message: str | None = None
    payload_json: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UploadBatchResponse(StrictBaseModel):
    knowledge_base_id: str
    accepted_files: int
    jobs: list[PipelineJobSummary] = Field(default_factory=list)


class DocumentUpdateRequest(StrictBaseModel):
    new_name: str | None = Field(default=None, min_length=1, max_length=255)
    new_parent_path: str | None = Field(default=None, max_length=500)


class DocumentBulkDeleteRequest(StrictBaseModel):
    document_ids: list[str] = Field(min_length=1)


class FolderRenameRequest(StrictBaseModel):
    folder_path: str = Field(min_length=1, max_length=500)
    new_folder_path: str = Field(min_length=1, max_length=500)


class FolderDeleteRequest(StrictBaseModel):
    folder_path: str = Field(min_length=1, max_length=500)
