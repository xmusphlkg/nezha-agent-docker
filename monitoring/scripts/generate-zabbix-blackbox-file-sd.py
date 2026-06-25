#!/usr/bin/env python3
"""Generate Prometheus file_sd targets from the Zabbix database.

The script is intended to run on the monitoring host. It only reads the Zabbix
database and atomically replaces file_sd target files after a successful query.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


IFACE_TYPES = {
    "1": "agent",
    "2": "snmp",
    "3": "ipmi",
    "4": "jmx",
}

DEFAULT_CORE_HTTP = [
    ("grafana", "http://192.168.30.91:30037/api/health"),
    ("prometheus", "http://192.168.3.222:9090/-/ready"),
    ("zabbix", "http://192.168.3.222:8080/"),
]


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = shlex.split(value.strip())[0] if value.strip() else ""
    return values


def parse_zabbix_server_conf(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    mapping = {
        "DBHost": "MYSQL_HOST",
        "DBPort": "MYSQL_PORT",
        "DBName": "MYSQL_DATABASE",
        "DBUser": "MYSQL_USER",
        "DBPassword": "MYSQL_PASSWORD",
    }
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() in mapping:
            values[mapping[key.strip()]] = value.strip()
    return values


def load_config(env_file: Path, zabbix_conf: Path) -> dict[str, str]:
    config = {
        "MYSQL_HOST": "localhost",
        "MYSQL_PORT": "3306",
        "MYSQL_DATABASE": "zabbix",
        "MYSQL_USER": "zabbix",
        "MYSQL_PASSWORD": "",
    }
    config.update(parse_zabbix_server_conf(zabbix_conf))
    config.update(parse_env_file(env_file))
    config.update({k: v for k, v in os.environ.items() if k.startswith("MYSQL_")})
    return config


def run_mysql(config: dict[str, str], query: str) -> list[list[str]]:
    command = [
        "mysql",
        "--batch",
        "--raw",
        "--skip-column-names",
        f"--host={config['MYSQL_HOST']}",
        f"--port={config['MYSQL_PORT']}",
        f"--user={config['MYSQL_USER']}",
        config["MYSQL_DATABASE"],
        "--execute",
        query,
    ]
    env = os.environ.copy()
    if config.get("MYSQL_PASSWORD"):
        env["MYSQL_PWD"] = config["MYSQL_PASSWORD"]

    result = subprocess.run(
        command,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    rows: list[list[str]] = []
    for line in result.stdout.splitlines():
        if line.strip():
            rows.append(line.split("\t"))
    return rows


def is_usable_ip(ip: str) -> bool:
    if not ip or ip in {"127.0.0.1", "0.0.0.0", "::1"}:
        return False
    return bool(re.match(r"^[0-9]{1,3}(\.[0-9]{1,3}){3}$", ip))


def zabbix_targets(config: dict[str, str]) -> list[dict[str, object]]:
    query = r"""
        SELECT
          i.ip,
          h.host,
          h.name,
          i.type,
          COALESCE(GROUP_CONCAT(DISTINCT g.name ORDER BY g.name SEPARATOR ','), '') AS zbx_groups
        FROM hosts h
        JOIN interface i ON h.hostid = i.hostid
        LEFT JOIN hosts_groups hg ON h.hostid = hg.hostid
        LEFT JOIN hstgrp g ON hg.groupid = g.groupid
        WHERE h.flags = 0
          AND h.status = 0
          AND i.ip <> ''
          AND i.ip <> '127.0.0.1'
        GROUP BY i.interfaceid, i.ip, h.host, h.name, i.type
        ORDER BY h.hostid, i.main DESC, i.interfaceid
    """
    rows = run_mysql(config, query)
    targets: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()

    for ip, host, name, iface_type, groups in rows:
        if not is_usable_ip(ip):
            continue
        labels = {
            "source": "zabbix",
            "zbx_host": host,
            "zbx_name": name,
            "zbx_group": groups or "ungrouped",
            "iface_type": IFACE_TYPES.get(iface_type, f"type_{iface_type}"),
        }
        dedupe_key = (ip, labels["zbx_host"], labels["iface_type"])
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        targets.append({"targets": [ip], "labels": labels})
    return targets


def core_http_targets() -> list[dict[str, object]]:
    targets = []
    for service, url in DEFAULT_CORE_HTTP:
        targets.append(
            {
                "targets": [url],
                "labels": {
                    "source": "static-core",
                    "service": service,
                },
            }
        )
    return targets


def atomic_write_json(path: Path, payload: object, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        tmp_name = handle.name

    tmp_path = Path(tmp_name)
    try:
        json.loads(tmp_path.read_text(encoding="utf-8"))
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default="/etc/prometheus/zabbix-file-sd.env")
    parser.add_argument("--zabbix-conf", default="/etc/zabbix/zabbix_server.conf")
    parser.add_argument(
        "--zabbix-output",
        default="/etc/prometheus/file_sd/zabbix-blackbox-icmp.json",
    )
    parser.add_argument(
        "--core-output",
        default="/etc/prometheus/file_sd/core-http.json",
    )
    args = parser.parse_args()

    config = load_config(Path(args.env_file), Path(args.zabbix_conf))
    zbx_targets = zabbix_targets(config)
    if not zbx_targets:
        print("refusing to replace file_sd with an empty Zabbix target list", file=sys.stderr)
        return 2

    atomic_write_json(Path(args.zabbix_output), zbx_targets)
    atomic_write_json(Path(args.core_output), core_http_targets())
    print(f"wrote {len(zbx_targets)} Zabbix blackbox targets")
    print(f"wrote {len(DEFAULT_CORE_HTTP)} core HTTP targets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
