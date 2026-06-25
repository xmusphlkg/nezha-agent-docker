from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import Settings
from ..models import SourceStatus, utc_now


class ZabbixError(RuntimeError):
    pass


@dataclass
class ZabbixClient:
    settings: Settings
    client: httpx.AsyncClient

    def __post_init__(self) -> None:
        self._sem = asyncio.Semaphore(self.settings.zabbix_concurrency)
        self._auth_token: str | None = self.settings.zabbix_token
        self.status = SourceStatus(source="zabbix", ok=False, lastError="not collected yet")

    async def call(self, method: str, params: dict[str, Any] | None = None, *, auth: bool = True) -> Any:
        if auth and not self._auth_token:
            await self._login_if_needed()
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": int(time.time() * 1000),
        }
        headers = {"Content-Type": "application/json"}
        if auth:
            if not self._auth_token:
                raise ZabbixError("Zabbix token is not configured")
            headers["Authorization"] = f"Bearer {self._auth_token}"
        started = time.perf_counter()
        async with self._sem:
            try:
                response = await self.client.post(
                    self.settings.zabbix_url,
                    json=payload,
                    headers=headers,
                    timeout=self.settings.zabbix_timeout_sec,
                )
                response.raise_for_status()
                body = response.json()
                if "error" in body:
                    message = body["error"].get("data") or body["error"].get("message") or body["error"]
                    raise ZabbixError(str(message))
                self.status = SourceStatus(
                    source="zabbix",
                    ok=True,
                    latencyMs=(time.perf_counter() - started) * 1000,
                    lastSuccessAt=utc_now(),
                )
                return body.get("result")
            except Exception as exc:
                self.status = SourceStatus(
                    source="zabbix",
                    ok=False,
                    latencyMs=(time.perf_counter() - started) * 1000,
                    lastSuccessAt=self.status.lastSuccessAt,
                    lastError=str(exc),
                )
                raise

    async def _login_if_needed(self) -> None:
        if self._auth_token:
            return
        if not self.settings.zabbix_user or not self.settings.zabbix_password:
            raise ZabbixError("ZABBIX_TOKEN or ZABBIX_USER/ZABBIX_PASSWORD must be configured")
        result = await self.call(
            "user.login",
            {"username": self.settings.zabbix_user, "password": self.settings.zabbix_password},
            auth=False,
        )
        if not isinstance(result, str):
            raise ZabbixError("Zabbix login did not return a token")
        self._auth_token = result

    async def api_version(self) -> str:
        return await self.call("apiinfo.version", auth=False)

    async def hosts(self) -> list[dict[str, Any]]:
        return await self.call(
            "host.get",
            {
                "output": ["hostid", "host", "name", "status"],
                "selectGroups": ["groupid", "name"],
                "selectInterfaces": ["interfaceid", "ip", "dns", "type", "main", "available", "error"],
                "selectInventory": ["type", "os", "location", "model", "serialno_a"],
                "sortfield": ["name"],
            },
        )

    async def items_for_hosts(self, hostids: list[str]) -> list[dict[str, Any]]:
        if not hostids:
            return []
        return await self.call(
            "item.get",
            {
                "hostids": hostids,
                "output": [
                    "itemid",
                    "hostid",
                    "name",
                    "key_",
                    "lastvalue",
                    "lastclock",
                    "units",
                    "value_type",
                    "status",
                    "state",
                ],
                "filter": {"status": 0},
            },
        )

    async def problems(self) -> list[dict[str, Any]]:
        return await self.call(
            "problem.get",
            {
                "output": ["eventid", "name", "severity", "clock", "acknowledged", "objectid"],
                "sortfield": ["eventid"],
                "sortorder": "DESC",
                "recent": False,
            },
        )

    async def triggers(self, triggerids: list[str]) -> list[dict[str, Any]]:
        if not triggerids:
            return []
        return await self.call(
            "trigger.get",
            {
                "triggerids": triggerids,
                "output": ["triggerid", "description", "priority"],
                "selectHosts": ["hostid", "host", "name"],
            },
        )

    async def history(
        self,
        itemids: list[str],
        *,
        history_type: int,
        time_from: int,
        time_till: int,
        limit: int = 1200,
    ) -> list[dict[str, Any]]:
        if not itemids:
            return []
        return await self.call(
            "history.get",
            {
                "output": "extend",
                "history": history_type,
                "itemids": itemids,
                "time_from": time_from,
                "time_till": time_till,
                "sortfield": "clock",
                "sortorder": "ASC",
                "limit": limit,
            },
        )

    async def trends(
        self,
        itemids: list[str],
        *,
        time_from: int,
        time_till: int,
        limit: int = 1200,
    ) -> list[dict[str, Any]]:
        if not itemids:
            return []
        return await self.call(
            "trend.get",
            {
                "output": ["itemid", "clock", "num", "value_min", "value_avg", "value_max"],
                "itemids": itemids,
                "time_from": time_from,
                "time_till": time_till,
                "sortfield": "clock",
                "sortorder": "ASC",
                "limit": limit,
            },
        )
