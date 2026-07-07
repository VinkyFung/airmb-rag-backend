from typing import Generic, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class ApiResponse(BaseModel, Generic[DataT]):
    code: str = "OK"
    message: str = "success"
    data: DataT


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int


class PageData(BaseModel, Generic[DataT]):
    items: list[DataT]
    pagination: PageMeta

