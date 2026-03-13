from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from app.core.config import get_settings

router = APIRouter()


@router.get("/files")
def get_storage_file(
    request: Request,
    path: str = Query(..., description="Absolute path inside storage root"),
) -> FileResponse:
    settings = getattr(request.app.state, "settings", get_settings())
    target = Path(path).expanduser().resolve()
    storage_root = settings.storage_root.resolve()

    if storage_root not in target.parents and target != storage_root:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只允许访问 storage 目录内的文件。",
        )
    if not target.exists() or not target.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文件不存在：{target}",
        )
    return FileResponse(target)
