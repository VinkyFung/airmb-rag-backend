from fastapi import APIRouter

from app.api.v1.endpoints.faqs import router as faq_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.search import router as search_router
from app.api.v1.endpoints.vector import router as vector_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["系统"])
api_router.include_router(faq_router, tags=["FAQ 管理"])
api_router.include_router(search_router, tags=["FAQ 语义检索"])
api_router.include_router(vector_router, tags=["向量库"])
