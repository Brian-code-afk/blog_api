#!/bin/sh
# ============================================================
# 容器启动入口
#   1. 等待 MySQL 就绪（容器编排时应用几乎总比数据库先起来）
#   2. 执行 Alembic 迁移
#   3. exec 启动真正的命令（CMD 传进来的 uvicorn 或 worker）
#
# ⚠️ 本文件必须是 LF 换行。CRLF 会报
#    "/bin/sh^M: bad interpreter: No such file or directory"
# ============================================================
set -e

echo "[entrypoint] 等待 MySQL 就绪 ..."
python /app/scripts/wait_for_db.py

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "[entrypoint] 执行数据库迁移 ..."
    alembic upgrade head
else
    echo "[entrypoint] 跳过数据库迁移（由其他服务负责）"
fi

echo "[entrypoint] 启动: $@"
exec "$@"
