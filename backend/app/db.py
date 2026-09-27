from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import DateTime, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """SQLite drops timezone info; always hand back aware UTC datetimes so comparisons never mix naive and aware."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            raise ValueError('Naive datetime passed to the database; use timezone-aware UTC.')
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class Base(DeclarativeBase):
    type_annotation_map = {datetime: UTCDateTime()}


def make_engine(url: str) -> Engine:
    if url.startswith('sqlite'):
        kwargs = {'connect_args': {'check_same_thread': False}}
        if url in ('sqlite://', 'sqlite:///:memory:'):
            kwargs['poolclass'] = StaticPool  # one shared in-memory database across threads (tests)
        return create_engine(url, **kwargs)
    return create_engine(url, pool_pre_ping=True)


class Database:
    def __init__(self, url: str):
        self.engine = make_engine(url)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        from app import models  # noqa: F401  registers tables

        Base.metadata.create_all(self.engine)

    def session(self) -> Iterator[Session]:
        with self.sessions() as s:
            yield s
