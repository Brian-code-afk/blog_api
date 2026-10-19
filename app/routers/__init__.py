# app/routers/__init__.py
"""路由聚合。

main.py 里只需 `from app.routers import register_routers` 一行。
"""
from fastapi import FastAPI

from app.routers import article, auth, tag, user


def register_routers(app: FastAPI, prefix: str = "/api") -> None:
    app.include_router(auth.router, prefix=prefix)
    app.include_router(user.router, prefix=prefix)
    app.include_router(article.router, prefix=prefix)
    app.include_router(tag.router, prefix=prefix)


__all__ = ["register_routers", "article", "auth", "tag", "user"]