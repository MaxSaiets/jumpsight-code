"""Transactional session store. The schema is created by an explicit initialize()."""

from __future__ import annotations

from sqlalchemy import Column, Float, Integer, MetaData, String, Table, case, create_engine, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError


class AuthStoreUnavailable(RuntimeError):
    """An HTTP-safe reason for refusal, without URLs or DB secrets."""


class DatabaseAuthStore:
    def __init__(self, url: str):
        self.engine = create_engine(url, pool_pre_ping=True)
        if self.engine.dialect.name not in ("postgresql", "sqlite"):
            raise ValueError("auth store requires PostgreSQL or local SQLite")
        self.metadata = MetaData()
        self.credentials = Table(
            "auth_credentials",
            self.metadata,
            Column("key", String(80), primary_key=True),
            Column("uid", String(64), nullable=False),
            Column("expires", Float, nullable=False, index=True),
        )
        self.attempts = Table(
            "auth_attempts",
            self.metadata,
            Column("key", String(80), primary_key=True),
            Column("expires", Float, nullable=False, index=True),
            Column("count", Integer, nullable=False),
        )

    def initialize(self):
        """A separate rollout step; an HTTP request does not change the schema."""
        self.metadata.create_all(self.engine)

    def _insert(self, table):
        return (pg_insert if self.engine.dialect.name == "postgresql" else sqlite_insert)(table)

    def _execute(self, statement):
        try:
            with self.engine.begin() as con:
                result = con.execute(statement)
                return result.first() if result.returns_rows else None
        except SQLAlchemyError:
            raise AuthStoreUnavailable("authentication storage unavailable") from None

    def put(self, key, row):
        statement = self._insert(self.credentials).values(key=key, uid=row[0], expires=row[1])
        self._execute(
            statement.on_conflict_do_update(
                index_elements=[self.credentials.c.key],
                set_={"uid": statement.excluded.uid, "expires": statement.excluded.expires},
            )
        )

    def get(self, key):
        return self._execute(
            select(self.credentials.c.uid, self.credentials.c.expires).where(self.credentials.c.key == key)
        )

    def pop(self, key, default=None):
        row = self._execute(
            delete(self.credentials)
            .where(self.credentials.c.key == key)
            .returning(self.credentials.c.uid, self.credentials.c.expires)
        )
        return row if row is not None else default

    def attempt_statement(self, key, now, limit, window_s):
        table = self.attempts
        expired = table.c.expires <= now
        return (
            self._insert(table)
            .values(key=key, expires=now + window_s, count=1)
            .on_conflict_do_update(
                index_elements=[table.c.key],
                set_={
                    "expires": case((expired, now + window_s), else_=table.c.expires),
                    "count": case((expired, 1), else_=table.c.count + 1),
                },
                where=expired | (table.c.count < limit),
            )
            .returning(table.c.count)
        )

    def atomic_increment(self, key, now, limit, window_s):
        if limit < 1 or window_s <= 0:
            raise ValueError("invalid attempt limit")
        return self._execute(self.attempt_statement(key, now, limit, window_s)) is not None

    def purge_expired(self, now):
        """Periodic cleanup, outside the session-check path."""
        self._execute(delete(self.credentials).where(self.credentials.c.expires <= now))
        self._execute(delete(self.attempts).where(self.attempts.c.expires <= now))
