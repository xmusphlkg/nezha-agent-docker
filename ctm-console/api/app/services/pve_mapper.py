from __future__ import annotations

from typing import Any

from ..clients.pve import PVEServerConfig
from ..models import Health, PVENode, PVEResource, PVEServerStatus, PVESummary, utc_now


def build_pve_summary(
    *,
    configured: bool,
    collected: list[dict[str, Any]],
    errors: list[tuple[PVEServerConfig, str]],
    stale: bool = False,
) -> PVESummary:
    nodes: list[PVENode] = []
    guests: list[PVEResource] = []
    statuses: list[PVEServerStatus] = []

    for item in collected:
        server: PVEServerConfig = item["server"]
        version = item.get("version") or {}
        statuses.append(
            PVEServerStatus(
                name=server.name,
                host=server.host,
                ok=True,
                latencyMs=item.get("latencyMs"),
                version=str(version.get("version") or "") or None,
            )
        )
        for raw_node in item.get("nodes", []):
            nodes.append(normalize_node(server, raw_node))
        for raw_guest in item.get("resources", []):
            guest = normalize_guest(server, raw_guest)
            if guest:
                guests.append(guest)

    for server, error in errors:
        statuses.append(PVEServerStatus(name=server.name, host=server.host, ok=False, lastError=error))

    total_servers = len(statuses)
    online_servers = sum(1 for status in statuses if status.ok)
    online_nodes = sum(1 for node in nodes if node.status == "online")
    running_guests = sum(1 for guest in guests if guest.status == "running")

    health = Health.UNKNOWN
    if stale:
        health = Health.STALE
    elif configured and total_servers and online_servers == 0:
        health = Health.CRITICAL
    elif errors:
        health = Health.WARNING
    elif configured:
        health = Health.OK

    return PVESummary(
        health=health,
        configured=configured,
        totalServers=total_servers,
        onlineServers=online_servers,
        totalNodes=len(nodes),
        onlineNodes=online_nodes,
        totalGuests=len(guests),
        runningGuests=running_guests,
        qemuGuests=sum(1 for guest in guests if guest.type == "qemu"),
        lxcGuests=sum(1 for guest in guests if guest.type == "lxc"),
        cpuPct=avg([node.cpuPct for node in nodes]),
        memPct=ratio_pct(sum_float(node.memBytes for node in nodes), sum_float(node.maxMemBytes for node in nodes)),
        diskPct=ratio_pct(sum_float(node.diskBytes for node in nodes), sum_float(node.maxDiskBytes for node in nodes)),
        nodes=sorted(nodes, key=lambda node: (node.server, node.node)),
        guests=sorted(guests, key=lambda guest: (guest.status != "running", guest.node, guest.vmid)),
        serverStatuses=sorted(statuses, key=lambda status: status.name),
        updatedAt=utc_now(),
        stale=stale,
    )


def normalize_node(server: PVEServerConfig, raw: dict[str, Any]) -> PVENode:
    node = str(raw.get("node") or raw.get("name") or "unknown")
    return PVENode(
        id=f"{server.name}:{node}",
        server=server.name,
        node=node,
        status=str(raw.get("status") or "unknown"),
        cpuPct=ratio_to_pct(raw.get("cpu")),
        memBytes=to_float(raw.get("mem")),
        maxMemBytes=to_float(raw.get("maxmem")),
        diskBytes=to_float(raw.get("disk")),
        maxDiskBytes=to_float(raw.get("maxdisk")),
        uptimeSec=to_float(raw.get("uptime")),
    )


def normalize_guest(server: PVEServerConfig, raw: dict[str, Any]) -> PVEResource | None:
    guest_type = str(raw.get("type") or "").lower()
    if guest_type not in {"qemu", "lxc"}:
        return None
    vmid = raw.get("vmid")
    try:
        vmid_int = int(vmid)
    except (TypeError, ValueError):
        return None
    node = str(raw.get("node") or "unknown")
    name = str(raw.get("name") or raw.get("id") or f"{guest_type}-{vmid_int}")
    return PVEResource(
        id=f"{server.name}:{node}:{guest_type}:{vmid_int}",
        server=server.name,
        node=node,
        vmid=vmid_int,
        type=guest_type,  # type: ignore[arg-type]
        name=name,
        status=str(raw.get("status") or "unknown"),
        cpuPct=ratio_to_pct(raw.get("cpu")),
        cpus=to_float(raw.get("maxcpu")),
        memBytes=to_float(raw.get("mem")),
        maxMemBytes=to_float(raw.get("maxmem")),
        diskBytes=to_float(raw.get("disk")),
        maxDiskBytes=to_float(raw.get("maxdisk")),
        uptimeSec=to_float(raw.get("uptime")),
        template=bool(raw.get("template")),
    )


def to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def ratio_to_pct(value: Any) -> float | None:
    parsed = to_float(value)
    if parsed is None:
        return None
    return max(0.0, min(parsed * 100, 100.0))


def ratio_pct(value: float | None, total: float | None) -> float | None:
    if not value or not total:
        return None
    return max(0.0, min((value / total) * 100, 100.0))


def sum_float(values: Any) -> float | None:
    total = 0.0
    seen = False
    for value in values:
        if value is None:
            continue
        total += float(value)
        seen = True
    return total if seen else None


def avg(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)
