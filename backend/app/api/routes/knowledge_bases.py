import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.repositories.documents import DocumentRepository
from app.repositories.jobs import PipelineJobRepository
from app.repositories.knowledge_bases import KnowledgeBaseRepository
from app.schemas.api import (
    DocumentBulkDeleteRequest,
    DocumentFileSummary,
    DocumentUpdateRequest,
    FolderDeleteRequest,
    FolderRenameRequest,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseSummary,
    KnowledgeBaseUpdateRequest,
    PipelineJobSummary,
    UploadBatchResponse,
)
from app.schemas.qa import AnswerUsage, AskRequest, AskResponse
from app.services.file_manager_service import FileManagerService
from app.services.ingestion_service import KnowledgeBaseIngestionService
from app.services.qa_service import QAService
from app.services.retrieval_service import HybridRetrievalService
from app.services.storage import StorageManager

router = APIRouter()


def _validate_knowledge_base_exists(knowledge_base_id: str) -> None:
    with SessionLocal() as session:
        repository = DocumentRepository(session)
        if not repository.knowledge_base_exists(knowledge_base_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"知识库 `{knowledge_base_id}` 不存在。",
            )


def _sse(event: str, payload: dict | list | str) -> str:
    data = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


@router.get("", response_model=list[KnowledgeBaseSummary])
def list_knowledge_bases() -> list[KnowledgeBaseSummary]:
    with SessionLocal() as session:
        repository = KnowledgeBaseRepository(session)
        return repository.list_summaries()


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseSummary)
def update_knowledge_base(
    knowledge_base_id: str,
    payload: KnowledgeBaseUpdateRequest,
) -> KnowledgeBaseSummary:
    with SessionLocal() as session:
        repository = KnowledgeBaseRepository(session)
        existing = repository.get_entity(knowledge_base_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"知识库 `{knowledge_base_id}` 不存在。",
            )
        if payload.name != existing.name and repository.exists_by_name(payload.name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"知识库 `{payload.name}` 已存在。",
            )
        return repository.update(knowledge_base_id, payload)


