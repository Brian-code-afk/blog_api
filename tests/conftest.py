# tests/conftest.py
"""pytest 全局 fixture。

三个关键设计
------------
1. 环境变量必须在 `import app.*` 之前设置。config.Settings 用了 lru_cache，
   一旦被读取就固化，之后再改 os.environ 无效。
2. 数据库隔离采用「外层事务 + savepoint」：service 里的 db.commit()
   只提交 savepoint，用例结束整体 rollback，数据自动清空，无需手写清理逻辑。
3. Redis 使用独立 db 号（默认 15），每个用例前后 flushdb，
   既不会污染开发数据，用例之间也互不干扰。

⚠️ 测试库会被 drop_all + create_all，切勿指向开发/生产库。
"""
import os
import sys
from pathlib import Path

# 把项目根目录加入 sys.path。
# pytest 默认只把 tests/ 目录插入 sys.path（因为 tests 下没有 __init__.py），
# 不加这行就会 ModuleNotFoundError: No module named 'app'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TEST_DB_NAME = os.getenv("TEST_DB_NAME", "blog_test")

# ---- 必须在导入 app 之前设置 ----
os.environ.setdefault("ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")
os.environ.setdefault(
    "DATABASE_URL",
    f"mysql+pymysql://root:123456@localhost:3306/{TEST_DB_NAME}?charset=utf8mb4",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
# 固定参数，避免依赖开发者本地 .env 的值造成断言不稳定
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_GRACE_SECONDS", "60")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.redis import redis_client  # noqa: E402
from app.dependencies import get_db  # noqa: E402
from app.main import app as fastapi_app# noqa: E402

import app.models  # noqa: E402,F401  必须导入：保证所有表注册进 Base.metadata

USER_A = {"email": "alice@example.com", "username": "alice", "password": "alice12345"}
USER_B = {"email": "bob@example.com", "username": "bob", "password": "bob123456"}

ARTICLE_PAYLOAD = {
    "title": "Docker 多阶段构建",
    "summary": "镜像从 800MB 瘦到 20MB",
    "content": "这是正文内容。",
    "status": "published",
    "tag_names": ["Docker", "部署"],
}


def create_article(client, **overrides):
    """创建文章并返回响应 data，失败时打印响应体便于排查。"""
    payload = {**ARTICLE_PAYLOAD, **overrides}
    r = client.post("/api/articles", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["data"]


# ────────────────────────── 数据库 ──────────────────────────


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.exit(
            f"\n无法连接测试数据库：{settings.database_url}\n"
            f"请先执行：CREATE DATABASE {TEST_DB_NAME} "
            f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
            f"原始错误：{exc}",
            returncode=1,
        )

    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    """每个用例一个会话，包在外层事务里，结束即回滚。"""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ────────────────────────── Redis ──────────────────────────


@pytest.fixture(autouse=True)
def _clean_redis():
    try:
        redis_client.flushdb()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"Redis 不可用，测试需要 Redis（当前 {settings.redis_url}）：{exc}"
        )
    yield
    try:
        redis_client.flushdb()
    except Exception:  # noqa: BLE001,S110
        pass


# ────────────────────────── 客户端 ──────────────────────────


def _build_client(session):
    """把路由的 get_db 覆盖成测试会话。

    注意不使用 `with TestClient(app)`：那会触发 lifespan 里的
    wait_for_database，而它连的是真实库，不是测试库。
    """
    def _override_get_db():
        yield session

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    return TestClient(fastapi_app)


@pytest.fixture
def client(db):
    """匿名客户端"""
    return _build_client(db)


@pytest.fixture
def client_a(db):
    """Alice 的已登录客户端"""
    c = _build_client(db)
    r = c.post("/api/auth/register", json=USER_A)
    assert r.status_code == 201, r.text
    c.headers["Authorization"] = f"Bearer {r.json()['data']['access_token']}"
    return c


@pytest.fixture
def client_b(db):
    """Bob 的已登录客户端（用于验证越权）"""
    c = _build_client(db)
    r = c.post("/api/auth/register", json=USER_B)
    assert r.status_code == 201, r.text
    c.headers["Authorization"] = f"Bearer {r.json()['data']['access_token']}"
    return c


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    fastapi_app.dependency_overrides.clear()
