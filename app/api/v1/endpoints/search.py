from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.schemas.common import ApiResponse
from app.schemas.embedding import FaqSearchData, FaqSearchRequest
from app.services.faq_embedding import FaqEmbeddingService

router = APIRouter(prefix="/search")


def get_faq_embedding_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FaqEmbeddingService:
    return FaqEmbeddingService(session)


@router.post("/faqs", response_model=ApiResponse[FaqSearchData])
async def search_faqs(
    payload: FaqSearchRequest,
    service: Annotated[FaqEmbeddingService, Depends(get_faq_embedding_service)],
) -> ApiResponse[FaqSearchData]:
    return ApiResponse(
        message="FAQ 语义检索成功",
        data=await service.search_faqs(query=payload.query.strip(), top_k=payload.top_k),
    )

