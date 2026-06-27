from __future__ import annotations

import json
import math
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..models import Health, Machine, NetworkDevice, Problem

HOST_PREFIX_RE = re.compile(r"^(sys|phy)[_\s-]+(.+)$", re.IGNORECASE)
SAFE_ID_RE = re.compile(r"[^\w.-]+", re.UNICODE)
POWER_DEVICE_TERMS = ("pdu", "ups", "apc", "市电", "电源", "配电", "battery", "电池")
DISK_SPACE_TERMS = (
    "filesystem",
    "file system",
    "fs [",
    "disk space",
    "space:",
    "mounted filesystem",
    "storage",
    "磁盘空间",
    "文件系统",
    "存储",
)
DISK_IO_TERMS = (
    "disk utilization",
    "disk read",
    "disk write",
    "disk queue",
    "disk average",
    "vfs.dev.",
    "diskiola",
    "diskio",
)


SEVERITY_NAMES = {
    "0": "not-classified",
    "1": "information",
    "2": "warning",
    "3": "average",
    "4": "high",
    "5": "disaster",
}


def safe_id(value: str) -> str:
    return SAFE_ID_RE.sub("-", value.strip()).strip("-").lower() or "unknown"


def channel_and_id(host: dict[str, Any]) -> tuple[str | None, str]:
    raw = str(host.get("host") or host.get("name") or host.get("hostid") or "")
    name = str(host.get("name") or raw)

    # Prefer the visible Zabbix name when it carries the sys/phy pairing prefix.
    # Some hosts use opaque internal ids such as "sys s9" while their display
    # names are the stable pair identifiers, for example "sys_GPU".
    for candidate in (name, raw):
        match = HOST_PREFIX_RE.match(candidate)
        if match:
            return match.group(1).lower(), safe_id(match.group(2))
    return None, safe_id(raw or name)


def host_search_text(host: dict[str, Any]) -> tuple[list[str], str]:
    groups = host.get("groups") or host.get("hostgroups") or []
    group_names = [str(group.get("name", "")).lower() for group in groups]
    text = " ".join(
        [
            str(host.get("host") or ""),
            str(host.get("name") or ""),
            *group_names,
        ]
    ).lower()
    return group_names, text


def is_exchange_host(host: dict[str, Any]) -> bool:
    group_names, names = host_search_text(host)
    return (
        any(name == "exchange" or "exchange" in name for name in group_names)
        or "switch" in names
        or "交换机" in names
    )


def is_power_host(host: dict[str, Any]) -> bool:
    _, names = host_search_text(host)
    return any(term in names for term in POWER_DEVICE_TERMS)


def is_infrastructure_device(host: dict[str, Any]) -> bool:
    return is_exchange_host(host) or is_power_host(host)


def to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def item_text(item: dict[str, Any]) -> str:
    return f"{item.get('name', '')} {item.get('key_', '')}".lower()


def clamp_pct(value: float) -> float:
    return min(max(value, 0), 100)


def bracket_args(key: str) -> list[str]:
    match = re.search(r"\[(.*)\]", key)
    if not match:
        return []
    return [part.strip().strip('"') for part in match.group(1).split(",")]


def is_cpu_item(item: dict[str, Any]) -> bool:
    text = item_text(item)
    return "system.cpu.util" in text or "cpu utilization" in text or "cpu使用率" in text


def cpu_value(item: dict[str, Any]) -> float | None:
    value = to_float(item.get("lastvalue"))
    if value is None:
        return None
    text = item_text(item)
    if "idle" in text and value <= 100:
        return clamp_pct(100 - value)
    return clamp_pct(value)


def is_cpu_count_item(item: dict[str, Any]) -> bool:
    text = item_text(item)
    key = str(item.get("key_") or "").lower()
    return (
        "system.cpu.num" in key
        or "number of cpus" in text
        or "number of cores" in text
        or "numberoflogicalprocessors" in text
        or "logical processors" in text
        or "cpu数量" in text
        or "cpu 核" in text
    )


def cpu_count_value(item: dict[str, Any]) -> float | None:
    value = to_float(item.get("lastvalue"))
    if value is None or value <= 0 or value > 4096:
        return None
    return value


