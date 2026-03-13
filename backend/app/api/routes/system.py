from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import ChildChunkORM, DocumentORM, KnowledgeBaseORM, PipelineJobORM
from app.db.session import SessionLocal
from app.schemas.api import (
    ArchitectureModule,
    BootstrapStatus,
    RoadmapStage,
    StorageStatus,
    SystemCounts,
    SystemOverview,
)

router = APIRouter()


@router.get("/overview", response_model=SystemOverview)
def get_system_overview(request: Request) -> SystemOverview:
    settings = getattr(request.app.state, "settings", get_settings())
    bootstrap = getattr(request.app.state, "bootstrap_report", {})

    with SessionLocal() as session:
        counts = SystemCounts(
            knowledge_bases=session.scalar(
                select(func.count()).select_from(KnowledgeBaseORM)
            )
            or 0,
            documents=session.scalar(select(func.count()).select_from(DocumentORM)) or 0,
            tasks=session.scalar(select(func.count()).select_from(PipelineJobORM)) or 0,
            child_chunks=session.scalar(select(func.count()).select_from(ChildChunkORM))
            or 0,
        )

    storage = StorageStatus(
        storage_root=str(settings.storage_root),
        sqlite_path=str(settings.sqlite_path),
        qdrant_mode=settings.qdrant_mode,
        qdrant_location=(
            str(settings.qdrant_path)
            if settings.qdrant_mode == "local"
            else settings.qdrant_url or ""
        ),
        qdrant_collection=settings.qdrant_collection,
        qdrant_vector_size=settings.qdrant_vector_size,
    )

    architecture = [
        ArchitectureModule(
            key="frontend",
            name="React Workbench",
            summary="知识库工作台壳子，后续承接上传、任务中心、问答与来源溯源。",
            status="ready",
        ),
        ArchitectureModule(
            key="api",
            name="FastAPI Service",
            summary="统一承接配置、任务编排、解析接入和知识库管理接口。",
            status="ready",
        ),
        ArchitectureModule(
            key="sqlite",
            name="SQLite Metadata",
            summary="负责知识库、文档、任务、资产、Chunk 元数据和 FTS5 入口。",
            status="ready",
        ),
        ArchitectureModule(
            key="qdrant",
            name="Qdrant Vector Base",
            summary="默认走本地 Qdrant 存储 child chunk 向量，后续可切远程实例。",
            status="ready" if bootstrap.get("qdrant_ready", False) else "warning",
        ),
        ArchitectureModule(
            key="schema",
            name="Schema Contracts",
            summary="已建立 Raw MinerU / Canonical IR / Parent Child Chunk 三层模型。",
            status="ready",
        ),
        ArchitectureModule(
            key="filesystem",
            name="Filesystem Layout",
            summary="预留上传文件、MinerU bundle、IR、chunk、asset、cache 分层目录。",
            status="ready",
        ),
    ]

    roadmap = [
        RoadmapStage(
            key="stage1",
            name="新版架构与数据底座",
            status="completed",
            summary="前后端骨架、SQLite、Qdrant、本地文件系统和核心数据模型已就位。",
        ),
        RoadmapStage(
            key="stage2",
            name="MinerU 解析与 IR 标准化",
            status="next",
            summary="接入 MinerU API、解压 bundle，并产出 document_ir.json。",
        ),
        RoadmapStage(
            key="stage3",
            name="结构感知切片与索引入库",
            status="next",
            summary="实现 DOM 重建、Parent/Child chunking、SQLite/Qdrant 入库。",
        ),
        RoadmapStage(
            key="stage4",
            name="混合检索、重排序与问答",
            status="planned",
            summary="向量召回、FTS5/BM25、重排序与多模态回答闭环。",
        ),
    ]

    return SystemOverview(
        app_name=settings.app_name,
        api_prefix=settings.api_v1_prefix,
        debug=settings.debug,
        bootstrap=BootstrapStatus(
            storage_ready=bootstrap.get("storage_ready", False),
            database_ready=bootstrap.get("database_ready", False),
            qdrant_ready=bootstrap.get("qdrant_ready", False),
            warnings=bootstrap.get("warnings", []),
        ),
        storage=storage,
        counts=counts,
        architecture=architecture,
        roadmap=roadmap,
    )
