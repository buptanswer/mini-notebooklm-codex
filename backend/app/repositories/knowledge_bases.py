from __future__ import annotations

import re
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import DocumentORM, KnowledgeBaseORM, PipelineJobORM
from app.schemas.api import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseSummary,
    KnowledgeBaseUpdateRequest,
)
from app.services.storage import StorageManager


class KnowledgeBaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def exists_by_name(self, name: str) -> bool:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(KnowledgeBaseORM)
                .where(KnowledgeBaseORM.name == name)
            )
            or 0
        ) > 0

    def get_entity(self, knowledge_base_id: str) -> KnowledgeBaseORM | None:
        return self.session.scalar(
            select(KnowledgeBaseORM).where(KnowledgeBaseORM.id == knowledge_base_id)
        )

    def get_summary(self, knowledge_base_id: str) -> KnowledgeBaseSummary | None:
        entity = self.get_entity(knowledge_base_id)
        if entity is None:
            return None
        return self._to_summary(entity)

    def get_by_name(self, name: str) -> KnowledgeBaseSummary | None:
        entity = self.session.scalar(
            select(KnowledgeBaseORM).where(KnowledgeBaseORM.name == name)
        )
        if entity is None:
            return None
        return self._to_summary(entity)

    def list_summaries(self) -> list[KnowledgeBaseSummary]:
        knowledge_bases = self.session.scalars(
            select(KnowledgeBaseORM).order_by(KnowledgeBaseORM.updated_at.desc())
        ).all()
        document_counts = dict(
            self.session.execute(
                select(DocumentORM.knowledge_base_id, func.count(DocumentORM.id)).group_by(
                    DocumentORM.knowledge_base_id
                )
            ).all()
        )
        task_counts = dict(
            self.session.execute(
                select(PipelineJobORM.knowledge_base_id, func.count(PipelineJobORM.id))
                .where(PipelineJobORM.knowledge_base_id.is_not(None))
                .group_by(PipelineJobORM.knowledge_base_id)
            ).all()
        )
        return [
            self._to_summary(item, document_counts=document_counts, task_counts=task_counts)
            for item in knowledge_bases
        ]

    def create(
        self,
        payload: KnowledgeBaseCreateRequest,
        storage_manager: StorageManager,
    ) -> KnowledgeBaseSummary:
        identifier = str(uuid4())
        slug = _slugify(payload.name)
        storage_root = storage_manager.ensure_knowledge_base_tree(identifier)

        entity = KnowledgeBaseORM(
            id=identifier,
            name=payload.name,
            slug=f"{slug}-{identifier[:8]}",
            description=payload.description,
            status="active",
            storage_root=str(storage_root),
        )
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)

        return KnowledgeBaseSummary(
            id=entity.id,
            name=entity.name,
            slug=entity.slug,
            description=entity.description,
            status=entity.status,
            storage_root=entity.storage_root,
            document_count=0,
            task_count=0,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def update(
        self,
        knowledge_base_id: str,
        payload: KnowledgeBaseUpdateRequest,
    ) -> KnowledgeBaseSummary:
        entity = self.get_entity(knowledge_base_id)
        if entity is None:
            raise ValueError(f"knowledge base `{knowledge_base_id}` not found")
        entity.name = payload.name
        entity.description = payload.description
        entity.slug = f"{_slugify(payload.name)}-{entity.id[:8]}"
        self.session.commit()
        self.session.refresh(entity)
        return self._to_summary(entity)

    def delete(self, knowledge_base_id: str) -> KnowledgeBaseSummary:
        entity = self.get_entity(knowledge_base_id)
        if entity is None:
            raise ValueError(f"knowledge base `{knowledge_base_id}` not found")
        summary = self._to_summary(entity)
        self.session.delete(entity)
        self.session.commit()
        return summary

    def _to_summary(
        self,
        entity: KnowledgeBaseORM,
        *,
        document_counts: dict[str, int] | None = None,
        task_counts: dict[str, int] | None = None,
    ) -> KnowledgeBaseSummary:
        document_count = (
            document_counts.get(entity.id)
            if document_counts is not None
            else self.session.scalar(
                select(func.count())
                .select_from(DocumentORM)
                .where(DocumentORM.knowledge_base_id == entity.id)
            )
        ) or 0
        task_count = (
            task_counts.get(entity.id)
            if task_counts is not None
            else self.session.scalar(
                select(func.count())
                .select_from(PipelineJobORM)
                .where(PipelineJobORM.knowledge_base_id == entity.id)
            )
        ) or 0
        return KnowledgeBaseSummary(
            id=entity.id,
            name=entity.name,
            slug=entity.slug,
            description=entity.description,
            status=entity.status,
            storage_root=entity.storage_root,
            document_count=document_count,
            task_count=task_count,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return normalized or "kb"
