# app/services/user_service.py
"""用户领域逻辑：查询、注册、更新、改密、启停用。"""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    EmailExistsException,
    PasswordErrorException,
    UserDisabledException,
    UserNotFoundException,
    UsernameExistsException,
)
from app.core.security import hash_password, verify_password
from app.core.token import revoke_all_for_user
from app.models import User
from app.schemas.user import PasswordUpdate, UserCreate, UserUpdate


# ------------------ 查询 ------------------

def get_by_id(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise UserNotFoundException()
    return user


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def get_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def get_by_account(db: Session, account: str) -> User | None:
    """登录用：account 可以是用户名或邮箱。"""
    account = account.strip()
    return db.scalar(
        select(User).where(
            or_(User.username == account, User.email == account.lower())
        )
    )


# ------------------ 写入 ------------------

def create_user(db: Session, payload: UserCreate) -> User:
    """注册。用户名/邮箱冲突由这里显式判重，
    数据库唯一约束作为并发下的最后一道防线（会被转成 409）。"""
    if get_by_username(db, payload.username) is not None:
        raise UsernameExistsException()
    if get_by_email(db, payload.email) is not None:
        raise EmailExistsException()

    user = User(
        email=payload.email.lower(),
        username=payload.username,
        hashed_password=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    db.commit()      # 需要拿到自增 id
    db.refresh(user)
    return user


def update_user(db: Session, user: User, payload: UserUpdate) -> User:
    if payload.username is not None and payload.username != user.username:
        if get_by_username(db, payload.username) is not None:
            raise UsernameExistsException()
        user.username = payload.username

    if payload.email is not None and payload.email != user.email:
        if get_by_email(db, payload.email) is not None:
            raise EmailExistsException()
        user.email = payload.email.lower()

    db.commit()
    db.refresh(user)
    return user


def update_password(db: Session, user: User, payload: PasswordUpdate) -> None:
    """改密：校验旧密码 → 写新密码 → 吊销全部 refresh token（所有设备下线）。"""
    if not verify_password(payload.old_password, user.hashed_password):
        raise PasswordErrorException("原密码错误")

    user.hashed_password = hash_password(payload.new_password)
    db.commit()

    # 改密后强制所有设备重新登录
    revoke_all_for_user(user.id)


def set_active(db: Session, user: User, is_active: bool) -> User:
    """封号/解封。封号时立即吊销全部 token，实现「即时踢下线」。"""
    user.is_active = is_active
    db.commit()
    db.refresh(user)

    if not is_active:
        revoke_all_for_user(user.id)
    return user


# ------------------ 登录校验 ------------------

def authenticate(db: Session, account: str, password: str) -> User:
    """校验账号密码。用户不存在与密码错误返回同一提示，避免账号枚举。"""
    user = get_by_account(db, account)
    if user is None or not verify_password(password, user.hashed_password):
        raise PasswordErrorException()

    if not user.is_active:
        raise UserDisabledException()
    return user