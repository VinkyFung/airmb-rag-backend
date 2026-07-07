from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.schemas.common import ApiResponse
from app.schemas.faq import FaqDeleteData, FaqItem, FaqListData, FaqUpdate
from app.services.faq import FaqService

router = APIRouter(prefix="/faqs")


def get_faq_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FaqService:
    return FaqService(session)


@router.get("", response_model=ApiResponse[FaqListData])
async def list_faqs(
    service: Annotated[FaqService, Depends(get_faq_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    keyword: Annotated[str | None, Query(max_length=200)] = None,
    category_l1: Annotated[str | None, Query(max_length=100)] = None,
    faq_status: Annotated[int | None, Query(alias="status", ge=0, le=2)] = None,
) -> ApiResponse[FaqListData]:
    data = await service.list_faqs(
        page=page,
        page_size=page_size,
        keyword=keyword.strip() if keyword else None,
        category_l1=category_l1,
        status=faq_status,
    )
    return ApiResponse(data=data)


@router.put("/{faq_id}", response_model=ApiResponse[FaqItem])
async def update_faq(
    faq_id: int,
    payload: FaqUpdate,
    service: Annotated[FaqService, Depends(get_faq_service)],
) -> ApiResponse[FaqItem]:
    return ApiResponse(message="FAQ 更新成功", data=await service.update_faq(faq_id, payload))


@router.delete(
    "/{faq_id}",
    response_model=ApiResponse[FaqDeleteData],
    status_code=status.HTTP_200_OK,
)
async def delete_faq(
    faq_id: int,
    service: Annotated[FaqService, Depends(get_faq_service)],
    updated_by: Annotated[str, Query(min_length=1, max_length=64)] = "客服运营",
) -> ApiResponse[FaqDeleteData]:
    return ApiResponse(
        message="FAQ 已停用并软删除",
        data=await service.delete_faq(faq_id, updated_by=updated_by),
    )

