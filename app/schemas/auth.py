# app/schemas/auth.py
from pydantic import Field

from app.schemas.common import ORMModel


class LoginRequest(ORMModel):
    """登录。account 可以是用户名或邮箱。"""

    account: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=72)


class RefreshRequest(ORMModel):
    """刷新。refresh token 是不透明随机串，不是 JWT。"""

    refresh_token: str = Field(min_length=1)


class LogoutRequest(ORMModel):
    """登出。带上 refresh token 才能精确吊销当前设备。"""

    refresh_token: str = Field(min_length=1)


class TokenPair(ORMModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="access token 剩余秒数")


class AccessToken(ORMModel):
    """刷新接口只返回新的 access token；refresh token 只有轮换时才一并返回。"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int