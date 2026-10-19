# app/utils/slug.py
"""slug 生成工具。"""
import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, Tag

# 保留中文字符（\w 在 Python 下已含中文，这里显式写出以免误删）
_KEEP = re.compile(r"[^a-z0-9\u4e00-\u9fff]+")


def slugify(text: str) -> str:
    """把标题转成 slug；中文会被保留，纯符号标题返回空串。"""
    text = text.strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    text = _KEEP.sub("-", text)
    return re.sub(r"-+", "-", text).strip("-")


def _candidate(base: str) -> str:
    return base or f"post-{secrets.token_hex(4)}"


def ensure_unique_slug(
    db: Session,
    model: type[Article] | type[Tag],
    slug: str,
    exclude_id: int | None = None,
    max_len: int = 200,
) -> str:
    """保证 slug 唯一：冲突时追加 -2、-3……实在不行追加随机串。

    max_len 必须和数据库列宽一致（articles 200 / tags 50），
    截断后仍有极小概率撞车，靠数据库唯一约束兜底。
    """
    base = _candidate(slug)[:max_len].strip("-") or "post"

    stmt = select(model.id).where(model.slug == base)
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)

    if db.scalar(stmt) is None:
        return base

    for i in range(2, 50):
        suffix = f"-{i}"
        candidate = f"{base[: max_len - len(suffix)]}{suffix}"
        stmt = select(model.id).where(model.slug == candidate)
        if exclude_id is not None:
            stmt = stmt.where(model.id != exclude_id)
        if db.scalar(stmt) is None:
            return candidate

    # 极端情况兜底
    return f"{base[: max_len - 9]}-{secrets.token_hex(4)}"