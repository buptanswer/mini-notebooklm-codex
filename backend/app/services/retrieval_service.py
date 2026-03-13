from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.repositories.chunks import ChunkRepository, ChunkSearchRecord
from app.repositories.documents import DocumentRepository
from app.services.embedding_client import DashScopeEmbeddingClient
from app.services.qdrant_manager import QdrantManager


@dataclass(slots=True)
class RetrievedCandidate:
    chunk: ChunkSearchRecord
    channels: set[str] = field(default_factory=set)
    vector_rank: int | None = None
    keyword_rank: int | None = None
    vector_score: float | None = None
    keyword_score: float | None = None
    fusion_score: float = 0.0
    rerank_score: float | None = None

    @property
    def child_chunk_id(self) -> str:
        return self.chunk.child_chunk_id

    def rerank_text(self, max_parent_chars: int) -> str:
        parent_context = self.chunk.parent_text.strip()
        if len(parent_context) > max_parent_chars:
            parent_context = f"{parent_context[:max_parent_chars].rstrip()}..."

        parts = [
            f"标题路径: {' > '.join(self.chunk.header_path)}",
            f"正文片段: {self.chunk.retrieval_text.strip()}",
            f"父级上下文: {parent_context}",
        ]
        return "\n".join(part for part in parts if part.strip())


class HybridRetrievalService:
    def __init__(
        self,
        settings: Settings | None = None,
        qdrant_manager: QdrantManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.qdrant_manager = qdrant_manager or QdrantManager(self.settings)

    def search(
        self,
        session: Session,
        knowledge_base_id: str,
        question: str,
        *,
        vector_top_k: int | None = None,
        keyword_top_k: int | None = None,
        fused_top_k: int | None = None,
    ) -> list[RetrievedCandidate]:
        document_repository = DocumentRepository(session)
        chunk_repository = ChunkRepository(session)

        documents = document_repository.list_entities_by_knowledge_base(knowledge_base_id)
        indexed_source_sha1s = [
            item.source_sha1
            for item in documents
            if item.indexing_status == "completed" and item.source_sha1
        ]
        if not indexed_source_sha1s:
            raise ValueError("knowledge base has no indexed documents")

        vector_candidates = self._vector_search(
            chunk_repository=chunk_repository,
            question=question,
            source_sha1s=indexed_source_sha1s,
            limit=vector_top_k or self.settings.retrieval_vector_top_k,
        )
        keyword_candidates = self._keyword_search(
            chunk_repository=chunk_repository,
            knowledge_base_id=knowledge_base_id,
            question=question,
            limit=keyword_top_k or self.settings.retrieval_keyword_top_k,
        )
        return self._fuse_candidates(
            vector_candidates=vector_candidates,
            keyword_candidates=keyword_candidates,
            limit=fused_top_k or self.settings.retrieval_fused_top_k,
        )

    def _vector_search(
        self,
        *,
        chunk_repository: ChunkRepository,
        question: str,
        source_sha1s: list[str],
        limit: int,
    ) -> list[tuple[ChunkSearchRecord, float]]:
        with DashScopeEmbeddingClient(self.settings) as client:
            batch_result = client.embed_texts([question])
        response = self.qdrant_manager.query_similar_chunks(
            query_vector=batch_result.vectors[0],
            limit=limit,
            source_sha1s=source_sha1s,
        )
        point_ids = [str(point.id) for point in response.points]
        rows = chunk_repository.get_by_qdrant_point_ids(point_ids)
        row_by_point_id = {
            row.qdrant_point_id: row
            for row in rows
            if row.qdrant_point_id is not None
        }

        ordered: list[tuple[ChunkSearchRecord, float]] = []
        for point in response.points:
            record = row_by_point_id.get(str(point.id))
            if record is None:
                continue
            ordered.append((record, float(point.score)))
        return ordered

    def _keyword_search(
        self,
        *,
        chunk_repository: ChunkRepository,
        knowledge_base_id: str,
        question: str,
        limit: int,
    ) -> list[ChunkSearchRecord]:
        terms = self._extract_terms(question)
        match_query = self._build_fts_query(question, terms)
        records = chunk_repository.keyword_search(
            knowledge_base_id=knowledge_base_id,
            match_query=match_query,
            limit=limit,
        )
        if records:
            return records
        return chunk_repository.keyword_like_search(
            knowledge_base_id=knowledge_base_id,
            terms=terms[:8],
            limit=limit,
        )

    def _fuse_candidates(
        self,
        *,
        vector_candidates: list[tuple[ChunkSearchRecord, float]],
        keyword_candidates: list[ChunkSearchRecord],
        limit: int,
    ) -> list[RetrievedCandidate]:
        fused: dict[str, RetrievedCandidate] = {}
        rrf_k = self.settings.retrieval_rrf_k

        for rank, (record, score) in enumerate(vector_candidates, start=1):
            candidate = fused.setdefault(record.child_chunk_id, RetrievedCandidate(chunk=record))
            candidate.channels.add("vector")
            candidate.vector_rank = rank
            candidate.vector_score = score
            candidate.fusion_score += 1.0 / (rrf_k + rank)

        for rank, record in enumerate(keyword_candidates, start=1):
            candidate = fused.setdefault(record.child_chunk_id, RetrievedCandidate(chunk=record))
            candidate.channels.add("keyword")
            candidate.keyword_rank = rank
            candidate.keyword_score = record.keyword_score
            candidate.fusion_score += 1.0 / (rrf_k + rank)

        ordered = sorted(
            fused.values(),
            key=lambda item: (
                item.fusion_score,
                item.vector_score or -1.0,
                -item.keyword_rank if item.keyword_rank is not None else -9999,
            ),
            reverse=True,
        )
        return ordered[:limit]

    def _extract_terms(self, question: str) -> list[str]:
        normalized = question.strip()
        terms: list[str] = []

        latin_terms = re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]{1,31}", normalized)
        chinese_runs = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)

        terms.extend(latin_terms)
        for run in chinese_runs:
            terms.append(run)
            run_length = len(run)
            window_sizes = (4, 3, 2)
            for size in window_sizes:
                if run_length < size:
                    continue
                for index in range(0, run_length - size + 1):
                    terms.append(run[index : index + size])

        # Keep order while de-duplicating, and prefer shorter, more reusable query fragments.
        deduped: list[str] = []
        seen: set[str] = set()
        for term in sorted(terms, key=lambda item: (len(item), item)):
            if term in seen:
                continue
            seen.add(term)
            deduped.append(term)
        return deduped[:24] or [normalized]

    def _build_fts_query(self, question: str, terms: list[str]) -> str:
        escaped_terms = [self._escape_fts_term(item) for item in terms if item.strip()]
        escaped_question = self._escape_fts_term(question)
        joined_terms = " OR ".join(f'"{item}"' for item in escaped_terms[:12])
        if joined_terms:
            return f'"{escaped_question}" OR {joined_terms}'
        return f'"{escaped_question}"'

    def _escape_fts_term(self, value: str) -> str:
        return value.replace('"', " ").strip()
