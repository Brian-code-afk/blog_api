# app/db/redis.py
"""Redis 客户端。

连接串统一来自 .env 的 REDIS_URL，形如 redis://[:密码]@host:port/db
"""
from redis import Redis

from app.config import settings

# decode_responses=True 让返回值直接是 str，省去各处 .decode()
redis_client = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=3,
    socket_timeout=3,
    # 容器环境下 Redis 可能比应用晚就绪，连接失败时重试几次
    retry_on_timeout=True,
    health_check_interval=30,
)

def get_redis() -> Redis:#定义获取redis客户端的函数
    """FastAPI 依赖：返回全局 client"""
    return redis_client