from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.core.config import Settings, get_settings
from app.db.session import session_scope
from app.repositories.chunks import ChunkRepository
from app.repositories.documents import DocumentRepository
from app.repositories.jobs import PipelineJobRepository
from app.services.enrichment_service import DocumentEnrichmentService
from app.services.bundle_parser import MineruBundleParser
from app.services.mineru_client import LocalMineruFile, MineruClient
from app.services.qdrant_manager import QdrantManager
from app.services.stage3_pipeline import Stage3Pipeline
from app.services.storage import StorageManager
from app.writers import write_json


SUPPORTED_SUFFIXES = {".pdf", ".ppt", ".pptx", ".doc", ".docx", ".png", ".jpg", ".jpeg"}


@dataclass(slots=True)
class SavedUpload:
    file_name: str
    relative_path: str
    absolute_path: Path
    parse_job_id: str


class KnowledgeBaseIngestionService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        storage_manager: StorageManager | None = None,
        qdrant_manager: QdrantManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage_manager = storage_manager or StorageManager(self.settings)
        self.qdrant_manager = qdrant_manager or QdrantManager(self.settings)
        self.bundle_parser = MineruBundleParser()
        self.enrichment_service = DocumentEnrichmentService(self.settings)
        self.stage3_pipeline = Stage3Pipeline(self.settings)

    def save_upload_bytes(
        self,
        *,
        knowledge_base_id: str,
        file_name: str,
        relative_path: str | None,
        content: bytes,
    ) -> Path:
        kb_root = self.storage_manager.ensure_knowledge_base_tree(knowledge_base_id)
        safe_relative = self._sanitize_relative_path(relative_path or file_name)
        target_path = kb_root / "uploads" / safe_relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        return target_path

    def enqueue_saved_uploads(
        self,
        *,
        knowledge_base_id: str,
        saved_files: list[tuple[str, str, Path]],
    ) -> list[SavedUpload]:
        queued: list[SavedUpload] = []
        with session_scope() as session:
            repository = PipelineJobRepository(session)
            for file_name, relative_path, absolute_path in saved_files:
                job = repository.create(
                    knowledge_base_id=knowledge_base_id,
                    stage="parse",
                    payload={
                        "file_name": file_name,
                        "relative_path": relative_path,
                        "source_path": str(absolute_path),
                    },
                )
                queued.append(
                    SavedUpload(
                        file_name=file_name,
                        relative_path=relative_path,
                        absolute_path=absolute_path,
                        parse_job_id=job.id,
                    )
                )
        return queued

    def ingest_saved_uploads(
        self,
        *,
        knowledge_base_id: str,
        uploads: list[SavedUpload],
    ) -> None:
        if not uploads:
            return

        with session_scope() as session:
            job_repository = PipelineJobRepository(session)
            for upload in uploads:
                job_repository.mark_running(upload.parse_job_id)

        with MineruClient(self.settings) as mineru_client:
            local_files = [
                LocalMineruFile(path=upload.absolute_path)
                for upload in uploads
            ]
            batch_id, prepared_files = mineru_client.submit_local_files(local_files)
            result_by_data_id = self._poll_batch_results(mineru_client, batch_id)

            for upload, prepared in zip(uploads, prepared_files, strict=True):
                item = result_by_data_id.get(prepared.data_id or "")
                if item is None:
                    self._mark_parse_failed(
                        upload.parse_job_id,
                        "MinerU batch result missing uploaded file",
                    )
                    continue
                if item.state != "done":
                    self._mark_parse_failed(
                        upload.parse_job_id,
                        item.err_msg or "MinerU parse failed",
                    )
                    continue

                document_summary = None
                try:
                    kb_root = self.storage_manager.ensure_knowledge_base_tree(knowledge_base_id)
                    bundle_root = kb_root / "mineru_bundles" / (prepared.data_id or upload.absolute_path.stem)
                    if bundle_root.exists():
                        shutil.rmtree(bundle_root)
                    bundle_root.mkdir(parents=True, exist_ok=True)

                    bundle_zip_path = mineru_client.download_bundle(
                        str(item.full_zip_url),
                        bundle_root / "bundle.zip",
                    )
                    extracted_root = self.bundle_parser.extract_bundle(bundle_zip_path, bundle_root / "bundle")
                    bundle_files = self.bundle_parser.inspect_bundle(extracted_root)
                    document_ir = self.bundle_parser.build_document_ir(
                        bundle_files,
                        upload.absolute_path,
                        mineru_request_model=self.settings.mineru_model_version,
                    )
                    ir_path = write_json(
                        bundle_files.bundle_root / "document_ir.json",
                        document_ir.model_dump(mode="json"),
                    )

                    with session_scope() as session:
                        document_repository = DocumentRepository(session)
                        document_summary = document_repository.upsert_from_ir(
                            knowledge_base_id=knowledge_base_id,
                            source_path=upload.absolute_path,
                            bundle_root=bundle_files.bundle_root,
                            ir_path=ir_path,
                            document_ir=document_ir,
                        )
                        job_repository = PipelineJobRepository(session)
                        job_repository.mark_completed(
                            upload.parse_job_id,
                            document_id=document_summary.id,
                            payload={
                                "batch_id": batch_id,
                                "data_id": prepared.data_id,
                                "bundle_root": str(bundle_files.bundle_root),
                                "ir_path": str(ir_path),
                            },
                        )

                    enrich_job_id = self._create_job(
                        knowledge_base_id=knowledge_base_id,
                        document_id=document_summary.id,
                        stage="enrich",
                    )
                    chunk_job_id = self._create_job(
                        knowledge_base_id=knowledge_base_id,
                        document_id=document_summary.id,
                        stage="chunk",
                    )
                    index_job_id = self._create_job(
                        knowledge_base_id=knowledge_base_id,
                        document_id=document_summary.id,
                        stage="index",
                    )
                    enriched_ir_path = self._run_enrichment(
                        document_id=document_summary.id,
                        bundle_root=bundle_files.bundle_root,
                        ir_path=ir_path,
                        enrich_job_id=enrich_job_id,
                    )
                    self._run_stage3(
                        document_id=document_summary.id,
                        bundle_root=bundle_files.bundle_root,
                        ir_path=enriched_ir_path or ir_path,
                        chunk_job_id=chunk_job_id,
                        index_job_id=index_job_id,
                    )
                except Exception as exc:
                    document_id = document_summary.id if document_summary else None
                    self._mark_parse_failed(
                        upload.parse_job_id,
                        str(exc),
                        document_id=document_id,
                    )

    def _run_stage3(
        self,
        *,
        document_id: str,
        bundle_root: str | Path,
        ir_path: str | Path,
        chunk_job_id: str,
        index_job_id: str,
    ) -> None:
        self._mark_job_running(chunk_job_id)
        try:
            artifacts = self.stage3_pipeline.process_document(
                document_ir_path=ir_path,
                output_root=bundle_root,
            )
            self._mark_job_completed(
                chunk_job_id,
                document_id=document_id,
                payload={
                    "parent_chunks_path": str(artifacts.parent_chunks_path),
                    "child_chunks_path": str(artifacts.child_chunks_path),
                    "parent_chunk_count": len(artifacts.parents),
                    "child_chunk_count": len(artifacts.children),
                },
            )
        except Exception as exc:
            self._mark_job_failed(chunk_job_id, str(exc), document_id=document_id)
            self._mark_job_failed(index_job_id, str(exc), document_id=document_id)
            raise

        self._mark_job_running(index_job_id)
        try:
            self.qdrant_manager.replace_document_chunks(artifacts.children, artifacts.vectors)
            with session_scope() as session:
                chunk_repository = ChunkRepository(session)
                chunk_repository.replace_document_chunks(
                    document_id=document_id,
                    parent_chunks=artifacts.parents,
                    child_chunks=artifacts.children,
                    embedding_model=artifacts.embedding_model,
                )
            self._mark_job_completed(
                index_job_id,
                document_id=document_id,
                payload={
                    "embedding_model": artifacts.embedding_model,
                    "indexed_points": len(artifacts.children),
                },
            )
        except Exception as exc:
            with session_scope() as session:
                chunk_repository = ChunkRepository(session)
                chunk_repository.mark_indexing_failed(document_id, str(exc))
            self._mark_job_failed(index_job_id, str(exc), document_id=document_id)
            raise

    def _run_enrichment(
        self,
        *,
        document_id: str,
        bundle_root: str | Path,
        ir_path: str | Path,
        enrich_job_id: str,
    ) -> str | Path | None:
        self._mark_job_running(enrich_job_id)
        try:
            artifacts = self.enrichment_service.enrich_document(
                document_ir_path=ir_path,
                bundle_root=bundle_root,
            )
            with session_scope() as session:
                DocumentRepository(session).set_enriched_ir_path(
                    document_id,
                    artifacts.enriched_ir_path,
                )
            self._mark_job_completed(
                enrich_job_id,
                document_id=document_id,
                payload={
                    "enriched_ir_path": str(artifacts.enriched_ir_path),
                    "image_enriched_count": artifacts.image_enriched_count,
                    "table_enriched_count": artifacts.table_enriched_count,
                },
            )
            return artifacts.enriched_ir_path
        except Exception as exc:
            self._mark_job_failed(enrich_job_id, str(exc), document_id=document_id)
            return None

    def _poll_batch_results(self, mineru_client: MineruClient, batch_id: str):
        started_at = time.monotonic()
        timeout = self.settings.mineru_poll_timeout_seconds
        interval = self.settings.mineru_poll_interval_seconds

        while True:
            result = mineru_client.get_batch_results(batch_id)
            items = result.data.extract_result
            if items and all(item.state in {"done", "failed"} for item in items):
                return {item.data_id or "": item for item in items}
            if time.monotonic() - started_at > timeout:
                raise TimeoutError(f"MinerU batch {batch_id} timed out after {timeout}s")
            time.sleep(interval)

    def _sanitize_relative_path(self, raw_path: str) -> Path:
        normalized = raw_path.replace("\\", "/").strip("/")
        relative = PurePosixPath(normalized)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"invalid relative path: {raw_path}")
        return Path(*relative.parts)

    def _create_job(
        self,
        *,
        knowledge_base_id: str,
        document_id: str | None,
        stage: str,
    ) -> str:
        with session_scope() as session:
            repository = PipelineJobRepository(session)
            summary = repository.create(
                stage=stage,
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
            )
            return summary.id

    def _mark_job_running(self, job_id: str) -> None:
        with session_scope() as session:
            PipelineJobRepository(session).mark_running(job_id)

    def _mark_job_completed(
        self,
        job_id: str,
        *,
        document_id: str | None = None,
        payload: dict | None = None,
    ) -> None:
        with session_scope() as session:
            PipelineJobRepository(session).mark_completed(
                job_id,
                document_id=document_id,
                payload=payload,
            )

    def _mark_job_failed(
        self,
        job_id: str,
        error_message: str,
        *,
        document_id: str | None = None,
    ) -> None:
        with session_scope() as session:
            PipelineJobRepository(session).mark_failed(
                job_id,
                error_message,
                document_id=document_id,
            )

    def _mark_parse_failed(
        self,
        job_id: str,
        error_message: str,
        *,
        document_id: str | None = None,
    ) -> None:
        self._mark_job_failed(job_id, error_message, document_id=document_id)
