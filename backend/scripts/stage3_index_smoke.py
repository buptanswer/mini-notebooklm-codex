from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from app.core.config import get_settings
from app.db.session import init_db, session_scope
from app.repositories.chunks import ChunkRepository
from app.repositories.documents import DocumentRepository
from app.repositories.knowledge_bases import KnowledgeBaseRepository
from app.services.qdrant_manager import QdrantManager
from app.services.stage3_pipeline import Stage3Pipeline
from app.writers import write_json


@dataclass(slots=True)
class Stage3DocumentSummary:
    document_id: str
    source_filename: str
    review_status: str
    parent_chunk_count: int
    child_chunk_count: int
    parent_chunks_path: str
    child_chunks_path: str
    embedding_model: str
    skipped: bool = False
    skip_reason: str | None = None


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage3 chunking and indexing smoke test")
    parser.add_argument(
        "--knowledge-base-name",
        default="Stage2 联调样本",
        help="Knowledge base name used by stage2 smoke data",
    )
    parser.add_argument(
        "--allow-needs-review",
        action="store_true",
        help="Index documents even when review_status=needs_review",
    )
    parser.add_argument(
        "--fake-embeddings",
        action="store_true",
        help="Use deterministic fake embeddings instead of DashScope API",
    )
    args = parser.parse_args()

    settings = get_settings()
    init_db()
    qdrant_manager = QdrantManager(settings)
    try:
        qdrant_manager.ensure_collection()
        pipeline = Stage3Pipeline(settings)
        run_root = settings.storage_root / "stage3_runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
        run_root.mkdir(parents=True, exist_ok=True)

        with session_scope() as session:
            kb_repository = KnowledgeBaseRepository(session)
            kb_summary = kb_repository.get_by_name(args.knowledge_base_name)
            if kb_summary is None:
                raise ValueError(f"knowledge base `{args.knowledge_base_name}` not found")

            document_repository = DocumentRepository(session)
            documents = document_repository.list_entities_by_knowledge_base(kb_summary.id)

        summaries: list[Stage3DocumentSummary] = []

        for document in documents:
            if not document.ir_path:
                summaries.append(
                    Stage3DocumentSummary(
                        document_id=document.id,
                        source_filename=document.source_filename,
                        review_status=document.review_status,
                        parent_chunk_count=0,
                        child_chunk_count=0,
                        parent_chunks_path="",
                        child_chunks_path="",
                        embedding_model="",
                        skipped=True,
                        skip_reason="missing ir_path",
                    )
                )
                continue

            if document.review_status != "ok" and not args.allow_needs_review:
                summaries.append(
                    Stage3DocumentSummary(
                        document_id=document.id,
                        source_filename=document.source_filename,
                        review_status=document.review_status,
                        parent_chunk_count=0,
                        child_chunk_count=0,
                        parent_chunks_path="",
                        child_chunks_path="",
                        embedding_model="",
                        skipped=True,
                        skip_reason="document needs review",
                    )
                )
                print(
                    json.dumps(
                        {
                            "source": document.source_filename,
                            "status": "skipped",
                            "reason": "document needs review",
                        },
                        ensure_ascii=False,
                    )
                )
                continue

            try:
                bundle_root = Path(document.bundle_root) if document.bundle_root else Path(document.ir_path).parent
                artifacts = pipeline.process_document(
                    document_ir_path=document.ir_path,
                    output_root=bundle_root,
                    use_fake_embeddings=args.fake_embeddings,
                )
                qdrant_manager.replace_document_chunks(artifacts.children, artifacts.vectors)

                with session_scope() as session:
                    chunk_repository = ChunkRepository(session)
                    chunk_repository.replace_document_chunks(
                        document_id=document.id,
                        parent_chunks=artifacts.parents,
                        child_chunks=artifacts.children,
                        embedding_model=artifacts.embedding_model,
                    )

                summary = Stage3DocumentSummary(
                    document_id=document.id,
                    source_filename=document.source_filename,
                    review_status=document.review_status,
                    parent_chunk_count=len(artifacts.parents),
                    child_chunk_count=len(artifacts.children),
                    parent_chunks_path=artifacts.parent_chunks_path.as_posix(),
                    child_chunks_path=artifacts.child_chunks_path.as_posix(),
                    embedding_model=artifacts.embedding_model,
                )
                summaries.append(summary)
                print(json.dumps(asdict(summary), ensure_ascii=False))
            except Exception as exc:
                with session_scope() as session:
                    chunk_repository = ChunkRepository(session)
                    chunk_repository.mark_indexing_failed(document.id, str(exc))
                summaries.append(
                    Stage3DocumentSummary(
                        document_id=document.id,
                        source_filename=document.source_filename,
                        review_status=document.review_status,
                        parent_chunk_count=0,
                        child_chunk_count=0,
                        parent_chunks_path="",
                        child_chunks_path="",
                        embedding_model="",
                        skipped=True,
                        skip_reason=str(exc),
                    )
                )
                raise

        summary_path = write_json(
            run_root / "summary.json",
            {
                "generated_at": datetime.now().isoformat(),
                "knowledge_base_name": args.knowledge_base_name,
                "fake_embeddings": args.fake_embeddings,
                "documents": [asdict(item) for item in summaries],
            },
        )
        print(f"[stage3] summary -> {summary_path}")
    finally:
        qdrant_manager.close()


if __name__ == "__main__":
    main()
