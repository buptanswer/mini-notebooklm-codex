from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PipelineJobORM
from app.schemas.api import PipelineJobSummary


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PipelineJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        stage: str,
        state: str = "pending",
        knowledge_base_id: str | None = None,
        document_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> PipelineJobSummary:
        entity = PipelineJobORM(
            stage=stage,
            state=state,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            payload_json=json.dumps(payload, ensure_ascii=False) if payload else None,
        )
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return self._to_summary(entity)

    def list_by_knowledge_base(self, knowledge_base_id: str) -> list[PipelineJobSummary]:
        entities = self.session.scalars(
            select(PipelineJobORM)
            .where(PipelineJobORM.knowledge_base_id == knowledge_base_id)
            .order_by(PipelineJobORM.updated_at.desc(), PipelineJobORM.created_at.desc())
        ).all()
        return [self._to_summary(item) for item in entities]

    def mark_running(self, job_id: str) -> PipelineJobSummary:
        entity = self._get_entity(job_id)
        entity.state = "running"
        entity.attempts += 1
        entity.started_at = utcnow()
        self.session.commit()
        self.session.refresh(entity)
        return self._to_summary(entity)

    def mark_completed(
        self,
        job_id: str,
        *,
        document_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> PipelineJobSummary:
        entity = self._get_entity(job_id)
        entity.state = "completed"
        entity.finished_at = utcnow()
        if document_id is not None:
            entity.document_id = document_id
        if payload is not None:
            entity.payload_json = json.dumps(payload, ensure_ascii=False)
        self.session.commit()
        self.session.refresh(entity)
        return self._to_summary(entity)

    def mark_failed(
        self,
        job_id: str,
        error_message: str,
        *,
        document_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> PipelineJobSummary:
        entity = self._get_entity(job_id)
        entity.state = "failed"
        entity.error_message = error_message
        entity.finished_at = utcnow()
        if document_id is not None:
            entity.document_id = document_id
        if payload is not None:
            entity.payload_json = json.dumps(payload, ensure_ascii=False)
        self.session.commit()
        self.session.refresh(entity)
        return self._to_summary(entity)

    def _get_entity(self, job_id: str) -> PipelineJobORM:
        entity = self.session.scalar(
            select(PipelineJobORM).where(PipelineJobORM.id == job_id)
        )
        if entity is None:
            raise ValueError(f"pipeline job `{job_id}` not found")
        return entity

    def _to_summary(self, entity: PipelineJobORM) -> PipelineJobSummary:
        return PipelineJobSummary(
            id=entity.id,
            knowledge_base_id=entity.knowledge_base_id,
            document_id=entity.document_id,
            stage=entity.stage,
            state=entity.state,
            attempts=entity.attempts,
            error_message=entity.error_message,
            payload_json=entity.payload_json,
            started_at=entity.started_at,
            finished_at=entity.finished_at,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
