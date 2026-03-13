from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class KnowledgeBaseORM(TimestampMixin, Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    storage_root: Mapped[str] = mapped_column(String(500), nullable=False)

    documents: Mapped[list["DocumentORM"]] = relationship(
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list["PipelineJobORM"]] = relationship(
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )


class DocumentORM(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_format: Mapped[str] = mapped_column(String(24), nullable=False)
    source_path: Mapped[str] = mapped_column(String(500), nullable=False)
    source_relative_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    source_sha1: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    bundle_root: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    origin_pdf_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ir_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    enriched_ir_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    document_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    parsing_status: Mapped[str] = mapped_column(
        String(24),
        default="pending",
        nullable=False,
    )
    chunking_status: Mapped[str] = mapped_column(
        String(24),
        default="pending",
        nullable=False,
    )
    indexing_status: Mapped[str] = mapped_column(
        String(24),
        default="pending",
        nullable=False,
    )
    review_status: Mapped[str] = mapped_column(
        String(24),
        default="pending",
        nullable=False,
    )
    parser_warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unknown_block_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parent_chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    child_chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    review_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    knowledge_base: Mapped["KnowledgeBaseORM"] = relationship(back_populates="documents")
    assets: Mapped[list["DocumentAssetORM"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list["PipelineJobORM"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    parent_chunks: Mapped[list["ParentChunkORM"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    child_chunks: Mapped[list["ChildChunkORM"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class DocumentAssetORM(Base):
    __tablename__ = "document_assets"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    block_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    page_idx: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    document: Mapped["DocumentORM"] = relationship(back_populates="assets")


class PipelineJobORM(TimestampMixin, Base):
    __tablename__ = "pipeline_jobs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    knowledge_base_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=True,
    )
    document_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    knowledge_base: Mapped[Optional["KnowledgeBaseORM"]] = relationship(
        back_populates="jobs"
    )
    document: Mapped[Optional["DocumentORM"]] = relationship(back_populates="jobs")


class ParentChunkORM(Base):
    __tablename__ = "parent_chunks"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    header_path_json: Mapped[str] = mapped_column(Text, nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    block_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    text_for_generation: Mapped[str] = mapped_column(Text, nullable=False)
    assets_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    asset_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    document: Mapped["DocumentORM"] = relationship(back_populates="parent_chunks")
    child_chunks: Mapped[list["ChildChunkORM"]] = relationship(
        back_populates="parent_chunk",
        cascade="all, delete-orphan",
    )


class ChildChunkORM(Base):
    __tablename__ = "child_chunks"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_chunk_id: Mapped[str] = mapped_column(
        ForeignKey("parent_chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(32), nullable=False)
    header_path_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_block_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieval_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_text: Mapped[str] = mapped_column(Text, nullable=False)
    assets_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    embedding_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    qdrant_point_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    is_atomic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    document: Mapped["DocumentORM"] = relationship(back_populates="child_chunks")
    parent_chunk: Mapped["ParentChunkORM"] = relationship(back_populates="child_chunks")
