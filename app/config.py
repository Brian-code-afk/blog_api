from pydantic_settings import BaseSettings,SettingsConfigDict
from pathlib import Path
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="forbid"
    )
    # 字段名小写，自动匹配大写环境变量（大小写不敏感）
    app_name: str = "Blog API"
    env: str = "dev"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    database_url: str = "mysql+pymysql://blog:blogpass@localhost:3306/blog?charset=utf8mb4"
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_pre_ping: bool = True

    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = ""  # 空值启动时校验，防止忘记配置
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    refresh_token_grace_seconds: int = 60
    refresh_token_rotate: bool = True

    cors_origins: list[str] = ["*"]
    default_page_size: int = 20
    max_page_size: int = 100

    @property
    def debug(self) -> bool:
        return self.env != "prod"

#创建实例
settings = Settings()
