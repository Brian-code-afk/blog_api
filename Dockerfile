# ============================================================
# 多阶段构建：builder 装依赖，runtime 只拷贝结果
# 目的：不把 gcc / 编译工具链 / pip 缓存留在最终镜像里
# ============================================================

# ---------- Stage 1: builder ----------
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# 只拷贝依赖清单：改业务代码不会让这一层失效，最大化利用构建缓存
COPY requirements.txt .

# 依赖装进独立 venv，runtime 阶段直接整体拷走
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# gcc 只为可能的源码编译（如部分版本的 SQLAlchemy / bcrypt）准备，
# 装完立刻卸载，不会进入最终镜像
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        pkg-config \
        default-libmysqlclient-dev \
    && pip install --upgrade pip \
    && pip install -r requirements.txt \
    && apt-get purge -y gcc pkg-config default-libmysqlclient-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*


# ---------- Stage 2: runtime ----------
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    # 让 scripts/ 下的脚本能 import app.*
    PYTHONPATH=/app

WORKDIR /app

# 只拷 venv，不带编译工具链
COPY --from=builder /opt/venv /opt/venv

# 拷贝应用代码（.dockerignore 已排除 .venv / tests / .env 等）
COPY . .

# 非 root 运行：容器被攻破时降低破坏范围
RUN useradd -m -u 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 注意：CMD 用数组形式，entrypoint 里的 exec "$@" 才能正确接管
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# 启动流程交给 entrypoint：等数据库 → 跑迁移 → 启动应用
ENTRYPOINT ["/app/docker-entrypoint.sh"]
