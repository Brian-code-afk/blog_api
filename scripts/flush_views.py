# scripts/flush_views.py
"""浏览量落库 worker。

独立进程，每隔一段时间把 Redis 里的增量写回 MySQL。
在 compose 里作为单独 service 运行（同一个镜像、不同的 command）。

为什么单独跑：
- 塞进 Web 进程会让每个副本都跑一遍定时任务，重复写库
- 独立出来可以单独重启、单独看日志，不影响 API 可用性
"""
import logging
import os
import sys
import time

from app.db.session import SessionLocal
from app.services import article_service

INTERVAL = int(os.getenv("FLUSH_INTERVAL_SECONDS", "300"))

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("flush_views")


def run_once() -> None:
    db = SessionLocal()
    try:
        count = article_service.flush_views_to_db(db)
        if count:
            logger.info("已落库 %s 篇文章的浏览量", count)
    except Exception:  # noqa: BLE001
        logger.exception("浏览量落库失败")
        db.rollback()
    finally:
        db.close()


def main() -> None:
    logger.info("worker 启动，间隔 %ss", INTERVAL)
    while True:
        run_once()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
