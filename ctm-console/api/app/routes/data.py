from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ..models import (
    Diagnostics,
    GrafanaIntegration,
    LanSummary,
    Machine,
    MachineDetail,
    NetworkDevice,
    Overview,
    Problem,
    PVESummary,
    ServicesSummary,
    TailnetSummary,
    WazuhSummary,
)
from ..config import get_settings
from ..services.grafana_links import build_grafana_integration

router = APIRouter(prefix="/api", tags=["data"])


def collector():
    from ..main import app_state

    return app_state.collector


@router.get("/overview")
async def overview(service=Depends(collector)) -> Overview:
    return await service.get_overview()


@router.get("/machines")
async def machines(service=Depends(collector)) -> list[Machine]:
    data = await service.get_overview()
    return data.machines


@router.get("/machines/{machine_id}")
async def machine_detail(machine_id: str, service=Depends(collector)) -> MachineDetail:
    try:
        return await service.get_machine_detail(machine_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Machine not found") from None


@router.get("/machines/{machine_id}/series")
async def machine_series(
    machine_id: str,
    range_name: Literal["1h", "6h", "24h"] = Query(default="1h", alias="range"),
    service=Depends(collector),
) -> dict:
    try:
        return await service.get_machine_series(machine_id, range_name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Machine not found") from None


@router.get("/network/devices")
async def network_devices(service=Depends(collector)) -> list[NetworkDevice]:
    data = await service.get_overview()
    return data.networkDevices


@router.get("/tailnet")
async def tailnet(service=Depends(collector)) -> TailnetSummary:
    data = await service.get_overview()
    return data.tailnet


@router.get("/services")
async def services(service=Depends(collector)) -> ServicesSummary:
    data = await service.get_overview()
    return data.services


@router.get("/lan")
async def lan(service=Depends(collector)) -> LanSummary:
    return await service.get_lan()


@router.get("/pve")
async def pve(service=Depends(collector)) -> PVESummary:
    return await service.get_pve()


@router.get("/wazuh")
async def wazuh(service=Depends(collector)) -> WazuhSummary:
    return await service.get_wazuh()


@router.get("/grafana")
async def grafana() -> GrafanaIntegration:
    return build_grafana_integration(get_settings())


@router.get("/alerts")
async def alerts(service=Depends(collector)) -> list[Problem]:
    data = await service.get_overview()
    return data.problems


@router.get("/diagnostics")
async def diagnostics(service=Depends(collector)) -> Diagnostics:
    return await service.diagnostics()
