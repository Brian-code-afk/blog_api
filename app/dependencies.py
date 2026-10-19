# app/dependencies.py
"""路由依赖注入集合。

提供的依赖：
- get_db                 数据库会话
- get_page_params        分页参数
- get_current_user       从 access token 解析当前用户
- get_current_active_user 在上者基础上校验账号未被停用
- get_optional_user      令牌可缺失（列表页按权限返回不同内容时用）
- get_owned_article      按 slug 取文章并校验归属
"""
from typing import Annotated,TypeAlias

from fastapi import Depends, Query
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    NotOwnerException,
    TokenInvalidException,
    UnauthorizedException,
)
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models import Article, User
from app.schemas.common import PageParams

# tokenUrl 指向登录接口，Swagger 的 Authorize 按钮会用它
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login",
    auto_error=True,
)


# ────────────────────────── 数据库会话 ──────────────────────────

def get_db():
    """每次请求一个会话，请求结束后关闭。

    这里不做自动 commit —— 提交时机交给 service 层显式控制，
    避免在只读请求里产生无意义的事务。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ────────────────────────── 分页参数 ──────────────────────────

def get_page_params(
    page_num: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数，最多 100"),
) -> PageParams:
    """从 query 解析分页参数。

    注意：Query 的 le 写死为 100，如果要读 settings.max_page_size，
    需要改成函数内手工校验并抛 BadRequestException。
    """
    return PageParams(page_num=page_num, page_size=page_size)


# ────────────────────────── 当前用户 ──────────────────────────

def _load_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    # 令牌有效但用户已被删除（例如注销账号），同样按未认证处理
    if user is None:
        raise UnauthorizedException("用户不存在")
    return user


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """解析 Authorization: Bearer <access_token> 得到当前用户。

    失败一律 401（由全局处理器转成统一 JSON，并带 WWW-Authenticate 头）。
    """
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
    except (PyJWTError, TokenInvalidException):
        # decode_access_token 内部已区分过期/无效，这里再兜一层
        raise TokenInvalidException()
    except (TypeError, ValueError):
        # sub 缺失或不是数字
        raise TokenInvalidException()

    return _load_user(db, user_id)


def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """校验账号处于启用状态（封号后即时生效）。"""
    if not current_user.is_active:
        raise UnauthorizedException("账号已被禁用")
    return current_user


def get_optional_user(
    token: Annotated[str | None, Depends(
        OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
    )],
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    """令牌可缺失：带了就解析，没带返回 None。

    典型用途：文章列表页对游客只返回 published，
    对作者本人额外返回他自己的 draft。
    """
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
    except (PyJWTError, TokenInvalidException, TypeError, ValueError):
        return None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


# ────────────────────────── 资源归属 ──────────────────────────

def get_owned_article(
    slug: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Article:
    """按 slug 取文章并校验归属，非作者抛 403。

    只用于「修改/删除自己的文章」这类接口；
    公开详情页请用 article_service.get_by_slug。
    """
    article = (
        db.query(Article)
        .filter(Article.slug == slug, Article.author_id == current_user.id)
        .first()
    )
    if article is None:
        # 刻意不区分「不存在」和「不是你的」，
        # 避免通过响应码探测他人文章是否存在
        raise NotOwnerException("文章不存在或无权操作")
    return article


# ────────────────────────── 常用类型别名 ──────────────────────────

DbDep: TypeAlias = Annotated[Session, Depends(get_db)]
CurrentUserDep: TypeAlias = Annotated[User, Depends(get_current_active_user)]
OptionalUserDep: TypeAlias = Annotated[User | None, Depends(get_optional_user)]
PageParamsDep: TypeAlias = Annotated[PageParams, Depends(get_page_params)]
