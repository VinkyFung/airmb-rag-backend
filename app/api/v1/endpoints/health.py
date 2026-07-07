from fastapi import APIRouter

from app.core.config import settings
from app.schemas.common import ApiResponse

router = APIRouter()


@router.get("/health", response_model=ApiResponse[dict[str, str]])
async def health_check() -> ApiResponse[dict[str, str]]:
    return ApiResponse(
        data={
            "status": "ok",
            "service": settings.app_name,
            "environment": settings.app_env,
        }
    )

