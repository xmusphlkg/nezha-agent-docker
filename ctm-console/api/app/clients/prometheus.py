from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import Settings
from ..models import SourceStatus, utc_now


class PrometheusError(RuntimeError):
    pass


@dataclass
class PrometheusClient:
    settings: Settings
    client: httpx.AsyncClient

    def __post_init__(self) -> None:
        self._sem = asyncio.Semaphore(self.settings.prometheus_concurrency)
        self.status = SourceStatus(source="prometheus", ok=False, lastError="not collected yet")

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        started = time.perf_counter()
        async with self._sem:
            try:
                response = await self.client.get(
                    self.settings.prometheus_url.rstrip("/") + path,
                    params=params,
                    timeout=self.settings.prometheus_timeout_sec,
                )
                response.raise_for_status()
                body = response.json()
                if body.get("status") != "success":
                    raise PrometheusError(body.get("error") or "Prometheus returned non-success status")
                self.status = SourceStatus(
                    source="prometheus",
                    ok=True,
                    latencyMs=(time.perf_counter() - started) * 1000,
                    lastSuccessAt=utc_now(),
                )
                return body.get("data")
            except Exception as exc:
                self.status = SourceStatus(
                    source="prometheus",
                    ok=False,
                    latencyMs=(time.perf_counter() - started) * 1000,
                    lastSuccessAt=self.status.lastSuccessAt,
                    lastError=str(exc),
                )
                raise

    async def ready(self) -> bool:
        started = time.perf_counter()
        try:
            response = await self.client.get(
                self.settings.prometheus_url.rstrip("/") + "/-/ready",
                timeout=self.settings.prometheus_timeout_sec,
            )
            response.raise_for_status()
            self.status = SourceStatus(
                source="prometheus",
                ok=True,
                latencyMs=(time.perf_counter() - started) * 1000,
                lastSuccessAt=utc_now(),
            )
            return True
        except Exception as exc:
            self.status = SourceStatus(
                source="prometheus",
                ok=False,
                latencyMs=(time.perf_counter() - started) * 1000,
                lastSuccessAt=self.status.lastSuccessAt,
                lastError=str(exc),
            )
            return False

    async def query(self, expr: str) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/query", {"query": expr})
        return data.get("result", [])

    async def targets(self) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/targets")
        return data.get("activeTargets", [])

    async def alerts(self) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/alerts")
        return data.get("alerts", [])

    async def query_range(
        self, expr: str, *, start: int, end: int, step: str = "60s"
    ) -> list[dict[str, Any]]:
        data = await self._get(
            "/api/v1/query_range",
            {"query": expr, "start": start, "end": end, "step": step},
        )
        return data.get("result", [])
