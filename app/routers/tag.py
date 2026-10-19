# app/routers/tag.py
"""标签接口。

创建/更新/删除需要登录，列表公开。
鉴权统一挂在装饰器的 dependencies 上 —— 只要求令牌有效，
函数体内不需要用到用户信息，避免产生未使用的形参。
"""
from fastapi import APIRouter, Depends

from app.core import responses
from app.core.responses import APIResponse, PageData
from app.dependencies import (
    DbDep,
    PageParamsDep,
    get_current_active_user,
)
from app.schemas.tag import TagCreate, TagOut, TagUpdate
from app.services import tag_service

router = APIRouter(prefix="/tags", tags=["标签"])


@router.get("", response_model=APIResponse[PageData[TagOut]], summary="标签列表")
def list_tags(db: DbDep, params: PageParamsDep):
    tags, total = tag_service.list_tags(db, params)
    items = [TagOut.model_validate(t) for t in tags]
    return responses.page(
        items=items,
        total=total,
        page_num=params.page_num,
        page_size=params.page_size,
    )


@router.post(
    "",
    response_model=APIResponse[TagOut],
    status_code=201,
    dependencies=[Depends(get_current_active_user)],
    summary="创建标签（slug 不传时由名称自动生成）",
)
def create_tag(payload: TagCreate, db: DbDep):
    tag = tag_service.create_tag(db, payload)
    return responses.created(TagOut.model_validate(tag))


@router.patch(
    "/{tag_id}",
    response_model=APIResponse[TagOut],
    dependencies=[Depends(get_current_active_user)],
    summary="更新标签",
)
def update_tag(tag_id: int, payload: TagUpdate, db: DbDep):
    tag = tag_service.get_by_id(db, tag_id)
    tag = tag_service.update_tag(db, tag, payload)
    return responses.updated(TagOut.model_validate(tag))


@router.delete(
    "/{tag_id}",
    response_model=APIResponse[None],
    dependencies=[Depends(get_current_active_user)],
    summary="删除标签（文章关联记录由外键 CASCADE 清理）",
)
def delete_tag(tag_id: int, db: DbDep):
    tag = tag_service.get_by_id(db, tag_id)
    tag_service.delete_tag(db, tag)
    return responses.deleted()