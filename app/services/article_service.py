# app/services/article_service.py
"""文章领域逻辑：列表、详情、增删改、标签绑定、浏览量计数。"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ArticleNotFoundException,
    NotOwnerException,
    SlugExistsException,
)
from app.db.redis import redis_client
from app.models import Article, Tag
from app.schemas.article import ArticleCreate, ArticleUpdate
from app.schemas.common import PageParams
from app.utils.slug import ensure_unique_slug, slugify

# 浏览量在 Redis 里的增量键，定时落库
VIEW_KEY = "article:views:{aid}"
VIEW_KEY_PATTERN = "article:views:*"


# ------------------ 查询 ------------------

def get_by_id(db: Session, article_id: int) -> Article:
    article = db.get(Article, article_id)
    if article is None:
        raise ArticleNotFoundException()
    return article


def get_by_slug(db: Session, slug: str, *, only_published: bool = False) -> Article:
    stmt = select(Article).where(Article.slug == slug)
    if only_published:
        stmt = stmt.where(Article.status == "published")
    article = db.scalar(stmt)
    if article is None:
        raise ArticleNotFoundException()
    return article


def list_articles(
    db: Session,
    params: PageParams,
    *,
    status: str | None = None,
    tag_slug: str | None = None,
    author_id: int | None = None,
    keyword: str | None = None,
) -> tuple[list[Article], int]:
    """列表查询。

    用 Article.tags.any(...) 生成 EXISTS 子查询做标签筛选，
    相比 join 不会产生行放大，count 也更准确。
    """
    conditions = []
    if status:
        conditions.append(Article.status == status)
    if tag_slug:
        conditions.append(Article.tags.any(Tag.slug == tag_slug))
    if author_id is not None:
        conditions.append(Article.author_id == author_id)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        conditions.append(
            (Article.title.like(pattern)) | (Article.summary.like(pattern))
        )

    total = db.scalar(
        select(func.count()).select_from(Article).where(*conditions)
    ) or 0

    stmt = (
        select(Article)
        .where(*conditions)
        .order_by(Article.created_at.desc())   # 命中 (status, created_at) 联合索引
        .offset(params.offset)
        .limit(params.limit)
    )
    return list(db.scalars(stmt).all()), total


# ------------------ 写入 ------------------

def create_article(db: Session, payload: ArticleCreate, author_id: int) -> Article:
    base = payload.slug or slugify(payload.title)
    slug = ensure_unique_slug(db, Article, base, max_len=200)

    article = Article(
        title=payload.title,
        slug=slug,
        summary=payload.summary,
        content=payload.content,
        status=payload.status,
        author_id=author_id,
        published_at=(
            datetime.now(timezone.utc).replace(tzinfo=None)
            if payload.status == "published" else None
        ),
    )

    if payload.tag_names:
        article.tags = tag_service.get_or_create_many(db, payload.tag_names)

    db.add(article)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise SlugExistsException()
    db.refresh(article)
    return article


def update_article(db: Session, article: Article, payload: ArticleUpdate) -> Article:
    if payload.title is not None:
        article.title = payload.title
    if payload.summary is not None:
        article.summary = payload.summary
    if payload.content is not None:
        article.content = payload.content
    if payload.slug is not None and payload.slug != article.slug:
        article.slug = ensure_unique_slug(
            db, Article, payload.slug, exclude_id=article.id, max_len=200
        )

    # status 与 published_at 联动：首次发布时补上时间
    if payload.status is not None and payload.status != article.status:
        article.status = payload.status
        if payload.status == "published" and article.published_at is None:
            article.published_at = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise SlugExistsException()
    db.refresh(article)
    return article


def delete_article(db: Session, article: Article) -> None:
    """硬删除。关联行由外键 CASCADE 清理，浏览量计数键一并删除。"""
    redis_client.delete(VIEW_KEY.format(aid=article.id))
    db.delete(article)
    db.commit()


def set_article_tags(
    db: Session, article: Article, tag_names: list[str]
) -> Article:
    """全量替换文章标签（PUT 语义）。"""
    article.tags = tag_service.get_or_create_many(db, tag_names)
    db.commit()
    db.refresh(article)
    return article


def check_owner(article: Article, user_id: int) -> None:
    """校验资源归属，不通过抛 403。"""
    if article.author_id != user_id:
        raise NotOwnerException()


# ------------------ 浏览量 ------------------

def record_view(article_id: int) -> None:
    """详情页调用：只写 Redis，不碰数据库。

    避免每次阅读都 UPDATE 造成行锁竞争和缓存失效。
    """
    redis_client.incr(VIEW_KEY.format(aid=article_id))


def fetch_view_deltas(article_ids: list[int]) -> dict[int, int]:
    """批量取 Redis 中的增量，一次 MGET 完成，避免 N+1。"""
    if not article_ids:
        return {}

    keys = [VIEW_KEY.format(aid=aid) for aid in article_ids]
    values = redis_client.mget(keys)

    deltas: dict[int, int] = {}
    for aid, raw in zip(article_ids, values):
        if raw:
            try:
                deltas[aid] = int(raw)
            except (TypeError, ValueError):
                continue
    return deltas


def flush_views_to_db(db: Session) -> int:
    """定时任务：把 Redis 里的增量写回数据库。

    建议用 cron / APScheduler 每 5 分钟跑一次。
    返回本次更新的文章数。
    """
    updated = 0
    deltas: dict[int, int] = {}

    # 用 scan_iter 而非 keys，避免大批量 key 阻塞 Redis
    for key in redis_client.scan_iter(match=VIEW_KEY_PATTERN, count=500):
        try:
            article_id = int(str(key).rsplit(":", 1)[-1])
            raw = redis_client.get(key)
            delta = int(raw) if raw else 0
        except (ValueError, TypeError):
            continue
        if delta > 0:
            deltas[article_id] = delta

    if not deltas:
        return 0

    for article_id, delta in deltas.items():
        # 用 SQL 表达式自增，避免读改写丢失期间的新增量
        result = db.execute(
            Article.__table__.update()
            .where(Article.__table__.c.id == article_id)
            .values(view_count=Article.__table__.c.view_count + delta)
        )
        updated += result.rowcount or 0

    db.commit()

    # 落库成功后才删计数键；删除失败最多导致重复累加，可接受
    redis_client.delete(*[VIEW_KEY.format(aid=aid) for aid in deltas])
    return updated


from app.services import tag_service  # noqa: E402  置于末尾避免与上方引用冲突