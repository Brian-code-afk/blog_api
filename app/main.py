# app/main.py
import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.responses import APIResponse
from app.db.redis import redis_client
from app.db.session import engine
from app.routers import register_routers

logging.basicConfig(
    stream=sys.stdout,
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def wait_for_database(max_retries: int = 10, interval: float = 2.0) -> None:
    """启动前等待 MySQL 就绪。

    容器环境下应用往往比数据库先起来，不重试就会启动失败。
    这是 Docker 阶段的经典问题，提前加上能省不少事。
    """
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("MySQL 连接成功")
            return
        except Exception as exc:
            logger.warning(
                "MySQL 未就绪 (%s/%s)，%.1fs 后重试: %s",
                attempt, max_retries, interval, exc,
            )
            if attempt == max_retries:
                raise RuntimeError(f"MySQL 连接失败，已重试 {max_retries} 次") from exc
            time.sleep(interval)


def check_redis() -> None:
    """Redis 不是硬依赖：连不上只警告，保证已签发的 access token 仍能验签。"""
    try:
        redis_client.ping()
        logger.info("Redis 连接成功")
    except Exception as exc:
        logger.warning("Redis 连接失败，刷新与浏览量统计将不可用: %s", exc)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """应用生命周期：启动时自检，关闭时释放资源。"""
    logger.info("应用启动，环境=%s", settings.env)

    wait_for_database()
    check_redis()

    # 生产环境请用 Alembic：alembic upgrade head
    # 这里只用于本地开发首次启动
    if settings.env == "dev":
        from app.db.base import Base
        Base.metadata.create_all(bind=engine)
        logger.info("开发模式：已自动建表")

    yield

    # 关闭：释放连接池，避免 MySQL 端残留 sleep 连接
    engine.dispose()
    redis_client.close()
    logger.info("应用已关闭")


def create_app() -> FastAPI:
    if not settings.jwt_secret:
        raise RuntimeError("SECRET_KEY 未配置，请在 .env 中设置")

    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version="0.1.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(application)
    register_routers(application)

    @application.get("/healthz", tags=["运维"], summary="健康检查")
    def healthz() -> APIResponse[dict]:
        return APIResponse(code=0, message="ok", data={"env": settings.env})

    return application


app = create_app()