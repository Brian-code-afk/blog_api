# app/core/token.py
"""refresh token 的签发、校验、轮换与吊销。

设计要点：
1. refresh token 是不透明随机串（不是 JWT），服务端存 Redis，因此可即时吊销
2. Redis 里存的是 token 的 SHA-256 而非明文 —— Redis 泄露不等于令牌泄露
3. 每次刷新都轮换，旧 token 进入短宽限期后失效
4. access token 仍是无状态 JWT，本模块不碰它
"""
import hashlib
import secrets

from app.config import settings
from app.core.exceptions import TokenInvalidException
from app.core.security import create_access_token
from app.db.redis import redis_client

# Redis 键名。统一在此定义，避免各处散落字符串
REFRESH_KEY = "auth:refresh:{h}"      # 有效 token → user_id
GRACE_KEY = "auth:grace:{h}"          # 轮换后的宽限期 → user_id
USER_INDEX = "auth:user_tokens:{uid}"  # 某用户全部 token，用于批量吊销


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _refresh_ttl() -> int:
    return int(settings.refresh_token_ttl_days * 86400)


# ------------------ 签发 ------------------

def issue(user_id: int) -> str:
    """签发新的 refresh token 并写入 Redis，返回明文（唯一一次可见的机会）"""
    token = secrets.token_urlsafe(32)      # 256 bit 熵
    h = _hash(token)
    ttl = _refresh_ttl()
    index = USER_INDEX.format(uid=user_id)

    pipe = redis_client.pipeline()
    pipe.setex(REFRESH_KEY.format(h=h), ttl, str(user_id))
    pipe.sadd(index, h)
    pipe.expire(index, ttl)                # 索引不永久保留，随 token 一起过期
    pipe.execute()
    return token


def issue_pair(user_id: int) -> tuple[str, str]:
    """一次签出 (access_token, refresh_token)，供登录和刷新接口使用"""
    access = create_access_token({"sub": str(user_id)})
    return access, issue(user_id)


# ------------------ 校验与轮换 ------------------

def consume(token: str) -> tuple[int, str]:
    """校验 refresh token 并轮换，返回 (user_id, 新 refresh_token)。

    - 正常情况：旧 token 作废并进入宽限期，签发新 token
    - 宽限期内：允许兑换一次，用于网络抖动导致的客户端重试
    - 其他情况：抛 TokenInvalidException（401）
    """
    h = _hash(token)
    refresh_key = REFRESH_KEY.format(h=h)
    grace_key = GRACE_KEY.format(h=h)

    raw = redis_client.get(refresh_key)
    if raw is not None:
        redis_client.delete(refresh_key)
        # 旧 token 进宽限期，防客户端没收到响应就被强制登出
        redis_client.setex(
            grace_key, settings.refresh_token_grace_seconds, raw
        )
    else:
        raw = redis_client.get(grace_key)
        if raw is None:
            raise TokenInvalidException("登录凭证无效或已失效")
        # 宽限期内只允许兑换一次，之后再用即失效
        redis_client.delete(grace_key)

    user_id = int(raw)
    return user_id, issue(user_id)


def peek(token: str) -> int | None:
    """只看不轮换，返回 user_id；无效返回 None。用于需要静默校验的场景"""
    h = _hash(token)
    for key in (REFRESH_KEY.format(h=h), GRACE_KEY.format(h=h)):
        raw = redis_client.get(key)
        if raw is not None:
            return int(raw)
    return None


# ------------------ 吊销 ------------------

def revoke(token: str) -> None:
    """登出：作废单个 refresh token"""
    h = _hash(token)
    pipe = redis_client.pipeline()
    pipe.delete(REFRESH_KEY.format(h=h))
    pipe.delete(GRACE_KEY.format(h=h))
    pipe.execute()
    # 索引里的成员暂不清理，随索引 TTL 自然过期，避免反查 user_id


def revoke_all_for_user(user_id: int) -> None:
    """封号 / 改密码 / 检测到异常：作废该用户全部 refresh token，
    所有设备下次刷新时被踢下线"""
    index = USER_INDEX.format(uid=user_id)
    hashes = redis_client.smembers(index) or set()

    pipe = redis_client.pipeline()
    for h in hashes:
        pipe.delete(REFRESH_KEY.format(h=h))
        pipe.delete(GRACE_KEY.format(h=h))
    pipe.delete(index)
    pipe.execute()