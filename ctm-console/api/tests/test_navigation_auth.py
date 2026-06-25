from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.auth import hash_password, verify_password
from app.models import NavLinkCreate, NavLinkUpdate
from app.services.navigation import NavigationService, endpoint_key_from_url, infer_category, infer_icon, initial_candidates, normalize_url, scan_network


def test_password_hash_uses_pbkdf2_and_verifies_secret():
    password_hash = hash_password("correct horse battery staple")

    assert password_hash.startswith("pbkdf2_sha256$600000$")
    assert verify_password("correct horse battery staple", password_hash) is True
    assert verify_password("wrong", password_hash) is False


def test_nav_link_validation_accepts_internal_and_http_urls():
    assert NavLinkCreate(title="Monitor", url="/monitor").url == "/monitor"
    assert NavLinkUpdate(url="https://192.168.3.222:9090/").url == "https://192.168.3.222:9090/"

    with pytest.raises(ValidationError):
        NavLinkCreate(title="Bad", url="javascript:alert(1)")


def test_endpoint_key_from_url_compares_host_and_port_only():
    assert endpoint_key_from_url("http://192.168.3.222:9090/-/ready") == ("192.168.3.222", 9090)
    assert endpoint_key_from_url("https://192.168.3.13/") == ("192.168.3.13", 443)
    assert endpoint_key_from_url("/monitor") is None


def test_normalize_url_adds_trailing_slash_for_host_roots():
    assert normalize_url("http://192.168.30.185:8840") == "http://192.168.30.185:8840/"
    assert normalize_url("http://192.168.30.185:8840/app") == "http://192.168.30.185:8840/app"


def test_initial_candidates_are_importable_web_urls():
    candidates = initial_candidates()

    assert candidates
    assert all(candidate["url"].startswith(("http://", "https://")) for candidate in candidates)
    assert any(candidate["host"] == "192.168.3.200" and candidate["port"] == 5000 for candidate in candidates)


@pytest.mark.asyncio
async def test_scan_network_ignores_non_web_ports():
    assert await scan_network(
        ["127.0.0.1/32"],
        [22],
        connect_timeout=0.01,
        request_timeout=0.01,
        concurrency=1,
    ) == []


def test_category_inference_for_known_tools():
    assert infer_category("http://192.168.3.222:9090/", "Prometheus") == "监控"
    assert infer_category("http://192.168.3.13/", "中兴智能路由器") == "网络"
    assert infer_category("http://192.168.30.91:30037/d/ctm-ops-overview", "Grafana 总览") == "Grafana"


def test_icon_inference_for_known_tools():
    assert infer_icon("http://192.168.3.222:9090/", "Prometheus", "监控", ["prometheus"]) == "prometheus"
    assert infer_icon("http://192.168.3.13/", "中兴智能路由器", "网络", ["router"]) == "router"
    assert infer_icon("http://192.168.3.200:3000/", "NextChat", "应用", ["chat"]) == "chat"
    assert infer_icon("/monitor", "CTM 监控总览", "监控", ["ctm"]) == "console"


@pytest.mark.asyncio
async def test_manual_create_allows_same_endpoint_with_different_path():
    service = ManualCreateNavigationService()

    link = await service.create_link(
        NavLinkCreate(
            title="HA 监控面板",
            url="http://192.168.3.222:8123/dashboard-unknown/0",
            category="管理",
            description="Home Assistant",
            icon="dashboard",
            tags=["home", "assistant"],
            favorite=True,
        )
    )

    assert link.id == 42
    assert link.url == "http://192.168.3.222:8123/dashboard-unknown/0"


class ManualCreateNavigationService(NavigationService):
    def __init__(self):
        self.pool = FakePool()
        self.settings = object()
        self.url_checks = 0

    async def _link_by_url(self, url: str):
        self.url_checks += 1
        if self.url_checks == 1:
            return None
        return {
            "id": 42,
            "title": "HA 监控面板",
            "url": "http://192.168.3.222:8123/dashboard-unknown/0",
            "category": "管理",
            "description": "Home Assistant",
            "icon": "dashboard",
            "tags_json": '["home","assistant"]',
            "source": "manual",
            "source_key": None,
            "favorite": 1,
            "enabled": 1,
            "sort_order": 42,
            "status": "unknown",
            "status_code": None,
            "last_checked_at": None,
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }

    async def _link_by_endpoint(self, host: str, port: int):
        raise AssertionError("manual links must not be deduplicated by endpoint")

    async def _next_sort_order(self) -> int:
        return 42


class FakePool:
    def acquire(self):
        return FakeConnection()


class FakeConnection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return FakeCursor()

    async def commit(self):
        return None

    async def rollback(self):
        return None


class FakeCursor:
    lastrowid = 42

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, query, params=None):
        self.lastrowid = 42


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