def cpu_model_value(item: dict[str, Any]) -> str | None:
    raw = str(item.get("lastvalue") or "").strip()
    if not raw or to_float(raw) is not None:
        return None
    text = item_text(item)
    key = str(item.get("key_") or "").lower()
    if any(token in text for token in ["temperature", " temp", "utilization", "load average", "interrupt", "context switches"]):
        return None
    mentions_cpu = "cpu" in text or "processor" in text or "处理器" in text or "cpu" in key or "processor" in key
    if "system.hw.cpu" in key or "win32_processor" in key:
        return compact_cpu_model(raw)
    if mentions_cpu and any(token in text for token in ["model", "name", "info", "型号"]):
        return compact_cpu_model(raw)
    return None


def compact_cpu_model(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    text = re.sub(r"\b(Intel|AMD)\(R\)", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(CPU|Processor)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+@", " @", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" -")
    return text[:48]


def os_value(item: dict[str, Any]) -> str | None:
    raw = str(item.get("lastvalue") or "").strip()
    if not raw:
        return None
    text = item_text(item)
    key = str(item.get("key_") or "").lower()
    if "architecture" in text or key.endswith(".arch"):
        return None
    if (
        "system.sw.os" in key
        or "system.uname" in key
        or "system.descr" in key
        or "sysdescr" in key
        or "pve.version" in key
        or "pveversion" in key
        or "proxmox.version" in key
        or "operating system" in text
        or "system description" in text
        or "pve version" in text
        or "pve manager" in text
        or "proxmox version" in text
        or "systemosname" in key
        or "系统版本" in text
        or "pve-manager" in raw.lower()
        or "proxmox-ve" in raw.lower()
    ):
        return compact_os_name(raw)
    return None


def inventory_os_value(host: dict[str, Any]) -> str | None:
    inventory = host.get("inventory") or {}
    if not isinstance(inventory, dict):
        return None
    return compact_os_name(str(inventory.get("os") or "").strip())


def compact_os_name(value: str) -> str | None:
    if not value:
        return None
    raw = re.sub(r"\s+", " ", value).strip()
    lower = raw.lower()
    if "windows server" in lower:
        match = re.search(r"Windows Server\s+(\d{4})", raw, re.IGNORECASE)
        return f"Windows Server {match.group(1)}" if match else "Windows Server"
    if "windows" in lower:
        match = re.search(r"Windows\s+(?:10|11)(?:\s+[A-Za-z0-9().-]+)?", raw, re.IGNORECASE)
        return (match.group(0).strip() if match else "Windows") or "Windows"
    if "openwrt" in lower:
        return with_optional_version("OpenWrt", raw, r"OpenWrt\s+([0-9][A-Za-z0-9.+_-]*)")
    if "istoreos" in lower:
        return with_optional_version("iStoreOS", raw, r"iStoreOS\s+([0-9][A-Za-z0-9.+_-]*)")
    if "ikuai" in lower:
        return with_optional_version("iKuai", raw, r"iKuai\s+([0-9][A-Za-z0-9.+_-]*)")
    if "truenas" in lower:
        match = re.search(r"TrueNAS[-\s]+([0-9]+(?:\.[0-9]+){0,3})", raw, re.IGNORECASE)
        label = f"TrueNAS {match.group(1)}" if match else "TrueNAS"
        kernel = linux_kernel_label(raw)
        return f"{label} / {kernel}" if kernel else label
    if "routeros" in lower or "mikrotik" in lower:
        return with_optional_version("RouterOS", raw, r"RouterOS\s+([0-9][A-Za-z0-9.+_-]*)")
    if "cisco ios" in lower:
        version = first_match(raw, r"Version\s+([0-9][A-Za-z0-9()._-]*)")
        return f"Cisco IOS {version}" if version else "Cisco IOS"
    if "freebsd" in lower:
        return with_optional_version("FreeBSD", raw, r"FreeBSD\s+([0-9][A-Za-z0-9.+_-]*)")
    if "esxi" in lower or "vmware" in lower:
        version = first_match(raw, r"(?:VMware\s+)?ESXi\s+([0-9][A-Za-z0-9.+_-]*)")
        return f"VMware ESXi {version}" if version else "VMware ESXi"
    if "proxmox" in lower or "-pve" in lower or " pmx " in lower:
        pve_version = first_match(raw, r"(?:pve-manager[/:\s]+|proxmox-ve[/:\s]+|Proxmox VE\s+)([0-9][A-Za-z0-9.+_-]*)")
        label = f"Proxmox VE {pve_version}" if pve_version else "Proxmox VE"
        kernel = linux_kernel_label(raw) or pve_kernel_label(raw)
        return f"{label} / {kernel}" if kernel else label
    if "ubuntu" in lower:
        version = ubuntu_release_version(raw)
        kernel = linux_kernel_label(raw)
        label = f"Ubuntu {version}" if version else "Ubuntu"
        return f"{label} / {kernel}" if kernel else label
    if "debian" in lower:
        version = first_match(raw, r"Debian GNU/Linux\s+([0-9][A-Za-z0-9.+_-]*)")
        kernel = linux_kernel_label(raw)
        label = f"Debian {version}" if version else "Debian"
        return f"{label} / {kernel}" if kernel and not version else label
    if "rocky" in lower:
        return with_optional_version("Rocky Linux", raw, r"Rocky(?:\s+Linux)?\s+([0-9][A-Za-z0-9.+_-]*)")
    if "alma" in lower:
        return with_optional_version("AlmaLinux", raw, r"AlmaLinux\s+([0-9][A-Za-z0-9.+_-]*)")
    if "centos" in lower:
        return with_optional_version("CentOS", raw, r"CentOS(?:\s+Linux)?\s+([0-9][A-Za-z0-9.+_-]*)")
    if "red hat" in lower or "rhel" in lower:
        version = first_match(raw, r"(?:Red Hat Enterprise Linux|RHEL)\s+([0-9][A-Za-z0-9.+_-]*)")
        return f"RHEL {version}" if version else "RHEL"
    if "linux" in lower:
        return linux_kernel_label(raw) or "Linux"
    return raw[:80]


def first_match(value: str, pattern: str) -> str | None:
    match = re.search(pattern, value, re.IGNORECASE)
    return match.group(1).rstrip(".,;") if match else None


def with_optional_version(label: str, value: str, pattern: str) -> str:
    version = first_match(value, pattern)
    return f"{label} {version}" if version else label


def linux_kernel_label(value: str) -> str | None:
    version = first_match(value, r"Linux(?:\s+version)?\s+([0-9][A-Za-z0-9.+_-]*)")
    if not version:
        version = first_match(value, r"Linux\s+\S+\s+([0-9][A-Za-z0-9.+_-]*)")
    return f"Linux {version}" if version else None


def pve_kernel_label(value: str) -> str | None:
    version = first_match(value, r"(?:running\s+kernel:|kernel:?)\s+([0-9][A-Za-z0-9.+_-]*-pve)")
    return f"Linux {version}" if version else None


def ubuntu_release_version(value: str) -> str | None:
    for pattern in (
        r"ubuntu[0-9]*~([0-9]{2}\.[0-9]{2}(?:\.[0-9]+)?)",
        r"~([0-9]{2}\.[0-9]{2}(?:\.[0-9]+)?)[^\\s]*-Ubuntu",
        r"Ubuntu\s+([0-9]{2}\.[0-9]{2}(?:\.[0-9]+)?)",
    ):
        version = first_match(value, pattern)
        if version:
            return version
    return None


def best_label(values: list[str]) -> str | None:
    clean = [value for value in values if value]
    if not clean:
        return None
    return sorted(set(clean), key=lambda value: (value in {"Linux", "Windows"}, len(value)))[0]


def best_os_label(values: list[str]) -> str | None:
    clean = [value for value in values if value]
    if not clean:
        return None

    def score(value: str) -> tuple[int, int]:
        text = value.lower()
        known = any(
            token in text
            for token in [
                "ubuntu",
                "debian",
                "proxmox",
                "truenas",
                "ikuai",
                "openwrt",
                "istoreos",
                "routeros",
                "cisco ios",
                "freebsd",
                "esxi",
                "windows",
                "rocky",
                "alma",
                "centos",
                "rhel",
            ]
        )
        has_release_version = bool(
            re.search(
                r"\b(?:ubuntu|debian|proxmox ve|truenas|ikuai|openwrt|istoreos|routeros|freebsd|vmware esxi|rocky linux|almalinux|centos|rhel)\s+\d",
                value,
                re.IGNORECASE,
            )
        ) or bool(re.search(r"\bwindows(?: server)?\s+\d", value, re.IGNORECASE))
        has_version = bool(re.search(r"\d+\.\d+", value))
        has_kernel = " / linux " in text
        generic = text in {"linux", "windows"} or re.fullmatch(r"linux\s+\d+(?:\.\d+)+", text)
        return (
            (20 if known else 0)
            + (12 if has_release_version else 0)
            + (5 if has_version else 0)
            + (3 if has_kernel else 0)
            - (10 if generic else 0),
            -len(value),
        )

    return max(set(clean), key=score)


def is_memory_item(item: dict[str, Any]) -> bool:
    text = item_text(item)
    return (
        "vm.memory.size" in text
        or "vm.memory.total" in text
        or "vm.memory.free" in text
        or "vm.memory.available" in text
        or "vm.memory.used" in text
        or "memory utilization" in text
        or "内存使用率" in text
    )


def memory_value(item: dict[str, Any]) -> float | None:
    value = to_float(item.get("lastvalue"))
    if value is None:
        return None
    text = item_text(item)
    if "pavailable" in text or "available memory in %" in text:
        return clamp_pct(100 - value)
    if "pused" in text or "%" in text or "utilization" in text or "使用率" in text:
        return clamp_pct(value)
    return None


def is_disk_item(item: dict[str, Any]) -> bool:
    return disk_percent_value(item) is not None


def is_disk_space_item(item: dict[str, Any]) -> bool:
    text = item_text(item)
    key = str(item.get("key_") or "").lower()
    if key.startswith("vfs.dev.") or any(term in text for term in DISK_IO_TERMS):
        return False
    if "inode" in key or "inodes" in text:
        return False
    return "vfs.fs" in key or any(term in text for term in DISK_SPACE_TERMS)


def disk_scope(item: dict[str, Any]) -> str:
    key = str(item.get("key_") or "").lower()
    args = bracket_args(key)
    if args:
        return args[0] or str(item.get("itemid") or item.get("name") or key)
    name = str(item.get("name") or "")
    match = re.search(r"fs\s*\[([^\]]+)\]", name, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"(?:filesystem|file system|storage)\s+([^:]+)", name, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return str(item.get("itemid") or name or key or "disk")


def disk_part_kind(item: dict[str, Any]) -> str | None:
    if not is_disk_space_item(item):
        return None
    key = str(item.get("key_") or "").lower()
    text = item_text(item)
    args = bracket_args(key)
    selector = args[-1].lower() if args else ""
    if selector in {"used", "free", "available", "total"}:
        return "available" if selector == "free" else selector
    if "space: used" in text or "used space" in text or "space used" in text or "used bytes" in text:
        return "used"
    if "space: available" in text or "space: free" in text or "available space" in text or "free space" in text:
        return "available"
    if "space: total" in text or "total space" in text or "space total" in text:
        return "total"
    return None


def disk_percent_value(item: dict[str, Any]) -> float | None:
    value = to_float(item.get("lastvalue"))
    if value is None or not is_disk_space_item(item):
        return None
    text = item_text(item)
    key = str(item.get("key_") or "").lower()
    args = [arg.lower() for arg in bracket_args(key)]
    if "pused" in args or ",pused" in key or "pused]" in key:
        return clamp_pct(value)
    return (
        clamp_pct(value)
        if (
            "disk space usage" in text
            or "磁盘使用率" in text
            or ("used" in text and "%" in text and "space" in text)
        )
        else None
    )


def disk_free_percent_value(item: dict[str, Any]) -> float | None:
    value = to_float(item.get("lastvalue"))
    if value is None or not is_disk_space_item(item):
        return None
    key = str(item.get("key_") or "").lower()
    args = [arg.lower() for arg in bracket_args(key)]
    if "pfree" in args or ",pfree" in key or "pfree]" in key:
        return clamp_pct(value)
    return None


def is_network_item(item: dict[str, Any]) -> bool:
    text = item_text(item)
    return (
        "net.if.in" in text
        or "net.if.out" in text
        or "interface" in text
        and ("bits" in text or "bps" in text or "流量" in text)
    )


def is_agent_ping_item(item: dict[str, Any]) -> bool:
    text = item_text(item)
    key = str(item.get("key_") or "").lower()
    return (
        "agent.ping" in text
        or "icmpping" == key
        or "zabbix agent availability" in text
        or "snmp agent availability" in text
        or "zabbix[host,agent,available]" in key
        or "zabbix[host,snmp,available]" in key
    )


def is_temperature_item(item: dict[str, Any]) -> bool:
    text = item_text(item)
    return (
        "temperature" in text
        or " temp" in text
        or "temp:" in text
        or "温度" in text
        or "sensor" in text
        and ("degrees" in text or "celsius" in text or "°c" in text)
    )


def is_fan_item(item: dict[str, Any]) -> bool:
    text = item_text(item)
    return "fan" in text or "rpm" in text or "风扇" in text


def is_uptime_item(item: dict[str, Any]) -> bool:
    text = item_text(item)
    return "uptime" in text or "sysuptime" in text or "运行时间" in text


@dataclass
class ResourceParts:
    used: float | None = None
    total: float | None = None
    available: float | None = None

    def put(self, kind: str | None, value: float | None) -> None:
        if kind is None or value is None or value < 0:
            return
        if kind == "used":
            self.used = max(self.used or 0, value)
        elif kind == "total":
            self.total = max(self.total or 0, value)
        elif kind in {"available", "free"}:
            self.available = max(self.available or 0, value)

    def usage_pct(self) -> float | None:
        if not self.total:
            return None
        if self.used is not None:
            return clamp_pct((self.used / self.total) * 100)
        if self.available is not None:
            return clamp_pct(((self.total - self.available) / self.total) * 100)
        return None

    def used_bytes(self, pct: float | None = None) -> float | None:
        if self.used is not None:
            return self.used
        if self.total is not None and self.available is not None:
            return max(self.total - self.available, 0)
        if self.total is not None and pct is not None:
            return max((self.total * pct) / 100, 0)
        return None


def memory_part_kind(item: dict[str, Any]) -> str | None:
    if not is_memory_item(item):
        return None
    text = item_text(item)
    key = str(item.get("key_") or "").lower()
    args = [arg.lower() for arg in bracket_args(key)]
    units = str(item.get("units") or "").lower()
    selector = args[-1] if args else ""
    if selector in {"pused", "pavailable"} or units == "%" or "utilization" in key:
        return None
    if any(token in key for token in ["buffer", "cached"]) or any(token in text for token in ["buffers", "cached"]):
        return None
    if selector == "total" or "total" in key or "total memory" in text or "memtotalreal" in key:
        return "total"
    if selector == "used" or "used memory" in text:
        return "used"
    if selector == "available" or "available" in key or "available memory" in text:
        return "available"
    if selector == "free" or "free" in key or "free memory" in text or "memavailreal" in key:
        return "available"
    return None


def parse_filesystem_payload(value: Any) -> list[tuple[str, ResourceParts, float | None]]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    results: list[tuple[str, ResourceParts, float | None]] = []

    def walk(node: Any, fallback_scope: str = "disk") -> None:
        if isinstance(node, list):
            for child in node:
                walk(child, fallback_scope)
            return
        if not isinstance(node, dict):
            return

        scope = str(
            node.get("fsname")
            or node.get("filesystem")
            or node.get("mountpoint")
            or node.get("name")
            or node.get("{#FSNAME}")
            or fallback_scope
        )
        bytes_info = node.get("bytes")
        if isinstance(bytes_info, dict):
            parts = ResourceParts()
            parts.put("used", to_float(bytes_info.get("used")))
            parts.put("total", to_float(bytes_info.get("total")))
            parts.put("available", to_float(bytes_info.get("free") or bytes_info.get("available")))
            pused = to_float(bytes_info.get("pused"))
            pfree = to_float(bytes_info.get("pfree"))
            pct_value = clamp_pct(pused) if pused is not None else clamp_pct(100 - pfree) if pfree is not None else None
            results.append((scope, parts, pct_value))

        for key, child in node.items():
            if key == "bytes":
                continue
            if isinstance(child, (dict, list)):
                walk(child, scope)

    walk(value)
    return results


@dataclass
class Metrics:
    os_names: list[str] = field(default_factory=list)
    cpu_models: list[str] = field(default_factory=list)
    cpu_cores: list[float] = field(default_factory=list)
    cpu: list[float] = field(default_factory=list)
    mem: list[float] = field(default_factory=list)
    disk: list[float] = field(default_factory=list)
    net: list[float] = field(default_factory=list)
    temp: list[float] = field(default_factory=list)
    fan: list[float] = field(default_factory=list)
    uptime: list[float] = field(default_factory=list)
    agent_up: list[bool] = field(default_factory=list)
    updated_at: datetime | None = None
    memory_parts: ResourceParts = field(default_factory=ResourceParts)
    disk_parts: dict[str, ResourceParts] = field(default_factory=lambda: defaultdict(ResourceParts))
    disk_pct_scopes: set[str] = field(default_factory=set)
    disk_pct_by_scope: dict[str, float] = field(default_factory=dict)
    disk_free_pct: dict[str, float] = field(default_factory=dict)
    disk_details: list[tuple[float, float, float]] = field(default_factory=list)
    mem_bytes: float | None = None
    max_mem_bytes: float | None = None
    disk_bytes: float | None = None
    max_disk_bytes: float | None = None

    def add_item(self, item: dict[str, Any]) -> None:
        value = to_float(item.get("lastvalue"))
        lastclock = to_float(item.get("lastclock"))
        if lastclock:
            dt = datetime.fromtimestamp(lastclock, timezone.utc)
            self.updated_at = max(self.updated_at, dt) if self.updated_at else dt
        item_os = os_value(item)
        if item_os:
            self.os_names.append(item_os)
        cpu_model = cpu_model_value(item)
        if cpu_model:
            self.cpu_models.append(cpu_model)
        cpu_count = cpu_count_value(item) if is_cpu_count_item(item) else None
        if cpu_count is not None:
            self.cpu_cores.append(cpu_count)
        if is_cpu_item(item):
            cpu = cpu_value(item)
            if cpu is not None:
                self.cpu.append(cpu)
        if is_memory_item(item):
            mem = memory_value(item)
            if mem is not None:
                self.mem.append(mem)
            self.memory_parts.put(memory_part_kind(item), value)
        disk_pct = disk_percent_value(item)
        if disk_pct is not None:
            self.disk.append(disk_pct)
            scope = disk_scope(item)
            self.disk_pct_scopes.add(scope)
            self.disk_pct_by_scope[scope] = disk_pct
        disk_free_pct = disk_free_percent_value(item)
        if disk_free_pct is not None:
            self.disk_free_pct[disk_scope(item)] = disk_free_pct
        disk_kind = disk_part_kind(item)
        if disk_kind and value is not None:
            self.disk_parts[disk_scope(item)].put(disk_kind, value)
        for scope, parts, pct_value in parse_filesystem_payload(item.get("lastvalue")):
            if pct_value is not None:
                self.disk.append(pct_value)
                self.disk_pct_scopes.add(scope)
                self.disk_pct_by_scope[scope] = pct_value
            self.disk_parts[scope].put("used", parts.used)
            self.disk_parts[scope].put("total", parts.total)
            self.disk_parts[scope].put("available", parts.available)
        if is_network_item(item) and value is not None:
            self.net.append(max(value, 0))
        if is_temperature_item(item) and value is not None and -20 <= value <= 150:
            self.temp.append(value)
        if is_fan_item(item) and value is not None and value >= 0:
            self.fan.append(value)
        if is_uptime_item(item) and value is not None and value >= 0:
            self.uptime.append(value)
        if is_agent_ping_item(item) and value is not None:
            self.agent_up.append(value > 0)

    def add_host(self, host: dict[str, Any]) -> None:
        host_os = inventory_os_value(host)
        if host_os:
            self.os_names.append(host_os)

    def finalize(self) -> None:
        if not self.mem:
            mem_pct = self.memory_parts.usage_pct()
            if mem_pct is not None:
                self.mem.append(mem_pct)
        mem_pct = avg(self.mem)
        self.max_mem_bytes = self.memory_parts.total
        self.mem_bytes = self.memory_parts.used_bytes(mem_pct)
        for scope, free_pct in self.disk_free_pct.items():
            if scope not in self.disk_pct_scopes:
                disk_pct = clamp_pct(100 - free_pct)
                self.disk.append(disk_pct)
                self.disk_pct_scopes.add(scope)
                self.disk_pct_by_scope[scope] = disk_pct
        for scope, parts in self.disk_parts.items():
            disk_pct = self.disk_pct_by_scope.get(scope)
            if disk_pct is None:
                disk_pct = parts.usage_pct()
            if disk_pct is not None and scope not in self.disk_pct_scopes:
                self.disk.append(disk_pct)
            used = parts.used_bytes(disk_pct)
            if disk_pct is not None and used is not None and parts.total:
                self.disk_details.append((disk_pct, used, parts.total))
        if self.disk_details:
            _, self.disk_bytes, self.max_disk_bytes = max(self.disk_details, key=lambda detail: detail[0])

    def latest_at(self) -> datetime:
        return self.updated_at or datetime.now(timezone.utc)


def summarize_items(items: list[dict[str, Any]]) -> Metrics:
    metrics = Metrics()
    for item in items:
        metrics.add_item(item)
    metrics.finalize()
    return metrics


def merge_health(*healths: Health) -> Health:
    priority = {
        Health.CRITICAL: 5,
        Health.OFFLINE: 4,
        Health.WARNING: 3,
        Health.STALE: 2,
        Health.UNKNOWN: 1,
        Health.OK: 0,
    }
    return max(healths, key=lambda value: priority[value])


def health_from_metrics(metrics: Metrics, problems: list[Problem], *, stale: bool = False) -> Health:
    if stale:
        return Health.STALE
    if metrics.agent_up and not any(metrics.agent_up):
        return Health.OFFLINE
    if any(problem.severity in {"disaster", "high"} for problem in problems):
        return Health.CRITICAL
    if problems:
        return Health.WARNING
    if metrics.temp and max(metrics.temp) >= 80:
        return Health.CRITICAL
    if metrics.cpu and max(metrics.cpu) >= 95:
        return Health.CRITICAL
    if metrics.mem and max(metrics.mem) >= 95:
        return Health.CRITICAL
    if metrics.disk and max(metrics.disk) >= 95:
        return Health.CRITICAL
    if metrics.temp and max(metrics.temp) >= 70:
        return Health.WARNING
    if metrics.cpu and max(metrics.cpu) >= 85:
        return Health.WARNING
    if metrics.mem and max(metrics.mem) >= 85:
        return Health.WARNING
    if metrics.disk and max(metrics.disk) >= 85:
        return Health.WARNING
    if not any([metrics.cpu, metrics.mem, metrics.disk, metrics.net, metrics.temp, metrics.agent_up]):
        return Health.UNKNOWN
    return Health.OK


def normalize_problem(raw: dict[str, Any]) -> Problem:
    hosts = raw.get("hosts") or []
    host = ""
    if hosts:
        host = str(hosts[0].get("name") or hosts[0].get("host") or "")
    clock = int(to_float(raw.get("clock")) or time.time())
    severity = SEVERITY_NAMES.get(str(raw.get("severity")), str(raw.get("severity") or "unknown"))
    return Problem(
        source="zabbix",
        severity=severity,
        host=host,
        name=str(raw.get("name") or "Zabbix problem"),
        ageSec=max(int(time.time()) - clock, 0),
        eventId=str(raw.get("eventid") or raw.get("objectid") or ""),
        acknowledged=str(raw.get("acknowledged", "0")) == "1",
    )


def build_problem_index(problems: list[Problem]) -> dict[str, list[Problem]]:
    indexed: dict[str, list[Problem]] = defaultdict(list)
    for problem in problems:
        key = safe_id(problem.host)
        indexed[key].append(problem)
        match = HOST_PREFIX_RE.match(problem.host)
        if match:
            indexed[safe_id(match.group(2))].append(problem)
    return indexed


def normalize_machines(
    hosts: list[dict[str, Any]],
    items: list[dict[str, Any]],
    problems: list[Problem],
    *,
    stale: bool = False,
) -> tuple[list[Machine], list[NetworkDevice]]:
    hosts = [host for host in hosts if str(host.get("status", "0")) == "0"]
    host_by_id = {str(host["hostid"]): host for host in hosts}
    items_by_host: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        hostid = str(item.get("hostid"))
        if hostid in host_by_id:
            items_by_host[hostid].append(item)

    problem_index = build_problem_index(problems)
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"sys": None, "phy": None, "other": []})
    network_devices: list[NetworkDevice] = []

    for host in hosts:
        hostid = str(host["hostid"])
        channel, normalized_id = channel_and_id(host)
        host_items = items_by_host.get(hostid, [])
        metrics = summarize_items(host_items)
        metrics.add_host(host)
        name = str(host.get("name") or host.get("host"))
        host_problems = problem_index.get(safe_id(name), []) + problem_index.get(normalized_id, [])

        if is_infrastructure_device(host):
            health = health_from_metrics(metrics, host_problems, stale=stale)
            network_devices.append(
                NetworkDevice(
                    id=normalized_id,
                    host=name,
                    health=health,
                    uptimeSec=max(metrics.uptime) if metrics.uptime else None,
                    netBps=sum(metrics.net) if metrics.net else None,
                    problems=dedupe_problems(host_problems),
                    updatedAt=metrics.latest_at(),
                    stale=stale,
                )
            )
            continue

        entry = grouped[normalized_id]
        payload = {"host": host, "items": host_items, "metrics": metrics, "name": name}
        if channel == "sys":
            entry["sys"] = payload
        elif channel == "phy":
            entry["phy"] = payload
        else:
            entry["other"].append(payload)

    machines: list[Machine] = []
    for machine_id, entry in grouped.items():
        sys_payload = entry["sys"]
        phy_payload = entry["phy"]
        other_payloads = entry["other"]
        if sys_payload and phy_payload:
            mode = "paired"
        elif sys_payload:
            mode = "sys-only"
        elif phy_payload:
            mode = "phy-only"
        else:
            mode = "standalone"

        metrics = Metrics()
        for payload in [sys_payload, phy_payload, *other_payloads]:
            if not payload:
                continue
            pm: Metrics = payload["metrics"]
            metrics.cpu.extend(pm.cpu)
            metrics.os_names.extend(pm.os_names)
            metrics.cpu_models.extend(pm.cpu_models)
            metrics.cpu_cores.extend(pm.cpu_cores)
            metrics.mem.extend(pm.mem)
            metrics.disk.extend(pm.disk)
            metrics.net.extend(pm.net)
            metrics.temp.extend(pm.temp)
            metrics.fan.extend(pm.fan)
            metrics.uptime.extend(pm.uptime)
            metrics.agent_up.extend(pm.agent_up)
            if pm.mem_bytes is not None and pm.max_mem_bytes is not None:
                metrics.mem_bytes = (metrics.mem_bytes or 0) + pm.mem_bytes
                metrics.max_mem_bytes = (metrics.max_mem_bytes or 0) + pm.max_mem_bytes
            if pm.disk_bytes is not None and pm.max_disk_bytes is not None:
                disk_pct = usage_pct(pm.disk_bytes, pm.max_disk_bytes)
                if disk_pct is not None:
                    metrics.disk_details.append((disk_pct, pm.disk_bytes, pm.max_disk_bytes))
            if pm.updated_at:
                metrics.updated_at = max(metrics.updated_at, pm.updated_at) if metrics.updated_at else pm.updated_at

        if metrics.disk_details:
            _, metrics.disk_bytes, metrics.max_disk_bytes = max(metrics.disk_details, key=lambda detail: detail[0])

        names = [
            payload["name"]
            for payload in [sys_payload, phy_payload, *other_payloads]
            if payload
        ]
        machine_problems: list[Problem] = []
        for name in names:
            machine_problems.extend(problem_index.get(safe_id(name), []))
        machine_problems.extend(problem_index.get(machine_id, []))
        machine_problems = dedupe_problems(machine_problems)

        machines.append(
            Machine(
                id=machine_id,
                sysHost=(
                    sys_payload["name"]
                    if sys_payload
                    else names[0] if mode == "standalone" and names else None
                ),
                phyHost=phy_payload["name"] if phy_payload else None,
                mode=mode,
                health=health_from_metrics(metrics, machine_problems, stale=stale),
                osName=best_os_label(metrics.os_names),
                cpuModel=best_label(metrics.cpu_models),
                cpuCores=max(metrics.cpu_cores) if metrics.cpu_cores else None,
                cpuPct=avg(metrics.cpu),
                memPct=avg(metrics.mem),
                memBytes=metrics.mem_bytes,
                maxMemBytes=metrics.max_mem_bytes,
                diskPct=max(metrics.disk) if metrics.disk else None,
                diskBytes=metrics.disk_bytes,
                maxDiskBytes=metrics.max_disk_bytes,
                netBps=sum(metrics.net) if metrics.net else None,
                uptimeSec=max(metrics.uptime) if metrics.uptime else None,
                maxTempC=max(metrics.temp) if metrics.temp else None,
                fanRpm=max(metrics.fan) if metrics.fan else None,
                agentUp=all(metrics.agent_up) if metrics.agent_up else None,
                problems=machine_problems,
                updatedAt=metrics.latest_at(),
                stale=stale,
            )
        )

    machines.sort(key=lambda machine: (health_sort(machine.health), machine.id))
    network_devices.sort(key=lambda device: (health_sort(device.health), device.host))
    return machines, network_devices


def dedupe_problems(problems: list[Problem]) -> list[Problem]:
    seen: set[str] = set()
    deduped: list[Problem] = []
    for problem in problems:
        key = f"{problem.source}:{problem.eventId}:{problem.host}:{problem.name}"
        if key not in seen:
            seen.add(key)
            deduped.append(problem)
    return deduped


def avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def usage_pct(value: float | None, total: float | None) -> float | None:
    if value is None or not total:
        return None
    return clamp_pct((value / total) * 100)


def health_sort(health: Health) -> int:
    order = {
        Health.CRITICAL: 0,
        Health.OFFLINE: 1,
        Health.WARNING: 2,
        Health.STALE: 3,
        Health.UNKNOWN: 4,
        Health.OK: 5,
    }
    return order[health]


def host_ids_for_machine(hosts: list[dict[str, Any]], machine_id: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for host in hosts:
        channel, normalized_id = channel_and_id(host)
        if normalized_id != machine_id:
            continue
        hostid = str(host["hostid"])
        if channel:
            result[channel] = hostid
        else:
            result[f"standalone:{hostid}"] = hostid
    return result
