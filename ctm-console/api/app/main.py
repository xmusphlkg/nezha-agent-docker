from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import httpx
import aiomysql
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, ORJSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .auth import AuthService
from .cache import JsonCache
from .clients.prometheus import PrometheusClient
from .clients.pve import PVEClient
from .clients.zabbix import ZabbixClient
from .config import get_settings
from .routes.auth import router as auth_router
from .routes.data import router as data_router
from .routes.navigation import router as navigation_router
from .services.collector import Collector
from .services.navigation import NavigationService

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"


class AppState:
    cache: JsonCache
    mysql: aiomysql.Pool
    http: httpx.AsyncClient
    zabbix: ZabbixClient
    prometheus: PrometheusClient
    pve: PVEClient
    collector: Collector
    auth: AuthService
    nav: NavigationService


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app_state.mysql = await aiomysql.create_pool(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password or "",
        db=settings.mysql_database,
        autocommit=False,
        connect_timeout=settings.mysql_connect_timeout_sec,
        minsize=1,
        maxsize=8,
        charset="utf8mb4",
    )
    app_state.cache = JsonCache(app_state.mysql, settings)
    await app_state.cache.setup()
    app_state.auth = AuthService(app_state.mysql, settings)
    await app_state.auth.setup()
    app_state.nav = NavigationService(app_state.mysql, settings)
    await app_state.nav.setup()
    app_state.http = httpx.AsyncClient()
    app_state.zabbix = ZabbixClient(settings=settings, client=app_state.http)
    app_state.prometheus = PrometheusClient(settings=settings, client=app_state.http)
    app_state.pve = PVEClient(settings=settings)
    app_state.collector = Collector(
        settings=settings,
        cache=app_state.cache,
        zabbix=app_state.zabbix,
        prometheus=app_state.prometheus,
        pve=app_state.pve,
    )
    app_state.collector.start()
    try:
        yield
    finally:
        await app_state.collector.stop()
        await app_state.http.aclose()
        app_state.mysql.close()
        await app_state.mysql.wait_closed()


app = FastAPI(default_response_class=ORJSONResponse, lifespan=lifespan, title="CTM Console")
app.include_router(auth_router)
app.include_router(navigation_router)
app.include_router(data_router)


if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"ok": "true"}


@app.get("/api/health")
async def api_health() -> dict[str, str]:
    return {"ok": "true"}


def index_response() -> FileResponse:
    return FileResponse(
        INDEX_FILE,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/")
async def index() -> Response:
    if INDEX_FILE.exists():
        return index_response()
    return HTMLResponse(
        "<!doctype html><title>CTM Console</title><h1>CTM Console API is running</h1>",
        status_code=200,
    )


@app.get("/{path:path}")
async def spa_fallback(path: str) -> Response:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    if INDEX_FILE.exists():
        return index_response()
    raise HTTPException(status_code=404, detail="Static frontend has not been built")
