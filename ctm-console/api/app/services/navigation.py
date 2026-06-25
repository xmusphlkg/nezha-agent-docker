from __future__ import annotations

import asyncio
import html
import ipaddress
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import aiomysql
import httpx
import pymysql

from ..config import Settings
from ..models import (
    DiscoveryRun,
    NavCandidate,
    NavLink,
    NavLinkCreate,
    NavLinkPreview,
    NavLinkUpdate,
)
from .grafana_links import build_grafana_integration


WEB_PORTS = {80, 443, 3000, 3001, 5000, 5001, 5173, 5601, 8000, 8006, 8080, 8081, 8088, 8090, 8443, 8888, 9000, 9001, 9090, 9093, 9200, 9443}


class NavigationService:
    def __init__(self, pool: aiomysql.Pool, settings: Settings):
        self.pool = pool
        self.settings = settings
        self._scan_tasks: dict[int, asyncio.Task[None]] = {}

    async def setup(self) -> None:
        await self._create_tables()
        await self.seed_links()
        await self.seed_initial_candidates()

    async def _create_tables(self) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ctm_nav_links (
                        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        title VARCHAR(160) NOT NULL,
                        url VARCHAR(2048) NOT NULL,
                        category VARCHAR(80) NOT NULL DEFAULT '其他',
                        description VARCHAR(500) NULL,
                        icon VARCHAR(80) NULL,
                        tags_json LONGTEXT NOT NULL,
                        source VARCHAR(40) NOT NULL DEFAULT 'manual',
                        source_key VARCHAR(191) NULL,
                        favorite TINYINT(1) NOT NULL DEFAULT 0,
                        sort_order INT NOT NULL DEFAULT 0,
                        enabled TINYINT(1) NOT NULL DEFAULT 1,
                        status VARCHAR(20) NOT NULL DEFAULT 'unknown',
                        status_code INT NULL,
                        last_checked_at DATETIME(6) NULL,
                        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                        updated_at DATETIME(6) NOT NULL
                            DEFAULT CURRENT_TIMESTAMP(6)
                            ON UPDATE CURRENT_TIMESTAMP(6),
                        UNIQUE KEY uniq_url (url(768)),
                        UNIQUE KEY uniq_source_key (source_key),
                        KEY idx_category (category),
                        KEY idx_enabled_sort (enabled, sort_order)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ctm_nav_discovery_runs (
                        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        status VARCHAR(20) NOT NULL DEFAULT 'running',
                        cidrs_json LONGTEXT NOT NULL,
                        ports_json LONGTEXT NOT NULL,
                        found_count INT NOT NULL DEFAULT 0,
                        importable_count INT NOT NULL DEFAULT 0,
                        error_message VARCHAR(1000) NULL,
                        started_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                        finished_at DATETIME(6) NULL,
                        KEY idx_status (status)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ctm_nav_discovery_candidates (
                        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        run_id BIGINT UNSIGNED NULL,
                        title VARCHAR(160) NOT NULL,
                        url VARCHAR(2048) NOT NULL,
                        host VARCHAR(255) NOT NULL,
                        port INT NOT NULL,
                        scheme VARCHAR(10) NOT NULL,
                        status_code INT NULL,
                        server_header VARCHAR(255) NULL,
                        content_type VARCHAR(160) NULL,
                        category VARCHAR(80) NOT NULL DEFAULT '待分类',
                        suggestion_reason VARCHAR(500) NULL,
                        tags_json LONGTEXT NOT NULL,
                        source VARCHAR(40) NOT NULL DEFAULT 'scan',
                        dedupe_key VARCHAR(191) NOT NULL,
                        ignored TINYINT(1) NOT NULL DEFAULT 0,
                        imported_link_id BIGINT UNSIGNED NULL,
                        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                        updated_at DATETIME(6) NOT NULL
                            DEFAULT CURRENT_TIMESTAMP(6)
                            ON UPDATE CURRENT_TIMESTAMP(6),
                        UNIQUE KEY uniq_dedupe_key (dedupe_key),
                        KEY idx_run_id (run_id),
                        KEY idx_import_state (ignored, imported_link_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
            await conn.commit()

    async def seed_links(self) -> None:
        if await self._table_has_rows("ctm_nav_links"):
            return
        links = [
            NavLinkCreate(
                title="CTM 监控总览",
                url="/monitor",
                category="监控",
                description="CTM Console 主机、PVE、安全态势总览",
                icon="console",
                tags=["ctm", "monitor"],
                favorite=True,
                sortOrder=10,
            ),
            NavLinkCreate(
                title="Zabbix",
                url="http://192.168.3.222:8080/",
                category="监控",
                description="Zabbix 7.2 监控入口",
                icon="zabbix",
                tags=["zabbix"],
                favorite=True,
                sortOrder=30,
            ),
            NavLinkCreate(
                title="Prometheus",
                url="http://192.168.3.222:9090/",
                category="监控",
                description="Prometheus 指标查询与 targets",
                icon="prometheus",
                tags=["prometheus"],
                favorite=True,
                sortOrder=40,
            ),
            NavLinkCreate(
                title="NextChat",
                url="http://192.168.3.200:3000/",
                category="应用",
                description="内网 NextChat 服务",
                icon="chat",
                tags=["chat", "ai"],
                favorite=True,
                sortOrder=80,
            ),
        ]
        grafana = build_grafana_integration(self.settings)
        links.append(
            NavLinkCreate(
                title="Grafana",
                url=grafana.baseUrl,
                category="监控",
                description="Grafana 登录与仪表盘入口",
                icon="grafana",
                tags=["grafana"],
                favorite=True,
                sortOrder=20,
            )
        )
        for index, dashboard in enumerate(grafana.dashboards, start=1):
            links.append(
                NavLinkCreate(
                    title=dashboard.title,
                    url=dashboard.url,
                    category="Grafana",
                    description=dashboard.description,
                    icon="dashboard",
                    tags=["grafana", "dashboard"],
                    favorite=index <= 3,
                    sortOrder=100 + index,
                )
            )
        for link in links:
            source_key = f"seed:{link.url}"
            await self.upsert_seed_link(link, source="seed", source_key=source_key)

    async def seed_initial_candidates(self) -> None:
        if await self._table_has_rows("ctm_nav_discovery_candidates"):
            return
        for raw in initial_candidates():
            await self.upsert_candidate(raw)

    async def _table_has_rows(self, table: str) -> bool:
        if table not in {"ctm_nav_links", "ctm_nav_discovery_candidates"}:
            raise ValueError(f"Unsupported table for seed check: {table}")
        async with self.pool.acquire() as conn:
            await conn.commit()
            async with conn.cursor() as cur:
                await cur.execute(f"SELECT 1 FROM {table} LIMIT 1")
                row = await cur.fetchone()
        return row is not None

    async def list_links(self, include_disabled: bool = False) -> list[NavLink]:
        where = "" if include_disabled else "WHERE enabled = 1"
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    f"""
                    SELECT *
                    FROM ctm_nav_links
                    {where}
                    ORDER BY favorite DESC, sort_order ASC, title ASC
                    """
                )
                rows = await cur.fetchall()
        return [link_from_row(row) for row in rows]

    async def get_link(self, link_id: int) -> NavLink:
        row = await self._link_row(link_id)
        if not row:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="导航链接不存在")
        return link_from_row(row)

    async def create_link(self, payload: NavLinkCreate, *, source: str = "manual", source_key: str | None = None) -> NavLink:
        url = normalize_url(payload.url)
        existing = await self._link_by_url(url)
        if existing:
            return link_from_row(existing)
        sort_order = payload.sortOrder
        if sort_order is None:
            sort_order = await self._next_sort_order()
        icon = payload.icon or infer_icon(url, payload.title, payload.category, payload.tags)
        async with self.pool.acquire() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO ctm_nav_links
                            (title, url, category, description, icon, tags_json, source, source_key,
                             favorite, sort_order, enabled)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            payload.title,
                            url,
                            payload.category,
                            payload.description,
                            icon,
                            json_dumps(payload.tags),
                            source,
                            source_key,
                            1 if payload.favorite else 0,
                            sort_order,
                            1 if payload.enabled else 0,
                        ),
                    )
                await conn.commit()
            except pymysql.err.IntegrityError:
                await conn.rollback()
                existing = await self._link_by_url(url)
                if existing:
                    return link_from_row(existing)
                raise
        created = await self._link_by_url(url)
        if not created:
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail="导航链接创建后无法读取")
        return link_from_row(created)

    async def upsert_seed_link(self, payload: NavLinkCreate, *, source: str, source_key: str) -> None:
        icon = payload.icon or infer_icon(payload.url, payload.title, payload.category, payload.tags)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO ctm_nav_links
                        (title, url, category, description, icon, tags_json, source, source_key,
                         favorite, sort_order, enabled)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        title = VALUES(title),
                        category = VALUES(category),
                        description = VALUES(description),
                        icon = VALUES(icon),
                        tags_json = VALUES(tags_json),
                        source = VALUES(source),
                        favorite = VALUES(favorite),
                        sort_order = VALUES(sort_order),
                        enabled = VALUES(enabled)
                    """,
                    (
                        payload.title,
                        payload.url,
                        payload.category,
                        payload.description,
                        icon,
                        json_dumps(payload.tags),
                        source,
                        source_key,
                        1 if payload.favorite else 0,
                        payload.sortOrder or 0,
                        1 if payload.enabled else 0,
                    ),
                )
            await conn.commit()

    async def update_link(self, link_id: int, payload: NavLinkUpdate) -> NavLink:
        values = payload.model_dump(exclude_unset=True)
        if "url" in values and values["url"]:
            values["url"] = normalize_url(values["url"])
            existing = await self._link_by_url(values["url"])
            if existing and int(existing["id"]) != link_id:
                from fastapi import HTTPException

                raise HTTPException(status_code=409, detail="已有相同地址的正式入口")
        columns: list[str] = []
        params: list[Any] = []
        mapping = {
            "title": "title",
            "url": "url",
            "category": "category",
            "description": "description",
            "icon": "icon",
            "favorite": "favorite",
            "enabled": "enabled",
            "sortOrder": "sort_order",
            "status": "status",
        }
        for key, column in mapping.items():
            if key not in values:
                continue
            columns.append(f"{column} = %s")
            value = values[key]
            if key in {"favorite", "enabled"}:
                value = 1 if value else 0
            params.append(value)
        if "tags" in values:
            columns.append("tags_json = %s")
            params.append(json_dumps(values["tags"] or []))
        if columns:
            params.append(link_id)
            async with self.pool.acquire() as conn:
                try:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            f"UPDATE ctm_nav_links SET {', '.join(columns)} WHERE id = %s",
                            tuple(params),
                        )
                    await conn.commit()
                except pymysql.err.IntegrityError as exc:
                    await conn.rollback()
                    from fastapi import HTTPException

                    raise HTTPException(status_code=409, detail="已有相同地址的正式入口") from exc
        return await self.get_link(link_id)

    async def delete_link(self, link_id: int) -> dict[str, bool]:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM ctm_nav_links WHERE id = %s", (link_id,))
                if cur.rowcount == 0:
                    from fastapi import HTTPException

                    raise HTTPException(status_code=404, detail="导航链接不存在")
            await conn.commit()
        return {"ok": True}

    async def reorder_links(self, items: list[tuple[int, int]]) -> dict[str, bool]:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                for link_id, sort_order in items:
                    await cur.execute(
                        "UPDATE ctm_nav_links SET sort_order = %s WHERE id = %s",
                        (sort_order, link_id),
                    )
            await conn.commit()
        return {"ok": True}

    async def preview_link(self, url: str) -> NavLinkPreview:
        normalized = normalize_url(url)
        parsed = urlparse(normalized)
        if normalized.startswith("/"):
            title = internal_title(normalized)
            category = "监控" if normalized.startswith("/monitor") else "应用"
            tags = ["ctm", "console"]
            icon = infer_icon(normalized, title, category, tags)
            return NavLinkPreview(
                title=title,
                url=normalized,
                category=category,
                description="CTM Console 内部入口",
                icon=icon,
                tags=tags,
                status="unknown",
                reachable=True,
            )

        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail="URL 必须是内部路径或 HTTP/HTTPS 地址")

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                verify=False,
                timeout=httpx.Timeout(self.settings.nav_scan_timeout_sec),
                headers={"User-Agent": "ctm-nav-preview/1.0"},
            ) as client:
                response = await client.get(normalized)
        except Exception:
            title = title_from_url(normalized)
            category = infer_category(normalized, title)
            tags = infer_tags(normalized, title)
            return NavLinkPreview(
                title=title,
                url=normalized,
                category=category,
                description="未能读取页面，可先保存后续探测",
                icon=infer_icon(normalized, title, category, tags),
                tags=tags,
                status="down",
                reachable=False,
            )

        content_type = response.headers.get("content-type", "")
        title = extract_title(response.text) if "text/html" in content_type.lower() else ""
        title = title or title_from_url(normalized)
        server_header = response.headers.get("server")
        category = infer_category(normalized, title)
        tags = infer_tags(normalized, title, server_header or "")
        icon = infer_icon(normalized, title, category, tags, server_header or "")
        status = "ok" if response.status_code < 400 else "warning"
        return NavLinkPreview(
            title=title,
            url=normalized,
            category=category,
            description=f"自动识别：HTTP {response.status_code}",
            icon=icon,
            tags=tags,
            status=status,
            statusCode=response.status_code,
            serverHeader=server_header,
            contentType=content_type[:160],
            reachable=True,
        )

    async def start_scan(self, cidrs: list[str] | None = None, ports: list[int] | None = None) -> DiscoveryRun:
        cidrs = cidrs or self.settings.nav_scan_cidr_list()
        ports = sorted(set(ports or self.settings.nav_scan_port_list()))
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO ctm_nav_discovery_runs (status, cidrs_json, ports_json)
                    VALUES ('running', %s, %s)
                    """,
                    (json_dumps(cidrs), json_dumps(ports)),
                )
                run_id = int(cur.lastrowid)
            await conn.commit()
        task = asyncio.create_task(self._run_scan(run_id, cidrs, ports))
        self._scan_tasks[run_id] = task
        task.add_done_callback(lambda _: self._scan_tasks.pop(run_id, None))
        return await self.get_run(run_id)

    async def _run_scan(self, run_id: int, cidrs: list[str], ports: list[int]) -> None:
        try:
            candidates = await scan_network(
                cidrs,
                ports,
                connect_timeout=self.settings.nav_scan_connect_timeout_sec,
                request_timeout=self.settings.nav_scan_timeout_sec,
                concurrency=self.settings.nav_scan_concurrency,
            )
            importable = 0
            for candidate in candidates:
                candidate["runId"] = run_id
                if await self.upsert_candidate(candidate):
                    importable += 1
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE ctm_nav_discovery_runs
                        SET status = 'completed',
                            found_count = %s,
                            importable_count = %s,
                            finished_at = UTC_TIMESTAMP(6)
                        WHERE id = %s
                        """,
                        (len(candidates), importable, run_id),
                    )
                await conn.commit()
        except Exception as exc:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE ctm_nav_discovery_runs
                        SET status = 'failed',
                            error_message = %s,
                            finished_at = UTC_TIMESTAMP(6)
                        WHERE id = %s
                        """,
                        (str(exc)[:1000], run_id),
                    )
                await conn.commit()

    async def get_run(self, run_id: int) -> DiscoveryRun:
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM ctm_nav_discovery_runs WHERE id = %s", (run_id,))
                row = await cur.fetchone()
        if not row:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="扫描任务不存在")
        return run_from_row(row)

    async def list_candidates(self, include_ignored: bool = False, include_imported: bool = False) -> list[NavCandidate]:
        clauses: list[str] = []
        if not include_ignored:
            clauses.append("ignored = 0")
        if not include_imported:
            clauses.append("imported_link_id IS NULL")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    f"""
                    SELECT *
                    FROM ctm_nav_discovery_candidates
                    {where}
                    ORDER BY updated_at DESC, host ASC, port ASC
                    LIMIT 500
                    """
                )
                rows = await cur.fetchall()
        link_keys = await self.link_endpoint_keys()
        candidates = [candidate_from_row(row) for row in rows]
        return [
            candidate
            for candidate in candidates
            if endpoint_key(candidate.host, candidate.port) not in link_keys
        ]

    async def update_candidate(self, candidate_id: int, values: dict[str, Any]) -> NavCandidate:
        columns: list[str] = []
        params: list[Any] = []
        mapping = {"ignored": "ignored", "title": "title", "category": "category"}
        for key, column in mapping.items():
            if key in values:
                columns.append(f"{column} = %s")
                value = values[key]
                if key == "ignored":
                    value = 1 if value else 0
                params.append(value)
        if "tags" in values:
            columns.append("tags_json = %s")
            params.append(json_dumps(values["tags"] or []))
        if columns:
            params.append(candidate_id)
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"UPDATE ctm_nav_discovery_candidates SET {', '.join(columns)} WHERE id = %s",
                        tuple(params),
                    )
                    if cur.rowcount == 0:
                        from fastapi import HTTPException

                        raise HTTPException(status_code=404, detail="候选入口不存在")
                await conn.commit()
        return await self.get_candidate(candidate_id)

    async def import_candidate(self, candidate_id: int) -> NavLink:
        candidate = await self.get_candidate(candidate_id)
        if candidate.importedLinkId:
            return await self.get_link(candidate.importedLinkId)
        existing = await self._link_by_url(candidate.url) or await self._link_by_endpoint(candidate.host, candidate.port)
        if existing:
            link = link_from_row(existing)
        else:
            link = await self.create_link(
                NavLinkCreate(
                    title=candidate.title,
                    url=candidate.url,
                    category=candidate.category,
                    description=candidate.suggestionReason,
                    icon=infer_icon(
                        candidate.url,
                        candidate.title,
                        candidate.category,
                        candidate.tags,
                        candidate.serverHeader or "",
                    ),
                    tags=candidate.tags,
                    favorite=False,
                    enabled=True,
                ),
                source="discovery",
                source_key=f"candidate:{candidate.id}",
            )
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE ctm_nav_discovery_candidates
                    SET imported_link_id = %s, ignored = 0
                    WHERE id = %s
                    """,
                    (link.id, candidate_id),
                )
            await conn.commit()
        return link

    async def get_candidate(self, candidate_id: int) -> NavCandidate:
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM ctm_nav_discovery_candidates WHERE id = %s",
                    (candidate_id,),
                )
                row = await cur.fetchone()
        if not row:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="候选入口不存在")
        return candidate_from_row(row)

    async def upsert_candidate(self, raw: dict[str, Any]) -> bool:
        url = normalize_url(str(raw["url"]))
        parsed = urlparse(url)
        host = str(raw.get("host") or parsed.hostname or "")
        port = int(raw.get("port") or parsed.port or default_port(parsed.scheme))
        if endpoint_key(host, port) in await self.link_endpoint_keys():
            return False
        tags = raw.get("tags") or []
        dedupe_key = url[:191]
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO ctm_nav_discovery_candidates
                        (run_id, title, url, host, port, scheme, status_code, server_header,
                         content_type, category, suggestion_reason, tags_json, source, dedupe_key)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        run_id = VALUES(run_id),
                        title = VALUES(title),
                        status_code = VALUES(status_code),
                        server_header = VALUES(server_header),
                        content_type = VALUES(content_type),
                        category = VALUES(category),
                        suggestion_reason = VALUES(suggestion_reason),
                        tags_json = VALUES(tags_json),
                        source = VALUES(source)
                    """,
                    (
                        raw.get("runId"),
                        (raw.get("title") or title_from_url(url))[:160],
                        url,
                        host,
                        port,
                        raw.get("scheme") or parsed.scheme,
                        raw.get("statusCode"),
                        raw.get("serverHeader"),
                        raw.get("contentType"),
                        raw.get("category") or infer_category(url, raw.get("title") or ""),
                        raw.get("suggestionReason"),
                        json_dumps(tags),
                        raw.get("source") or "scan",
                        dedupe_key,
                    ),
                )
            await conn.commit()
        return True

    async def _next_sort_order(self) -> int:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COALESCE(MAX(sort_order), 0) + 10 FROM ctm_nav_links")
                row = await cur.fetchone()
        return int(row[0] or 10)

    async def _link_row(self, link_id: int) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM ctm_nav_links WHERE id = %s", (link_id,))
                return await cur.fetchone()

    async def _link_by_url(self, url: str) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM ctm_nav_links WHERE url = %s", (url,))
                return await cur.fetchone()

    async def _link_by_url_or_endpoint(self, url: str) -> dict[str, Any] | None:
        existing = await self._link_by_url(url)
        if existing:
            return existing
        key = endpoint_key_from_url(url)
        if not key:
            return None
        return await self._link_by_endpoint(*key)

    async def _link_by_endpoint(self, host: str, port: int) -> dict[str, Any] | None:
        key = endpoint_key(host, port)
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT *
                    FROM ctm_nav_links
                    ORDER BY favorite DESC, sort_order ASC, id ASC
                    """
                )
                rows = await cur.fetchall()
        for row in rows:
            if endpoint_key_from_url(str(row["url"])) == key:
                return row
        return None

    async def link_endpoint_keys(self) -> set[tuple[str, int]]:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT url FROM ctm_nav_links")
                rows = await cur.fetchall()
        keys: set[tuple[str, int]] = set()
        for row in rows:
            key = endpoint_key_from_url(str(row[0]))
            if key:
                keys.add(key)
        return keys


async def scan_network(
    cidrs: list[str],
    ports: list[int],
    *,
    connect_timeout: float,
    request_timeout: float,
    concurrency: int,
) -> list[dict[str, Any]]:
    hosts: list[str] = []
    for cidr in cidrs:
        network = ipaddress.ip_network(cidr, strict=False)
        if network.num_addresses > 1024:
            raise ValueError(f"扫描网段过大: {cidr}")
        hosts.extend(str(ip) for ip in network.hosts())

    semaphore = asyncio.Semaphore(max(1, concurrency))
    async with httpx.AsyncClient(
        follow_redirects=True,
        verify=False,
        timeout=httpx.Timeout(request_timeout),
        headers={"User-Agent": "ctm-nav-discovery/1.0"},
    ) as client:
        tasks = [
            probe_web_endpoint(host, port, client, semaphore, connect_timeout)
            for host in hosts
            for port in ports
            if port in WEB_PORTS
        ]
        results = await asyncio.gather(*tasks)
    candidates = [result for result in results if result]
    candidates.sort(key=lambda item: (item["host"], item["port"], item["scheme"]))
    return candidates


async def probe_web_endpoint(
    host: str,
    port: int,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    connect_timeout: float,
) -> dict[str, Any] | None:
    async with semaphore:
        if not await tcp_open(host, port, connect_timeout):
            return None
        schemes = ["https", "http"] if port in {443, 8006, 8443, 9443} else ["http", "https"]
        for scheme in schemes:
            url = f"{scheme}://{host}:{port}/"
            try:
                response = await client.get(url)
            except Exception:
                continue
            content_type = response.headers.get("content-type", "")
            title = extract_title(response.text) if "text/html" in content_type.lower() else ""
            display_title = title or title_from_url(url)
            return {
                "title": display_title,
                "url": url,
                "host": host,
                "port": port,
                "scheme": scheme,
                "statusCode": response.status_code,
                "serverHeader": response.headers.get("server"),
                "contentType": content_type[:160],
                "category": infer_category(url, display_title),
                "icon": infer_icon(url, display_title, infer_category(url, display_title), infer_tags(url, display_title, response.headers.get("server", ""))),
                "suggestionReason": f"扫描发现 {host}:{port} 返回 HTTP {response.status_code}",
                "tags": infer_tags(url, display_title, response.headers.get("server", "")),
                "source": "scan",
            }
    return None


async def tcp_open(host: str, port: int, timeout: float) -> bool:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


def extract_title(text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return html.unescape(re.sub(r"\s+", " ", match.group(1))).strip()[:160]


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.netloc and not parsed.path:
        return f"{url}/"
    return url


def default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def endpoint_key(host: str, port: int) -> tuple[str, int]:
    return (host.strip().lower(), int(port))


def endpoint_key_from_url(url: str) -> tuple[str, int] | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return endpoint_key(parsed.hostname, parsed.port or default_port(parsed.scheme))


def title_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or url
    if parsed.port:
        return f"{host}:{parsed.port}"
    return host


def internal_title(url: str) -> str:
    if url == "/" or url.startswith("/nav"):
        return "CTM 导航"
    if url.startswith("/monitor"):
        return "CTM 监控总览"
    if url.startswith("/hosts"):
        return "主机视图"
    return "CTM Console"


def infer_category(url: str, title: str) -> str:
    text = f"{url} {title}".lower()
    if "grafana" in text or "/d/ctm-" in text:
        return "Grafana"
    if "zabbix" in text or ":8080" in text:
        return "监控"
    if "prometheus" in text or ":9090" in text:
        return "监控"
    if "router" in text or "路由" in text or "zte" in text:
        return "网络"
    if "chat" in text:
        return "应用"
    return "待分类"


def infer_icon(url: str, title: str, category: str, tags: list[str], server: str = "") -> str:
    text = f"{url} {title} {category} {' '.join(tags)} {server}".lower()
    if url.startswith("/"):
        return "console"
    if "grafana" in text or "/d/" in text:
        return "dashboard" if "/d/" in text else "grafana"
    if "prometheus" in text or ":9090" in text:
        return "prometheus"
    if "zabbix" in text or ":8080" in text:
        return "zabbix"
    if "wazuh" in text or "security" in text or "安全" in text:
        return "security"
    if "nextchat" in text or "chat" in text or "聊天" in text:
        return "chat"
    if "router" in text or "route" in text or "路由" in text or "zte" in text:
        return "router"
    if "switch" in text or "交换机" in text:
        return "switch"
    if "pve" in text or "proxmox" in text or "虚拟" in text:
        return "server"
    if "mysql" in text or "redis" in text or "database" in text or "数据库" in text:
        return "database"
    if category == "监控" or "monitor" in text:
        return "monitor"
    if category == "网络":
        return "network"
    if category == "应用":
        return "app"
    return "web"


def infer_tags(url: str, title: str, server: str = "") -> list[str]:
    text = f"{url} {title} {server}".lower()
    tags: list[str] = []
    for token in ["grafana", "zabbix", "prometheus", "nginx", "openresty", "router", "uvicorn"]:
        if token in text:
            tags.append(token)
    if "路由" in text or "zte" in text:
        tags.append("router")
    if ":8080" in text:
        tags.append("web")
    return sorted(set(tags))


def link_from_row(row: dict[str, Any]) -> NavLink:
    return NavLink(
        id=int(row["id"]),
        title=row["title"],
        url=row["url"],
        category=row["category"],
        description=row.get("description"),
        icon=row.get("icon"),
        tags=json_loads(row.get("tags_json"), []),
        source=row.get("source") or "manual",
        sourceKey=row.get("source_key"),
        favorite=bool(row.get("favorite")),
        sortOrder=int(row.get("sort_order") or 0),
        enabled=bool(row.get("enabled")),
        status=row.get("status") or "unknown",
        statusCode=row.get("status_code"),
        lastCheckedAt=row.get("last_checked_at"),
        createdAt=row["created_at"],
        updatedAt=row["updated_at"],
    )


def run_from_row(row: dict[str, Any]) -> DiscoveryRun:
    return DiscoveryRun(
        id=int(row["id"]),
        status=row.get("status") or "running",
        cidrs=json_loads(row.get("cidrs_json"), []),
        ports=json_loads(row.get("ports_json"), []),
        foundCount=int(row.get("found_count") or 0),
        importableCount=int(row.get("importable_count") or 0),
        errorMessage=row.get("error_message"),
        startedAt=row["started_at"],
        finishedAt=row.get("finished_at"),
    )


def candidate_from_row(row: dict[str, Any]) -> NavCandidate:
    return NavCandidate(
        id=int(row["id"]),
        runId=row.get("run_id"),
        title=row["title"],
        url=row["url"],
        host=row["host"],
        port=int(row["port"]),
        scheme=row["scheme"],
        statusCode=row.get("status_code"),
        serverHeader=row.get("server_header"),
        contentType=row.get("content_type"),
        category=row.get("category") or "待分类",
        suggestionReason=row.get("suggestion_reason"),
        tags=json_loads(row.get("tags_json"), []),
        source=row.get("source") or "scan",
        ignored=bool(row.get("ignored")),
        importedLinkId=row.get("imported_link_id"),
        createdAt=row["created_at"],
        updatedAt=row["updated_at"],
    )


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def initial_candidates() -> list[dict[str, Any]]:
    return [
        {
            "title": "417交换机",
            "url": "http://192.168.3.12:80/",
            "host": "192.168.3.12",
            "port": 80,
            "scheme": "http",
            "statusCode": 200,
            "serverHeader": "GoAhead-Webs/2.5.0",
            "contentType": "text/html",
            "category": "网络",
            "suggestionReason": "初始扫描发现交换机 Web 管理页",
            "tags": ["switch", "web"],
        },
        {
            "title": "中兴智能路由器",
            "url": "http://192.168.3.13:80/",
            "host": "192.168.3.13",
            "port": 80,
            "scheme": "http",
            "statusCode": 200,
            "serverHeader": "ZTE web server 1.0 ZTE corp 2015.",
            "contentType": "text/html; charset=utf-8",
            "category": "网络",
            "suggestionReason": "初始扫描发现路由器 Web 管理页",
            "tags": ["router", "zte"],
        },
        {
            "title": "中兴智能路由器 HTTPS",
            "url": "https://192.168.3.13:443/",
            "host": "192.168.3.13",
            "port": 443,
            "scheme": "https",
            "statusCode": 200,
            "serverHeader": "ZTE web server 1.0 ZTE corp 2015.",
            "contentType": "text/html; charset=utf-8",
            "category": "网络",
            "suggestionReason": "初始扫描发现路由器 HTTPS 管理页",
            "tags": ["router", "zte"],
        },
        {
            "title": "192.168.3.49",
            "url": "http://192.168.3.49:80/",
            "host": "192.168.3.49",
            "port": 80,
            "scheme": "http",
            "statusCode": 200,
            "contentType": "text/html",
            "category": "待分类",
            "suggestionReason": "初始扫描发现 Web 页面",
            "tags": ["web"],
        },
        {
            "title": "192.168.3.81 Nginx",
            "url": "http://192.168.3.81:80/",
            "host": "192.168.3.81",
            "port": 80,
            "scheme": "http",
            "statusCode": 200,
            "serverHeader": "nginx",
            "contentType": "text/html",
            "category": "待分类",
            "suggestionReason": "初始扫描发现 Nginx Web 页面",
            "tags": ["nginx", "web"],
        },
        {
            "title": "192.168.3.81 HTTPS",
            "url": "https://192.168.3.81:443/",
            "host": "192.168.3.81",
            "port": 443,
            "scheme": "https",
            "statusCode": 200,
            "serverHeader": "nginx",
            "contentType": "text/html",
            "category": "待分类",
            "suggestionReason": "初始扫描发现 HTTPS Web 页面",
            "tags": ["nginx", "web"],
        },
        {
            "title": "192.168.3.81:8080",
            "url": "http://192.168.3.81:8080/",
            "host": "192.168.3.81",
            "port": 8080,
            "scheme": "http",
            "statusCode": 200,
            "serverHeader": "nginx",
            "contentType": "text/html",
            "category": "待分类",
            "suggestionReason": "初始扫描发现 8080 Web 页面",
            "tags": ["nginx", "web"],
        },
        {
            "title": "网关 Web",
            "url": "http://192.168.3.192:80/",
            "host": "192.168.3.192",
            "port": 80,
            "scheme": "http",
            "statusCode": 200,
            "contentType": "text/html",
            "category": "网络",
            "suggestionReason": "初始扫描发现默认网关 Web 页面",
            "tags": ["gateway", "web"],
        },
        {
            "title": "网关 HTTPS",
            "url": "https://192.168.3.192:443/",
            "host": "192.168.3.192",
            "port": 443,
            "scheme": "https",
            "statusCode": 200,
            "contentType": "text/html",
            "category": "网络",
            "suggestionReason": "初始扫描发现默认网关 HTTPS 页面",
            "tags": ["gateway", "web"],
        },
        {
            "title": "192.168.3.200 Root",
            "url": "http://192.168.3.200:80/",
            "host": "192.168.3.200",
            "port": 80,
            "scheme": "http",
            "statusCode": 200,
            "serverHeader": "openresty",
            "contentType": "text/html",
            "category": "应用",
            "suggestionReason": "初始扫描发现 openresty Web 页面",
            "tags": ["openresty", "web"],
        },
        {
            "title": "192.168.3.200 API",
            "url": "http://192.168.3.200:5000/",
            "host": "192.168.3.200",
            "port": 5000,
            "scheme": "http",
            "statusCode": 200,
            "serverHeader": "uvicorn",
            "contentType": "text/html; charset=utf-8",
            "category": "应用",
            "suggestionReason": "初始扫描发现 Uvicorn Web 服务",
            "tags": ["uvicorn", "api"],
        },
        {
            "title": "192.168.3.200 Zabbix",
            "url": "http://192.168.3.200:8080/",
            "host": "192.168.3.200",
            "port": 8080,
            "scheme": "http",
            "statusCode": 200,
            "serverHeader": "openresty",
            "contentType": "text/html; charset=UTF-8",
            "category": "监控",
            "suggestionReason": "初始扫描发现 Zabbix 页面",
            "tags": ["zabbix", "openresty"],
        },
        {
            "title": "192.168.3.200:8888",
            "url": "http://192.168.3.200:8888/",
            "host": "192.168.3.200",
            "port": 8888,
            "scheme": "http",
            "statusCode": 200,
            "serverHeader": "openresty",
            "contentType": "text/html",
            "category": "待分类",
            "suggestionReason": "初始扫描发现站点创建成功页",
            "tags": ["openresty", "web"],
        },
        {
            "title": "192.168.3.222 Apache 默认页",
            "url": "http://192.168.3.222:80/",
            "host": "192.168.3.222",
            "port": 80,
            "scheme": "http",
            "statusCode": 200,
            "serverHeader": "nginx/1.18.0 (Ubuntu)",
            "contentType": "text/html",
            "category": "待分类",
            "suggestionReason": "初始扫描发现 Apache 默认页",
            "tags": ["nginx", "apache"],
        },
    ]
