from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.db.session import init_db
from app.services.qdrant_manager import QdrantManager
from app.services.storage import StorageManager

settings = get_settings()
storage_manager = StorageManager(settings)
qdrant_manager = QdrantManager(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    warnings: list[str] = []

    storage_manager.ensure_roots()
    storage_ready = True

    init_db()
    database_ready = True

    try:
        qdrant_manager.ensure_collection()
        qdrant_ready = True
    except Exception as exc:  # pragma: no cover - startup fallback
        qdrant_ready = False
        warnings.append(f"Qdrant bootstrap failed: {exc}")

    app.state.settings = settings
    app.state.storage_manager = storage_manager
    app.state.qdrant_manager = qdrant_manager
    app.state.bootstrap_report = {
        "storage_ready": storage_ready,
        "database_ready": database_ready,
        "qdrant_ready": qdrant_ready,
        "warnings": warnings,
    }
    yield
    qdrant_manager.close()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)
