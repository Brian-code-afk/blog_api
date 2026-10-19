# app/schemas/user.py
import re
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import ORMModel

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,50}$")


class UserBase(ORMModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        v = v.strip()
        if not _USERNAME_RE.match(v):
            raise ValueError("用户名只能包含字母、数字、下划线和连字符，长度 3-50")
        return v


class UserCreate(UserBase):
    """注册请求。password 只在请求体里出现，绝不进任何输出模型。"""

    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        # bcrypt 只取前 72 字节，超长会被静默截断；
        # 中文一个字 3 字节，所以按字节数而非字符数判断
        if len(v.encode("utf-8")) > 72:
            raise ValueError("密码过长（最多 72 字节）")
        if v.isdigit() or v.isalpha():
            raise ValueError("密码需同时包含字母和数字")
        return v


class UserUpdate(ORMModel):
    """资料更新，字段全部可选。"""

    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=3, max_length=50)


class PasswordUpdate(ORMModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=72)


class UserBrief(ORMModel):
    """嵌在文章里的作者摘要。

    刻意不含 articles 字段 —— 否则 ArticleOut.author 里再嵌文章、
    文章里再嵌作者，序列化时会无限递归。
    """

    id: int
    username: str


class UserOut(ORMModel):
    """用户输出。注意没有 hashed_password。"""

    id: int
    email: EmailStr
    username: str
    is_active: bool
    created_at: datetime
    updated_at: datetime