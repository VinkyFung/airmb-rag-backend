from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "爱藏知识库管理后台 API"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    db_host: str = "110.42.237.108"
    db_port: int = 3306
    db_name: str = "airmbrag"
    db_user: str = ""
    db_password: str = ""
    db_charset: str = "utf8mb4"
    db_echo: bool = False
    db_connect_timeout: int = 8
    db_pool_timeout: int = 10

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cors_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    redis_url: str = "redis://127.0.0.1:6379/0"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def sqlalchemy_database_uri(self) -> URL:
        return URL.create(
            drivername="mysql+aiomysql",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"charset": self.db_charset},
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
