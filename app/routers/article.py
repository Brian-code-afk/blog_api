# app/routers/article.py
"""文章接口。标签的绑定/解绑归入本模块（PUT /{slug}/tags）。"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core import responses
from app.core.exceptions import ArticleNotFoundException
from app.core.responses import APIResponse, PageData
from app.dependencies import (
    CurrentUserDep,
    DbDep,
    OptionalUserDep,
    PageParamsDep,
    get_owned_article,
)
from app.models import Article
from app.schemas.article import (
    ArticleCreate,
    ArticleListItem,
    ArticleOut,
    ArticleTagsUpdate,
    ArticleUpdate,
)
from app.services import article_service

router = APIRouter(prefix="/articles", tags=["文章"])


# ────────────────────────── 读 ──────────────────────────

@router.get("", response_model=APIResponse[PageData[ArticleListItem]],
            summary="文章列表")
def list_articles(
    db: DbDep,
    params: PageParamsDep,
    status: str | None = Query(None, pattern="^(draft|published)$"),
    tag: str | None = Query(None, description="按标签 slug 筛选"),
    keyword: str | None = Query(None, description="标题/摘要模糊搜索"),
):
    articles, total = article_service.list_articles(
        db, params, status=status, tag_slug=tag, keyword=keyword
    )

    deltas = article_service.fetch_view_deltas([a.id for a in articles])
    items = []
    for a in articles:
        item = ArticleListItem.model_validate(a)
        item.view_count += deltas.get(a.id, 0)   # 合并 Redis 中未落库的增量
        items.append(item)

    return responses.page(
        items=items, total=total,
        page_num=params.page_num, page_size=params.page_size,
    )


@router.get("/{slug}", response_model=APIResponse[ArticleOut], summary="文章详情")
def get_article(
    slug: str,
    db: DbDep,
    current_user: OptionalUserDep,   # 游客可访问，但草稿只对作者可见
):
    article = article_service.get_by_slug(db, slug)

    if article.status != "published":
        # 未发布：非作者一律按不存在处理，避免暴露草稿存在性
        if current_user is None or article.author_id != current_user.id:
            raise ArticleNotFoundException()

    article_service.record_view(article.id)      # 只写 Redis，不 UPDATE 数据库

    out = ArticleOut.model_validate(article)
    out.view_count += article_service.fetch_view_deltas([article.id]).get(
        article.id, 0
    )
    return responses.success(out)


# ────────────────────────── 写 ──────────────────────────

@router.post("", response_model=APIResponse[ArticleOut], status_code=201,
             summary="创建文章")
def create_article(payload: ArticleCreate, db: DbDep, current_user: CurrentUserDep):
    article = article_service.create_article(db, payload, author_id=current_user.id)
    return responses.created(ArticleOut.model_validate(article))


@router.patch("/{slug}", response_model=APIResponse[ArticleOut], summary="更新文章")
def update_article(
    payload: ArticleUpdate,
    db: DbDep,
    article: Annotated[Article, Depends(get_owned_article)],
):
    updated = article_service.update_article(db, article, payload)
    return responses.updated(ArticleOut.model_validate(updated))


@router.delete("/{slug}", response_model=APIResponse[None], summary="删除文章")
def delete_article(
    db: DbDep,
    article: Annotated[Article, Depends(get_owned_article)],
):
    article_service.delete_article(db, article)
    return responses.deleted()


# ────────────────────────── 标签绑定 ──────────────────────────

@router.put(
    "/{slug}/tags",
    response_model=APIResponse[ArticleOut],
    summary="全量替换文章标签（传入即最终标签集合）",
)
def set_article_tags(
    payload: ArticleTagsUpdate,
    db: DbDep,
    article: Annotated[Article, Depends(get_owned_article)],
):
    updated = article_service.set_article_tags(db, article, payload.tag_names)
    return responses.updated(ArticleOut.model_validate(updated), "标签已更新")