@router.delete("/{knowledge_base_id}", response_model=KnowledgeBaseSummary)
def delete_knowledge_base(
    knowledge_base_id: str,
    request: Request,
) -> KnowledgeBaseSummary:
    settings = getattr(request.app.state, "settings", get_settings())
    storage_manager = getattr(request.app.state, "storage_manager", StorageManager(settings))
    qdrant_manager = getattr(request.app.state, "qdrant_manager", None)
    with SessionLocal() as session:
        service = FileManagerService(
            storage_manager=storage_manager,
            qdrant_manager=qdrant_manager,
        )
        try:
            return service.delete_knowledge_base(session, knowledge_base_id=knowledge_base_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc


@router.get("/{knowledge_base_id}/documents", response_model=list[DocumentFileSummary])
def list_knowledge_base_documents(knowledge_base_id: str) -> list[DocumentFileSummary]:
    with SessionLocal() as session:
        repository = DocumentRepository(session)
        if not repository.knowledge_base_exists(knowledge_base_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"知识库 `{knowledge_base_id}` 不存在。",
            )
        return repository.list_by_knowledge_base(knowledge_base_id)


@router.patch(
    "/{knowledge_base_id}/documents/{document_id}",
    response_model=DocumentFileSummary,
)
def update_knowledge_base_document(
    knowledge_base_id: str,
    document_id: str,
    payload: DocumentUpdateRequest,
    request: Request,
) -> DocumentFileSummary:
    settings = getattr(request.app.state, "settings", get_settings())
    storage_manager = getattr(request.app.state, "storage_manager", StorageManager(settings))
    qdrant_manager = getattr(request.app.state, "qdrant_manager", None)
    with SessionLocal() as session:
        service = FileManagerService(
            storage_manager=storage_manager,
            qdrant_manager=qdrant_manager,
        )
        try:
            return service.move_document(
                session,
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
                new_name=payload.new_name,
                new_parent_path=payload.new_parent_path,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc


@router.delete(
    "/{knowledge_base_id}/documents/{document_id}",
    response_model=DocumentFileSummary,
)
def delete_knowledge_base_document(
    knowledge_base_id: str,
    document_id: str,
    request: Request,
) -> DocumentFileSummary:
    settings = getattr(request.app.state, "settings", get_settings())
    storage_manager = getattr(request.app.state, "storage_manager", StorageManager(settings))
    qdrant_manager = getattr(request.app.state, "qdrant_manager", None)
    with SessionLocal() as session:
        service = FileManagerService(
            storage_manager=storage_manager,
            qdrant_manager=qdrant_manager,
        )
        try:
            return service.delete_document(
                session,
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc


@router.post("/{knowledge_base_id}/documents/bulk-delete")
def bulk_delete_knowledge_base_documents(
    knowledge_base_id: str,
    payload: DocumentBulkDeleteRequest,
    request: Request,
) -> dict[str, object]:
    settings = getattr(request.app.state, "settings", get_settings())
    storage_manager = getattr(request.app.state, "storage_manager", StorageManager(settings))
    qdrant_manager = getattr(request.app.state, "qdrant_manager", None)
    with SessionLocal() as session:
        service = FileManagerService(
            storage_manager=storage_manager,
            qdrant_manager=qdrant_manager,
        )
        deleted_ids = service.bulk_delete_documents(
            session,
            knowledge_base_id=knowledge_base_id,
            document_ids=payload.document_ids,
        )
    return {"deleted_ids": deleted_ids, "deleted_count": len(deleted_ids)}


@router.post("/{knowledge_base_id}/folders/rename")
def rename_knowledge_base_folder(
    knowledge_base_id: str,
    payload: FolderRenameRequest,
    request: Request,
) -> dict[str, object]:
    settings = getattr(request.app.state, "settings", get_settings())
    storage_manager = getattr(request.app.state, "storage_manager", StorageManager(settings))
    qdrant_manager = getattr(request.app.state, "qdrant_manager", None)
    with SessionLocal() as session:
        service = FileManagerService(
            storage_manager=storage_manager,
            qdrant_manager=qdrant_manager,
        )
        try:
            moved_ids = service.rename_folder(
                session,
                knowledge_base_id=knowledge_base_id,
                folder_path=payload.folder_path,
                new_folder_path=payload.new_folder_path,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
    return {"updated_ids": moved_ids, "updated_count": len(moved_ids)}


@router.post("/{knowledge_base_id}/folders/delete")
def delete_knowledge_base_folder(
    knowledge_base_id: str,
    payload: FolderDeleteRequest,
    request: Request,
) -> dict[str, object]:
    settings = getattr(request.app.state, "settings", get_settings())
    storage_manager = getattr(request.app.state, "storage_manager", StorageManager(settings))
    qdrant_manager = getattr(request.app.state, "qdrant_manager", None)
    with SessionLocal() as session:
        service = FileManagerService(
            storage_manager=storage_manager,
            qdrant_manager=qdrant_manager,
        )
        try:
            deleted_ids = service.delete_folder(
                session,
                knowledge_base_id=knowledge_base_id,
                folder_path=payload.folder_path,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
    return {"deleted_ids": deleted_ids, "deleted_count": len(deleted_ids)}


@router.get("/{knowledge_base_id}/jobs", response_model=list[PipelineJobSummary])
def list_knowledge_base_jobs(knowledge_base_id: str) -> list[PipelineJobSummary]:
    with SessionLocal() as session:
        document_repository = DocumentRepository(session)
        if not document_repository.knowledge_base_exists(knowledge_base_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"知识库 `{knowledge_base_id}` 不存在。",
            )
        repository = PipelineJobRepository(session)
        return repository.list_by_knowledge_base(knowledge_base_id)


@router.post(
    "/{knowledge_base_id}/upload",
    response_model=UploadBatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_knowledge_base_files(
    knowledge_base_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    relative_paths: list[str] | None = Form(default=None),
) -> UploadBatchResponse:
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要上传一个文件。",
        )

    if relative_paths and len(relative_paths) != len(files):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="relative_paths 数量必须与 files 一致。",
        )

    settings = getattr(request.app.state, "settings", get_settings())
    storage_manager = getattr(
        request.app.state,
        "storage_manager",
        StorageManager(settings),
    )
    qdrant_manager = getattr(request.app.state, "qdrant_manager", None)

    with SessionLocal() as session:
        document_repository = DocumentRepository(session)
        if not document_repository.knowledge_base_exists(knowledge_base_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"知识库 `{knowledge_base_id}` 不存在。",
            )

    ingestion_service = KnowledgeBaseIngestionService(
        settings=settings,
        storage_manager=storage_manager,
        qdrant_manager=qdrant_manager,
    )

    saved_files: list[tuple[str, str, str]] = []
    for index, upload in enumerate(files):
        relative_path = (
            relative_paths[index]
            if relative_paths and index < len(relative_paths)
            else upload.filename
        )
        if not upload.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="上传文件必须带文件名。",
            )
        suffix = upload.filename.lower().rsplit(".", 1)
        if len(suffix) != 2 or f".{suffix[1]}" not in {".pdf", ".ppt", ".pptx", ".doc", ".docx", ".png", ".jpg", ".jpeg"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"暂不支持的文件类型：{upload.filename}",
            )

        content = await upload.read()
        saved_path = ingestion_service.save_upload_bytes(
            knowledge_base_id=knowledge_base_id,
            file_name=upload.filename,
            relative_path=relative_path,
            content=content,
        )
        saved_files.append((upload.filename, relative_path, str(saved_path)))

    queued_uploads = ingestion_service.enqueue_saved_uploads(
        knowledge_base_id=knowledge_base_id,
        saved_files=[
            (file_name, relative_path, Path(saved_path))
            for file_name, relative_path, saved_path in saved_files
        ],
    )
    background_tasks.add_task(
        ingestion_service.ingest_saved_uploads,
        knowledge_base_id=knowledge_base_id,
        uploads=queued_uploads,
    )

    with SessionLocal() as session:
        repository = PipelineJobRepository(session)
        jobs = repository.list_by_knowledge_base(knowledge_base_id)
        queued_job_ids = {item.parse_job_id for item in queued_uploads}
        queued_jobs = [job for job in jobs if job.id in queued_job_ids]

    return UploadBatchResponse(
        knowledge_base_id=knowledge_base_id,
        accepted_files=len(queued_uploads),
        jobs=queued_jobs,
    )


@router.post("/{knowledge_base_id}/ask", response_model=AskResponse)
def ask_knowledge_base(
    knowledge_base_id: str,
    payload: AskRequest,
    request: Request,
) -> AskResponse:
    with SessionLocal() as session:
        repository = DocumentRepository(session)
        if not repository.knowledge_base_exists(knowledge_base_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"知识库 `{knowledge_base_id}` 不存在。",
            )

        settings = getattr(request.app.state, "settings", get_settings())
        qdrant_manager = getattr(request.app.state, "qdrant_manager", None)
        retrieval_service = HybridRetrievalService(
            settings=settings,
            qdrant_manager=qdrant_manager,
        )
        service = QAService(
            settings=settings,
            retrieval_service=retrieval_service,
        )
        try:
            return service.ask(
                session=session,
                knowledge_base_id=knowledge_base_id,
                payload=payload,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc


@router.post("/{knowledge_base_id}/ask/stream")
def stream_knowledge_base_answer(
    knowledge_base_id: str,
    payload: AskRequest,
    request: Request,
) -> StreamingResponse:
    settings = getattr(request.app.state, "settings", get_settings())
    qdrant_manager = getattr(request.app.state, "qdrant_manager", None)

    def event_stream():
        with SessionLocal() as session:
            repository = DocumentRepository(session)
            if not repository.knowledge_base_exists(knowledge_base_id):
                yield _sse("error", {"message": f"知识库 `{knowledge_base_id}` 不存在。"})
                return

            retrieval_service = HybridRetrievalService(
                settings=settings,
                qdrant_manager=qdrant_manager,
            )
            service = QAService(
                settings=settings,
                retrieval_service=retrieval_service,
            )
            try:
                prepared = service.prepare_answer(session, knowledge_base_id, payload)
            except ValueError as exc:
                yield _sse("error", {"message": str(exc)})
                return

            yield _sse(
                "meta",
                {
                    "knowledge_base_id": knowledge_base_id,
                    "question": payload.question,
                    "answer_model": settings.qa_model,
                    "rerank_model": settings.rerank_model,
                    "embedding_model": settings.embedding_model,
                    "sources": [item.source.model_dump(mode="json") for item in prepared.sources],
                    "retrieval_trace": [
                        item.model_dump(mode="json")
                        for item in service._build_trace(prepared.fused_candidates)
                    ],
                },
            )

            answer_parts: list[str] = []
            prompt_tokens = None
            completion_tokens = None
            total_tokens = None
            for chunk in service.stream_answer(prepared):
                if chunk.content_delta:
                    answer_parts.append(chunk.content_delta)
                    yield _sse("delta", {"text": chunk.content_delta})
                if chunk.prompt_tokens is not None:
                    prompt_tokens = chunk.prompt_tokens
                if chunk.completion_tokens is not None:
                    completion_tokens = chunk.completion_tokens
                if chunk.total_tokens is not None:
                    total_tokens = chunk.total_tokens

            full_answer = "".join(answer_parts).strip()
            response = AskResponse(
                knowledge_base_id=knowledge_base_id,
                question=payload.question,
                answer=full_answer,
                answer_model=settings.qa_model,
                rerank_model=settings.rerank_model,
                embedding_model=settings.embedding_model,
                generated_at=datetime.now(),
                sources=[item.source for item in prepared.sources],
                retrieval_trace=service._build_trace(prepared.fused_candidates),
                usage=AnswerUsage(
                    retrieval_candidates=len(prepared.fused_candidates),
                    reranked_candidates=len(prepared.reranked_candidates),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=(total_tokens or 0) + (prepared.rerank_tokens or 0),
                ),
            )
            yield _sse("done", response.model_dump(mode="json"))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "",
    response_model=KnowledgeBaseSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_base(
    payload: KnowledgeBaseCreateRequest,
    request: Request,
) -> KnowledgeBaseSummary:
    storage_manager = getattr(
        request.app.state,
        "storage_manager",
        StorageManager(get_settings()),
    )
    with SessionLocal() as session:
        repository = KnowledgeBaseRepository(session)
        if repository.exists_by_name(payload.name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"知识库 `{payload.name}` 已存在。",
            )
        return repository.create(payload=payload, storage_manager=storage_manager)
