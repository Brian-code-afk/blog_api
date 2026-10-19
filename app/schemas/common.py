# app/schemas/common.py
"""所有 schema 共用的基类与分页参数。"""
from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    """允许直接由 SQLAlchemy 模型实例构造（等价于旧版的 orm_mode）。

    输出模型统一继承它，路由里就能 `ArticleOut.model_validate(article_obj)`。
    """
    model_config = ConfigDict(from_attributes=True)


class PageParams(BaseModel):
    """列表分页参数，配合 Depends() 从 query 解析。"""

    page_num: int = Field(default=1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(default=20, ge=1, le=100, description="每页条数")

    @property
    def offset(self) -> int:
        return (self.page_num - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size