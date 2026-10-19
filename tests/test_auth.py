# tests/test_auth.py
"""认证链路测试：注册 → 登录 → 刷新 → 登出 → 越权。"""
from conftest import USER_A


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["code"] == 0


# ────────────────────────── 注册 ──────────────────────────


def test_register_returns_token_pair(client):
    r = client.post("/api/auth/register", json=USER_A)
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 15 * 60


def test_register_duplicate_username(client):
    assert client.post("/api/auth/register", json=USER_A).status_code == 201
    r = client.post(
        "/api/auth/register",
        json={**USER_A, "email": "another@example.com"},
    )
    assert r.status_code == 409


def test_register_duplicate_email(client):
    assert client.post("/api/auth/register", json=USER_A).status_code == 201
    r = client.post(
        "/api/auth/register",
        json={**USER_A, "username": "alice2"},
    )
    assert r.status_code == 409


def test_register_weak_password_rejected(client):
    r = client.post("/api/auth/register", json={**USER_A, "password": "12345678"})
    assert r.status_code == 422


def test_register_invalid_email_rejected(client):
    r = client.post("/api/auth/register", json={**USER_A, "email": "not-an-email"})
    assert r.status_code == 422


# ────────────────────────── 登录 ──────────────────────────


def test_login_with_username(client):
    client.post("/api/auth/register", json=USER_A)
    r = client.post(
        "/api/auth/login",
        json={"account": USER_A["username"], "password": USER_A["password"]},
    )
    assert r.status_code == 200
    assert r.json()["data"]["access_token"]


def test_login_with_email(client):
    client.post("/api/auth/register", json=USER_A)
    r = client.post(
        "/api/auth/login",
        json={"account": USER_A["email"], "password": USER_A["password"]},
    )
    assert r.status_code == 200


def test_login_wrong_password(client):
    client.post("/api/auth/register", json=USER_A)
    r = client.post(
        "/api/auth/login",
        json={"account": USER_A["username"], "password": "totally-wrong"},
    )
    assert r.status_code == 401


def test_login_nonexistent_account(client):
    r = client.post(
        "/api/auth/login",
        json={"account": "ghost", "password": "whatever123"},
    )
    # 用户不存在与密码错误返回同一结果，避免账号枚举
    assert r.status_code == 401


# ────────────────────────── 当前用户 ──────────────────────────


def test_me_requires_auth(client):
    assert client.get("/api/users/me").status_code == 401


def test_me_rejects_garbage_token(client):
    client.headers["Authorization"] = "Bearer not.a.jwt"
    assert client.get("/api/users/me").status_code == 401


def test_me_returns_current_user(client_a):
    r = client_a.get("/api/users/me")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["username"] == USER_A["username"]
    # 输出模型绝不能带密码哈希
    assert "hashed_password" not in data
    assert "password" not in data


# ────────────────────────── 刷新与轮换 ──────────────────────────


def test_refresh_rotates_token(client):
    r = client.post("/api/auth/register", json=USER_A)
    old = r.json()["data"]["refresh_token"]

    r2 = client.post("/api/auth/refresh", json={"refresh_token": old})
    assert r2.status_code == 200
    new = r2.json()["data"]["refresh_token"]
    assert new != old


def test_refresh_old_token_usable_once_in_grace_period(client):
    """旧 token 在宽限期（60s）内仍可兑换一次，应对客户端没收到响应的重试。"""
    old = client.post("/api/auth/register", json=USER_A).json()["data"]["refresh_token"]
    client.post("/api/auth/refresh", json={"refresh_token": old})

    r = client.post("/api/auth/refresh", json={"refresh_token": old})
    assert r.status_code == 200

    # 宽限期内兑换过一次后再次使用即失效
    r2 = client.post("/api/auth/refresh", json={"refresh_token": old})
    assert r2.status_code == 401


def test_refresh_with_invalid_token(client):
    r = client.post("/api/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert r.status_code == 401


def test_refresh_rejects_access_token(client):
    """access token 不能当 refresh token 用（payload.type 校验）"""
    access = client.post("/api/auth/register", json=USER_A).json()["data"]["access_token"]
    r = client.post("/api/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 401


# ────────────────────────── 登出 ──────────────────────────


def test_logout_revokes_refresh(client):
    refresh = client.post("/api/auth/register", json=USER_A).json()["data"]["refresh_token"]
    assert client.post("/api/auth/logout", json={"refresh_token": refresh}).status_code == 200

    r = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401


def test_access_token_still_valid_after_logout(client):
    """已知限制：登出只吊销 refresh token，
    access token 在剩余寿命内（15 分钟）仍然有效 —— 无状态 JWT 的固有代价。
    若需登出即时失效，需要额外维护 jti 黑名单。"""
    register = client.post("/api/auth/register", json=USER_A).json()["data"]
    client.post("/api/auth/logout", json={"refresh_token": register["refresh_token"]})

    client.headers["Authorization"] = f"Bearer {register['access_token']}"
    assert client.get("/api/users/me").status_code == 200
