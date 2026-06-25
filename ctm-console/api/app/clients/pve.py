from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import Settings
from ..models import SourceStatus, utc_now


@dataclass(frozen=True)
class PVEServerConfig:
    name: str
    host: str
    port: int = 8006
    token_id: str = ""
    token_secret: str = ""
    verify_ssl: bool = False

    @property
    def base_url(self) -> str:
        return f"https://{self.host}:{self.port}/api2/json"


class PVEClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.status = SourceStatus(source="pve", ok=False, lastError="not configured")

    def servers(self) -> list[PVEServerConfig]:
        configs: list[PVEServerConfig] = []
        for index, raw in enumerate(self.settings.pve_servers()):
            host = str(raw.get("host") or "").strip()
            token_id = str(raw.get("token_id") or raw.get("tokenId") or "").strip()
            token_secret = str(raw.get("token_secret") or raw.get("tokenSecret") or "").strip()
            if not host or not token_id or not token_secret:
                continue
            configs.append(
                PVEServerConfig(
                    name=str(raw.get("name") or host or f"PVE {index + 1}"),
                    host=host,
                    port=int(raw.get("port") or 8006),
                    token_id=token_id,
                    token_secret=token_secret,
                    verify_ssl=bool(raw.get("verify_ssl") or raw.get("verifySsl") or False),
                )
            )
        return configs

    async def get(self, server: PVEServerConfig, path: str, params: dict[str, Any] | None = None) -> Any:
        endpoint = path if path.startswith("/") else f"/{path}"
        headers = {"Authorization": f"PVEAPIToken={server.token_id}={server.token_secret}"}
        async with httpx.AsyncClient(
            verify=server.verify_ssl,
            timeout=self.settings.pve_timeout_sec,
            headers=headers,
        ) as client:
            response = await client.get(f"{server.base_url}{endpoint}", params=params)
            response.raise_for_status()
            payload = response.json()
            return payload.get("data", payload)

    async def collect_server(self, server: PVEServerConfig) -> dict[str, Any]:
        started = time.perf_counter()
        version, nodes, resources = await self._collect_server_payload(server)
        return {
            "server": server,
            "version": version,
            "nodes": nodes if isinstance(nodes, list) else [],
            "resources": resources if isinstance(resources, list) else [],
            "latencyMs": (time.perf_counter() - started) * 1000,
        }

    async def _collect_server_payload(self, server: PVEServerConfig) -> tuple[Any, Any, Any]:
        async with httpx.AsyncClient(
            verify=server.verify_ssl,
            timeout=self.settings.pve_timeout_sec,
            headers={"Authorization": f"PVEAPIToken={server.token_id}={server.token_secret}"},
        ) as client:
            version_response, nodes_response, resources_response = await client.get(
                f"{server.base_url}/version"
            ), await client.get(f"{server.base_url}/nodes"), await client.get(
                f"{server.base_url}/cluster/resources",
                params={"type": "vm"},
            )
            version_response.raise_for_status()
            nodes_response.raise_for_status()
            resources_response.raise_for_status()
            return (
                version_response.json().get("data", {}),
                nodes_response.json().get("data", []),
                resources_response.json().get("data", []),
            )

    def mark_ok(self, latency_ms: float | None = None) -> None:
        self.status = SourceStatus(source="pve", ok=True, latencyMs=latency_ms, lastSuccessAt=utc_now())

    def mark_error(self, error: str) -> None:
        self.status = SourceStatus(source="pve", ok=False, lastError=error)
