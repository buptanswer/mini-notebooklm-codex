from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.schemas.api import HealthStatus

router = APIRouter(prefix="/health")


@router.get("", response_model=HealthStatus)
def get_health(request: Request) -> HealthStatus:
    bootstrap = getattr(request.app.state, "bootstrap_report", {})
    return HealthStatus(
        status="ok" if bootstrap.get("database_ready", False) else "degraded",
        timestamp=datetime.now(timezone.utc),
        storage_ready=bootstrap.get("storage_ready", False),
        database_ready=bootstrap.get("database_ready", False),
        qdrant_ready=bootstrap.get("qdrant_ready", False),
        warnings=bootstrap.get("warnings", []),
    )
