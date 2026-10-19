# app/schemas/article.py
import re
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.common import ORMModel
from app.schemas.tag import TagBrief, normalize_slug
from app.schemas.user import UserBrief

ArticleStatus = Literal["draft", "published"]


class ArticleBase(ORMModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=500)
    content: str = Field(min_length=1)
    status: ArticleStatus = "draft"

    @field_validator("title")
    @classmethod
    def check_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("标题不能为空")
        return v


class ArticleCreate(ArticleBase):
    slug: str | None = Field(default=None, max_length=200)
    # 允许创建时直接带标签：传标签名列表，service 层负责 get_or_create
    tag_names: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("slug")
    @classmethod
    def check_slug(cls, v: str | None) -> str | None:
        return normalize_slug(v) if v else v

    @field_validator("tag_names")
    @classmethod
    def check_tag_names(cls, v: list[str]) -> list[str]:
        cleaned = [name.strip() for name in v if name and name.strip()]
        for name in cleaned:
            if len(name) > 50:
                raise ValueError(f"标签名过长: {name}")
        return cleaned

    @model_validator(mode="after")
    def default_slug_from_title(self) -> "ArticleCreate":
        """没传 slug 时由标题生成，避免每个路由都写一遍。"""
        if not self.slug:
            base = re.sub(r"[\s_]+", "-", self.title.strip().lower())
            base = re.sub(r"[^\w\u4e00-\u9fa5-]", "", base).strip("-")
            # 中文标题会被上面那句清空（\w 在 Python 下其实匹配中文，
            # 这里再兜一次，实在生成不出来就留空交给 service 层用 id 兜底）
            self.slug = re.sub(r"-+", "-", base) or None
        return self


class ArticleUpdate(ORMModel):
    """更新请求。所有字段可选，且不提供 status 的「取消发布」以外的隐式行为。"""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=500)
    content: str | None = Field(default=None, min_length=1)
    status: ArticleStatus | None = None
    slug: str | None = Field(default=None, max_length=200)

    @field_validator("slug")
    @classmethod
    def check_slug(cls, v: str | None) -> str | None:
        return normalize_slug(v) if v else v


class ArticleTagsUpdate(ORMModel):
    """PUT /api/articles/{slug}/tags —— 全量替换该文章的标签。"""

    tag_names: list[str] = Field(default_factory=list, max_length=20)


class ArticleListItem(ORMModel):
    """列表页用：不含 content，减少传输量。"""

    id: int
    title: str
    slug: str
    summary: str | None
    status: ArticleStatus
    view_count: int
    published_at: datetime | None
    author_id: int
    author: UserBrief | None = None
    tags: list[TagBrief] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ArticleOut(ORMModel):
    """详情页用：含完整正文。"""

    id: int
    title: str
    slug: str
    summary: str | None
    content: str
    status: ArticleStatus
    view_count: int
    published_at: datetime | None
    author_id: int
    author: UserBrief | None = None
    tags: list[TagBrief] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime