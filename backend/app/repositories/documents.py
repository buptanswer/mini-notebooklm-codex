from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentORM, KnowledgeBaseORM
from app.schemas.api import DocumentFileSummary
from app.schemas.ir import DocumentIR
from app.services.document_review import inspect_document_ir


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_entity(self, document_id: str) -> DocumentORM | None:
        return self.session.scalar(select(DocumentORM).where(DocumentORM.id == document_id))

    def list_entities_by_knowledge_base(self, knowledge_base_id: str) -> list[DocumentORM]:
        return self.session.scalars(
            select(DocumentORM)
            .where(DocumentORM.knowledge_base_id == knowledge_base_id)
            .order_by(DocumentORM.updated_at.desc(), DocumentORM.created_at.desc())
        ).all()

    def list_by_knowledge_base(self, knowledge_base_id: str) -> list[DocumentFileSummary]:
        documents = self.list_entities_by_knowledge_base(knowledge_base_id)
        return [self._to_summary(item) for item in documents]

    def upsert_from_ir(
        self,
        knowledge_base_id: str,
        source_path: str | Path,
        bundle_root: str | Path,
        ir_path: str | Path,
        document_ir: DocumentIR,
    ) -> DocumentFileSummary:
        source_file = Path(source_path).resolve()
        bundle_root_path = Path(bundle_root).resolve()
        ir_output_path = Path(ir_path).resolve()
        review = inspect_document_ir(document_ir)

        entity = self.session.scalar(
            select(DocumentORM).where(
                DocumentORM.knowledge_base_id == knowledge_base_id,
                DocumentORM.source_sha1 == document_ir.source.doc_id,
            )
        )
        kb = self.session.scalar(
            select(KnowledgeBaseORM).where(KnowledgeBaseORM.id == knowledge_base_id)
        )
        if kb is None:
            raise ValueError(f"knowledge base `{knowledge_base_id}` not found")
        relative_path = self._relative_upload_path(source_file, Path(kb.storage_root))
        if entity is None:
            entity = DocumentORM(
                knowledge_base_id=knowledge_base_id,
                source_filename=document_ir.source.source_filename,
                source_format=document_ir.source.source_format,
                source_path=str(source_file),
                source_relative_path=relative_path,
                source_sha1=document_ir.source.doc_id,
            )
            self.session.add(entity)

        entity.source_filename = document_ir.source.source_filename
        entity.source_format = document_ir.source.source_format
        entity.source_path = str(source_file)
        entity.source_relative_path = relative_path
        entity.source_sha1 = document_ir.source.doc_id
        entity.document_title = document_ir.document.title
        entity.bundle_root = str(bundle_root_path)
        entity.origin_pdf_path = str(bundle_root_path / document_ir.source.origin_pdf_path)
        entity.ir_path = str(ir_output_path)
        entity.enriched_ir_path = None
        entity.parsing_status = "completed"
        entity.chunking_status = "pending"
        entity.indexing_status = "pending"
        entity.review_status = review.review_status
        entity.parser_warning_count = review.parser_warning_count
        entity.unknown_block_count = review.unknown_block_count
        entity.parent_chunk_count = 0
        entity.child_chunk_count = 0
        entity.review_summary = review.review_summary
        entity.error_message = review.review_summary if review.review_status == "needs_review" else None

        self.session.commit()
        self.session.refresh(entity)
        return self._to_summary(entity)

    def knowledge_base_exists(self, knowledge_base_id: str) -> bool:
        return (
            self.session.scalar(
                select(KnowledgeBaseORM.id).where(KnowledgeBaseORM.id == knowledge_base_id)
            )
            is not None
        )

    def update_relative_path(self, document_id: str, relative_path: str, source_path: str | Path) -> DocumentFileSummary:
        entity = self.get_entity(document_id)
        if entity is None:
            raise ValueError(f"document `{document_id}` not found")
        entity.source_relative_path = relative_path
        entity.source_filename = Path(relative_path).name
        entity.source_path = str(Path(source_path).resolve())
        self.session.commit()
        self.session.refresh(entity)
        return self._to_summary(entity)

    def set_enriched_ir_path(self, document_id: str, enriched_ir_path: str | Path) -> DocumentFileSummary:
        entity = self.get_entity(document_id)
        if entity is None:
            raise ValueError(f"document `{document_id}` not found")
        entity.enriched_ir_path = str(Path(enriched_ir_path).resolve())
        self.session.commit()
        self.session.refresh(entity)
        return self._to_summary(entity)

    def delete(self, document_id: str) -> DocumentFileSummary:
        entity = self.get_entity(document_id)
        if entity is None:
            raise ValueError(f"document `{document_id}` not found")
        summary = self._to_summary(entity)
        self.session.delete(entity)
        self.session.commit()
        return summary

    def list_by_prefix(self, knowledge_base_id: str, prefix: str) -> list[DocumentORM]:
        normalized = prefix.strip("/\\")
        entities = self.list_entities_by_knowledge_base(knowledge_base_id)
        return [
            entity
            for entity in entities
            if entity.source_relative_path == normalized
            or entity.source_relative_path.startswith(f"{normalized}/")
            or entity.source_relative_path.startswith(f"{normalized}\\")
        ]

    def _to_summary(self, entity: DocumentORM) -> DocumentFileSummary:
        return DocumentFileSummary(
            id=entity.id,
            knowledge_base_id=entity.knowledge_base_id,
            source_filename=entity.source_filename,
            source_format=entity.source_format,
            source_path=entity.source_path,
            source_relative_path=entity.source_relative_path or entity.source_filename,
            source_sha1=entity.source_sha1,
            document_title=entity.document_title,
            bundle_root=entity.bundle_root,
            origin_pdf_path=entity.origin_pdf_path,
            ir_path=entity.ir_path,
            enriched_ir_path=entity.enriched_ir_path,
            parsing_status=entity.parsing_status,
            chunking_status=entity.chunking_status,
            indexing_status=entity.indexing_status,
            review_status=entity.review_status,  # type: ignore[arg-type]
            parser_warning_count=entity.parser_warning_count,
            unknown_block_count=entity.unknown_block_count,
            parent_chunk_count=entity.parent_chunk_count,
            child_chunk_count=entity.child_chunk_count,
            review_summary=entity.review_summary,
            error_message=entity.error_message,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _relative_upload_path(self, source_path: Path, storage_root: Path) -> str:
        uploads_root = storage_root / "uploads"
        try:
            return source_path.resolve().relative_to(uploads_root.resolve()).as_posix()
        except ValueError:
            return source_path.name
