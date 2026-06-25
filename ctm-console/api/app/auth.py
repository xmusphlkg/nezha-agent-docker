from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import aiomysql
from fastapi import HTTPException, Request, Response, status

from .config import Settings
from .models import CurrentUser


SESSION_COOKIE = "ctm_session"
PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000


def utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "$".join(
        [
            PASSWORD_ALGORITHM,
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = password_hash.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = base64.urlsafe_b64decode(salt_raw.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_raw.encode("ascii"))
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


class AuthService:
    def __init__(self, pool: aiomysql.Pool, settings: Settings):
        self.pool = pool
        self.settings = settings

    async def setup(self) -> None:
        await self._create_tables()
        await self.bootstrap_admin()

    async def _create_tables(self) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ctm_nav_users (
                        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        username VARCHAR(80) NOT NULL UNIQUE,
                        display_name VARCHAR(120) NULL,
                        role VARCHAR(32) NOT NULL DEFAULT 'admin',
                        password_hash VARCHAR(512) NOT NULL,
                        active TINYINT(1) NOT NULL DEFAULT 1,
                        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                        updated_at DATETIME(6) NOT NULL
                            DEFAULT CURRENT_TIMESTAMP(6)
                            ON UPDATE CURRENT_TIMESTAMP(6),
                        last_login_at DATETIME(6) NULL,
                        KEY idx_active (active)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ctm_nav_sessions (
                        id CHAR(64) NOT NULL PRIMARY KEY,
                        user_id BIGINT UNSIGNED NOT NULL,
                        expires_at DATETIME(6) NOT NULL,
                        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                        last_seen_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                        ip_address VARCHAR(64) NULL,
                        user_agent VARCHAR(255) NULL,
                        KEY idx_user_id (user_id),
                        KEY idx_expires_at (expires_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
            await conn.commit()

    async def bootstrap_admin(self) -> None:
        if not self.settings.ctm_session_secret:
            raise RuntimeError("CTM_SESSION_SECRET is required for session cookies")
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM ctm_nav_users")
                count_row = await cur.fetchone()
                user_count = int(count_row[0] or 0)
                if user_count:
                    return
                if not self.settings.ctm_admin_password:
                    raise RuntimeError("CTM_ADMIN_PASSWORD is required to create the first admin user")
                await cur.execute(
                    """
                    INSERT INTO ctm_nav_users
                        (username, display_name, role, password_hash, active)
                    VALUES (%s, %s, 'admin', %s, 1)
                    """,
                    (
                        self.settings.ctm_admin_username,
                        self.settings.ctm_admin_username,
                        hash_password(self.settings.ctm_admin_password),
                    ),
                )
            await conn.commit()

    def _require_secret(self) -> bytes:
        if not self.settings.ctm_session_secret:
            raise RuntimeError("CTM_SESSION_SECRET is required for session cookies")
        return self.settings.ctm_session_secret.encode("utf-8")

    def _sign(self, token: str) -> str:
        return hmac.new(self._require_secret(), token.encode("utf-8"), hashlib.sha256).hexdigest()

    def _session_hash(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _cookie_value(self, token: str) -> str:
        return f"{token}.{self._sign(token)}"

    def _token_from_cookie(self, value: str | None) -> str | None:
        if not value or "." not in value:
            return None
        token, signature = value.rsplit(".", 1)
        if not token or not signature:
            return None
        if not hmac.compare_digest(signature, self._sign(token)):
            return None
        return token

    async def login(
        self,
        username: str,
        password: str,
        *,
        response: Response,
        request: Request,
    ) -> CurrentUser:
        row = await self._user_row(username=username)
        if not row or not row["active"] or not verify_password(password, row["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

        token = secrets.token_urlsafe(32)
        session_id = self._session_hash(token)
        ttl = max(1, self.settings.ctm_session_ttl_hours)
        expires_at = utc_naive() + timedelta(hours=ttl)
        user_agent = request.headers.get("user-agent", "")[:255] or None
        client_ip = request.client.host if request.client else None
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO ctm_nav_sessions
                        (id, user_id, expires_at, ip_address, user_agent)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (session_id, row["id"], expires_at, client_ip, user_agent),
                )
                await cur.execute(
                    "UPDATE ctm_nav_users SET last_login_at = UTC_TIMESTAMP(6) WHERE id = %s",
                    (row["id"],),
                )
            await conn.commit()

        response.set_cookie(
            SESSION_COOKIE,
            self._cookie_value(token),
            max_age=ttl * 3600,
            httponly=True,
            secure=self.settings.public_base_url.startswith("https://"),
            samesite="lax",
            path="/",
        )
        return current_user_from_row(row)

    async def logout(self, request: Request, response: Response) -> dict[str, bool]:
        token = self._token_from_cookie(request.cookies.get(SESSION_COOKIE))
        if token:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "DELETE FROM ctm_nav_sessions WHERE id = %s",
                        (self._session_hash(token),),
                    )
                await conn.commit()
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"ok": True}

    async def user_from_request(self, request: Request) -> CurrentUser | None:
        token = self._token_from_cookie(request.cookies.get(SESSION_COOKIE))
        if not token:
            return None
        session_id = self._session_hash(token)
        async with self.pool.acquire() as conn:
            await conn.commit()
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT
                        u.id,
                        u.username,
                        u.display_name,
                        u.role,
                        u.active,
                        u.password_hash
                    FROM ctm_nav_sessions s
                    JOIN ctm_nav_users u ON u.id = s.user_id
                    WHERE s.id = %s
                      AND s.expires_at > UTC_TIMESTAMP(6)
                      AND u.active = 1
                    """,
                    (session_id,),
                )
                row = await cur.fetchone()
                if row:
                    await cur.execute(
                        "UPDATE ctm_nav_sessions SET last_seen_at = UTC_TIMESTAMP(6) WHERE id = %s",
                        (session_id,),
                    )
            await conn.commit()
        if not row:
            return None
        return current_user_from_row(row)

    async def list_users(self) -> list[CurrentUser]:
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT id, username, display_name, role, active
                    FROM ctm_nav_users
                    ORDER BY username
                    """
                )
                rows = await cur.fetchall()
        return [current_user_from_row(row) for row in rows]

    async def create_user(
        self,
        *,
        username: str,
        password: str,
        display_name: str | None,
        role: str,
        active: bool,
    ) -> CurrentUser:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO ctm_nav_users
                        (username, display_name, role, password_hash, active)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (username, display_name, role, hash_password(password), 1 if active else 0),
                )
                user_id = cur.lastrowid
            await conn.commit()
        row = await self._user_row(user_id=user_id)
        if not row:
            raise HTTPException(status_code=500, detail="用户创建后无法读取")
        return current_user_from_row(row)

    async def update_user(
        self,
        user_id: int,
        values: dict[str, Any],
    ) -> CurrentUser:
        updates: list[str] = []
        params: list[Any] = []
        if "displayName" in values:
            updates.append("display_name = %s")
            params.append(values["displayName"])
        if "role" in values:
            updates.append("role = %s")
            params.append(values["role"])
        if "active" in values:
            updates.append("active = %s")
            params.append(1 if values["active"] else 0)
        if "password" in values:
            updates.append("password_hash = %s")
            params.append(hash_password(values["password"]))
        if updates:
            params.append(user_id)
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"UPDATE ctm_nav_users SET {', '.join(updates)} WHERE id = %s",
                        tuple(params),
                    )
                    if cur.rowcount == 0:
                        raise HTTPException(status_code=404, detail="用户不存在")
                await conn.commit()
        row = await self._user_row(user_id=user_id)
        if not row:
            raise HTTPException(status_code=404, detail="用户不存在")
        return current_user_from_row(row)

    async def _user_row(
        self,
        *,
        username: str | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any] | None:
        if username is None and user_id is None:
            raise ValueError("username or user_id is required")
        where = "username = %s" if username is not None else "id = %s"
        value = username if username is not None else user_id
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    f"""
                    SELECT id, username, display_name, role, active, password_hash
                    FROM ctm_nav_users
                    WHERE {where}
                    """,
                    (value,),
                )
                return await cur.fetchone()


def current_user_from_row(row: dict[str, Any]) -> CurrentUser:
    return CurrentUser(
        id=int(row["id"]),
        username=str(row["username"]),
        displayName=row.get("display_name"),
        role=row.get("role") or "admin",
        active=bool(row.get("active")),
    )


async def current_user(request: Request) -> CurrentUser:
    user = getattr(request.state, "current_user", None)
    if user:
        return user
    from .main import app_state

    user = await app_state.auth.user_from_request(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    request.state.current_user = user
    return user


async def require_admin(request: Request) -> CurrentUser:
    user = await current_user(request)
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user
