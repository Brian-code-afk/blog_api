# scripts/wait_for_db.py
"""等待 MySQL 可连接。

容器编排时，应用容器几乎总是比 MySQL 先就绪 —— MySQL 首次启动要
初始化数据目录，可能耗时十几秒。不等就会启动失败。
"""
import os
import sys
import time
from urllib.parse import unquote, urlparse

import pymysql

from app.config import settings

MAX_RETRIES = int(os.getenv("DB_WAIT_RETRIES", "30"))
INTERVAL = float(os.getenv("DB_WAIT_INTERVAL", "2"))


def parse_mysql_url(url: str) -> dict:
    """解析 mysql+pymysql://user:pass@host:port/db?charset=utf8mb4"""
    u = urlparse(url)
    return {
        "host": u.hostname or "localhost",
        "port": u.port or 3306,
        "user": unquote(u.username) if u.username else "root",
        "password": unquote(u.password) if u.password else "",
        "database": (u.path or "/").lstrip("/").split("?")[0],
    }


def main() -> int:
    cfg = parse_mysql_url(settings.database_url)
    # database 可能还没建，先连到实例本身
    cfg.pop("database", None)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            conn = pymysql.connect(connect_timeout=3, **cfg)
            conn.close()
            print(f"[wait_for_db] MySQL 就绪（第 {attempt} 次尝试）")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(
                f"[wait_for_db] 未就绪 {attempt}/{MAX_RETRIES}：{exc}"
                f"，{INTERVAL}s 后重试"
            )
            if attempt == MAX_RETRIES:
                print("[wait_for_db] 放弃等待", file=sys.stderr)
                return 1
            time.sleep(INTERVAL)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
