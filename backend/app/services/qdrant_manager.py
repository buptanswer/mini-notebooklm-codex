from __future__ import annotations

from functools import cached_property

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    MatchAny,
    PointStruct,
    QueryResponse,
    VectorParams,
)

from app.schemas.chunk import ChildChunk
from app.services.qdrant_ids import qdrant_point_id_for_child

from app.core.config import Settings


class QdrantManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @cached_property
    def client(self) -> QdrantClient:
        if self.settings.qdrant_mode == "remote":
            if not self.settings.qdrant_url:
                raise ValueError("QDRANT_URL is required when qdrant_mode=remote")
            return QdrantClient(
                url=self.settings.qdrant_url,
                api_key=self.settings.qdrant_api_key,
            )

        self.settings.qdrant_path.mkdir(parents=True, exist_ok=True)
        return QdrantClient(path=str(self.settings.qdrant_path))

    def ensure_collection(self) -> None:
        collections = self.client.get_collections().collections
        existing = {item.name for item in collections}
        if self.settings.qdrant_collection in existing:
            return

        distance = getattr(Distance, self.settings.qdrant_distance.upper())
        self.client.create_collection(
            collection_name=self.settings.qdrant_collection,
            vectors_config=VectorParams(
                size=self.settings.qdrant_vector_size,
                distance=distance,
            ),
        )

    def replace_document_chunks(
        self,
        child_chunks: list[ChildChunk],
        vectors: list[list[float]],
    ) -> None:
        if len(child_chunks) != len(vectors):
            raise ValueError("child chunk count must match vector count")
        if not child_chunks:
            return

        doc_ids = {chunk.doc_id for chunk in child_chunks}
        if len(doc_ids) != 1:
            raise ValueError("replace_document_chunks expects chunks from a single document")

        doc_id = next(iter(doc_ids))
        self.delete_document_chunks(doc_id)

        points = [
            PointStruct(
                id=qdrant_point_id_for_child(chunk.child_chunk_id),
                vector=vector,
                payload={
                    "doc_id": chunk.doc_id,
                    "parent_chunk_id": chunk.parent_chunk_id,
                    "section_id": chunk.section_id,
                    "header_path": chunk.header_path,
                    "header_path_text": " > ".join(chunk.header_path),
                    "chunk_type": chunk.chunk_type,
                    "page_start": chunk.page_span.root[0],
                    "page_end": chunk.page_span.root[1],
                    "source_block_ids": chunk.source_block_ids,
                    "retrieval_text": chunk.retrieval_text,
                    "embedding_text": chunk.embedding_text,
                    "asset_paths": [asset.path for asset in chunk.assets],
                    "is_atomic": chunk.metadata.is_atomic,
                    "is_atomic_fragment": chunk.metadata.is_atomic_fragment,
                },
            )
            for chunk, vector in zip(child_chunks, vectors, strict=True)
        ]
        self.client.upsert(collection_name=self.settings.qdrant_collection, points=points)

    def delete_document_chunks(self, doc_id: str) -> None:
        self.client.delete(
            collection_name=self.settings.qdrant_collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="doc_id",
                        match=MatchValue(value=doc_id),
                    )
                ]
            ),
        )

    def query_similar_chunks(
        self,
        query_vector: list[float],
        limit: int,
        source_sha1s: list[str] | None = None,
    ) -> QueryResponse:
        query_filter = None
        if source_sha1s:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="doc_id",
                        match=MatchAny(any=source_sha1s),
                    )
                ]
            )

        return self.client.query_points(
            collection_name=self.settings.qdrant_collection,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )

    def close(self) -> None:
        if "client" in self.__dict__:
            self.client.close()
