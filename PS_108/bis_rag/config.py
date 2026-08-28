"""
bis_rag.config
==============
Environment-variable based configuration. Reads from .env if present.

Environment variables:
    POSTGRES_HOST      (default: localhost)
    POSTGRES_PORT      (default: 5432)
    POSTGRES_DB        (default: bis_rag)
    POSTGRES_USER      (default: bis_rag_user)
    POSTGRES_PASSWORD  (required in production)
    APP_ENV            (default: development)

Usage:
    from bis_rag.config import settings
    print(settings.db.dsn)
"""

from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=False)
except ImportError:
    pass


@dataclass(frozen=True)
class DBConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str

    @property
    def dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} "
            f"dbname={self.dbname} user={self.user} password={self.password}"
        )

    @property
    def url(self) -> str:
        pw = urllib.parse.quote(self.password, safe="")
        return f"postgresql://{self.user}:{pw}@{self.host}:{self.port}/{self.dbname}"


@dataclass(frozen=True)
class Settings:
    db: DBConfig
    app_env: str

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def _load_settings() -> Settings:
    db = DBConfig(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "bis_rag"),
        user=os.environ.get("POSTGRES_USER", "bis_rag_user"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
    )
    app_env = os.environ.get("APP_ENV", "development").lower()
    if app_env == "production" and not db.password:
        raise ValueError("POSTGRES_PASSWORD must be set in production.")
    return Settings(db=db, app_env=app_env)


settings: Settings = _load_settings()
