# app/services/auth_service.py
"""认证流程：注册、登录、刷新、登出。

串起 core/security.py（密码 + access token）与 core/token.py（refresh token）。
"""
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import create_access_token
from app.core.token import consume, issue, revoke
from app.schemas.auth import LoginRequest, LogoutRequest, TokenPair
from app.schemas.user import UserCreate
from app.services import user_service


def _pair(user_id: int, refresh_token: str | None = None) -> TokenPair:
    """组装令牌对。

    refresh_token 为 None 时才新签发一个；
    刷新流程必须传入 consume() 返回的那个，否则会重复签发。
    """
    access = create_access_token({"sub": str(user_id)})
    if refresh_token is None:
        refresh_token = issue(user_id)

    return TokenPair(
        access_token=access,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.access_token_ttl_minutes * 60,
    )


def register(db: Session, payload: UserCreate) -> TokenPair:
    """注册并直接返回令牌对（注册即登录）。"""
    user = user_service.create_user(db, payload)
    return _pair(user.id)


def login(db: Session, payload: LoginRequest) -> TokenPair:
    """登录。账号可以是用户名或邮箱。"""
    user = user_service.authenticate(db, payload.account, payload.password)
    return _pair(user.id)


def refresh(refresh_token: str) -> TokenPair:
    """刷新并轮换。

    consume() 内部已完成「旧 token 作废 + 签新 token」，
    所以它返回的新 refresh token 必须直接透传，不能再次签发。
    """
    user_id, new_refresh = consume(refresh_token)  # 无效/已吊销时抛 401
    return _pair(user_id, new_refresh)


def logout(refresh_token: str, db: Session | None = None) -> None:
    """登出：吊销当前设备的 refresh token。

    已知限制：access token 在剩余寿命内（默认 15 分钟）仍然有效，
    这是无状态 JWT 的固有代价。若要登出即时生效，需要额外维护 jti 黑名单。
    """
    revoke(refresh_token)