# app/core/exception_handlers.py
"""全局异常处理器（原 middleware.py，改名以正名）。

只负责「异常 → 统一 JSON 响应」的映射。
CORS、request-id 这类真正的中间件请放在 app/core/middleware.py 或直接在 main.py 注册。
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import BusinessException
from app.core.responses import APIResponse
from typing import Any
logger = logging.getLogger(__name__)


def _json(content: APIResponse, status_code: int) -> JSONResponse:
    """统一出口：401 自动补 WWW-Authenticate 头，便于前端识别需重新认证"""
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
    return JSONResponse(
        status_code=status_code,
        content=content.to_dict(),
        headers=headers,
    )


def _safe(obj: Any) -> Any:
    """把不可序列化的对象（UploadFile、异常实例等）转成可 JSON 化的值"""
    try:
        return jsonable_encoder(obj)
    except Exception:
        return str(obj)


# ────────────────────────── 1. 业务异常 ──────────────────────────


async def business_exception_handler(
    _request: Request, exc: BusinessException
) -> JSONResponse:
    logger.warning("BusinessException code=%s: %s", exc.code, exc.message)
    return _json(
        APIResponse(code=exc.code, message=exc.message, data=exc.data),
        exc.status_code,
    )


# ────────────────────────── 2. 参数校验失败 ──────────────────────────


async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors: list[dict] = []
    for err in exc.errors():
        cleaned: dict = {
            "type": err.get("type"),
            "loc": err.get("loc"),
            "msg": err.get("msg"),
        }
        # input / ctx 里可能有 UploadFile 或异常实例，直接塞进 JSONResponse 会 500，
        # 反而把真正的 422 掩盖掉
        if "input" in err:
            cleaned["input"] = _safe(err["input"])
        if err.get("ctx"):
            cleaned["ctx"] = _safe(err["ctx"])
        errors.append(cleaned)

    if errors:
        first = errors[0]
        field = ".".join(
            str(loc) for loc in first.get("loc", []) if loc != "body"
        )
        message = f"{field}: {first.get('msg', '参数校验失败')}" if field \
            else str(first.get("msg", "参数校验失败"))
    else:
        message = "请求参数校验失败"

    return _json(
        APIResponse(code=422, message=message, data=errors),
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


# ────────────────────────── 3. HTTP 异常 ──────────────────────────


async def http_exception_handler(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return _json(
        APIResponse(code=exc.status_code, message=str(exc.detail)),
        exc.status_code,
    )


# ────────────────────────── 4. 数据库异常 ──────────────────────────


def _conflict_message(exc: IntegrityError) -> str:
    """把 MySQL 的完整性错误翻译成人话"""
    text = str(getattr(exc, "orig", None) or exc)
    if "Duplicate entry" in text:
        return "数据已存在，请勿重复提交"
    if "foreign key constraint fails" in text.lower():
        return "关联数据不存在，或该数据仍被引用"
    if "cannot be null" in text.lower():
        return "必填字段不能为空"
    return "数据冲突，请检查输入"


async def sqlalchemy_exception_handler(
    _request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    # 真实异常必须记日志，否则线上只能看到"数据库操作失败"却查不到原因
    logger.exception("SQLAlchemyError: %s", exc)

    if isinstance(exc, IntegrityError):
        return _json(
            APIResponse(code=409, message=_conflict_message(exc)),
            status.HTTP_409_CONFLICT,
        )

    return _json(
        APIResponse(code=5001, message="数据库操作失败"),
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


# ────────────────────────── 5. 兜底 ──────────────────────────


async def global_exception_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    logger.exception("Unhandled exception: %s", exc)
    return _json(
        APIResponse(code=500, message="服务器内部错误"),
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


# ────────────────────────── 注册入口 ──────────────────────────


def register_exception_handlers(app: FastAPI) -> None:
    """统一的异常处理器注册入口"""
    # type: ignore 是让类型检查器忽略异步处理器的签名推断，不影响运行
    app.add_exception_handler(BusinessException, business_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, global_exception_handler)  # type: ignore[arg-type]