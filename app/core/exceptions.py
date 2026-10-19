# app/core/exceptions.py
"""业务异常定义。

约定：
- 业务 code 默认与 HTTP 状态码一致，前端可直接用 code 做分支，不必再解析 HTTP 状态
- 路由里不需要 try/except，全部交给 exception_handlers.py 统一捕获
"""
from typing import Any

from fastapi import status


class BusinessException(Exception):
    """业务异常基类"""

    def __init__(
        self,
        message: str = "业务处理失败",
        code: int = 500,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        data: Any = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.data = data
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


# ────────────────────────── 客户端错误 4xx ──────────────────────────


class BadRequestException(BusinessException):
    """请求参数错误"""

    def __init__(self, message: str = "请求参数错误", data: Any = None):
        super().__init__(message, code=400,
                         status_code=status.HTTP_400_BAD_REQUEST, data=data)


class UnauthorizedException(BusinessException):
    """未认证 / 登录失效"""

    def __init__(self, message: str = "未登录或登录已过期", data: Any = None):
        super().__init__(message, code=401,
                         status_code=status.HTTP_401_UNAUTHORIZED, data=data)


class ForbiddenException(BusinessException):
    """无权限访问"""

    def __init__(self, message: str = "无权访问该资源", data: Any = None):
        super().__init__(message, code=403,
                         status_code=status.HTTP_403_FORBIDDEN, data=data)


class NotFoundException(BusinessException):
    """资源不存在"""

    def __init__(self, message: str = "请求的资源不存在", data: Any = None):
        super().__init__(message, code=404,
                         status_code=status.HTTP_404_NOT_FOUND, data=data)


class ConflictException(BusinessException):
    """资源冲突，如重复创建"""

    def __init__(self, message: str = "资源已存在", data: Any = None):
        super().__init__(message, code=409,
                         status_code=status.HTTP_409_CONFLICT, data=data)


# ────────────────────────── 服务端错误 5xx ──────────────────────────


class InternalErrorException(BusinessException):
    """内部服务错误"""

    def __init__(self, message: str = "服务器内部错误", data: Any = None):
        super().__init__(message, code=500,
                         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                         data=data)


class DatabaseException(BusinessException):
    """数据库操作异常（业务 code 用 5001，与 HTTP 500 区分）"""

    def __init__(self, message: str = "数据库操作失败", data: Any = None):
        super().__init__(message, code=5001,
                         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                         data=data)


# ────────────────────────── 认证授权 ──────────────────────────


class TokenExpiredException(UnauthorizedException):
    """access token 已过期，前端应静默刷新"""

    def __init__(self, message: str = "登录已过期"):
        super().__init__(message)


class TokenInvalidException(UnauthorizedException):
    """token 无效（签名错误 / 类型不符 / 已被吊销），前端应跳登录页"""

    def __init__(self, message: str = "登录凭证无效"):
        super().__init__(message)


class PasswordErrorException(UnauthorizedException):
    """账号或密码错误。

    登录失败语义上是 401 而非 400 —— 400 会让前端误判为参数问题而不跳登录
    """

    def __init__(self, message: str = "账号或密码错误"):
        super().__init__(message)


class UserDisabledException(ForbiddenException):
    """账号被禁用"""

    def __init__(self, message: str = "账号已被禁用"):
        super().__init__(message)


class NotOwnerException(ForbiddenException):
    """资源不属于当前用户（如修改他人文章）"""

    def __init__(self, message: str = "只能操作自己的资源"):
        super().__init__(message)


# ────────────────────────── 资源相关 ──────────────────────────


class UserNotFoundException(NotFoundException):
    def __init__(self, message: str = "用户不存在"):
        super().__init__(message)


class UsernameExistsException(ConflictException):
    def __init__(self, message: str = "该用户名已被注册"):
        super().__init__(message)


class EmailExistsException(ConflictException):
    def __init__(self, message: str = "该邮箱已被注册"):
        super().__init__(message)


class ArticleNotFoundException(NotFoundException):
    def __init__(self, message: str = "文章不存在"):
        super().__init__(message)


class SlugExistsException(ConflictException):
    def __init__(self, message: str = "该 URL 别名已被占用"):
        super().__init__(message)


class TagNotFoundException(NotFoundException):
    def __init__(self, message: str = "标签不存在"):
        super().__init__(message)


class TagExistsException(ConflictException):
    def __init__(self, message: str = "该标签已存在"):
        super().__init__(message)