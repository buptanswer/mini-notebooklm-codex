from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.db.models import ChildChunkORM, DocumentORM, ParentChunkORM
from app.schemas.chunk import ChildChunk, ParentChunk
from app.services.qdrant_ids import qdrant_point_id_for_child


@dataclass(slots=True)
class ChunkSearchRecord:
    child_chunk_id: str
    qdrant_point_id: str | None
    chunk_type: str
    document_id: str
    source_sha1: str | None
    source_filename: str
    document_title: str | None
    bundle_root: str | None
    origin_pdf_path: str | None
    ir_path: str | None
    review_status: str
    parent_chunk_id: str
    parent_text: str
    header_path: list[str]
    source_block_ids: list[str]
    page_start: int
    page_end: int
    retrieval_text: str
    embedding_text: str
    assets: list[dict]
    metadata: dict
    keyword_score: float | None = None


class ChunkRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_document_chunks(
        self,
        document_id: str,
        parent_chunks: list[ParentChunk],
        child_chunks: list[ChildChunk],
        embedding_model: str,
    ) -> None:
        self.session.execute(
            delete(ChildChunkORM).where(ChildChunkORM.document_id == document_id)
        )
        self.session.execute(
            delete(ParentChunkORM).where(ParentChunkORM.document_id == document_id)
        )

        parent_entities = [
            ParentChunkORM(
                id=parent.parent_chunk_id,
                document_id=document_id,
                section_id=parent.section_id,
                title=parent.title,
                header_path_json=json.dumps(parent.header_path, ensure_ascii=False),
                page_start=parent.page_span.root[0],
                page_end=parent.page_span.root[1],
                block_ids_json=json.dumps(parent.block_ids, ensure_ascii=False),
                text_for_generation=parent.text_for_generation,
                assets_json=json.dumps(
                    [asset.model_dump(mode="json") for asset in parent.assets],
                    ensure_ascii=False,
                ),
                metadata_json=json.dumps(parent.metadata.model_dump(mode="json"), ensure_ascii=False),
                asset_count=len(parent.assets),
            )
            for parent in parent_chunks
        ]
        self.session.add_all(parent_entities)
        self.session.flush()

        child_entities = [
            ChildChunkORM(
                id=child.child_chunk_id,
                document_id=document_id,
                parent_chunk_id=child.parent_chunk_id,
                section_id=child.section_id,
                chunk_type=child.chunk_type,
                header_path_json=json.dumps(child.header_path, ensure_ascii=False),
                source_block_ids_json=json.dumps(child.source_block_ids, ensure_ascii=False),
                page_start=child.page_span.root[0],
                page_end=child.page_span.root[1],
                retrieval_text=child.retrieval_text,
                embedding_text=child.embedding_text,
                assets_json=json.dumps(
                    [asset.model_dump(mode="json") for asset in child.assets],
                    ensure_ascii=False,
                ),
                metadata_json=json.dumps(child.metadata.model_dump(mode="json"), ensure_ascii=False),
                embedding_model=embedding_model,
                qdrant_point_id=qdrant_point_id_for_child(child.child_chunk_id),
                is_atomic=child.metadata.is_atomic,
            )
            for child in child_chunks
        ]
        self.session.add_all(child_entities)

        document = self.session.scalar(
            select(DocumentORM).where(DocumentORM.id == document_id)
        )
        if document is None:
            raise ValueError(f"document {document_id} not found")

        document.parent_chunk_count = len(parent_chunks)
        document.child_chunk_count = len(child_chunks)
        document.chunking_status = "completed"
        document.indexing_status = "completed"

        self.session.commit()

    def mark_indexing_failed(self, document_id: str, error_message: str) -> None:
        document = self.session.scalar(
            select(DocumentORM).where(DocumentORM.id == document_id)
        )
        if document is None:
            raise ValueError(f"document {document_id} not found")

        document.chunking_status = "failed"
        document.indexing_status = "failed"
        document.error_message = error_message
        self.session.commit()

    def keyword_search(
        self,
        knowledge_base_id: str,
        match_query: str,
        limit: int,
    ) -> list[ChunkSearchRecord]:
        statement = text(
            """
            SELECT
                c.id AS child_chunk_id,
                c.qdrant_point_id AS qdrant_point_id,
                c.chunk_type AS chunk_type,
                d.id AS document_id,
                d.source_sha1 AS source_sha1,
                d.source_filename AS source_filename,
                d.document_title AS document_title,
                d.bundle_root AS bundle_root,
                d.origin_pdf_path AS origin_pdf_path,
                d.ir_path AS ir_path,
                d.review_status AS review_status,
                c.parent_chunk_id AS parent_chunk_id,
                p.text_for_generation AS parent_text,
                c.header_path_json AS header_path_json,
                c.source_block_ids_json AS source_block_ids_json,
                c.page_start AS page_start,
                c.page_end AS page_end,
                c.retrieval_text AS retrieval_text,
                c.embedding_text AS embedding_text,
                c.assets_json AS assets_json,
                c.metadata_json AS metadata_json,
                bm25(child_chunks_fts, 1.2, 0.8, 1.0, 1.0, 1.0) AS keyword_score
            FROM child_chunks_fts
            JOIN child_chunks c ON child_chunks_fts.rowid = c.rowid
            JOIN parent_chunks p ON p.id = c.parent_chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE d.knowledge_base_id = :knowledge_base_id
              AND d.indexing_status = 'completed'
              AND child_chunks_fts MATCH :match_query
            ORDER BY bm25(child_chunks_fts, 1.2, 0.8, 1.0, 1.0, 1.0), c.created_at DESC
            LIMIT :limit
            """
        )
        rows = self.session.execute(
            statement,
            {
                "knowledge_base_id": knowledge_base_id,
                "match_query": match_query,
                "limit": limit,
            },
        ).mappings()
        return [self._record_from_mapping(row) for row in rows]

    def keyword_like_search(
        self,
        knowledge_base_id: str,
        terms: list[str],
        limit: int,
    ) -> list[ChunkSearchRecord]:
        normalized_terms = [term.strip() for term in terms if term.strip()]
        if not normalized_terms:
            return []

        conditions: list[str] = []
        parameters: dict[str, str | int] = {
            "knowledge_base_id": knowledge_base_id,
            "limit": limit,
        }
        for index, term in enumerate(normalized_terms):
            key = f"term_{index}"
            conditions.append(
                f"(c.retrieval_text LIKE :{key} OR c.embedding_text LIKE :{key} OR c.header_path_json LIKE :{key})"
            )
            parameters[key] = f"%{term}%"

        statement = text(
            f"""
            SELECT
                c.id AS child_chunk_id,
                c.qdrant_point_id AS qdrant_point_id,
                c.chunk_type AS chunk_type,
                d.id AS document_id,
                d.source_sha1 AS source_sha1,
                d.source_filename AS source_filename,
                d.document_title AS document_title,
                d.bundle_root AS bundle_root,
                d.origin_pdf_path AS origin_pdf_path,
                d.ir_path AS ir_path,
                d.review_status AS review_status,
                c.parent_chunk_id AS parent_chunk_id,
                p.text_for_generation AS parent_text,
                c.header_path_json AS header_path_json,
                c.source_block_ids_json AS source_block_ids_json,
                c.page_start AS page_start,
                c.page_end AS page_end,
                c.retrieval_text AS retrieval_text,
                c.embedding_text AS embedding_text,
                c.assets_json AS assets_json,
                c.metadata_json AS metadata_json,
                0.0 AS keyword_score
            FROM child_chunks c
            JOIN parent_chunks p ON p.id = c.parent_chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE d.knowledge_base_id = :knowledge_base_id
              AND d.indexing_status = 'completed'
              AND ({' OR '.join(conditions)})
            ORDER BY c.created_at DESC
            LIMIT :limit
            """
        )
        rows = self.session.execute(statement, parameters).mappings()
        return [self._record_from_mapping(row) for row in rows]

    def get_by_qdrant_point_ids(
        self,
        qdrant_point_ids: list[str],
    ) -> list[ChunkSearchRecord]:
        if not qdrant_point_ids:
            return []

        statement = (
            select(
                ChildChunkORM.id.label("child_chunk_id"),
                ChildChunkORM.qdrant_point_id.label("qdrant_point_id"),
                ChildChunkORM.chunk_type.label("chunk_type"),
                DocumentORM.id.label("document_id"),
                DocumentORM.source_sha1.label("source_sha1"),
                DocumentORM.source_filename.label("source_filename"),
                DocumentORM.document_title.label("document_title"),
                DocumentORM.bundle_root.label("bundle_root"),
                DocumentORM.origin_pdf_path.label("origin_pdf_path"),
                DocumentORM.ir_path.label("ir_path"),
                DocumentORM.review_status.label("review_status"),
                ChildChunkORM.parent_chunk_id.label("parent_chunk_id"),
                ParentChunkORM.text_for_generation.label("parent_text"),
                ChildChunkORM.header_path_json.label("header_path_json"),
                ChildChunkORM.source_block_ids_json.label("source_block_ids_json"),
                ChildChunkORM.page_start.label("page_start"),
                ChildChunkORM.page_end.label("page_end"),
                ChildChunkORM.retrieval_text.label("retrieval_text"),
                ChildChunkORM.embedding_text.label("embedding_text"),
                ChildChunkORM.assets_json.label("assets_json"),
                ChildChunkORM.metadata_json.label("metadata_json"),
            )
            .join(DocumentORM, DocumentORM.id == ChildChunkORM.document_id)
            .join(ParentChunkORM, ParentChunkORM.id == ChildChunkORM.parent_chunk_id)
            .where(ChildChunkORM.qdrant_point_id.in_(qdrant_point_ids))
        )
        rows = self.session.execute(statement).mappings().all()
        return [self._record_from_mapping(row) for row in rows]

    def _record_from_mapping(self, row) -> ChunkSearchRecord:
        return ChunkSearchRecord(
            child_chunk_id=row["child_chunk_id"],
            qdrant_point_id=row["qdrant_point_id"],
            chunk_type=row["chunk_type"],
            document_id=row["document_id"],
            source_sha1=row["source_sha1"],
            source_filename=row["source_filename"],
            document_title=row["document_title"],
            bundle_root=row["bundle_root"],
            origin_pdf_path=row["origin_pdf_path"],
            ir_path=row["ir_path"],
            review_status=row["review_status"],
            parent_chunk_id=row["parent_chunk_id"],
            parent_text=row["parent_text"],
            header_path=json.loads(row["header_path_json"]),
            source_block_ids=json.loads(row["source_block_ids_json"]),
            page_start=row["page_start"],
            page_end=row["page_end"],
            retrieval_text=row["retrieval_text"],
            embedding_text=row["embedding_text"],
            assets=json.loads(row["assets_json"]),
            metadata=json.loads(row["metadata_json"]),
            keyword_score=row.get("keyword_score"),
        )
