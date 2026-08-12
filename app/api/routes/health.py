from fastapi import APIRouter, HTTPException, status

from app.core.config import get_settings
from app.core.database import check_database_connection
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse, summary="Liveness check")
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(service=settings.app_name, environment=settings.app_env)


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness check")
def readiness() -> ReadinessResponse:
    try:
        check_database_connection()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Metadata database is unavailable",
        ) from exc
    return ReadinessResponse(status="ready", checks={"metadata_database": "ok"})
