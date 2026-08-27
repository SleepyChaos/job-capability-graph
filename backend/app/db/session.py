from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _prepare_sqlite_directory(database_url: str) -> None:
    prefix = "sqlite+pysqlite:///"
    if not database_url.startswith(prefix):
        return
    database_path = database_url.removeprefix(prefix)
    if database_path == ":memory:":
        return
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)


settings = get_settings()
_prepare_sqlite_directory(settings.database_url)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
