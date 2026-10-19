# app/services/tag_service.py
"""标签领域逻辑。"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import TagExistsException, TagNotFoundException
from app.models import Tag
from app.schemas.common import PageParams
from app.schemas.tag import TagCreate, TagUpdate
from app.utils.slug import ensure_unique_slug, slugify


def get_by_id(db: Session, tag_id: int) -> Tag:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise TagNotFoundException()
    return tag


def get_by_slug(db: Session, slug: str) -> Tag:
    tag = db.scalar(select(Tag).where(Tag.slug == slug))
    if tag is None:
        raise TagNotFoundException()
    return tag


def list_tags(db: Session, params: PageParams) -> tuple[list[Tag], int]:
    """按文章数倒序返回，同时给出总数供分页。"""
    total = db.scalar(select(func.count()).select_from(Tag)) or 0

    stmt = (
        select(Tag)
        .order_by(Tag.name)
        .offset(params.offset)
        .limit(params.limit)
    )
    return list(db.scalars(stmt).all()), total


def create_tag(db: Session, payload: TagCreate) -> Tag:
    base = payload.slug or slugify(payload.name)
    slug = ensure_unique_slug(db, Tag, base, max_len=50)

    tag = Tag(name=payload.name.strip(), slug=slug)
    db.add(tag)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise TagExistsException()
    db.refresh(tag)
    return tag


def update_tag(db: Session, tag: Tag, payload: TagUpdate) -> Tag:
    if payload.name is not None:
        tag.name = payload.name.strip()
    if payload.slug is not None:
        tag.slug = ensure_unique_slug(db, Tag, payload.slug,
                                      exclude_id=tag.id, max_len=50)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise TagExistsException()
    db.refresh(tag)
    return tag


def delete_tag(db: Session, tag: Tag) -> None:
    """删除标签。article_tags 里的关联行由外键 ON DELETE CASCADE 清掉。"""
    db.delete(tag)
    db.commit()


def get_or_create_many(db: Session, names: list[str]) -> list[Tag]:
    """按名字批量取（或建）标签。创建文章/设置标签时用。

    先批量 SELECT 已存在的，再 INSERT 缺失的，避免逐条查询。
    """
    cleaned: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = name.strip()
        if key and key.lower() not in seen:
            seen.add(key.lower())
            cleaned.append(key)

    if not cleaned:
        return []

    existing = {
        t.name.lower(): t
        for t in db.scalars(select(Tag).where(Tag.name.in_(cleaned))).all()
    }

    result: list[Tag] = []
    created = False
    for name in cleaned:
        tag = existing.get(name.lower())
        if tag is None:
            tag = Tag(name=name, slug=ensure_unique_slug(db, Tag, slugify(name),
                                                         max_len=50))
            db.add(tag)
            db.flush()          # 拿到 id，暂不提交
            existing[name.lower()] = tag
            created = True
        result.append(tag)

    if created:
        # 并发下仍可能撞唯一约束，交给全局处理器转成 409
        db.commit()
    return result