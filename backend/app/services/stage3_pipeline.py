from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings, get_settings
from app.schemas.chunk import ChildChunk, ParentChunk
from app.schemas.ir import DocumentIR
from app.services.chunking import StructureAwareChunker
from app.services.embedding_client import DashScopeEmbeddingClient
from app.validators import validate_chunks
from app.writers import write_jsonl


@dataclass(slots=True)
class Stage3Artifacts:
    document_ir: DocumentIR
    parents: list[ParentChunk]
    children: list[ChildChunk]
    vectors: list[list[float]]
    parent_chunks_path: Path
    child_chunks_path: Path
    embedding_model: str


class Stage3Pipeline:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.chunker = StructureAwareChunker(self.settings)

    def process_document(
        self,
        document_ir_path: str | Path,
        output_root: str | Path,
        use_fake_embeddings: bool = False,
    ) -> Stage3Artifacts:
        ir_path = Path(document_ir_path)
        output_dir = Path(output_root)
        document_ir = DocumentIR.model_validate_json(ir_path.read_text(encoding="utf-8"))

        chunking_result = self.chunker.chunk_document(document_ir)
        validate_chunks(document_ir, chunking_result.parents, chunking_result.children)

        parent_chunks_path = write_jsonl(output_dir / "parent_chunks.jsonl", chunking_result.parents)
        child_chunks_path = write_jsonl(output_dir / "child_chunks.jsonl", chunking_result.children)

        child_texts = [child.embedding_text for child in chunking_result.children]
        if use_fake_embeddings:
            vectors = [self._fake_embedding(text) for text in child_texts]
            embedding_model = "fake-hash-embedding"
        else:
            with DashScopeEmbeddingClient(self.settings) as client:
                batch_result = client.embed_texts(child_texts)
            vectors = batch_result.vectors
            embedding_model = batch_result.model

        return Stage3Artifacts(
            document_ir=document_ir,
            parents=chunking_result.parents,
            children=chunking_result.children,
            vectors=vectors,
            parent_chunks_path=parent_chunks_path,
            child_chunks_path=child_chunks_path,
            embedding_model=embedding_model,
        )

    def _fake_embedding(self, text: str) -> list[float]:
        dims = self.settings.embedding_dimensions
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = [((digest[index % len(digest)] / 255.0) * 2.0) - 1.0 for index in range(dims)]
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]
