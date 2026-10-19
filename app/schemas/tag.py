# app/schemas/tag.py
import re
from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import ORMModel

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_slug(v: str) -> str:
    """slug 统一转小写、去首尾空格、连续分隔符压成一个连字符。"""
    v = v.strip().lower()
    v = re.sub(r"[\s_]+", "-", v)
    v = re.sub(r"-+", "-", v).strip("-")
    if not _SLUG_RE.match(v):
        raise ValueError("slug 只能包含小写字母、数字和连字符")
    return v


class TagBase(ORMModel):
    name: str = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("标签名不能为空")
        return v


class TagCreate(TagBase):
    slug: str | None = Field(default=None, max_length=50)

    @field_validator("slug")
    @classmethod
    def check_slug(cls, v: str | None) -> str | None:
        return normalize_slug(v) if v else v


class TagUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    slug: str | None = Field(default=None, max_length=50)

    @field_validator("slug")
    @classmethod
    def check_slug(cls, v: str | None) -> str | None:
        return normalize_slug(v) if v else v


class TagBrief(ORMModel):
    """嵌在文章里的标签摘要，同样不含 articles 字段。"""

    id: int
    name: str
    slug: str


class TagOut(ORMModel):
    id: int
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime