from typing import Any

from fastapi import APIRouter

from app.core.exceptions import BusinessError
from app.schemas.common import ApiResponse
from app.services.vector_store import vector_store_service

router = APIRouter(prefix="/vector")


@router.get("/health", response_model=ApiResponse[dict[str, Any]])
async def vector_health() -> ApiResponse[dict[str, Any]]:
    try:
        data = await vector_store_service.health()
    except Exception as exc:
        raise BusinessError(
            "Qdrant 暂时无法连接，请检查服务是否已启动以及 QDRANT_URL 配置",
            code="VECTOR_DB_UNAVAILABLE",
            status_code=503,
        ) from exc

    return ApiResponse(data={"status": "ok", **data})


@router.post("/collections/ensure", response_model=ApiResponse[dict[str, Any]])
async def ensure_vector_collection() -> ApiResponse[dict[str, Any]]:
    try:
        data = await vector_store_service.ensure_collection()
    except Exception as exc:
        raise BusinessError(
            "Qdrant collection 创建/检查失败，请检查服务是否已启动以及向量维度配置",
            code="VECTOR_COLLECTION_UNAVAILABLE",
            status_code=503,
        ) from exc

    return ApiResponse(data=data)

