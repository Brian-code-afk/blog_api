# app/routers/user.py
"""用户接口。"""
from fastapi import APIRouter

from app.core import responses
from app.core.responses import APIResponse
from app.dependencies import CurrentUserDep, DbDep
from app.schemas.user import PasswordUpdate, UserOut, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["用户"])


@router.get("/me", response_model=APIResponse[UserOut], summary="获取当前登录用户")
def read_me(current_user: CurrentUserDep):
    return responses.success(UserOut.model_validate(current_user))


@router.patch("/me", response_model=APIResponse[UserOut], summary="更新当前用户资料")
def update_me(payload: UserUpdate, db: DbDep, current_user: CurrentUserDep):
    user = user_service.update_user(db, current_user, payload)
    return responses.success(UserOut.model_validate(user), "更新成功")


@router.post(
    "/me/password",
    response_model=APIResponse[None],
    summary="修改密码（成功后所有设备强制重新登录）",
)
def change_password(payload: PasswordUpdate, db: DbDep, current_user: CurrentUserDep):
    user_service.update_password(db, current_user, payload)
    return responses.success(None, "密码已修改，请重新登录")


# ⚠️ 路由顺序：`/me` 必须声明在 `/{user_id}` 之前，
# 否则 "me" 会被当成 user_id 匹配，导致 422（int 解析失败）
@router.get(
    "/{user_id}",
    response_model=APIResponse[UserOut],
    summary="按 id 查看用户公开信息",
)
def read_user(user_id: int, db: DbDep):
    user = user_service.get_by_id(db, user_id)
    return responses.success(UserOut.model_validate(user))