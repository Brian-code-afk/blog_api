# app/core/security.py
"""密码哈希与 access token 签发/校验。

refresh token 的生成、存储、轮换见 app/core/token.py
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.config import settings
from app.core.exceptions import TokenExpiredException, TokenInvalidException

# bcrypt 只取前 72 字节，超长密码会被静默截断
_BCRYPT_MAX_BYTES = 72


# ------------------ 密码相关 ------------------

def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pwd_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(pwd_bytes, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        # hash 不是合法 bcrypt 格式时 bcrypt 抛异常而非返回 False，
        # 不兜住就会变成 500 而不是 401
        return False


# ------------------ access token ------------------

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_ttl_minutes)
    )
    to_encode = data.copy()
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(
        to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],  # 必须显式指定，防 alg:none 攻击
        )
    except ExpiredSignatureError as exc:
        raise TokenExpiredException() from exc
    except InvalidTokenError as exc:
        raise TokenInvalidException() from exc

    if payload.get("type") != "access":   # 防止用 refresh token 冒充 access
        raise TokenInvalidException()
    return payload