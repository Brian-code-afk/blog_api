# app/core/responses.py
"""统一响应封装。

用 Pydantic 泛型模型替代裸 dict —— 裸 dict 会让 Swagger 丢失全部 response schema。
用法：
    @router.get("/articles", response_model=APIResponse[PageData[ArticleOut]])
"""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """统一响应结构。code=0 表示成功，非 0 为业务错误码"""

    code: int = 0
    message: str = "success"
    data: T | None = None

    def to_dict(self) -> dict:
        """异常处理器构造 JSONResponse 时需要 dict，统一走这个出口"""
        return self.model_dump(mode="json")


class PageData(BaseModel, Generic[T]):
    """分页数据结构"""

    items: list[T] = Field(default_factory=list)
    total: int = 0
    page_num: int = 1
    page_size: int = 20
    pages: int = 0


# ────────────────────────── 成功 ──────────────────────────


def success(data: Any = None, message: str = "success") -> APIResponse[Any]:
    return APIResponse(code=0, message=message, data=data)


def created(data: Any = None, message: str = "创建成功") -> APIResponse[Any]:
    return APIResponse(code=0, message=message, data=data)


def updated(data: Any = None, message: str = "更新成功") -> APIResponse[Any]:
    return APIResponse(code=0, message=message, data=data)


def deleted(message: str = "删除成功") -> APIResponse[Any]:
    return APIResponse(code=0, message=message, data=None)


# ────────────────────────── 失败 ──────────────────────────


def fail(message: str = "操作失败", code: int = 1,
         data: Any = None) -> APIResponse[Any]:
    return APIResponse(code=code, message=message, data=data)


# ────────────────────────── 分页 ──────────────────────────


def page(
    items: list,
    total: int,
    page_num: int = 1,
    page_size: int = 20,
) -> APIResponse[PageData[Any]]:
    """分页响应。page_size=0 时 pages 记为 0，避免除零"""
    pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return APIResponse(
        code=0,
        message="success",
        data=PageData(
            items=items,
            total=total,
            page_num=page_num,
            page_size=page_size,
            pages=pages,
        ),
    )