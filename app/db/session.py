#app/db/sessions.py
"""
    创建数据库连接与会话工程
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings
#实例化引擎
engine = create_engine(settings.database_url,pool_pre_ping=True,pool_recycle=3600)

#创建数据库会话对象
SessionLocal = sessionmaker(autoflush=False,autocommit=False,bind=engine)