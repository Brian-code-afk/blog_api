# app/routers/auth.py
"""认证接口：注册、登录、刷新、登出。"""
from fastapi import APIRouter
from app.core import responses
from app.core.responses import APIResponse
from app.dependencies import DbDep
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, TokenPair
from app.schemas.user import UserCreate
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post(
    "/register",
    response_model=APIResponse[TokenPair],
    status_code=201,
    summary="注册（注册即登录，直接返回令牌对）",
)
def register(payload: UserCreate, db: DbDep):
    token_pair = auth_service.register(db, payload)
    return responses.created(token_pair, "注册成功")


@router.post(
    "/login",
    response_model=APIResponse[TokenPair],
    summary="登录（账号可填用户名或邮箱）",
)
def login(payload: LoginRequest, db: DbDep):
    token_pair = auth_service.login(db, payload)
    return responses.success(token_pair, "登录成功")


@router.post(
    "/refresh",
    response_model=APIResponse[TokenPair],
    summary="刷新令牌（旧 refresh token 作废并轮换）",
)
def refresh(payload: RefreshRequest):
    # 不依赖 db：刷新链路只操作 Redis，MySQL 故障时已登录用户仍可续期
    token_pair = auth_service.refresh(payload.refresh_token)
    return responses.success(token_pair)


@router.post(
    "/logout",
    response_model=APIResponse[None],
    summary="登出（吊销当前设备的 refresh token）",
)
def logout(payload: LogoutRequest):
    auth_service.logout(payload.refresh_token)
    return responses.success(None, "已登出")