from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import aiomysql
import orjson

from .config import Settings


class JsonCache:
    def __init__(self, pool: aiomysql.Pool, settings: Settings):
        self.pool = pool
        self.table = settings.mysql_table

    async def setup(self) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS `{self.table}` (
                        cache_key VARCHAR(191) NOT NULL PRIMARY KEY,
                        value_json LONGTEXT NOT NULL,
                        expires_at DATETIME(6) NULL,
                        updated_at DATETIME(6) NOT NULL
                            DEFAULT CURRENT_TIMESTAMP(6)
                            ON UPDATE CURRENT_TIMESTAMP(6),
                        KEY idx_expires_at (expires_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
            await conn.commit()

    async def get(self, key: str) -> Any | None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    SELECT value_json
                    FROM `{self.table}`
                    WHERE cache_key = %s
                      AND (expires_at IS NULL OR expires_at > UTC_TIMESTAMP(6))
                    """,
                    (key,),
                )
                row = await cur.fetchone()
        if not row:
            return None
        return orjson.loads(row[0])

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        data = orjson.dumps(value, option=orjson.OPT_NAIVE_UTC).decode("utf-8")
        expires_at = None
        if ttl:
            expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=ttl)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    INSERT INTO `{self.table}` (cache_key, value_json, expires_at)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        value_json = VALUES(value_json),
                        expires_at = VALUES(expires_at)
                    """,
                    (key, data, expires_at),
                )
            await conn.commit()

    async def delete(self, key: str) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"DELETE FROM `{self.table}` WHERE cache_key = %s", (key,))
            await conn.commit()

    async def ping(self) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                row = await cur.fetchone()
        return bool(row and row[0] == 1)

    async def info_memory(self) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"DELETE FROM `{self.table}` WHERE expires_at IS NOT NULL AND expires_at <= UTC_TIMESTAMP(6)")
                deleted = cur.rowcount
                await cur.execute(f"SELECT COUNT(*), COALESCE(SUM(CHAR_LENGTH(value_json)), 0) FROM `{self.table}`")
                count, bytes_used = await cur.fetchone()
            await conn.commit()
        return {
            "backend": "mysql",
            "table": self.table,
            "rows": count,
            "valueBytes": int(bytes_used or 0),
            "expiredRowsDeleted": deleted,
        }


def json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return json.loads(orjson.dumps(value, option=orjson.OPT_NAIVE_UTC))
