from collections.abc import Sequence
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


def pagination_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size)


def paginate(items: Sequence[T], page: int, page_size: int) -> Page[T]:
    start = (page - 1) * page_size
    end = start + page_size
    return Page(items=list(items[start:end]), page=page, page_size=page_size, total=len(items))
