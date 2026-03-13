from fastapi import APIRouter

from app.api.routes import files, health, knowledge_bases, system

api_router = APIRouter()
api_router.include_router(files.router, tags=["files"])
api_router.include_router(health.router, tags=["health"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(
    knowledge_bases.router,
    prefix="/knowledge-bases",
    tags=["knowledge-bases"],
)
