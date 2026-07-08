from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import BusinessError
from app.schemas.common import ApiResponse
from app.schemas.embedding import (
    FaqEmbeddingData,
    FaqEmbeddingRebuildRequest,
    FaqEmbeddingTaskData,
)
from app.schemas.faq import FaqDeleteData, FaqItem, FaqListData, FaqUpdate
from app.schemas.faq_import import FaqImportConfirmData, FaqImportParseData
from app.services.embedding_task import faq_embedding_task_manager
from app.services.faq import FaqService
from app.services.faq_embedding import FaqEmbeddingService
from app.services.faq_import import FaqImportService

router = APIRouter(prefix="/faqs")


def get_faq_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FaqService:
    return FaqService(session)


def get_faq_embedding_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FaqEmbeddingService:
    return FaqEmbeddingService(session)


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


@router.post("/{faq_id}/embedding", response_model=ApiResponse[FaqEmbeddingData])
async def generate_faq_embedding(
    faq_id: int,
    service: Annotated[FaqEmbeddingService, Depends(get_faq_embedding_service)],
) -> ApiResponse[FaqEmbeddingData]:
    return ApiResponse(
        message="FAQ 向量生成成功",
        data=await service.generate_faq_embedding(faq_id),
    )


@router.post("/import/parse", response_model=ApiResponse[FaqImportParseData])
async def parse_faq_import(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    file: Annotated[UploadFile, File(...)],
    preview_limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ApiResponse[FaqImportParseData]:
    file_name = file.filename or "unknown.xlsx"
    if not file_name.lower().endswith(".xlsx"):
        raise BusinessError(
            "仅支持上传 .xlsx 格式的 FAQ 文件",
            code="FAQ_IMPORT_FILE_TYPE_INVALID",
            status_code=400,
        )

    content = await file.read()
    if not content:
        raise BusinessError("上传文件为空", code="FAQ_IMPORT_FILE_EMPTY", status_code=400)
    if len(content) > 20 * 1024 * 1024:
        raise BusinessError(
            "FAQ 文件不能超过 20MB",
            code="FAQ_IMPORT_FILE_TOO_LARGE",
            status_code=400,
        )

    data = await FaqImportService(session).parse_excel_with_conflicts(
        content=content,
        file_name=file_name,
        preview_limit=preview_limit,
    )
    return ApiResponse(message="FAQ 文件解析成功", data=data)


@router.post("/import/confirm", response_model=ApiResponse[FaqImportConfirmData])
async def confirm_faq_import(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    file: Annotated[UploadFile, File(...)],
    import_status: Annotated[int, Query(alias="status", ge=0, le=1)] = 0,
    updated_by: Annotated[str, Query(min_length=1, max_length=64)] = "客服运营",
) -> ApiResponse[FaqImportConfirmData]:
    file_name = file.filename or "unknown.xlsx"
    if not file_name.lower().endswith(".xlsx"):
        raise BusinessError(
            "仅支持上传 .xlsx 格式的 FAQ 文件",
            code="FAQ_IMPORT_FILE_TYPE_INVALID",
            status_code=400,
        )

    content = await file.read()
    if not content:
        raise BusinessError("上传文件为空", code="FAQ_IMPORT_FILE_EMPTY", status_code=400)
    if len(content) > 20 * 1024 * 1024:
        raise BusinessError(
            "FAQ 文件不能超过 20MB",
            code="FAQ_IMPORT_FILE_TOO_LARGE",
            status_code=400,
        )

    data = await FaqImportService(session).confirm_excel(
        content=content,
        file_name=file_name,
        status=import_status,
        updated_by=updated_by,
    )
    return ApiResponse(message="FAQ 文件已确认入库", data=data)


@router.post(
    "/embeddings/rebuild",
    response_model=ApiResponse[FaqEmbeddingTaskData],
    status_code=status.HTTP_202_ACCEPTED,
)
async def rebuild_faq_embeddings(
    payload: FaqEmbeddingRebuildRequest,
) -> ApiResponse[FaqEmbeddingTaskData]:
    return ApiResponse(
        message="FAQ 向量批量重建任务已创建",
        data=faq_embedding_task_manager.create_rebuild_task(
            limit=payload.limit,
            only_pending=payload.only_pending,
            faq_ids=payload.faq_ids,
        ),
    )


@router.get(
    "/embeddings/tasks/{task_id}",
    response_model=ApiResponse[FaqEmbeddingTaskData],
)
async def get_faq_embedding_task(task_id: str) -> ApiResponse[FaqEmbeddingTaskData]:
    task = faq_embedding_task_manager.get_task(task_id)
    if task is None:
        raise BusinessError(
            "FAQ 向量任务不存在",
            code="FAQ_EMBEDDING_TASK_NOT_FOUND",
            status_code=404,
        )
    return ApiResponse(data=task)


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
